"""Compare actual pixel recognizers on development crops; never used by product inference."""

# ruff: noqa: E402 -- configure Paddle and isolated storage before model imports

import argparse
import hashlib
import json
import os
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "tmp/v4-ocr-dev-data")
os.environ["SAFETRACE_OFFLINE"] = "1"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["FLAGS_enable_pir_api"] = "0"

import numpy as np
from paddleocr import TextRecognition
from PIL import Image, ImageDraw, ImageFont

from backend import storage
from backend.links import extract_urls
from backend.ocr import recognize

OUT = ROOT / "datasets/ocr-dev-v4"
INLINE = [
    (
        "ru",
        "Новая группа открыта, заходи по ссылке и получай бонус.",
        "https://n64eab2c9d8.test/item/e29fc46?ref=R3E1B07",
        29,
    ),
    ("kk", "Кешкі ұсыныс бар: тіркеліп, сыйлық алыңыз.", "https://n82df64ae30.test/entry/ae3e681", 29),
    (
        "mixed",
        "Достар, переходи в новый раздел, бонус ждёт.",
        "https://n36e1d8f4b9.test/item/fc817e2?ref=Z74E3AD",
        20,
    ),
    ("ru", "Осторожно, не переходите: рекламная рассылка.", "https://n5e9b3c7a61.test/entry/39ec28f", 26),
    (
        "kk",
        "Біздің мақалада мысал бар, бұл тек ескерту.",
        "https://n0e4d2c6a81.test/item/d47e12b?ref=C91B6E2",
        24,
    ),
    ("mixed", "Кешке қосыл, подарок участнику внутри.", "https://n7c15e8d2a4.test/entry/e1b6c93", 29),
    ("ru", "Нажимай на приглашение, активируй код.", "https://n92de84ac10.test/item/7e430bc?ref=F1D3E87", 29),
    ("kk", "Құпия клубқа қосыл, мәлімет жеке бетте.", "https://n1e730f4ab6.test/entry/5ce29d8", 20),
    (
        "mixed",
        "Қауіпсіздік: не регистрируйтесь по этому адресу.",
        "https://n6a8e14bd72.test/item/a95ec61?ref=B87F0E1",
        29,
    ),
    ("ru", "Пример адреса из статьи о мошеннических письмах.", "https://n8e274bc6d0.test/entry/7a1ee94", 22),
    ("kk", "Сілтемеге өтіңіз де жаңа бонус алыңыз.", "https://n24c9de81b7.test/item/63eb4a2?ref=D29E1B4", 27),
    (
        "mixed",
        "Бұл — пример международного пути, сохраните адрес.",
        "https://n48a2d37ce1.test/мақала?ref=N7e32",
        26,
    ),
]


def main(label, embedded):
    storage.init()
    prior = json.loads((ROOT / "reports/acceptance-v4/ocr-dev-initial.json").read_text(encoding="utf-8"))
    rows = prior["rows"][:]
    for i, (lang, caption, url, size) in enumerate(INLINE):
        name = hashlib.sha256(f"{'embedded' if embedded else 'inline'}-ocr-v4-{i}".encode()).hexdigest()[:20]
        file = name + ".png"
        path = OUT / file
        text = "DEMO. " + caption + " " + url
        lines = (
            [caption, "Приглашение: " + url]
            if embedded
            else textwrap.wrap(text, width=62 if size >= 26 else 80, break_long_words=False)
        )
        if not path.exists():
            im = Image.new("RGB", (1180, 95 + len(lines) * 48), "#fdfbf5")
            draw = ImageDraw.Draw(im)
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
            for j, line in enumerate(lines):
                draw.text((34, 28 + j * 48), line, fill="#29394b", font=font)
            im.save(path)
        start = time.perf_counter()
        result = recognize(path, use_cache=False)
        urls = extract_urls(result["text"])
        rows.append(
            {
                "id": name,
                "image": file,
                "url": url,
                "language": lang,
                "font_size": size,
                "style": "inline",
                "caption": caption,
                "base": {
                    **result,
                    "urls": urls,
                    "exact_url": url in urls,
                    "seconds": time.perf_counter() - start,
                },
            }
        )
    model = TextRecognition(
        model_name="en_PP-OCRv5_mobile_rec",
        model_dir=str(ROOT / "tmp/v4-ocr-model/en_PP-OCRv5_mobile_rec"),
        device="cpu",
        enable_mkldnn=False,
        cpu_threads=4,
    )
    for row in rows:
        original = Image.open(OUT / row["image"]).convert("RGB")
        readings = []
        for line in row["base"]["raw_lines"]:
            if "http" not in line["text"].lower():
                continue
            xs, ys = zip(*line["polygon"])
            crop = original.crop(
                (
                    max(0, min(xs) - 3),
                    max(0, min(ys) - 3),
                    min(original.width, max(xs) + 3),
                    min(original.height, max(ys) + 3),
                )
            )
            crop = crop.rotate(row["base"]["rotation_ccw"], expand=True)
            item = {"original_line": line, "attempts": []}
            for scale in (1, 2):
                pixels = np.array(
                    crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
                )
                start = time.perf_counter()
                raw = list(model.predict(pixels))[0].json
                result = raw.get("res", raw)
                urls = extract_urls(result["rec_text"])
                item["attempts"].append(
                    {
                        "text": result["rec_text"],
                        "confidence": float(result["rec_score"]),
                        "urls": urls,
                        "exact_url": row["url"] in urls,
                        "seconds": time.perf_counter() - start,
                    }
                )
            readings.append(item)
        row["english"] = readings
        print(
            json.dumps(
                {
                    "id": row["id"],
                    "base": row["base"]["exact_url"],
                    "english": [
                        [a["text"], round(a["confidence"], 4), a["exact_url"]]
                        for r in readings
                        for a in r["attempts"]
                    ],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    target = ROOT / "reports/acceptance-v4" / f"ocr-dev-{label}.json"
    if target.exists():
        raise RuntimeError("Report already exists")
    target.write_text(
        json.dumps(
            {"provenance": "author_synthetic_development", "rows": rows}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--embedded", action="store_true")
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum():
        raise SystemExit("Unsafe label")
    main(args.label, args.embedded)
