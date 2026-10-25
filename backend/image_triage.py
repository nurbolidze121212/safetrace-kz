"""Cheap pixel gate. Only nearly uniform frames can skip recognition; never call them safe."""

from PIL import Image, ImageOps, ImageStat

VERSION = "pixel-triage-1.0"


def inspect(path):
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("L")
        image.thumbnail((512, 512))
        std = ImageStat.Stat(image).stddev[0]
        entropy = image.entropy()
    uniform = std < .6 and entropy < .15
    return {"version": VERSION, "requires_ocr": not uniform, "stddev": round(std, 4),
            "entropy": round(entropy, 4), "decision": "uniform_frame" if uniform else "content_requires_ocr",
            "meaning": "Pixel gate only; skipped image has insufficient evidence, never a negative classification"}
