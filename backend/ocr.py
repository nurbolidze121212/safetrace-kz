import os
import re
import threading
from importlib.metadata import version

from PIL import Image, ImageOps

from .config import MODEL_DIR, OCR_VERSION
from .storage import cached, digest, put_cache

_lock = threading.Lock()
_engine = None


def engine():
    global _engine
    if _engine is None:
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        os.environ["FLAGS_enable_pir_api"] = "0"
        from paddleocr import PaddleOCR

        names = {"text_detection": "PP-OCRv5_mobile_det", "text_recognition": "cyrillic_PP-OCRv5_mobile_rec"}
        args = {}
        for role, name in names.items():
            local = MODEL_DIR / name
            if not local.exists():
                raise RuntimeError("Модель OCR не установлена. Выполните scripts/setup.ps1.")
            args[role + "_model_name"] = name
            args[role + "_model_dir"] = str(local)
        _engine = PaddleOCR(
            **args,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
            enable_mkldnn=False,
            cpu_threads=4,
        )
    return _engine


def _read_lines(pixels):
    raw = list(engine().predict(pixels))[0].json
    data = raw.get("res", raw)
    return [
        {"text": text, "confidence": float(conf), "polygon": polygon}
        for text, conf, polygon in zip(data["rec_texts"], data["rec_scores"], data["rec_polys"])
    ]


def _quality(lines):
    counts = [sum(c.isalnum() for c in line["text"]) for line in lines]
    count = sum(counts)
    mean = sum(n * line["confidence"] for n, line in zip(counts, lines)) / max(1, count)
    score = sum(n * line["confidence"] ** 3 for n, line in zip(counts, lines))
    vertical = sum(
        n
        for n, line in zip(counts, lines)
        if max(p[1] for p in line["polygon"]) - min(p[1] for p in line["polygon"])
        > 1.5 * (max(p[0] for p in line["polygon"]) - min(p[0] for p in line["polygon"]))
    )
    vertical_fraction = vertical / max(1, count)
    return {
        "characters": count,
        "mean_confidence": mean,
        "score": score * (1 - 0.9 * vertical_fraction),
        "vertical_fraction": vertical_fraction,
    }


def _original_polygon(polygon, angle, width, height):
    """Inverse np.rot90 mapping, in pixels of the EXIF-oriented original."""
    result = []
    for x, y in polygon:
        if angle == 90:
            x, y = width - 1 - y, x
        elif angle == 180:
            x, y = width - 1 - x, height - 1 - y
        elif angle == 270:
            x, y = y, height - 1 - x
        result.append([max(0, min(width - 1, float(x))), max(0, min(height - 1, float(y)))])
    return result


def _group_lines(lines):
    """Join only adjacent boxes on the same visual line; retain all original segments."""
    groups = []
    for index, line in sorted(
        enumerate(lines),
        key=lambda pair: (min(p[1] for p in pair[1]["polygon"]), min(p[0] for p in pair[1]["polygon"])),
    ):
        if not line["text"].strip():
            continue
        xs, ys = zip(*line["polygon"])
        box = (min(xs), min(ys), max(xs), max(ys))
        center, height = (box[1] + box[3]) / 2, max(1, box[3] - box[1])
        target = None
        for group in groups:
            gx1, gy1, gx2, gy2 = group["box"]
            if abs(center - (gy1 + gy2) / 2) <= 0.45 * min(height, gy2 - gy1):
                target = group
                break
        if target is None:
            target = {"box": box, "indices": []}
            groups.append(target)
        target["indices"].append(index)
        a, b, c, d = target["box"]
        target["box"] = (min(a, box[0]), min(b, box[1]), max(c, box[2]), max(d, box[3]))
    adjacent_groups = []
    for group in groups:
        indices = sorted(group["indices"], key=lambda i: min(p[0] for p in lines[i]["polygon"]))
        chunk = []
        right = None
        for index in indices:
            polygon = lines[index]["polygon"]
            left = min(p[0] for p in polygon)
            height = max(1, max(p[1] for p in polygon) - min(p[1] for p in polygon))
            if right is not None and left - right > 3 * height:
                adjacent_groups.append(chunk)
                chunk = []
            chunk.append(index)
            right = max(right or 0, max(p[0] for p in polygon))
        adjacent_groups.append(chunk)
    output = []
    for indices in adjacent_groups:
        segments = [lines[i] for i in indices]
        lengths = [max(1, len(s["text"].strip())) for s in segments]
        points = [point for segment in segments for point in segment["polygon"]]
        x1, y1 = min(p[0] for p in points), min(p[1] for p in points)
        x2, y2 = max(p[0] for p in points), max(p[1] for p in points)
        overlap = any(
            max(p[0] for p in left["polygon"]) - min(p[0] for p in right["polygon"])
            > 0.12
            * min(
                max(p[0] for p in left["polygon"]) - min(p[0] for p in left["polygon"]),
                max(p[0] for p in right["polygon"]) - min(p[0] for p in right["polygon"]),
            )
            for left, right in zip(segments, segments[1:])
        )
        output.append(
            {
                "text": " ".join(s["text"].strip() for s in segments),
                "confidence": sum(n * s["confidence"] for n, s in zip(lengths, segments)) / sum(lengths),
                "minimum_segment_confidence": min(s["confidence"] for s in segments),
                "polygon": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                if len(segments) > 1
                else segments[0]["polygon"],
                "segment_indices": indices,
                "overlapping_segments": overlap,
            }
        )
    return output


