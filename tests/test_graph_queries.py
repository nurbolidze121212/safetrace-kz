"""A dossier needs matching peer evidence, not every other case's analysis history."""

import io
import json
import zipfile
from contextlib import contextmanager
from copy import deepcopy

import pytest

from backend import storage
from backend.app import detail
from backend.exports import package
from backend.graph import build_graph


@pytest.fixture
def graph_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path)
    storage.init()

    def document(case_id, scope, mode="synthetic"):
        material_id, evidence_id = case_id + "-m", case_id + "-e"
        return {
            "id": case_id, "title": case_id, "mode": mode, "created_at": "2026-01-01T00:00:00+00:00",
            "status": "completed", "limitations": [], "trace": {"observations": [], "relations": []},
            "materials": [{"id": material_id, "source": case_id, "text": "DEMO", "url": "",
                           "source_evidence_id": evidence_id, "content_evidence_ids": [evidence_id]}],
            "identifiers": [{"scope": scope, "material_id": material_id, "evidence_id": evidence_id}],
            "evidence": [{"id": evidence_id, "quote": "DEMO", "material_id": material_id,
                          "source_id": material_id, "method": "source_text"}],
            "history": [{"old_private_data": "Not needed for a cross-case match"}],
        }

    documents = [
        document("own", "arena.test|/welcome|ref|A1"),
        document("match", "arena.test|/welcome|ref|A1"),
        document("other-path", "arena.test|/different|ref|A1"),
        document("other-domain", "shop.test|/welcome|ref|A1"),
        document("other-token", "arena.test|/welcome|ref|A12"),
        document("other-mode", "arena.test|/welcome|ref|A1", "local"),
    ]
    for document in documents:
        storage.save(document)
    return documents


def test_peer_projection_keeps_exact_scope_and_mode_only(graph_cases):
    peers = storage.graph_peers(graph_cases[0])
    assert [peer["id"] for peer in peers] == ["match"]
    assert "history" not in peers[0]
    assert peers[0]["evidence"] == graph_cases[1]["evidence"]
    assert peers[0]["materials"] == graph_cases[1]["materials"]


def test_detail_and_export_keep_the_same_proven_graph_without_full_case_reads(graph_cases, monkeypatch):
    expected = build_graph(graph_cases[0], storage.all_cases())
    expected.pop("generated_at")

    def fail_full_read():
        raise AssertionError("Unrelated full histories must not be read")

    monkeypatch.setattr(storage, "all_cases", fail_full_read)
    actual = detail("own")["graph"]
    actual.pop("generated_at")
    assert actual == expected
    with zipfile.ZipFile(io.BytesIO(package(graph_cases[0]))) as archive:
        exported = json.loads(archive.read("case.json"))["graph"]
    exported.pop("generated_at")
    assert exported == expected


def test_changed_peer_scope_disappears_without_a_stale_cached_link(graph_cases):
    assert len(storage.graph_peers(graph_cases[0])) == 1
    changed = graph_cases[1]
    changed["identifiers"][0]["scope"] = "arena.test|/welcome|ref|NEW"
    storage.save(changed)
    assert storage.graph_peers(graph_cases[0]) == []


def test_case_without_identifiers_needs_no_peer_query(graph_cases, monkeypatch):
    own = graph_cases[0]
    own["identifiers"] = []

    def fail_connection():
        raise AssertionError("No identifier means no peer lookup")

    monkeypatch.setattr(storage, "connect", fail_connection)
    assert storage.graph_peers(own) == []


def test_peer_filter_and_evidence_share_a_snapshot_during_concurrent_update(graph_cases, monkeypatch):
    original_connect = storage.connect
    changed = False
    updated = deepcopy(graph_cases[1])
    updated["identifiers"][0]["scope"] = "arena.test|/welcome|ref|NEW"

    def update_between_queries(sql):
        nonlocal changed
        if "AS peer" in sql and not changed:
            changed = True
            storage.save(updated)

    @contextmanager
    def observed_connect():
        with original_connect() as connection:
            connection.set_trace_callback(update_between_queries)
            yield connection

    monkeypatch.setattr(storage, "connect", observed_connect)
    peers = storage.graph_peers(graph_cases[0])
    assert changed
    assert peers[0]["identifiers"] == graph_cases[1]["identifiers"]
    assert storage.get("match")["identifiers"] == updated["identifiers"]
