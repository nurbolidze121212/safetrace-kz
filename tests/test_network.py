from copy import deepcopy

import pytest

from backend.network import build_network


def case(key, scope="example.test|ref|SAME", mode="synthetic", text=None):
    eid, mid = key + "-e", key + "-m"
    return {"id": key, "title": key, "mode": mode, "created_at": "2026-10-25T00:00:00Z",
            "materials": [{"id": mid, "source": "@" + key, "text": text or key,
                           "source_evidence_id": eid, "content_evidence_ids": [eid]}],
            "evidence": [{"id": eid, "quote": key, "method": "source_text"}],
            "identifiers": [{"scope": scope, "material_id": mid, "evidence_id": eid}]}


def test_cross_case_community_has_both_sources_and_does_not_mutate_cases():
    docs = [case("a"), case("b"), case("c", "other.test|ref|SAME")]
    before = deepcopy(docs)
    result = build_network(docs)
    assert sorted(c["size"] for c in result["communities"]) == [1, 2]
    assert result["counts"]["matching_pairs"] == 1
    edge = next(e for e in result["edges"] if e["type"] == "matching_identifier")
    assert set(edge["evidence_ids"]) == {"a-e", "b-e"}
    assert edge["status"] == "inferred" and docs == before
    assert build_network(list(reversed(docs))) == result


def test_duplicates_and_missing_evidence_do_not_create_relationship():
    left, right = case("a", text="same post"), case("b", text="same post")
    assert build_network([left, right])["counts"]["matching_pairs"] == 0
    right["materials"][0]["text"] = "different"
    right["identifiers"][0]["evidence_id"] = "absent"
    assert build_network([left, right])["counts"]["matching_pairs"] == 0


def test_modes_are_never_merged_and_empty_network_is_valid():
    with pytest.raises(ValueError, match="mode"):
        build_network([case("a"), case("b", mode="local")])
    assert build_network([])["communities"] == []


def test_network_api_limits_cases_and_separates_modes(tmp_path, monkeypatch):
    import json
    import sqlite3

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend import network_api

    database = tmp_path / "cases.db"

    def connect():
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        return conn

    with connect() as conn:
        conn.execute("CREATE TABLE cases (id TEXT PRIMARY KEY, document TEXT)")
        docs = [case("a", mode="local"), case("b", mode="local"), case("c")]
        empty = case("z", mode="local")
        empty["evidence"] = []
        for doc in [*docs, empty]:
            conn.execute("INSERT INTO cases VALUES (?, ?)", (doc["id"], json.dumps(doc)))
    monkeypatch.setattr(network_api.storage, "connect", connect)
    app = FastAPI()
    app.include_router(network_api.router)
    client = TestClient(app)
    local = client.get("/api/network?mode=local&limit=1").json()
    assert local["truncated"] is True and local["counts"]["cases"] == 1
    synthetic = client.get("/api/network?mode=synthetic").json()
    assert synthetic["truncated"] is False and synthetic["counts"]["cases"] == 1
    assert {e["case_id"] for e in synthetic["evidence"]} == {"c"}
    for query in ("mode=invalid", "limit=201", "limit=0"):
        assert client.get("/api/network?" + query).status_code == 422
