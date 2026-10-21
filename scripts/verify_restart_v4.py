"""Read-only fingerprint of a private acceptance database before/after managed restart."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tmp/v4-browser-data"
OUT = ROOT / "reports/acceptance-v4"
CASE = "aa7d719d0bb74487b852e67969ae077b"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def snapshot():
    with sqlite3.connect((DATA / "safetrace.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        tables = {}
        for table in ("cases", "decisions", "cache"):
            rows = db.execute("SELECT * FROM " + table + " ORDER BY 1").fetchall()
            tables[table] = {"n": len(rows), "sha256": digest(json.dumps(rows, ensure_ascii=False).encode())}
    originals = {p.name: digest(p.read_bytes()) for p in (DATA / "originals").iterdir() if p.is_file()}
    return {"tables": tables, "originals": originals}


def main(phase):
    before = OUT / "restart-before.json"
    if phase == "before":
        with before.open("x", encoding="utf-8") as file:
            json.dump(snapshot(), file, indent=2)
        print("Before-restart row and original fingerprints saved")
        return
    assert json.loads(before.read_text(encoding="utf-8")) == snapshot(), "Stored data changed across restart"
    with httpx.Client(base_url="http://127.0.0.1:8768", trust_env=False) as client:
        health = client.get("/api/health").raise_for_status().json()
        doc = client.get("/api/cases/" + CASE).raise_for_status().json()
    assert health["app_version"] == "2.2.0" and health["versions"]["rules"] == "rules-4.0"
    assert doc["score"]["value"] == 90 and doc["analysis_assisted"] and len(doc["history"]) == 2
    assert len(doc["decisions"]) == 1 and len(doc["materials"][0]["url_corrections"]) == 1
    with (OUT / "restart-after.json").open("x", encoding="utf-8") as file:
        json.dump(
            {
                "ok": True,
                "all_stored_rows_unchanged": True,
                "all_originals_unchanged": True,
                "case_id": CASE,
                "health": health,
                "stored_analysis_versions": doc["versions"],
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
    print("All stored cases, decisions, cache rows and originals preserved; v4 API reopened saved case")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["before", "after"])
    main(parser.parse_args().phase)
