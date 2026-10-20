"""OCR robustness check with independently rendered pixels and separate reference text."""

import json
import os
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "data" / "ocr-checks")
os.environ["SAFETRACE_OFFLINE"] = "1"
from PIL import Image, ImageDraw, ImageFont

from backend import storage
from backend.ocr import recognize

storage.init()
out = ROOT / "reports" / "technical"
reference = [
    "Ә Ғ Қ Ң Ө Ұ Ү Һ І — ә ғ қ ң ө ұ ү һ і",
    "Қауіпсіздік: күмәнді сілтемеге өтпеңіз.",
    "Бонус 200%, promo QALA7. DEMO",
    "https://go.safetrace.test/r/q7",
]
results = []
for name, size, quality, rotation in (
    ("normal", 32, 95, 0),
    ("small-compressed", 17, 45, 0),
    ("tilted", 29, 70, 7),
    ("quarter-turn", 29, 85, 90),
):
    image = Image.new("RGB", (1000, 290), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
    for i, line in enumerate(reference):
        draw.text((25, 20 + i * 63), line, font=font, fill="#172324")
    image = image.rotate(rotation, expand=True, fillcolor="white")
    path = out / f"ocr-{name}.jpg"
    image.save(path, quality=quality)
    started = time.perf_counter()
    output = recognize(path, use_cache=False)
    results.append(
        {
            "variant": name,
            "font_px": size,
            "jpeg_quality": quality,
            "rotation": rotation,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "reference": "\n".join(reference),
            "similarity": SequenceMatcher(None, "\n".join(reference), output["text"]).ratio(),
            "output": output,
        }
    )
(out / "ocr-robustness.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
for result in results:
    print(result["variant"], round(result["similarity"], 3), result["output"]["text"])