def recognize(path, use_cache=True):
    key = digest(path.read_bytes() + OCR_VERSION.encode())
    if use_cache and (result := cached("ocr|" + key)):
        return {**result, "cache_hit": True}
    import numpy as np

    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        width, height = image.size
        pixels = np.array(image)
    with _lock:
        raw_lines = _read_lines(pixels)
        quality = _quality(raw_lines)
        attempts = [{"angle_ccw": 0, **quality}]
        angle = 0
        if (
            quality["characters"] < 6
            or quality["mean_confidence"] < 0.85
            or quality["vertical_fraction"] > 0.5
        ):
            candidates = [(0, raw_lines, quality)]
            for rotation in (90, 180, 270):
                candidate = _read_lines(np.ascontiguousarray(np.rot90(pixels, rotation // 90)))
                candidate_quality = _quality(candidate)
                attempts.append({"angle_ccw": rotation, **candidate_quality})
                candidates.append((rotation, candidate, candidate_quality))
            best_angle, best_lines, best_quality = max(
                candidates, key=lambda candidate: candidate[2]["score"]
            )
            if best_quality["score"] > quality["score"] * 1.15 and (
                best_quality["mean_confidence"] >= quality["mean_confidence"] + 0.05
                or quality["characters"] < 6
                or quality["vertical_fraction"] > 0.5
            ):
                angle, raw_lines = best_angle, best_lines
    lines = []
    for line in _group_lines(raw_lines):
        text, conf = line["text"], line["confidence"]
        mixed_tokens = [
            token
            for token in re.findall(r"\S+", text)
            if re.search("[A-Za-z]", token) and re.search("[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]", token)
        ]
        lines.append(
            {
                "text": text,
                "confidence": float(conf),
                "polygon": _original_polygon(line["polygon"], angle, width, height),
                "segment_indices": line["segment_indices"],
                "uncertain": line["minimum_segment_confidence"] < 0.85
                or bool(mixed_tokens)
                or line["overlapping_segments"],
                "warnings": (
                    ["Низкая уверенность одного или нескольких фрагментов."]
                    if line["minimum_segment_confidence"] < 0.85
                    else []
                )
                + ["Смешение алфавитов в токене: " + token for token in mixed_tokens]
                + (
                    ["Фрагменты распознавания перекрываются: проверьте возможный повтор символов."]
                    if line["overlapping_segments"]
                    else []
                ),
            }
        )
    output = {
        "text": "\n".join(line["text"] for line in lines),
        "lines": lines,
        "raw_text": "\n".join(line["text"] for line in raw_lines),
        "raw_lines": [
            {**line, "polygon": _original_polygon(line["polygon"], angle, width, height)}
            for line in raw_lines
        ],
        "rotation_ccw": angle,
        "orientation_attempts": attempts,
        "width": width,
        "height": height,
        "model": OCR_VERSION,
        "library": version("paddleocr"),
        "cache_hit": False,
        "coordinate_space": "EXIF-oriented image pixels",
        "limitations": "OCR может ошибаться в символах. Соседние фрагменты объединены пробелами; raw_lines сохраняет исходный вывод. URL и коды не исправлялись. Ориентация выбирается эвристически.",
    }
    put_cache("ocr|" + key, output)
    return output
