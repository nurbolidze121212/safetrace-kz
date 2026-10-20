"""Real pixels only. No fixture text is passed to the recognizer."""

import json
import os
import time
from pathlib import Path

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["PADDLE_PDX_MODEL_SOURCE"] = "BOS"
os.environ["FLAGS_enable_pir_api"] = "0"
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
out = root / "reports" / "technical"
out.mkdir(parents=True, exist_ok=True)
font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 32)
lines = [
    "SafeTrace KZ — синтетический материал DEMO",
    "Әріптер: ә ғ қ ң ө ұ ү һ і",
    "Қауіпсіздік: күмәнді сілтемеге өтпеңіз.",
    "Бонус 200%, промокод QALA7. Переходи по ссылке.",
    "https://go.safetrace.test/r/q7",
]
im = Image.new("RGB", (1100, 350), "white")
draw = ImageDraw.Draw(im)
for i, line in enumerate(lines):
    draw.text((30, 24 + i * 59), line, fill="#142434", font=font)
im.save(out / "probe.png")
from paddleocr import PaddleOCR

start = time.perf_counter()
ocr = PaddleOCR(
    text_detection_model_name="PP-OCRv5_mobile_det",
    text_recognition_model_name="cyrillic_PP-OCRv5_mobile_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    device="cpu",
    enable_mkldnn=False,
    cpu_threads=4,
)
for result in ocr.predict(str(out / "probe.png")):
    result.save_to_json(str(out))
    print(json.dumps(result.json, ensure_ascii=False))
print(f"elapsed_seconds={time.perf_counter() - start:.3f}")
