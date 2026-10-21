"""Pixel-based alternatives for uncertain OCR addresses. Suggestions never initiate requests."""

import re

from PIL import Image, ImageOps

from .config import MODEL_DIR
from .links import extract_urls

_recognizer = None
MODEL = "en_PP-OCRv5_mobile_rec"
MAX_REVIEW_LINES = 3


def _english():
    global _recognizer
    if _recognizer is None:
        from paddleocr import TextRecognition

        local = MODEL_DIR / MODEL
        if not local.is_dir():
            raise RuntimeError("Optional URL recognizer is not installed")
        _recognizer = TextRecognition(
            model_name=MODEL, model_dir=str(local), device="cpu", enable_mkldnn=False, cpu_threads=4
        )
    return _recognizer


def _read_crop(path, line, rotation):
    import numpy as np

    with Image.open(path) as im:
        original = ImageOps.exif_transpose(im).convert("RGB")
    xs, ys = zip(*line["polygon"])
    crop = original.crop(
        (
            max(0, min(xs) - 3),
            max(0, min(ys) - 3),
            min(original.width, max(xs) + 3),
            min(original.height, max(ys) + 3),
        )
    )
    crop = crop.rotate(rotation, expand=True)
    attempts = []
    for scale in (1, 2):
        pixels = np.array(crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS))
        raw = list(_english().predict(pixels))[0].json
        item = raw.get("res", raw)
        attempts.append(
            {
                "text": item["rec_text"],
                "confidence": float(item["rec_score"]),
                "urls": extract_urls(item["rec_text"]),
                "scale": scale,
            }
        )
    return attempts


def review_addresses(path, result):
    """Retain primary readings, flag uncertainty, add bounded alternatives with provenance."""
    reviews, used = [], 0
    lines = result["lines"]
    for index, line in enumerate(lines):
        urls = extract_urls(line["text"])
        if not urls:
            continue
        attempts = None
        for url in urls:
            reasons = []
            if any(ord(c) > 127 for c in url):
                reasons.append(
                    "В адресе есть нелатинские символы: возможны как ошибка OCR, так и настоящий международный путь."
                )
            if line["confidence"] < 0.85 or any("Низкая уверенность" in w for w in line.get("warnings", [])):
                reasons.append("Низкая уверенность распознавания строки с адресом.")
            if any("перекрываются" in w for w in line.get("warnings", [])):
                reasons.append("Перекрывающиеся фрагменты могут повторять символы адреса.")
            continuation = None
            if index + 1 < len(lines):
                following = lines[index + 1]["text"].strip()
                if re.fullmatch(r'[/?&#][^\s<>"«»]+', following):
                    continuation = following
                    reasons.append(
                        "Следующая строка похожа на продолжение адреса; неполный префикс не открывался."
                    )
            review = {
                "raw_url": url,
                "line_indices": [index],
                "needs_review": bool(reasons),
                "reasons": reasons,
                "suggestions": [],
                "method": "primary_ocr",
                "auto_follow": not reasons,
            }
            if continuation:
                review["line_indices"].append(index + 1)
                review["suggestions"].append(
                    {
                        "url": url + continuation,
                        "method": "adjacent_ocr_lines",
                        "confidence": min(line["confidence"], lines[index + 1]["confidence"]),
                        "agreement": False,
                    }
                )
            if reasons and not continuation:
                if attempts is None and used < MAX_REVIEW_LINES:
                    used += 1
                    try:
                        attempts = _read_crop(path, line, result.get("rotation_ccw", 0))
                    except Exception:
                        attempts = []
                        review["reasons"].append(
                            "Дополнительное чтение недоступно; сверяйте адрес с оригиналом."
                        )
                if attempts:
                    review["secondary_attempts"] = attempts
                    for candidate in dict.fromkeys(u for a in attempts for u in a["urls"]):
                        if candidate == url:
                            continue
                        readings = [a for a in attempts if candidate in a["urls"]]
                        review["suggestions"].append(
                            {
                                "url": candidate,
                                "method": MODEL,
                                "confidence": min(a["confidence"] for a in readings),
                                "agreement": len(readings) == 2,
                            }
                        )
                elif used >= MAX_REVIEW_LINES:
                    review["reasons"].append(
                        "Дополнительное чтение ограничено тремя строками на изображение."
                    )
            reviews.append(review)
    return reviews
