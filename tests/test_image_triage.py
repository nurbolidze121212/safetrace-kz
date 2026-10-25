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


def test_uniform_image_never_becomes_a_safe_result(monkeypatch):
    from backend import pipeline
    from backend.config import DATA
    from backend.schemas import CaseInput, MaterialInput

    image_id = "0" * 32 + ".png"
    Image.new("RGB", (200, 200), "white").save(DATA / "originals" / image_id)
    def unexpected(*args, **kwargs):
        raise AssertionError("Uniform image should not run OCR")
    monkeypatch.setattr(pipeline, "recognize", unexpected)
    doc = pipeline.new_case(CaseInput(title="Uniform input", mode="synthetic", materials=[MaterialInput(image_id=image_id)]))
    pipeline.analyze(doc)
    assert doc["status"] == "partial" and not doc["sufficient_data"]
    assert doc["materials"][0]["ocr_skipped"]
