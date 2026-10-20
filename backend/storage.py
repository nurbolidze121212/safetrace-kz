import hashlib
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

from .config import DATA, MAX_IMAGE

LOCK = threading.RLock()


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


class OriginalIntegrityError(ValueError):
    """Safe, user-facing integrity failure without disclosing a filesystem path."""


def read_image(image_id, expected_sha256=None):
    if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpg|webp)", image_id):
        raise OriginalIntegrityError("Некорректный идентификатор оригинала изображения.")
    try:
        with (DATA / "originals" / image_id).open("rb") as original:
            data = original.read(MAX_IMAGE + 1)
    except OSError:
        raise OriginalIntegrityError("Оригинал изображения отсутствует или недоступен.") from None
    if len(data) > MAX_IMAGE:
        raise OriginalIntegrityError("Оригинал изображения изменен: превышен сохраненный лимит размера.")
    actual = digest(data)
    if expected_sha256 is not None and actual != expected_sha256:
        raise OriginalIntegrityError("Оригинал изображения изменен: SHA-256 не совпадает с сохраненным.")
    return data, actual


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


def graph_peers(doc):
    scopes = {item["scope"] for item in doc.get("identifiers", [])}
    if not scopes:
        return []
    fields = ("id", "title", "mode", "identifiers", "evidence", "materials")
    with connect() as conn:
        # Keep both small projections on one read snapshot, including concurrent case updates.
        conn.execute("BEGIN")
        selected = []
        for row in conn.execute("""
            SELECT id, json_extract(document, '$.mode', '$.identifiers') AS match_data
            FROM cases WHERE id != ?
        """, (doc["id"],)):
            mode, identifiers = json.loads(row["match_data"])
            if mode == doc["mode"] and any(item["scope"] in scopes for item in identifiers or []):
                selected.append(row["id"])
        if not selected:
            return []
        rows = conn.execute("""
            SELECT json_extract(c.document, '$.id', '$.title', '$.mode', '$.identifiers',
                                '$.evidence', '$.materials') AS peer
            FROM cases c WHERE c.id IN (SELECT value FROM json_each(?))
            ORDER BY c.rowid
        """, (json.dumps(selected),))
        return [dict(zip(fields, json.loads(row["peer"]), strict=True)) for row in rows]


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
