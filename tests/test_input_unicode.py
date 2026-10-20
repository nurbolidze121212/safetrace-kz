"""Malformed JSON strings must produce a usable 422 without writing partial state."""

import json

import pytest
from fastapi.testclient import TestClient

from backend import pipeline, storage
from backend.app import app
from backend.schemas import CaseInput, MaterialInput


def post_json(client, path, value):
    return client.post(path, content=json.dumps(value, ensure_ascii=True).encode(),
                       headers={"content-type": "application/json"})


@pytest.mark.parametrize("field", ["title", "text", "source", "url"])
def test_create_rejects_unpaired_surrogates_without_creating_a_case(monkeypatch, field):
    submitted = []
    monkeypatch.setattr(pipeline, "submit", lambda case_id: submitted.append(case_id))
    before = {doc["id"] for doc in storage.all_cases()}
    payload = {"title": "Unicode input", "materials": [{"text": "A source"}]}
    if field == "title":
        payload["title"] = "bad\ud800"
    else:
        payload["materials"][0][field] = "https://entry.test/\ud800" if field == "url" else "bad\ud800"
    with TestClient(app, raise_server_exceptions=False) as client:
        response = post_json(client, "/api/cases", payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert "bad" not in response.text and "input" not in response.json()
    assert {doc["id"] for doc in storage.all_cases()} == before
    assert submitted == []


def test_invalid_added_material_does_not_mutate_the_case():
    doc = pipeline.new_case(CaseInput(title="Add", materials=[MaterialInput(text="Original")]))
    with TestClient(app, raise_server_exceptions=False) as client:
        before = storage.get(doc["id"])
        response = post_json(client, f"/api/cases/{doc['id']}/materials", {"text": "bad\udfff"})
        assert response.status_code == 422
        assert storage.get(doc["id"]) == before


def test_invalid_decision_does_not_write_history():
    doc = pipeline.new_case(CaseInput(title="Review", materials=[MaterialInput(text="Original")]))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = post_json(client, f"/api/cases/{doc['id']}/decision",
                             {"decision": "needs_data", "comment": "bad\udfff"})
        assert response.status_code == 422
        assert storage.decisions(doc["id"]) == []


def test_invalid_unicode_in_jsonl_is_rejected_before_submission(monkeypatch):
    submitted = []
    monkeypatch.setattr(pipeline, "submit", lambda case_id: submitted.append(case_id))
    content = json.dumps({"text": "bad\ud800"}).encode()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/import", files={"file": ("input.jsonl", content, "application/jsonl")})
    assert response.status_code == 422 and submitted == []


def test_validation_error_with_a_malformed_field_name_is_safe_json():
    with TestClient(app, raise_server_exceptions=False) as client:
        response = post_json(client, "/api/cases", {"title": "Input", "materials": [{"text": "Fine"}],
                                                    "unknown\ud800": "private marker"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert "private marker" not in response.text


def test_valid_supplementary_unicode_and_kazakh_survive_json_roundtrip(monkeypatch):
    monkeypatch.setattr(pipeline, "submit", lambda case_id: None)
    text = "Әғқңөұүһі 🇰🇿 😀"
    with TestClient(app) as client:
        response = post_json(client, "/api/cases", {"title": text, "materials": [{"text": text, "source": text}]})
        assert response.status_code == 201
        doc = client.get('/api/cases/' + response.json()["id"]).json()
    assert doc["title"] == doc["materials"][0]["text"] == doc["materials"][0]["source"] == text
