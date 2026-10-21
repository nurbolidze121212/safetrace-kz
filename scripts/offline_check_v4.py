"""Real v4 OCR/export with all outgoing socket operations blocked in this process."""

import hashlib
import json
import os
import socket
import sys
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/acceptance-v4/offline-check.json"
DATA = ROOT / "tmp/v4-offline-release-data"
assert not OUT.exists() and not DATA.exists(), "Use a fresh isolated check; retain prior evidence"
os.environ["SAFETRACE_DATA_DIR"] = str(DATA)
os.environ["SAFETRACE_OFFLINE"] = "1"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
sys.path.insert(0, str(ROOT))
attempts = []


def denied(*args, **kwargs):
    attempts.append("outgoing socket operation blocked")
    raise OSError("Network denied by acceptance check")


socket.create_connection = denied
socket.getaddrinfo = denied
socket.socket.connect = denied

from backend import pipeline, storage  # noqa: E402 - network guard must precede imports
from backend.exports import package  # noqa: E402
from backend.schemas import CaseInput, MaterialInput  # noqa: E402
from scripts.measure_runtime_v4 import pixels  # noqa: E402

storage.init()
raw = pixels(99)
image_id = hashlib.sha256(raw).hexdigest()[:32] + ".png"
(DATA / "originals" / image_id).write_bytes(raw)
doc = pipeline.new_case(
    CaseInput(title="Offline v4", mode="synthetic", materials=[MaterialInput(image_id=image_id)])
)
pipeline.analyze(doc, use_ocr_cache=False)
assert doc["status"] == "completed" and doc["sufficient_data"] and doc["score"]["value"] == 80
assert len(doc["trace"]["observations"]) == 3
storage.save(doc)
storage.add_decision(doc["id"], "confirmed", "Техническая проверка offline; синтетический материал")
archive = package(doc)
with zipfile.ZipFile(BytesIO(archive)) as zipped:
    for item in json.loads(zipped.read("manifest.json"))["files"]:
        data = zipped.read(item["path"])
        assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"]
    assert zipped.read("originals/01.png") == raw

# A previously frozen image is used only for offline fallback acceptance,
# not as a new quality test or a source for model/rule changes.
inputs = [
    json.loads(line)
    for line in (ROOT / "datasets/synthetic-v4/inputs.jsonl").read_text(encoding="utf-8").splitlines()
]
review_input = next(row for row in inputs if row["id"] == "b1ccaf7c41a93f0c")
source = ROOT / "datasets/synthetic-v4" / review_input["materials"][0]["image"]
second_id = hashlib.sha256(source.read_bytes()).hexdigest()[:32] + ".png"
(DATA / "originals" / second_id).write_bytes(source.read_bytes())
second = pipeline.new_case(
    CaseInput(title="Offline URL review", mode="synthetic", materials=[MaterialInput(image_id=second_id)])
)
pipeline.analyze(second, use_ocr_cache=False)
readings = second["materials"][0]["ocr"]["url_readings"]
assert readings and not any(row["auto_follow"] for row in readings)
assert any(row["suggestions"] for row in readings)
result = {
    "at": storage.now(),
    "ok": True,
    "versions": doc["versions"],
    "network_guard": "socket.create_connection/getaddrinfo/socket.connect denied before model imports",
    "blocked_attempts": len(attempts),
    "real_ocr": True,
    "score": doc["score"]["value"],
    "observations": len(doc["trace"]["observations"]),
    "zip_manifest_and_original_verified": True,
    "zip_bytes": len(archive),
    "secondary_ocr_review_available_offline": True,
    "limits": "Process-level network denial on this machine after dependency/model installation; no claim of live websites, cloud or another physical PC.",
}
with OUT.open("x", encoding="utf-8") as file:
    json.dump(result, file, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False))
