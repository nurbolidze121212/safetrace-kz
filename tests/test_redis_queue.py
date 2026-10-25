import os
import uuid

import pytest

from backend import queue_store as queue


@pytest.fixture
def redis_queue(monkeypatch):
    url = os.getenv("SAFETRACE_TEST_REDIS_URL")
    if not url:
        pytest.skip("Real Redis integration runs in CI with SAFETRACE_TEST_REDIS_URL")
    prefix = "safetrace-test:" + uuid.uuid4().hex
    monkeypatch.setenv("SAFETRACE_REDIS_URL", url)
    monkeypatch.setattr(queue, "PREFIX", prefix)
    monkeypatch.setattr(queue, "STREAM", prefix + ":stream")
    monkeypatch.setattr(queue, "ACTIVE", prefix + ":active")
    queue.initialize()
    yield queue
    conn = queue.client()
    keys = list(conn.scan_iter(prefix + ":*"))
    if keys:
        conn.delete(*keys)


def test_redis_admission_is_bounded_and_duplicate_safe(redis_queue):
    q = redis_queue
    for i in range(128):
        q.enqueue(str(i), "token")
    assert q.full() and q.stats()["active"] == 128
    assert q.enqueue("0", "token") == "already_active"
    with pytest.raises(ValueError, match="full"):
        q.enqueue("overflow", "token")


def test_redis_delivery_lease_and_ack_are_real(redis_queue):
    q = redis_queue
    q.enqueue("case", "token")
    message_id, payload = q.take("consumer-1")
    assert payload == {"case_id": "case", "token": "token"}
    assert q.lease("case", "owner-1") and not q.lease("case", "owner-2")
    assert not q.pulse("case", "owner-2", message_id, "consumer-2")
    assert q.pulse("case", "owner-1", message_id, "consumer-1")
    q.cancel("case")
    assert q.cancelled("case")
    q.finish("case", "owner-2", message_id)
    assert q.is_active("case")
    q.finish("case", "owner-1", message_id)
    assert not q.is_active("case") and not q.cancelled("case")
    assert q.client().xlen(q.STREAM) == 0


def test_abandoned_delivery_can_be_reclaimed_without_sleep(redis_queue):
    q = redis_queue
    q.enqueue("case", "token")
    message_id, _ = q.take("dead-consumer")
    q.client().xclaim(q.STREAM, q.GROUP, "dead-consumer", 0, [message_id], idle=q.LEASE_MS + 1)
    recovered, payload = q.take("replacement")
    assert recovered == message_id and payload["case_id"] == "case"
