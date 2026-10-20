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
        result = list(engine().predict(pixels))[0]
    raw = result.json
    data = raw.get("res", raw)
    lines = []
    for text, conf, polygon in zip(data["rec_texts"], data["rec_scores"], data["rec_polys"]):
        mixed_tokens = [
            token
            for token in re.findall(r"\S+", text)
            if re.search("[A-Za-z]", token) and re.search("[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]", token)
        ]
        lines.append(
            {
                "text": text,
                "confidence": float(conf),
                "polygon": polygon,
                "uncertain": float(conf) < 0.85 or bool(mixed_tokens),
                "warnings": ["Смешение алфавитов в токене: " + token for token in mixed_tokens],
            }
        )
    output = {
        "text": "\n".join(line["text"] for line in lines),
        "lines": lines,
        "width": width,
        "height": height,
        "model": OCR_VERSION,
        "library": version("paddleocr"),
        "cache_hit": False,
        "coordinate_space": "EXIF-oriented image pixels",
        "limitations": "OCR может ошибаться в URL, промокодах и казахских буквах; строки не исправлялись.",
    }
    put_cache("ocr|" + key, output)
    return output
