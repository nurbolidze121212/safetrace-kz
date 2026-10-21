"""Check a real release archive in an isolated ASCII path with a space, on this PC."""

import argparse
import hashlib
import io
import json
import shutil
import sqlite3
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "tmp/Transfer check v4"
OUT = ROOT / "reports/acceptance-v4"
RELEASE = ROOT / "deliverables/releases/v4"
sys.path.insert(0, str(ROOT))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(data):
    with sqlite3.connect((data / "safetrace.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        tables = {name: db.execute("SELECT * FROM " + name + " ORDER BY 1").fetchall() for name in ("cases", "decisions", "cache")}
    return {"tables": {key: {"n": len(rows), "sha256": sha(json.dumps(rows, ensure_ascii=False).encode())} for key, rows in tables.items()}, "originals": {p.name: sha(p.read_bytes()) for p in (data / "originals").iterdir() if p.is_file()}}


def stage():
    from scripts.backup_data import restore_backup

    assert not DEST.exists() and DEST.resolve().is_relative_to((ROOT / "tmp").resolve())
    archive = RELEASE / "SafeTrace-KZ-v4-candidate.zip"
    with zipfile.ZipFile(archive) as zipped:
        manifest = json.loads(zipped.read("PACKAGE_MANIFEST.json"))
        for name, item in manifest["files"].items():
            pure = PurePosixPath(name)
            assert not pure.is_absolute() and ".." not in pure.parts and "\\" not in name
            data = zipped.read(name)
            assert len(data) == item["bytes"] and sha(data) == item["sha256"]
            target = DEST / name
            assert target.resolve().is_relative_to(DEST.resolve())
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_bytes(data)
        (DEST / "PACKAGE_MANIFEST.json").write_bytes(zipped.read("PACKAGE_MANIFEST.json"))
    model_manifest = json.loads((DEST / "models-manifest.json").read_text(encoding="utf-8"))
    for name, expected in model_manifest["files"].items():
        src, dst = ROOT / "models" / name, DEST / "models" / name
        dst.parent.mkdir(exist_ok=True, parents=True)
        shutil.copy2(src, dst)
        assert sha(dst.read_bytes()) == expected
    restored = restore_backup(RELEASE / "SafeTrace-KZ-v4-demo-data.zip", DEST / "data")
    assert snapshot(ROOT / "data") == snapshot(DEST / "data")
    result = {"ok": True, "candidate_sha256": sha(archive.read_bytes()), "source_files_verified": len(manifest["files"]), "destination": str(DEST), "model_files_copied_and_verified": len(model_manifest["files"]), "restore": restored["database"], "all_originals_and_rows_equal": True, "scope": "Different directory on same Windows PC, ASCII path with space. Existing Python environment will be reused by a junction; not a fresh install or another physical machine."}
    (OUT / "transfer-stage.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


def exercise():
    from scripts.measure_runtime_v4 import pixels

    with httpx.Client(base_url="http://127.0.0.1:8770", trust_env=False, timeout=15) as client:
        health = client.get("/api/health").raise_for_status().json()
        assert health["app_version"] == "2.2.1" and health["offline"]
        for cid in ("e4e5424a4abc4b129c7ad5fc8636345f", "4016da2c3ed0481fb5c7750b717bfb10"):
            a = client.get("/api/cases/" + cid).raise_for_status().json()
            b = httpx.get("http://127.0.0.1:8765/api/cases/" + cid, trust_env=False).raise_for_status().json()
            # This is request-time graph assembly metadata, not a persisted observation.
            a["graph"].pop("generated_at", None)
            b["graph"].pop("generated_at", None)
            assert a == b
        raw = pixels(887)
        image_id = client.post("/api/uploads", files={"file": ("fresh.png", raw, "image/png")}).raise_for_status().json()["image_id"]
        started = time.perf_counter()
        cid = client.post("/api/cases", json={"title": "Перенос v4 · новый OCR", "mode": "synthetic", "materials": [{"image_id": image_id}]}).raise_for_status().json()["id"]
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            doc = client.get("/api/cases/" + cid).raise_for_status().json()
            if doc["status"] not in ("pending", "running"):
                break
            time.sleep(0.15)
        assert doc["status"] == "completed" and doc["score"]["value"] == 80 and doc["sufficient_data"]
        assert not doc["materials"][0]["ocr"]["cache_hit"] and len(doc["trace"]["observations"]) == 3
        elapsed = (time.perf_counter() - started) * 1000
        client.post("/api/cases/" + cid + "/decision", json={"decision": "confirmed", "comment": "Техническая проверка переноса; синтетические данные"}).raise_for_status()
        payload = client.get("/api/cases/" + cid + "/export").raise_for_status().content
        with zipfile.ZipFile(io.BytesIO(payload)) as zipped:
            manifest = json.loads(zipped.read("manifest.json"))
            for item in manifest["files"]:
                content = zipped.read(item["path"])
                assert sha(content) == item["sha256"] and len(content) == item["bytes"]
            assert zipped.read("originals/01.png") == raw
            assert len(json.loads(zipped.read("case.json"))["decisions"]) == 1
        (OUT / "transfer-new-case.zip").write_bytes(payload)
        (OUT / "transfer-before-restart.json").write_text(json.dumps(snapshot(DEST / "data"), indent=2), encoding="utf-8")
        result = {"ok": True, "case_id": cid, "health": health, "score": 80, "fresh_real_ocr": True, "cache_hit": False, "end_to_end_ms": elapsed, "observations": 3, "restored_demo_cases_equal": True, "export_original_and_manifest_verified": True, "zip_sha256": sha(payload)}
        (OUT / "transfer-exercise.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))


def restart():
    before = json.loads((OUT / "transfer-before-restart.json").read_text(encoding="utf-8"))
    assert before == snapshot(DEST / "data")
    exercise_result = json.loads((OUT / "transfer-exercise.json").read_text(encoding="utf-8"))
    doc = httpx.get("http://127.0.0.1:8770/api/cases/" + exercise_result["case_id"], trust_env=False).raise_for_status().json()
    assert len(doc["decisions"]) == 1 and doc["score"]["value"] == 80
    result = {"ok": True, "all_rows_and_originals_unchanged": True, "tables": before["tables"], "decision_and_result_reopened": True, "scope": "Restart of actual extracted candidate on same machine"}
    (OUT / "transfer-restart.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["stage", "exercise", "restart"])
    {"stage": stage, "exercise": exercise, "restart": restart}[parser.parse_args().phase]()
