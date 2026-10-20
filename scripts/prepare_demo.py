"""Generate explicitly labeled replay files by running the real pipeline."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "data" / "demo-preparation")
os.environ["SAFETRACE_OFFLINE"] = "1"
from backend import pipeline, storage
from backend.app import DEMOS
from backend.schemas import CaseInput, MaterialInput

storage.init()
out = ROOT / "fixtures" / "replays"
out.mkdir(parents=True, exist_ok=True)
for item in DEMOS:
    doc = pipeline.new_case(
        CaseInput(title=item["title"], mode="synthetic", materials=[MaterialInput(**item["material"])])
    )
    pipeline.analyze(doc)
    (out / f"{item['id']}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(item["id"], doc["status"], doc["score"]["value"])
