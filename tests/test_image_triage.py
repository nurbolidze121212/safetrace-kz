from PIL import Image, ImageDraw

from backend.image_triage import inspect


def test_only_uniform_frame_is_skipped(tmp_path):
    path = tmp_path / "frame.png"
    image = Image.new("RGB", (640, 480), "white")
    image.save(path)
    assert inspect(path)["requires_ocr"] is False
    ImageDraw.Draw(image).text((30, 30), "Casino bonus 200%", fill="black")
    image.save(path)
    assert inspect(path)["requires_ocr"] is True
