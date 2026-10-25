import json

from PIL import Image
from test_provider import setup_fake

from backend import pipeline, providers
from backend.config import DATA
from backend.schemas import CaseInput, MaterialInput

EMPTY = '{"language":"ru","context":"ambiguous","claims":[],"contradictions":[],"limitations":[]}'


def test_three_text_materials_do_not_use_image_budget(monkeypatch):
    calls = setup_fake(monkeypatch, [EMPTY])
    doc = pipeline.new_case(
        CaseInput(
            title="Текстовый пакет",
            mode="cloud",
            materials=[MaterialInput(text=s) for s in ("Первый текст.", "Второй текст.", "Третий текст.")],
        )
    )
    pipeline.analyze(doc)
    assert len(calls) == 1
    assert doc["stages"]["features"] == "completed"
    assert doc["provider_input"]["complete"]
    assert doc["provider_input"]["images_total"] == 0


def test_serialized_wrapper_counts_toward_budget(monkeypatch):
    setup_fake(monkeypatch, [EMPTY])
    doc = pipeline.new_case(
        CaseInput(
            title="Пакет",
            mode="cloud",
            materials=[MaterialInput(text="а" * 19990), MaterialInput(text="б" * 19990)],
        )
    )
    pipeline.analyze(doc)
    assert doc["stages"]["features"] == "partial"
    assert not doc["provider_input"]["complete"]
    assert doc["provider_input"]["serialized_chars"] <= 40000
    assert any(not m["cloud_input_complete"] for m in doc["materials"])
    assert not doc["sufficient_data"]


def test_budget_keeps_valid_json_and_represents_each_source(monkeypatch):
    calls = setup_fake(monkeypatch, [EMPTY])
    source = {f"m{i}": '«Қазақ»\\\n"</source>"' * 1000 for i in range(20)}
    provider = providers.GeminiProvider()
    provider.extract(source)
    body = calls[0]["contents"][0].text
    payload = body.split("SOURCE_DATA_JSON\n", 1)[1]
    parsed = json.loads(payload)
    assert len(payload) <= 40000
    assert {r["source_id"] for r in parsed["sources"]} == set(source)
    assert all(source[r["source_id"]].startswith(r["text"]) and r["text"] for r in parsed["sources"])
    assert provider.sent_sources == {r["source_id"]: r["text"] for r in parsed["sources"]}
    assert not provider.input_coverage["complete"]


def test_exact_input_coverage_is_rebuilt_on_cache_hit(monkeypatch):
    calls = setup_fake(monkeypatch, [EMPTY])
    source = {"coverage-cache": "Обычный текст."}
    first, second = providers.GeminiProvider(), providers.GeminiProvider()
    first.extract(source)
    second.extract(source)
    assert len(calls) == 1
    assert first.sent_sources == second.sent_sources == source
    assert first.input_coverage == second.input_coverage
    assert second.input_coverage["complete"]


def test_images_count_and_total_bytes_are_bounded(monkeypatch):
    calls = setup_fake(monkeypatch, [EMPTY])
    provider = providers.GeminiProvider()
    images = [b"a" * (5 * 1024 * 1024), b"b" * (5 * 1024 * 1024), b"c"]
    provider.extract({"image-budget": "Материал"}, images)
    sent = [p.inline_data.data for p in calls[0]["contents"][1:]]
    assert len(sent) <= 2 and sum(map(len, sent)) <= 8 * 1024 * 1024
    assert not provider.input_coverage["complete"]
    assert provider.input_coverage["images_total"] == 3
    assert provider.input_coverage["images_sent"] == len(sent)


