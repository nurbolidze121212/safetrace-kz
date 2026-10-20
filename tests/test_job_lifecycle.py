"""Exercise job ownership and cancellation without timing-dependent OCR or live data."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend import pipeline, storage
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
