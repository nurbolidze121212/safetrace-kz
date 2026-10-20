"""Exercise job ownership and cancellation without timing-dependent OCR or live data."""

import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from backend import pipeline, storage
from backend.app import app
from backend.schemas import CaseInput, MaterialInput


def make_case():
    return pipeline.new_case(CaseInput(title="Очередь", materials=[MaterialInput(text="Текст проверки")]))


@pytest.fixture
def held_executor(monkeypatch):
    executor = ThreadPoolExecutor(max_workers=1)
    release = threading.Event()
    started = threading.Event()

    def hold_worker():
        started.set()
        assert release.wait(10), "Test did not release the worker"

    blocker = executor.submit(hold_worker)
    assert started.wait(2)
    monkeypatch.setattr(pipeline, "EXECUTOR", executor)
    monkeypatch.setattr(pipeline, "ACTIVE", set())
    monkeypatch.setattr(pipeline, "CANCELS", {})
    monkeypatch.setattr(pipeline, "FUTURES", {}, raising=False)
    try:
        yield executor, release
    finally:
        release.set()
        executor.shutdown(wait=True)
        blocker.result()


def test_cancel_waiting_job_frees_capacity_and_does_not_run(held_executor, monkeypatch):
    called = []
    monkeypatch.setattr(pipeline, "analyze", lambda doc, **kwargs: called.append(doc["id"]))
    doc = make_case()
    pipeline.submit(doc["id"])
    assert doc["id"] in pipeline.ACTIVE

    pipeline.cancel(doc["id"])

    current = storage.get(doc["id"])
    assert current["status"] == "cancelled"
    assert all(value == "cancelled" for value in current["stages"].values())
    assert doc["id"] not in pipeline.ACTIVE
    assert doc["id"] not in pipeline.CANCELS
    executor, release = held_executor
    release.set()
    executor.submit(lambda: None).result(timeout=3)
    assert called == []


def test_cancelled_waiting_job_can_be_retried(held_executor):
    doc = make_case()
    pipeline.submit(doc["id"])
    pipeline.cancel(doc["id"])
    pipeline.submit(doc["id"])

    executor, release = held_executor
    release.set()
    executor.submit(lambda: None).result(timeout=3)
    assert storage.get(doc["id"])["status"] == "completed"
    assert doc["id"] not in pipeline.ACTIVE
    assert doc["id"] not in pipeline.CANCELS


def test_executor_rejection_restores_document_and_job_ownership(monkeypatch):
    class RejectingExecutor:
        def submit(self, *args):
            raise RuntimeError("executor stopped")

    monkeypatch.setattr(pipeline, "EXECUTOR", RejectingExecutor())
    monkeypatch.setattr(pipeline, "ACTIVE", set())
    monkeypatch.setattr(pipeline, "CANCELS", {})
    monkeypatch.setattr(pipeline, "FUTURES", {}, raising=False)
    doc = make_case()
    pipeline.analyze(doc)
    storage.save(doc)
    before = storage.get(doc["id"])

    with pytest.raises(RuntimeError, match="executor stopped"):
        pipeline.submit(doc["id"])

    assert storage.get(doc["id"]) == before
    assert doc["id"] not in pipeline.ACTIVE
    assert doc["id"] not in pipeline.CANCELS


def test_running_cancellation_keeps_ownership_until_worker_exits(held_executor, monkeypatch):
    executor, release = held_executor
    started, proceed = threading.Event(), threading.Event()
    real_analyze = pipeline.analyze

    def running_analysis(doc, **kwargs):
        started.set()
        assert proceed.wait(5)
        return real_analyze(doc, **kwargs)

    monkeypatch.setattr(pipeline, "analyze", running_analysis)
    doc = make_case()
    pipeline.submit(doc["id"])
    release.set()
    try:
        assert started.wait(2)
        pipeline.cancel(doc["id"])
        assert doc["id"] in pipeline.ACTIVE
        assert pipeline.CANCELS[doc["id"]].is_set()
        pipeline.submit(doc["id"])
        assert len(pipeline.ACTIVE) == 1
    finally:
        proceed.set()
    executor.submit(lambda: None).result(timeout=3)
    assert storage.get(doc["id"])["status"] == "cancelled"
    assert doc["id"] not in pipeline.ACTIVE


