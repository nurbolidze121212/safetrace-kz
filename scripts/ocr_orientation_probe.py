"""Development experiment: actual OCR outputs for right-angle rotations, no reference input to OCR."""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "data/ocr-v2-dev")
os.environ["SAFETRACE_OFFLINE"] = "1"

import numpy as np
from PIL import Image

from backend.ocr import engine

out = ROOT / "reports/core-v2-dev"
out.mkdir(parents=True, exist_ok=True)
base = Image.open(ROOT / "reports/redesign-v2/new-material.png").convert("RGB")
rows = []
model = engine()
for angle in (0, 90, 180, 270):
    image = base.rotate(angle, expand=True)
    image.save(out / f"orientation-{angle}.png")
    start = time.perf_counter()
    raw = list(model.predict(np.array(image)))[0].json
    data = raw.get("res", raw)
    row = {
        "rotation_ccw": angle,
        "texts": data["rec_texts"],
        "scores": data["rec_scores"],
        "polygons": data["rec_polys"],
        "elapsed_ms": (time.perf_counter() - start) * 1000,
    }
    rows.append(row)
    print(json.dumps({k: v for k, v in row.items() if k != "polygons"}, ensure_ascii=False), flush=True)
(out / "orientation-probe.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
