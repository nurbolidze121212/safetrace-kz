"""Verify the actual browser-downloaded archive and recorded restart responses."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/acceptance-v2"
before = json.loads((REPORT / "before-restart.json").read_text(encoding="utf-8-sig"))
after = json.loads((REPORT / "after-restart.json").read_text(encoding="utf-8-sig"))
changes = []


def differences(left, right, path=""):
    if isinstance(left, dict) and isinstance(right, dict):
        for key in left.keys() | right.keys():
            differences(left.get(key), right.get(key), path + "/" + key)
    elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        for index, (a, b) in enumerate(zip(left, right)):
            differences(a, b, path + "/" + str(index))
    elif left != right:
        changes.append({"path": path, "before": left, "after": right})


differences(before, after)
assert all(change["path"] == "/graph/generated_at" for change in changes), changes
with zipfile.ZipFile(REPORT / "browser-export.zip") as archive:
    manifest = json.loads(archive.read("manifest.json"))
    checks = []
    for entry in manifest["files"]:
        data = archive.read(entry["path"])
        assert len(data) == entry["bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        checks.append({"path": entry["path"], "bytes": len(data), "sha256": entry["sha256"], "ok": True})
    case = json.loads(archive.read("case.json"))
    assert case["id"] == before["id"]
    assert len(case["materials"]) == 2
    assert case["materials"][0]["qr"]["codes"][0]["text"] == "https://go.safetrace.test/r/q7"
    assert case["materials"][0]["ocr"]["lines"]
    assert case["decisions"][-1]["decision"] == "confirmed"
    assert case["decisions"][-1]["comment"] == before["decisions"][-1]["comment"]
    assert len(case["trace"]["observations"]) == 5
    assert b"<script" not in archive.read("report.html").lower()
result = {
    "case_id": case["id"],
    "restart_persisted_content_identical": True,
    "request_time_only_changes": changes,
    "materials": len(case["materials"]),
    "score": case["score"]["value"],
    "decision": case["decisions"][-1]["decision"],
    "versions": case["versions"],
    "files": checks,
    "archive_sha256": hashlib.sha256((REPORT / "browser-export.zip").read_bytes()).hexdigest(),
}
(REPORT / "export-restart-check.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(result, ensure_ascii=False))
