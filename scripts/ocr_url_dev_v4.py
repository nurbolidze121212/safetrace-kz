"""Author-generated development pixels; labels are used only by this evaluator."""

# ruff: noqa: E402 -- environment and import root must precede backend imports

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "tmp/v4-ocr-dev-data")
os.environ["SAFETRACE_OFFLINE"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from backend import storage
from backend.links import extract_urls
from backend.ocr import _quality, _read_lines, recognize

OUT = ROOT / "datasets/ocr-dev-v4"

SAMPLES = [
    ("ru", "Переходи по приглашению, бонус внутри.", "https://m42e8f.example/item?ref=R7e31", 24, "plain"),
    ("kk", "Сілтемеге өтіңіз, сыйлық алыңыз.", "https://q8ed17.example/entry?ref=Q2k84", 22, "plain"),
    ("mixed", "Кешкі кездесу: заходи по ссылке.", "https://n73b5e.example/join?code=N8p20", 18, "jpeg"),
    ("ru", "Не переходите: это рекламный адрес.", "https://r2ce90.example/invite?tag=M4e93", 16, "jpeg"),
    ("kk", "Қауіпсіздік сабағына арналған мысал.", "https://v86e3a.example/read?ref=H6a12", 28, "dark"),
    (
        "mixed",
        "Ескерту: исследование рекламных переходов.",
        "https://a5e02c.example/post?ref=W9x65",
        20,
        "rotate",
    ),
    ("ru", "Забирай предложение в личном разделе.", "https://p4d9ef.example/item?ref=A3n78", 14, "plain"),
    ("kk", "Жаңа топқа қосыл, шарттары сілтемеде.", "https://s7e2c1.example/list?ref=K4u37", 32, "jpeg"),
    ("ru", "Расписание и правила встречи.", "https://j09ea4.example/calendar?ref=J5r62", 24, "blur"),
    (
        "mixed",
        "Казино туралы мақала. Не регистрируйся.",
        "https://b4e8d0.example/articles?ref=T7c28",
        18,
        "dark",
    ),
    (
        "ru",
        "Читайте разбор подозрительной публикации.",
        "https://f53ec7.example/notes?ref=V6m19",
        24,
        "wrapped",
    ),
    ("kk", "Бонус туралы толық мәлімет осы бетте.", "https://d98e26.example/item?ref=D8e53", 20, "rotate"),
    ("ru", "Пример международного адреса.", "https://z21ad6.example/памятка?ref=C2p47", 24, "plain"),
    (
        "mixed",
        "Ойын туралы ескерту. Материал для проверки.",
        "https://k3be78.example/info?ref=B5i41",
        16,
        "blur",
    ),
    ("kk", "Деректі тексеріңіз. Сілтеме төменде.", "https://c78e49.example/entry?ref=P1d96", 30, "dark"),
    (
        "ru",
        "Играй бесплатно, переходи к инструкции.",
        "https://w6a3e2.example/tutorial?ref=L9q34",
        26,
        "plain",
    ),
]


def generate():
    if (OUT / "labels.json").exists():
        return json.loads((OUT / "labels.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, (lang, caption, url, size, style) in enumerate(SAMPLES):
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
        width = max(760, int(font.getlength(url)) + 70)
        im = Image.new("RGB", (width, 210), "#182733" if style == "dark" else "white")
        draw = ImageDraw.Draw(im)
        fill = "#f3f6fa" if style == "dark" else "#142434"
        draw.text((25, 20), caption, font=font, fill=fill)
        parts = [url]
        if style == "wrapped":
            at = url.index("/notes")
            parts = [url[:at], url[at:]]
        for j, line in enumerate(parts):
            draw.text((25, 85 + j * (size + 12)), line, font=font, fill=fill)
        if style == "rotate":
            im = im.rotate(90, expand=True)
        if style == "blur":
            im = im.filter(ImageFilter.GaussianBlur(0.65))
        name = hashlib.sha256(f"ocrdev4-{i}".encode()).hexdigest()[:20]
        file = name + (".jpg" if style == "jpeg" else ".png")
        im.save(OUT / file, quality=48)
        rows.append(
            {
                "id": name,
                "image": file,
                "url": url,
                "language": lang,
                "font_size": size,
                "style": style,
                "caption": caption,
                "provenance": "author_synthetic_development",
            }
        )
    (OUT / "labels.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def run(label, compare_preprocessing):
    rows = generate()
    storage.init()
    output = []
    for row in rows:
        path = OUT / row["image"]
        start = time.perf_counter()
        result = recognize(path, use_cache=False)
        elapsed = time.perf_counter() - start
        observed = extract_urls(result["text"])
        item = {
            **row,
            "base": {
                "text": result["text"],
                "urls": observed,
                "exact_url": row["url"] in observed,
                "seconds": elapsed,
                "lines": result["lines"],
                "raw_lines": result["raw_lines"],
                "rotation_ccw": result["rotation_ccw"],
            },
        }
        if compare_preprocessing:
            pixels = np.array(Image.open(path).convert("RGB").rotate(result["rotation_ccw"], expand=True))
            im = Image.fromarray(pixels)
            start = time.perf_counter()
            scaled = _read_lines(np.array(im.resize((im.width * 2, im.height * 2), Image.Resampling.LANCZOS)))
            text = "\n".join(line["text"] for line in scaled)
            item["full_scale2"] = {
                "text": text,
                "quality": _quality(scaled),
                "exact_url": row["url"] in extract_urls(text),
                "seconds": time.perf_counter() - start,
            }
            crops = []
            for line in result["raw_lines"]:
                if "http" not in line["text"].lower():
                    continue
                # The crop is selected from OCR text, not expected coordinates or labels.
                xs, ys = zip(*line["polygon"])
                # original coordinate space, before the rotation used for recognition
                original = Image.open(path).convert("RGB")
                crop = original.crop(
                    (
                        max(0, min(xs) - 8),
                        max(0, min(ys) - 8),
                        min(original.width, max(xs) + 8),
                        min(original.height, max(ys) + 8),
                    )
                )
                crop = crop.rotate(result["rotation_ccw"], expand=True)
                crop = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS)
                candidates = _read_lines(np.array(crop))
                text = "\n".join(c["text"] for c in candidates)
                crops.append(
                    {
                        "text": text,
                        "quality": _quality(candidates),
                        "exact_url": row["url"] in extract_urls(text),
                    }
                )
            item["crops_scale2"] = crops
        output.append(item)
        print(
            json.dumps(
                {
                    "id": row["id"],
                    "base": item["base"]["exact_url"],
                    "scale": item.get("full_scale2", {}).get("exact_url"),
                    "urls": observed,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    target = ROOT / "reports/acceptance-v4" / f"ocr-dev-{label}.json"
    if target.exists():
        raise RuntimeError("Report already exists; use another label")
    target.write_text(
        json.dumps(
            {
                "label": label,
                "provenance": "author_synthetic_development",
                "rows": output,
                "base_exact": sum(r["base"]["exact_url"] for r in output),
                "n": len(output),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--compare-preprocessing", action="store_true")
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum():
        raise SystemExit("Unsafe report label")
    run(args.label, args.compare_preprocessing)
