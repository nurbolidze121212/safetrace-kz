"""A material can mention several targets; a call is not about every target."""

import pytest

from backend import pipeline
from backend.links import SyntheticTransport
from backend.schemas import CaseInput, MaterialInput

GUIDE = "https://branch-guide.test/doc"
GAME = "https://branch-game.test/start?ref=AB4"
HUB = "https://branch-hub.test/r/4"


def analyze(text, url=""):
    doc = pipeline.new_case(
        CaseInput(title="Ветви", mode="synthetic", materials=[MaterialInput(text=text, url=url)])
    )
    pipeline.analyze(
        doc,
        fetch=SyntheticTransport(
            {
                GUIDE: {"status": 200, "body": "<p>Календарь встреч.</p>"},
                GAME: {"status": 200, "body": "<p>Казино и слоты.</p>"},
                HUB: {"status": 302, "headers": {"location": GAME}},
            }
        ),
    )
    return doc


@pytest.mark.parametrize("reference", ["Дополнительный адрес", "Адрес казино из архива"])
def test_other_branch_cannot_supply_gambling_to_unrelated_call(reference):
    doc = analyze(f"Переходи сюда: {GUIDE}. {reference}: {GAME}")
    assert doc["score"]["value"] < 65
    assert doc["sufficient_data"]
    bindings = doc["materials"][0]["call_bindings"]
    assert {b["root_url"] for b in bindings} == {GUIDE}
    assert all(GAME not in b["reachable_urls"] for b in bindings)


def test_call_to_game_branch_keeps_the_specific_route_evidence():
    doc = analyze(f"Дополнительный адрес: {GUIDE}. Заходи за бонусом: {HUB}")
    assert doc["score"]["value"] == 80
    binding = doc["materials"][0]["call_bindings"][0]
    assert binding["root_url"] == HUB and GAME in binding["reachable_urls"]
    assert binding["route_evidence_ids"] and binding["destination_evidence_ids"]
    reason = next(c for c in doc["score"]["contributions"] if c["key"] == "destination_and_call")
    assert binding["call_evidence_id"] in reason["evidence_ids"]
    assert set(binding["root_evidence_ids"] + binding["route_evidence_ids"]) <= set(reason["evidence_ids"])


def test_two_same_clause_targets_are_an_explicit_attribution_gap():
    doc = analyze(f"Переходи: {GUIDE} или {GAME}")
    assert doc["score"]["value"] < 65
    assert not doc["sufficient_data"] and doc["status"] == "partial"
    assert doc["materials"][0]["attribution_incomplete"]


def test_separate_url_field_remains_a_recorded_material_level_inference():
    doc = analyze("Заходи, забирай бонус!", GAME)
    assert doc["score"]["value"] == 80
    assert all(b["method"] == "single_material_target" for b in doc["materials"][0]["call_bindings"])


def test_quoted_call_does_not_bind_a_separate_game_reference():
    doc = analyze(f"В сообщении написано «Переходи сюда». Дополнительный адрес: {GAME}")
    assert doc["score"]["value"] < 65
    assert not doc["materials"][0]["call_bindings"]


def test_real_qr_game_branch_does_not_override_explicit_visible_target():
    import cv2
    import numpy as np
    from PIL import Image

    from backend import storage
    from backend.config import DATA

    pixels = cv2.QRCodeEncoder_create().encode(GAME)
    pixels = cv2.copyMakeBorder(pixels, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    pixels = np.repeat(np.repeat(pixels, 8, axis=0), 8, axis=1)
    image_id = storage.digest(pixels.tobytes())[:32] + ".png"
    Image.fromarray(pixels).save(DATA / "originals" / image_id)
    doc = pipeline.new_case(
        CaseInput(
            title="Разные назначения",
            mode="synthetic",
            materials=[
                MaterialInput(
                    text=f"Переходи сюда: {GUIDE}. Дополнительный код помещён в приложении.",
                    image_id=image_id,
                )
            ],
        )
    )
    pipeline.analyze(
        doc,
        fetch=SyntheticTransport(
            {
                GUIDE: {"status": 200, "body": "Календарь встреч."},
                GAME: {"status": 200, "body": "Казино и слоты."},
            }
        ),
        use_ocr_cache=False,
    )
    assert doc["materials"][0]["qr"]["codes"][0]["text"] == GAME
    assert doc["score"]["value"] < 65
    assert {b["root_url"] for b in doc["materials"][0]["call_bindings"]} == {GUIDE}