def test_quote_outside_sent_prefix_is_rejected(monkeypatch):
    doc = pipeline.new_case(
        CaseInput(
            title="Обрезка",
            mode="cloud",
            materials=[MaterialInput(text="а" * 19994 + "казино"), MaterialInput(text="б" * 20000)],
        )
    )
    source_id = doc["materials"][0]["id"]
    response = json.dumps(
        {
            "language": "ru",
            "context": "promotion",
            "claims": [
                {"kind": "gambling", "quote": "казино", "source_id": source_id, "explanation": "test"}
            ],
            "contradictions": [],
            "limitations": [],
        }
    )
    calls = setup_fake(monkeypatch, [response])
    pipeline.analyze(doc)
    assert len(calls) == 1
    assert not doc["claims"] and len(doc["rejected_claims"]) == 1


def test_retry_does_not_keep_previous_cloud_coverage(monkeypatch):
    setup_fake(monkeypatch, [EMPTY])
    doc = pipeline.new_case(
        CaseInput(title="Повтор", mode="cloud", materials=[MaterialInput(text="Материал")])
    )
    pipeline.analyze(doc)
    assert doc["provider_input"]["complete"]
    monkeypatch.setattr("backend.providers.offline", lambda: True)
    pipeline.analyze(doc)
    assert doc["provider"] == "local_rule"
    assert "provider_input" not in doc
    assert "cloud_input_complete" not in doc["materials"][0]


def test_third_image_is_reported_without_hiding_complete_texts(monkeypatch):
    monkeypatch.setattr(pipeline, "inspect_image", lambda _: {"requires_ocr": True})
    calls = setup_fake(monkeypatch, [EMPTY])
    monkeypatch.setattr(
        pipeline,
        "recognize",
        lambda *args, **kwargs: {
            "text": "Текст с картинки",
            "lines": [],
            "width": 12,
            "height": 12,
            "model": "test",
        },
    )
    monkeypatch.setattr(pipeline, "decode_qr", lambda *args, **kwargs: {"codes": []})
    materials = []
    for i in range(3):
        image_id = f"{i + 500:032x}.png"
        Image.new("RGB", (12, 12), (i * 50, 0, 0)).save(DATA / "originals" / image_id)
        materials.append(MaterialInput(text=f"Материал {i}", image_id=image_id))
    doc = pipeline.new_case(CaseInput(title="Три изображения", mode="cloud", materials=materials))
    pipeline.analyze(doc)
    assert len(calls[0]["contents"]) == 3
    assert doc["provider_input"]["images_total"] == 3
    assert doc["provider_input"]["images_sent"] == 2
    assert [m["cloud_input_complete"] for m in doc["materials"]] == [True, True, False]
    assert all(s["sent_chars"] == s["original_chars"] for s in doc["provider_input"]["sources"])
    assert doc["provider_input"]["image_material_ids"] == [m["id"] for m in doc["materials"][:2]]
    assert doc["status"] == "partial" and not doc["sufficient_data"]


def test_one_image_and_many_texts_are_fully_covered(monkeypatch):
    monkeypatch.setattr(pipeline, "inspect_image", lambda _: {"requires_ocr": True})
    calls = setup_fake(monkeypatch, [EMPTY])
    monkeypatch.setattr(
        pipeline,
        "recognize",
        lambda *args, **kwargs: {"text": "Текст", "lines": [], "width": 12, "height": 12, "model": "test"},
    )
    monkeypatch.setattr(pipeline, "decode_qr", lambda *args, **kwargs: {"codes": []})
    image_id = "f" * 32 + ".png"
    Image.new("RGB", (12, 12), "white").save(DATA / "originals" / image_id)
    doc = pipeline.new_case(
        CaseInput(
            title="Смешанный пакет",
            mode="cloud",
            materials=[MaterialInput(text="Фото", image_id=image_id)]
            + [MaterialInput(text=f"Текст {i}") for i in range(5)],
        )
    )
    pipeline.analyze(doc)
    assert len(calls[0]["contents"]) == 2
    assert doc["provider_input"]["complete"] and doc["provider_input"]["images_total"] == 1
    assert doc["status"] == "completed" and doc["sufficient_data"]
