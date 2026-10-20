from backend import pipeline
from backend.links import SyntheticTransport
from backend.schemas import CaseInput, MaterialInput


def make_case(materials):
    return pipeline.new_case(CaseInput(title="Приоритет материалов", mode="synthetic", materials=materials))


def test_priority_names_material_whose_evidence_contributed():
    doc = make_case(
        [
            MaterialInput(text="Осторожно: мошенники рекламируют казино.", source="Предупреждение"),
            MaterialInput(text="Играй в казино и забирай бонус!", source="Предложение"),
        ]
    )
    pipeline.analyze(doc)
    winner = doc["materials"][1]
    assert doc["score"]["value"] == 80
    assert doc["score"]["material_id"] == winner["id"]
    assert winner["context"]["context"] == "promotion"
    assert doc["materials"][0]["context"]["context"] == "warning"
    assert all(c["evidence_ids"] for c in doc["score"]["contributions"])


def test_incomplete_other_material_does_not_hide_known_high_priority():
    doc = make_case(
        [
            MaterialInput(text="Играй в казино и забирай бонус!"),
            MaterialInput(text="Переходи, бонус!", url="https://v5a.test/x"),
        ]
    )
    pipeline.analyze(doc, fetch=SyntheticTransport({"https://v5a.test/x": {"status": 503, "body": ""}}))
    assert doc["materials"][0]["sufficient_data"]
    assert not doc["materials"][1]["sufficient_data"]
    assert doc["score"]["value"] == 80
    assert doc["sufficient_data"]
    assert doc["score"]["material_id"] == doc["materials"][0]["id"]
    assert doc["status"] == "partial"
    assert any("Часть материалов" in text for text in doc["limitations"])


def test_known_low_does_not_turn_missing_destination_into_safe_case():
    doc = make_case(
        [
            MaterialInput(text="Учебный разбор рекламы казино, не играйте."),
            MaterialInput(text="Переходи, бонус!", url="https://v5a.test/x"),
        ]
    )
    pipeline.analyze(doc, fetch=SyntheticTransport({"https://v5a.test/x": {"status": 503, "body": ""}}))
    assert not doc["sufficient_data"]
    assert doc["status"] == "partial"


def test_winner_does_not_use_larger_but_incomplete_score():
    doc = make_case(
        [
            MaterialInput(text="Играй в казино!"),
            MaterialInput(text="Играй в казино, бонус, выиграй сегодня!"),
        ]
    )
    # A lost original image makes this material incomplete even when its text remains available.
    doc["materials"][1]["image_id"] = "d" * 32 + ".png"
    doc["materials"][1]["image_sha256"] = "0" * 64
    pipeline.analyze(doc)
    assert doc["materials"][0]["sufficient_data"]
    assert not doc["materials"][1]["sufficient_data"]
    assert doc["score"]["value"] == 65
    assert doc["score"]["material_id"] == doc["materials"][0]["id"]
    assert doc["sufficient_data"] and doc["status"] == "partial"


def test_retry_replaces_priority_source_and_its_context():
    doc = make_case(
        [
            MaterialInput(text="Играй в казино!"),
            MaterialInput(text="Переходи за бонусом!", url="https://v5a.test/x"),
        ]
    )
    pipeline.analyze(
        doc, fetch=SyntheticTransport({"https://v5a.test/x": {"status": 200, "body": "<p>Книги</p>"}})
    )
    assert doc["score"]["material_id"] == doc["materials"][0]["id"]
    pipeline.analyze(
        doc,
        fetch=SyntheticTransport(
            {"https://v5a.test/x": {"status": 200, "body": "<p>Казино. Играй в слоты.</p>"}}
        ),
    )
    assert doc["score"]["material_id"] == doc["materials"][1]["id"]
    assert doc["score"]["value"] == 80
