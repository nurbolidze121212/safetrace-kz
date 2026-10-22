from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend import storage
from backend.app import app
from backend.link_audit import build_audit

AT = datetime(2026, 10, 22, tzinfo=timezone.utc)
REFERENCE = {"brands": [{"name": "Example", "domains": ["brand.example"], "source": "https://brand.example/about", "checked_at": "2026-10-20", "review_after": "2026-12-20"}]}


def case(url="https://brand.example/prize", text=""):
    return {"id": "a" * 32, "status": "completed", "mode": "local", "analysis_id": "run-1", "materials": [{"id": "m1", "url": url, "text": text, "source_evidence_id": "label", "content_evidence_ids": ["e1"]}], "evidence": [{"id": "e1", "quote": text or url, "method": "source_text", "material_id": "m1"}, {"id": "label", "quote": "WhatsApp", "method": "user_supplied", "material_id": "m1"}], "trace": {"observations": []}}


def audit(doc):
    return build_audit(doc, REFERENCE, AT)


@pytest.mark.parametrize("url,expected", [
    ("https://brand.example/a", True), ("https://help.brand.example/a", True),
    ("https://brand.example.evil.test/a", False), ("https://notbrand.example/a", False),
])
def test_domain_boundaries(url, expected):
    report = audit(case(url))
    assert bool(report["urls"][0]["brands"]) is expected
    assert report["probability"] is None
    if not expected:
        assert report["findings"][0]["code"] == "embedded_brand_domain"
        assert report["findings"][0]["evidence_ids"] == ["e1"]


def test_reference_age_never_becomes_safety_verdict():
    report = build_audit(case(), REFERENCE, datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert report["urls"][0]["brands"][0]["status"] == "reference_expired"
    assert report["status"] == "no_selected_indicators"
    assert any(c["status"] == "not_verified" for c in report["checks"])


def test_uncertain_ocr_is_held_and_correction_is_used():
    doc = case(url="")
    doc["materials"][0]["url_reviews"] = [{"raw_url": "https://wrong.test", "needs_review": True}]
    assert audit(doc)["urls"] == []
    assert audit(doc)["coverage"]["held_ocr_urls"] == 1
    doc["materials"][0]["url_reviews"][0]["selected_url"] = "https://correct.test"
    assert audit(doc)["urls"][0]["url"] == "https://correct.test"
    assert audit(doc)["coverage"]["held_ocr_urls"] == 0


@pytest.mark.parametrize("text,found", [
    ("Вы выиграли iPhone! Отправьте код из SMS.", True),
    ("Предупреждение: фраза «Вы выиграли iPhone! Отправьте код из SMS» — обман.", False),
    ("Вы выиграли iPhone! Не сообщайте пароль.", False),
    ("Вы выиграли iPhone! Приходите в магазин.", False),
])
def test_prize_and_secret_need_same_nonwarning_source(text, found):
    assert any(f["code"] == "prize_secret" for f in audit(case(text=text))["findings"]) is found


def test_materials_do_not_combine_prize_and_secret():
    doc = case(text="Вы выиграли iPhone")
    doc["materials"].append({"id": "m2", "text": "Отправьте код из SMS"})
    assert not any(f["code"] == "prize_secret" for f in audit(doc)["findings"])


def test_finding_opens_message_content_not_claimed_source_label():
    result = audit(case(text="Вы выиграли iPhone! Отправьте код из SMS."))
    finding = next(f for f in result["findings"] if f["code"] == "prize_secret")
    assert finding["evidence_ids"] == ["e1"]
    assert "label" not in finding["evidence_ids"]


def test_passive_audit_does_not_resolve_or_modify(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: pytest.fail("Network forbidden"))
    doc = case("http://127.0.0.1/payload.exe")
    before = deepcopy(doc)
    result = audit(doc)
    assert {f["code"] for f in result["findings"]} == {"http", "ip_host", "download"}
    assert result["network_requests"] == 0
    assert not result["urls"][0]["observed"]
    assert doc == before


def test_separate_observation_and_incomplete_source():
    doc = case()
    doc["status"] = "running"
    doc["trace"]["observations"] = [{"url": "https://stopped.example", "stop": "offline"}]
    result = audit(doc)
    assert result["status"] == "source_incomplete"
    assert result["coverage"]["observed_urls"] == 0


def test_api_and_export_preserve_case():
    doc = case("https://apple.com.claim.test", "Вы выиграли iPhone! Отправьте код из SMS.")
    storage.save(doc)
    with TestClient(app) as client:
        response = client.get(f'/api/cases/{doc["id"]}/link-audit')
        assert response.status_code == 200
        assert response.json()["status"] == "needs_review"
        downloaded = client.get(f'/api/cases/{doc["id"]}/link-audit?download=true')
        assert 'attachment;' in downloaded.headers['content-disposition']
        assert downloaded.json()["case_id"] == doc["id"]
        assert client.get('/api/cases/' + 'f' * 32 + '/link-audit').status_code == 404
    assert storage.get(doc["id"]) == doc
