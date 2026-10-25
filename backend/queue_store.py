"""Redis Streams delivery with bounded admission and per-case execution leases."""

import os
import uuid

PREFIX = os.getenv("SAFETRACE_QUEUE_NAMESPACE", "safetrace:v1")
GROUP = "analysis"
LEASE_MS = 45000
STREAM = PREFIX + ":stream"
ACTIVE = PREFIX + ":active"


def enabled():
    return bool(os.getenv("SAFETRACE_REDIS_URL"))


def client():
    from redis import Redis

    return Redis.from_url(os.environ["SAFETRACE_REDIS_URL"], decode_responses=True,
                          socket_timeout=10, socket_connect_timeout=3)


def initialize():
    from redis.exceptions import ResponseError

    try:
        client().xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def is_active(case_id):
    return bool(client().sismember(ACTIVE, case_id))


def full():
    return client().scard(ACTIVE) >= 128


def enqueue(case_id, token):
    result = client().eval("""
      if redis.call('SISMEMBER',KEYS[1],ARGV[1]) == 1 then return 'already_active' end
      if redis.call('SCARD',KEYS[1]) >= 128 then return 'full' end
      redis.call('SADD',KEYS[1],ARGV[1])
      return redis.call('XADD',KEYS[2],'*','case_id',ARGV[1],'token',ARGV[2])
    """, 2, ACTIVE, STREAM, case_id, token)
    if result == "full":
        raise ValueError("Redis queue is full (128 jobs)")
    return result


def cancel(case_id):
    client().set(PREFIX + ":cancel:" + case_id, "1", ex=3600)


def cancelled(case_id):
    return bool(client().exists(PREFIX + ":cancel:" + case_id))


def new_token():
    return uuid.uuid4().hex


def take(consumer):
    conn = client()
    recovered = conn.xautoclaim(STREAM, GROUP, consumer, LEASE_MS, "0-0", count=1)[1]
    if recovered:
        return recovered[0]
    rows = conn.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=1, block=2000)
    return rows[0][1][0] if rows else None


def lease(case_id, owner):
    return client().set(PREFIX + ":lease:" + case_id, owner, nx=True, px=LEASE_MS)


def owns(case_id, owner):
    return client().get(PREFIX + ":lease:" + case_id) == owner


def pulse(case_id, owner, message_id, consumer):
    conn = client()
    renewed = conn.eval("""
      if redis.call('GET',KEYS[1]) ~= ARGV[1] then return 0 end
      return redis.call('PEXPIRE',KEYS[1],ARGV[2])
    """, 1, PREFIX + ":lease:" + case_id, owner, LEASE_MS)
    if renewed:
        conn.xclaim(STREAM, GROUP, consumer, 0, [message_id], idle=0, justid=True)
    return bool(renewed)


def finish(case_id, owner, message_id):
    client().eval("""
      if redis.call('GET',KEYS[1]) ~= ARGV[1] then return 0 end
      redis.call('XACK',KEYS[2],ARGV[3],ARGV[2])
      redis.call('XDEL',KEYS[2],ARGV[2])
      redis.call('SREM',KEYS[3],ARGV[4])
      redis.call('DEL',KEYS[1],KEYS[4])
      return 1
    """, 4, PREFIX + ":lease:" + case_id, STREAM, ACTIVE, PREFIX + ":cancel:" + case_id,
       owner, message_id, GROUP, case_id)


def stats():
    conn = client()
    return {"backend": "redis-streams", "active": conn.scard(ACTIVE), "capacity": 128,
            "pending_delivery": conn.xpending(STREAM, GROUP)["pending"], "delivery": "at-least-once"}
