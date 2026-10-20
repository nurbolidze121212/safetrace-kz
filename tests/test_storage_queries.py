"""Storage boundaries must close connections and list only the queue projection."""

import sqlite3

import pytest

from backend import storage
from backend.app import cases


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path)
    storage.init()


def test_connection_closes_after_commit_and_preserves_write(isolated_store):
    with storage.connect() as connection:
        connection.execute("INSERT INTO cache VALUES (?, ?)", ("commit-test", '{"saved": true}'))
    assert storage.cached("commit-test") == {"saved": True}
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_connection_rolls_back_and_closes_after_error(isolated_store):
    with pytest.raises(ValueError, match="rollback"):
        with storage.connect() as connection:
            connection.execute("INSERT INTO cache VALUES (?, ?)", ("rollback-test", '{}'))
            raise ValueError("rollback")
    assert storage.cached("rollback-test") is None
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_queue_projection_matches_documents_and_latest_inserted_decision(isolated_store, monkeypatch):
    documents = [
        {"id": "first", "title": "Тексеру", "created_at": "2026-01-02", "materials": [{"text": "x"}],
         "mode": "synthetic", "status": "partial", "progress": 100, "stage": "priority",
         "sufficient_data": False, "score": {"value": 0, "contributions": []}, "history": [{"private": "large"}]},
        {"id": "second", "title": "Без результата", "created_at": "2026-01-01", "materials": [],
         "mode": "local", "status": "pending", "progress": 0, "stage": "originals"},
    ]
    for document in documents:
        storage.save(document)
    storage.add_decision("first", "confirmed", "Old")
    storage.add_decision("first", "needs_data", "New")
    fields = ("id", "title", "mode", "status", "created_at", "score", "progress", "stage", "sufficient_data")
    expected = [
        {**{key: doc.get(key) for key in fields}, "material_count": len(doc["materials"]),
         "decision": "needs_data" if doc["id"] == "first" else None}
        for doc in documents
    ]

    def avoid_full_documents(*args):
        raise AssertionError("Queue listing must not load complete histories or N decision lists")

    monkeypatch.setattr(storage, "all_cases", avoid_full_documents)
    monkeypatch.setattr(storage, "decisions", avoid_full_documents)
    result = cases()
    assert result == expected
    assert result[0]["sufficient_data"] is False
    assert storage.get("first") == documents[0]


def test_empty_queue_is_an_empty_list(isolated_store):
    assert cases() == []
