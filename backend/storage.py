import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

from .config import DATA

LOCK = threading.RLock()


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


@contextmanager
def connect():
    DATA.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(DATA / "safetrace.sqlite3", timeout=20)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        with conn:
            yield conn
    finally:
        conn.close()


def init():
    (DATA / "originals").mkdir(exist_ok=True, parents=True)
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, document TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS decisions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL, at TEXT NOT NULL,
          decision TEXT NOT NULL, comment TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, document TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS decisions_case_latest ON decisions(case_id, id DESC);
        """)


def save(doc):
    with LOCK, connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cases VALUES(?,?)", (doc["id"], json.dumps(doc, ensure_ascii=False))
        )


def get(case_id):
    with connect() as conn:
        row = conn.execute("SELECT document FROM cases WHERE id=?", (case_id,)).fetchone()
    return json.loads(row["document"]) if row else None


def all_cases():
    with connect() as conn:
        return [json.loads(row["document"]) for row in conn.execute("SELECT document FROM cases")]


def case_summaries():
    fields = ("id", "title", "mode", "status", "created_at", "score", "progress", "stage", "sufficient_data")
    # Project in SQLite: a polling queue must not deserialize every OCR/history document into Python.
    with connect() as conn:
        rows = conn.execute("""
            SELECT json_extract(c.document, '$.id', '$.title', '$.mode', '$.status', '$.created_at',
                                '$.score', '$.progress', '$.stage', '$.sufficient_data') AS summary,
                   json_array_length(c.document, '$.materials') AS material_count,
                   (SELECT decision FROM decisions d WHERE d.case_id=c.id ORDER BY d.id DESC LIMIT 1)
                       AS decision
            FROM cases c ORDER BY json_extract(c.document, '$.created_at') DESC, c.rowid
        """)
        return [
            dict(zip(fields, json.loads(row["summary"]), strict=True))
            | {"material_count": row["material_count"], "decision": row["decision"]}
            for row in rows
        ]


def decisions(case_id):
    with connect() as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT * FROM decisions WHERE case_id=? ORDER BY id", (case_id,))
        ]


def add_decision(case_id, decision, comment):
    with connect() as conn:
        conn.execute(
            "INSERT INTO decisions(case_id,at,decision,comment) VALUES(?,?,?,?)",
            (case_id, now(), decision, comment),
        )


def cached(key):
    with connect() as conn:
        row = conn.execute("SELECT document FROM cache WHERE key=?", (key,)).fetchone()
    return json.loads(row["document"]) if row else None


def put_cache(key, value):
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO cache VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))