def test_repeated_waiting_cancellation_does_not_duplicate_previous_analysis(held_executor):
    doc = make_case()
    pipeline.analyze(doc)
    storage.save(doc)
    previous_materials = deepcopy(doc["materials"])
    for _ in range(3):
        pipeline.submit(doc["id"])
        pipeline.cancel(doc["id"])
    current = storage.get(doc["id"])
    assert len(current["history"]) == 1
    assert current["history"][0]["analysis_id"] == doc["analysis_id"]
    assert current["history"][0]["materials"] == previous_materials


def test_failed_addition_rolls_back_materials_and_analysis(monkeypatch):
    class RejectingExecutor:
        def submit(self, *args):
            raise RuntimeError("executor stopped")

    monkeypatch.setattr(pipeline, "EXECUTOR", RejectingExecutor())
    doc = make_case()
    pipeline.analyze(doc)
    storage.save(doc)
    before = storage.get(doc["id"])

    with pytest.raises(RuntimeError, match="executor stopped"):
        pipeline.add_materials(doc["id"], [MaterialInput(text="Второй материал")])

    assert storage.get(doc["id"]) == before
    assert doc["id"] not in pipeline.ACTIVE


def test_worker_read_failure_releases_slot_and_marks_retryable_error(held_executor, monkeypatch):
    doc = make_case()
    pipeline.submit(doc["id"])
    read = storage.get
    failures = 1

    def flaky_read(case_id):
        nonlocal failures
        if failures:
            failures -= 1
            raise OSError("temporary read error")
        return read(case_id)

    monkeypatch.setattr(storage, "get", flaky_read)
    executor, release = held_executor
    release.set()
    executor.submit(lambda: None).result(timeout=3)
    assert doc["id"] not in pipeline.ACTIVE
    assert doc["id"] not in pipeline.CANCELS
    assert doc["id"] not in pipeline.FUTURES
    assert read(doc["id"])["status"] == "error"


def test_worker_failure_log_does_not_expose_material_or_exception_message(held_executor, monkeypatch, caplog):
    def failing_analysis(doc, **kwargs):
        raise RuntimeError("private-provider-key and private-material-text")

    monkeypatch.setattr(pipeline, "analyze", failing_analysis)
    doc = make_case()
    pipeline.submit(doc["id"])
    executor, release = held_executor
    release.set()
    executor.submit(lambda: None).result(timeout=3)
    assert storage.get(doc["id"])["status"] == "error"
    assert doc["id"] in caplog.text
    assert "RuntimeError" in caplog.text
    assert "private-provider-key" not in caplog.text
    assert "private-material-text" not in caplog.text


def test_recovery_marks_unfinished_stages_stopped():
    doc = make_case()
    doc.update(status="running", stage="ocr", progress=17)
    doc["stages"]["originals"] = "completed"
    doc["stages"]["ocr"] = "running"
    storage.save(doc)

    pipeline.recover()

    current = storage.get(doc["id"])
    assert current["status"] == "partial"
    assert current["stage"] == "interrupted"
    assert current["stages"]["originals"] == "completed"
    assert all(current["stages"][key] == "cancelled" for key in pipeline.STAGES[1:])
    assert current["materials"] == doc["materials"]


def test_waiting_and_cancelled_case_have_a_stable_route_contract(held_executor):
    with TestClient(app) as client:
        created = client.post("/api/cases", json={"title": "Waiting route", "materials": [{"text": "Input"}]})
        assert created.status_code == 201
        case_id = created.json()["id"]
        waiting = client.get(f"/api/cases/{case_id}").json()
        assert waiting["status"] == "pending"
        assert waiting["trace"]["observations"] == []
        assert waiting["trace"]["relations"] == []
        assert client.post(f"/api/cases/{case_id}/cancel").status_code == 200
        cancelled = client.get(f"/api/cases/{case_id}").json()
        assert cancelled["status"] == "cancelled"
        assert cancelled["trace"]["observations"] == []
        assert client.get(f"/api/cases/{case_id}/export").status_code == 200


def test_legacy_pending_case_still_has_a_route_contract():
    with TestClient(app) as client:
        doc = make_case()
        doc.pop("trace", None)
        storage.save(doc)
        fetched = client.get(f"/api/cases/{doc['id']}").json()
        assert fetched["trace"] == {"observations": [], "relations": [], "requests": 0}
