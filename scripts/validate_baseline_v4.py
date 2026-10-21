"""Preservation and a fresh end-to-end API flow on the archived v3, in a restored clone."""

import hashlib
import io
import json
import sqlite3
import time
import zipfile
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/acceptance-v4"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def snapshot(folder):
    with sqlite3.connect((folder / "safetrace.sqlite3").resolve().as_uri() + "?mode=ro", uri=True) as db:
        tables = {
            table: sorted(db.execute("SELECT * FROM " + table).fetchall())
            for table in ("cases", "decisions", "cache")
        }
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    return {
        "tables": {
            name: {"n": len(rows), "sha256": digest(json.dumps(rows, ensure_ascii=False).encode())}
            for name, rows in tables.items()
        },
        "originals": {
            p.name: digest(p.read_bytes()) for p in sorted((folder / "originals").iterdir()) if p.is_file()
        },
    }


def main():
    report = OUT / "baseline-new-flow.json"
    if report.exists():
        raise RuntimeError("Report exists; inspect it, do not repeat")
    before = snapshot(ROOT / "data")
    restored = snapshot(ROOT / "tmp/v4-baseline-data")
    # A previously interrupted test may already have added its own case in the clone.
    # Verify every original row and image exactly; only the clone may have extra test data.
    with (
        sqlite3.connect(ROOT / "data/safetrace.sqlite3") as a,
        sqlite3.connect(ROOT / "tmp/v4-baseline-data/safetrace.sqlite3") as b,
    ):
        for table in ("cases", "decisions", "cache"):
            original_rows = a.execute("SELECT * FROM " + table).fetchall()
            clone_rows = {row[0]: row for row in b.execute("SELECT * FROM " + table).fetchall()}
            assert all(clone_rows.get(row[0]) == row for row in original_rows)
    assert all(restored["originals"].get(name) == value for name, value in before["originals"].items())
    result = {"restoration": {"all_original_rows_and_images_match": True, "snapshot": before}}
    with httpx.Client(base_url="http://127.0.0.1:8767", timeout=120) as client:

        def get(path):
            r = client.get(path)
            r.raise_for_status()
            return r.json()

        def post(path, value):
            r = client.post(path, json=value)
            r.raise_for_status()
            return r.json()

        def completed(case_id):
            end = time.monotonic() + 120
            while time.monotonic() < end:
                doc = get("/api/cases/" + case_id)
                if doc["status"] not in ("pending", "running"):
                    assert doc["status"] in ("completed", "partial"), doc["status"]
                    return doc
                time.sleep(0.2)
            raise TimeoutError("Case did not finish")

        result["health"] = get("/api/health")
        assert result["health"]["versions"]["rules"] == "rules-3.0"
        im = Image.new("RGB", (1000, 220), "#fbfcff")
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 28)
        for i, line in enumerate(
            [
                "DEMO — новый авторский материал для проверки",
                "Заходи в клуб, забирай персональный бонус.",
                "https://go.safetrace.test/r/q7",
            ]
        ):
            draw.text((24, 25 + i * 58), line, font=font, fill="#243549")
        path = OUT / "baseline-new-image.png"
        im.save(path)
        previous = next(
            (c for c in get("/api/cases") if c["title"] == "Проверка исходной версии перед v4"), None
        )
        if previous:
            case_id = previous["id"]
        else:
            upload = client.post("/api/uploads", files={"file": ("new.png", path.read_bytes(), "image/png")})
            upload.raise_for_status()
            image_id = upload.json()["image_id"]
            case_id = post(
                "/api/cases",
                {
                    "title": "Проверка исходной версии перед v4",
                    "mode": "synthetic",
                    "materials": [{"text": "", "source": "Авторский API-сценарий", "image_id": image_id}],
                },
            )["id"]
        doc = completed(case_id)
        assert doc["score"]["value"] >= 65 and doc["sufficient_data"]
        first_id = doc["analysis_id"]
        result["initial"] = {
            "id": case_id,
            "analysis_id": first_id,
            "score": doc["score"],
            "urls": doc["materials"][0]["urls"],
            "route_requests": doc["trace"]["requests"],
        }
        assert len(doc["trace"]["observations"]) == 3
        evidence = {e["id"] for e in doc["graph"]["evidence"]}
        assert all(set(edge["evidence_ids"]) <= evidence for edge in doc["graph"]["edges"])
        if len(doc["materials"]) == 1:
            post(
                "/api/cases/" + case_id + "/materials",
                {
                    "text": "Утром открыли ещё одно приглашение. "
                    "Переходи и забирай бонус: https://go.safetrace.test/r/second",
                    "source": "Второй авторский материал",
                },
            )
        doc = completed(case_id)
        assert len(doc["materials"]) == 2 and any(h["analysis_id"] == first_id for h in doc["history"])
        assert any(e["type"] == "matching_identifier" for e in doc["graph"]["edges"])
        if not doc["decisions"]:
            post(
                "/api/cases/" + case_id + "/decision",
                {"decision": "needs_data", "comment": "Техническая проверка синтетического стенда."},
            )
        post("/api/cases/" + case_id + "/retry", {})
        doc = completed(case_id)
        assert doc["decisions"][-1]["decision"] == "needs_data" and len(doc["history"]) >= 2
        r = client.get("/api/cases/" + case_id + "/export")
        r.raise_for_status()
        archive_path = OUT / "baseline-new-case.zip"
        archive_path.write_bytes(r.content)
        with zipfile.ZipFile(io.BytesIO(r.content)) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            for item in manifest["files"]:
                data = bundle.read(item["path"])
                assert len(data) == item["bytes"] and digest(data) == item["sha256"]
            exported = json.loads(bundle.read("case.json"))
            assert exported["decisions"] == doc["decisions"]
            assert bundle.read("originals/01.png") == path.read_bytes()
            html = BeautifulSoup(bundle.read("report.html"), "html.parser")
            ids = {node["id"] for node in html.select("[id]")}
            assert all(link["href"][1:] in ids for link in html.select('a[href^="#"]'))
        result["final"] = {
            "score": doc["score"],
            "history_count": len(doc["history"]),
            "decision_count": len(doc["decisions"]),
            "archive_sha256": digest(r.content),
            "archive_files": len(manifest["files"]),
            "ocr_cache_hit": doc["materials"][0]["ocr"]["cache_hit"],
        }
    assert snapshot(ROOT / "data") == before, "Main user data changed"
    result["main_data_unchanged"] = True
    result["scope"] = (
        "Real HTTP API and OCR, synthetic route fixture; no browser or real-world quality claim."
    )
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
