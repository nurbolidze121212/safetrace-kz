"""Local QR decoding. Payloads are data; URLs use the ordinary protected trace path."""

import time

import cv2
import numpy as np
from PIL import Image, ImageOps

from .config import QR_VERSION
from .links import LinkBlocked, validate_url
from .storage import cached, digest, put_cache


def decode(path, use_cache=True):
    key = "qr|" + digest(path.read_bytes() + (QR_VERSION + cv2.__version__).encode())
    if use_cache and (found := cached(key)):
        return {**found, "cache_hit": True}
    started = time.perf_counter()
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        width, height = image.size
        image.thumbnail((1600, 1600))
        sx, sy = width / image.width, height / image.height
        pixels = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    detector = cv2.QRCodeDetector()
    ok, values, points, _ = detector.detectAndDecodeMulti(pixels)
    if not ok:
        value, polygon, _ = detector.detectAndDecode(pixels)
        values, points = ([value], polygon) if value else ([], None)
    codes = []
    if points is not None:
        for value, polygon in list(zip(values, np.asarray(points).reshape(-1, 4, 2)))[:8]:
            if not value:
                continue
            valid, reason = False, None
            try:
                validate_url(value)
                valid = True
            except LinkBlocked as exc:
                reason = str(exc)
            codes.append(
                {
                    "text": value[:2048],
                    "truncated": len(value) > 2048,
                    "valid_url": valid,
                    "reason": reason,
                    "polygon": [[float(x) * sx, float(y) * sy] for x, y in polygon],
                }
            )
    output = {
        "codes": codes,
        "width": width,
        "height": height,
        "version": QR_VERSION,
        "decoder": "OpenCV " + cv2.__version__,
        "cache_hit": False,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "limitations": "До 8 QR-кодов, изображение до 1600 px по длинной стороне. Мелкие, поврежденные и составные QR могут не читаться. Декодирование не подтверждает безопасность адреса.",
    }
    put_cache(key, output)
    return output
