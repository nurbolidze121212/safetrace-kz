import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime

from .config import DATA

LOCK = threading.RLock()


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def connect():
    DATA.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(DATA / "safetrace.sqlite3", timeout=20)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init():
    (DATA / "originals").mkdir(exist_ok=True, parents=True)
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, document TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS decisions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL, at TEXT NOT NULL,
          decision TEXT NOT NULL, comment TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, document TEXT NOT NULL);
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
