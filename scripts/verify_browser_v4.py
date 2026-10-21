"""Verify bytes actually downloaded by the v4 browser acceptance session."""

import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = "aa7d719d0bb74487b852e67969ae077b"
SOURCE = Path.home() / "Downloads" / ("safetrace-" + CASE[:8] + ".zip")
OUT = ROOT / "reports/acceptance-v4"


def main():
    target = OUT / "browser-acceptance.json"
    if target.exists():
        raise RuntimeError("Browser evidence already recorded")
    with zipfile.ZipFile(SOURCE) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for entry in manifest["files"]:
            data = archive.read(entry["path"])
            assert len(data) == entry["bytes"]
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        doc = json.loads(archive.read("case.json"))
        html = archive.read("report.html").decode("utf-8")
        ids = set(re.findall(r"""id=["']([^"']+)["']""", html))
        anchors = re.findall(r"""href=["']#([^"']+)["']""", html)
        assert set(anchors) <= ids, set(anchors) - ids
        assert doc["id"] == CASE and doc["analysis_assisted"]
        assert len(doc["materials"]) == 2 and len(doc["decisions"]) == 1
        assert doc["score"]["value"] == 90 and doc["sufficient_data"]
        assert not doc["history"][0]["analysis_assisted"]
        assert not doc["history"][0]["sufficient_data"]
        assert doc["history"][0]["score"]["value"] == 0
        first = doc["materials"][0]
        assert first["ocr"]["raw_text"] == doc["history"][0]["materials"][0]["ocr"]["raw_text"]
        assert len(first["url_corrections"]) == 1
        assert archive.read("originals/01.png") == (OUT / "browser-new-material.png").read_bytes()
        assert "Первичное чтение" in html and "ручным уточнением" in html
    saved = OUT / "browser-new-case.zip"
    shutil.copyfile(SOURCE, saved)
    target.write_text(
        json.dumps(
            {
                "case_id": CASE,
                "download": str(SOURCE),
                "copy": saved.name,
                "sha256": hashlib.sha256(saved.read_bytes()).hexdigest(),
                "files_verified": len(manifest["files"]),
                "internal_anchors_verified": len(anchors),
                "analysis_id": doc["analysis_id"],
                "score": 90,
                "materials": 2,
                "decisions": 1,
                "history_count": len(doc["history"]),
                "automatic_initial_score": 0,
                "assisted_result": True,
                "browser_observations": [
                    "Fresh image uploaded via actual file chooser; OCR progressed before partial result",
                    "Uncertain split address not followed; original pixels and OCR boxes opened",
                    "Candidate explicitly selected and commented; submitted with keyboard Tab/Return",
                    "Second publication added in UI, score changed from 80 to 90",
                    "Decision saved, persisted after reload; actual ZIP downloaded by export button",
                    "390x844 viewport: document and body scroll width exactly 390; readable decision/history",
                    "1366x768 graph: HTTP edge opens saved synthetic transport observation",
                ],
                "limits": "Agent-operated functional acceptance, not independent human usability or label evaluation. Process restart and remaining error/cancel/retry checks recorded separately.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
