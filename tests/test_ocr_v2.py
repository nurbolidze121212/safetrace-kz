import numpy as np
import pytest
from PIL import Image

from backend.config import ROOT
from backend.ocr import _group_lines, _original_polygon, recognize


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_inverse_rotation_corresponds_to_actual_pixels(angle):
    original = np.arange(5 * 7).reshape((5, 7))
    rotated = np.rot90(original, angle // 90)
    for y, x in np.ndindex(rotated.shape):
        ox, oy = _original_polygon([[x, y]], angle, 7, 5)[0]
        assert original[int(oy), int(ox)] == rotated[y, x]


def test_line_grouping_preserves_segments_and_keeps_columns_separate():
    lines = [
        {"text": "Қосыл", "confidence": 0.9, "polygon": [[0, 0], [80, 0], [80, 20], [0, 20]]},
        {"text": " бонус а", "confidence": 0.8, "polygon": [[85, 1], [160, 1], [160, 21], [85, 21]]},
        {"text": "ал!", "confidence": 0.95, "polygon": [[163, 1], [190, 1], [190, 21], [163, 21]]},
        {"text": "Другая колонка", "confidence": 0.9, "polygon": [[500, 0], [700, 0], [700, 20], [500, 20]]},
        {"text": "Новая строка", "confidence": 0.9, "polygon": [[0, 40], [200, 40], [200, 60], [0, 60]]},
    ]
    grouped = _group_lines(lines)
    assert [line["text"] for line in grouped] == ["Қосыл бонус а ал!", "Другая колонка", "Новая строка"]
    assert grouped[0]["segment_indices"] == [0, 1, 2]
    assert grouped[0]["minimum_segment_confidence"] == 0.8
    assert lines[1]["text"] == " бонус а"  # No silent duplicate/character correction.


def test_overlap_is_flagged_without_correcting_characters():
    lines = [
        {"text": "бонус а", "confidence": 0.99, "polygon": [[0, 0], [100, 0], [100, 20], [0, 20]]},
        {"text": "ал!", "confidence": 0.99, "polygon": [[75, 0], [180, 0], [180, 20], [75, 20]]},
    ]
    output = _group_lines(lines)[0]
    assert output["overlapping_segments"] and output["text"] == "бонус а ал!"


@pytest.mark.parametrize("angle", [0, 90, 180])
def test_actual_ocr_rotated_image_and_original_coordinates(tmp_path, angle):
    image = Image.open(ROOT / "reports/redesign-v2/new-material.png").rotate(angle, expand=True)
    path = tmp_path / "unlabelled.png"
    image.save(path)
    result = recognize(path, use_cache=False)
    assert "https://go.safetrace.test/r/q7" in result["text"]
    assert result["rotation_ccw"] == (360 - angle) % 360
    assert len(result["lines"]) == 4
    assert result["raw_lines"]
    assert result["width"] == image.width and result["height"] == image.height
    assert all(
        0 <= p[0] < image.width and 0 <= p[1] < image.height
        for line in result["lines"]
        for p in line["polygon"]
    )
