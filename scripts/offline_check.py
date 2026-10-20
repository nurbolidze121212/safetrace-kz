"""Hermetic process check: outgoing socket operations are denied, real OCR still runs."""

import argparse
import json
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--report", default="reports/technical/offline-check.json")
args = parser.parse_args()
sys.path.insert(0, str(ROOT))
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "data" / "offline-check")
os.environ["SAFETRACE_OFFLINE"] = "1"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
attempts = []


def denied(*args, **kwargs):
    attempts.append("outgoing socket operation blocked")
    raise OSError("Network disabled by offline acceptance test")


socket.create_connection = denied
socket.getaddrinfo = denied
socket.socket.connect = denied

from backend import pipeline, storage
from backend.config import DATA
from backend.exports import package
from backend.schemas import CaseInput, MaterialInput

storage.init()
image_id = "1234567890abcdef1234567890abcdef.png"
(DATA / "originals" / image_id).write_bytes((ROOT / "reports/technical/browser-input.png").read_bytes())
doc = pipeline.new_case(
    CaseInput(
        title="Offline acceptance",
        mode="synthetic",
        materials=[MaterialInput(text="Переходи, бонус! Ссылка на изображении.", image_id=image_id)],
    )
)
pipeline.analyze(doc, use_ocr_cache=False)
assert doc["status"] == "completed"
assert "https://go.safetrace.test/r/q7" in doc["materials"][0]["ocr"]["text"]
assert doc["score"]["value"] >= 65
storage.save(doc)
storage.add_decision(doc["id"], "confirmed", "Offline verification")
archive = package(doc)
assert archive[:2] == b"PK"
report = {
    "status": "passed",
    "network_guard": "socket.create_connection/getaddrinfo/socket.connect denied",
    "blocked_attempts": len(attempts),
    "case_status": doc["status"],
    "score": doc["score"]["value"],
    "ocr_lines": len(doc["materials"][0]["ocr"]["lines"]),
    "export_bytes": len(archive),
    "observations": len(doc["trace"]["observations"]),
    "at": storage.now(),
}
report_path = ROOT / args.report
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
