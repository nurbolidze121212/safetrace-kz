import io
import json
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import links, pipeline, storage
from backend.app import app
from backend.config import DATA, ROOT
from backend.exports import package
from backend.ocr import recognize
from backend.ocr_urls import review_addresses
from backend.schemas import CaseInput, MaterialInput, URLCorrectionInput

RAW = "https://h4e6b9.test/еntry?ref=U4"
CORRECT = "https://h4e6b9.test/entry?ref=U4"


@pytest.fixture
def review_case(monkeypatch):
    # This fixture tests review of a mocked OCR reading, not the pixel gate.
    monkeypatch.setattr(pipeline, "inspect_image", lambda _: {"requires_ocr": True})
    image_id = uuid.uuid4().hex + ".png"
    Image.new("RGB", (80, 40), "white").save(DATA / "originals" / image_id)
    text = "Переходи и забирай бонус: " + RAW
    ocr = {
        "text": text,
        "raw_text": text,
        "width": 80,
        "height": 40,
        "model": "test-double",
        "lines": [{"text": text, "confidence": 0.98, "polygon": [[0, 0], [79, 0], [79, 39], [0, 39]]}],
        "raw_lines": [],
        "url_readings": [
            {
                "raw_url": RAW,
                "needs_review": True,
                "line_indices": [0],
                "reasons": ["Смешение алфавитов"],
                "suggestions": [{"url": CORRECT, "method": "test-double"}],
            }
        ],
    }
    monkeypatch.setattr(pipeline, "recognize", lambda *_args, **_kwargs: deepcopy(ocr))
    monkeypatch.setattr(pipeline, "decode_qr", lambda *_args, **_kwargs: {"codes": []})
    fetched = []
    transport = links.SyntheticTransport({CORRECT: {"status": 200, "body": "Казино, слоты и депозит"}})

    def fetch(url):
        fetched.append(url)
        return transport(url)

    monkeypatch.setattr(pipeline, "SyntheticTransport", lambda: fetch)
    executor = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(pipeline, "EXECUTOR", executor)
    doc = pipeline.new_case(
        CaseInput(title="Уточнение адреса", mode="synthetic", materials=[MaterialInput(image_id=image_id)])
    )
    pipeline.analyze(doc)
    storage.save(doc)
    assert fetched == [] and not doc["sufficient_data"]
    assert doc["status"] == "partial"
    try:
        yield doc, fetched, executor
    finally:
        executor.shutdown(wait=True)


def payload(doc, corrected=CORRECT):
    return URLCorrectionInput(
        material_id=doc["materials"][0]["id"],
        analysis_id=doc["analysis_id"],
        original_url=RAW,
        corrected_url=corrected,
        comment="Сверено с пикселями оригинала",
    )


def test_correction_preserves_automatic_snapshot_and_originals(review_case):
    old, fetched, executor = review_case
    storage.add_decision(old["id"], "needs_data", "Первоначальный автоматический результат")
    pipeline.correct_url(old["id"], payload(old))
    executor.submit(lambda: None).result(timeout=5)
    current = storage.get(old["id"])
    assert current["status"] == "completed" and current["analysis_assisted"]
    assert fetched == [CORRECT]
    assert current["score"]["value"] == 80 and current["sufficient_data"]
    assert current["materials"][0]["ocr"]["raw_text"] == old["materials"][0]["ocr"]["raw_text"]
    assert current["history"][0]["materials"] == old["materials"]
    assert not current["history"][0]["analysis_assisted"]
    assert "url_corrections" not in current["history"][0]["materials"][0]
    review = current["materials"][0]["url_reviews"][0]
    assert review["raw_url"] == RAW and review["selected_url"] == CORRECT
    manual = next(e for e in current["evidence"] if e["method"] == "manual_correction")
    assert manual["quote"] == CORRECT and manual["original_url"] == RAW
    assert manual["source_evidence_ids"]
    binding = current["materials"][0]["call_bindings"][0]
    assert binding["root_url"] == CORRECT and binding["method"] == "same_clause"
    assert manual["id"] in binding["root_evidence_ids"]
    edge = next(e for e in current["graph"]["edges"] if e["method"] == "manual_correction")
    assert edge["status"] == "inferred"
    with zipfile.ZipFile(io.BytesIO(package(current))) as archive:
        exported = json.loads(archive.read("case.json"))
        assert exported["analysis_assisted"] and len(exported["decisions"]) == 1
        assert exported["history"][0]["score"] == old["score"]


def test_old_analysis_and_unknown_url_do_not_mutate_case(review_case):
    old, _, _ = review_case
    for update in ({"analysis_id": "stale"}, {"original_url": "https://unknown.test/"}):
        request = payload(old).model_copy(update=update)
        with pytest.raises(ValueError):
            pipeline.correct_url(old["id"], request)
        assert storage.get(old["id"]) == old


def test_executor_failure_rolls_back_correction_and_history(review_case, monkeypatch):
    old, _, _ = review_case

    class Broken:
        def submit(self, *_args):
            raise RuntimeError("executor unavailable")

    monkeypatch.setattr(pipeline, "EXECUTOR", Broken())
    with pytest.raises(RuntimeError):
        pipeline.correct_url(old["id"], payload(old))
    assert storage.get(old["id"]) == old
    assert old["id"] not in pipeline.ACTIVE


def test_correction_endpoint_rejects_dangerous_scheme_and_stale_view(review_case):
    old, _, _ = review_case
    client = TestClient(app)
    body = payload(old).model_dump()
    assert (
        client.post(
            "/api/cases/" + old["id"] + "/url-corrections",
            json={**body, "corrected_url": "javascript:alert(1)"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/cases/" + old["id"] + "/url-corrections", json={**body, "analysis_id": "old-view"}
        ).status_code
        == 409
    )
    assert storage.get(old["id"]) == old


def test_manual_url_still_passes_live_ssrf_guards(review_case, monkeypatch):
    old, _, executor = review_case
    old["mode"] = "local"
    storage.save(old)
    monkeypatch.setattr(links, "offline", lambda: False)
    monkeypatch.setattr(
        links.socket, "create_connection", lambda *a, **k: pytest.fail("Private URL opened a socket")
    )
    pipeline.correct_url(old["id"], payload(old, "http://127.0.0.1/secret"))
    executor.submit(lambda: None).result(timeout=5)
    current = storage.get(old["id"])
    assert current["status"] == "partial" and not current["sufficient_data"]
    assert current["trace"]["observations"][0]["stop"]
    assert current["analysis_assisted"]


def test_uncertain_candidates_and_line_join_never_auto_follow(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.ocr_urls._read_crop",
        lambda *a: [
            {"text": CORRECT, "confidence": 0.99, "urls": [CORRECT], "scale": 1},
            {"text": CORRECT, "confidence": 0.99, "urls": [CORRECT], "scale": 2},
        ],
    )
    lines = [{"text": RAW, "confidence": 0.98, "polygon": []}]
    reviews = review_addresses(tmp_path / "unused.png", {"lines": lines})
    assert reviews[0]["needs_review"] and not reviews[0]["auto_follow"]
    assert reviews[0]["suggestions"][0]["agreement"]
    wrapped = review_addresses(
        tmp_path / "unused.png",
        {
            "lines": [
                {"text": "https://plain.test", "confidence": 0.99, "polygon": []},
                {"text": "/path?ref=K4", "confidence": 0.99, "polygon": []},
            ]
        },
    )
    assert not wrapped[0]["auto_follow"]
    assert wrapped[0]["suggestions"][0]["url"] == "https://plain.test/path?ref=K4"


def test_real_pixels_produce_separate_review_without_changing_raw_ocr():
    # New development image, unrelated to frozen v1/v2/v3 evaluation files.
    path = ROOT / "datasets/ocr-dev-v4/66d5c3c210e43e356aac.png"
    result = recognize(path, use_cache=False)
    review = next(r for r in result["url_readings"] if r["needs_review"])
    assert review["raw_url"] in result["text"] and review["raw_url"] in result["raw_text"]
    assert not review["auto_follow"]
    assert any(s["url"] == "https://n36e1d8f4b9.test/item/fc817e2?ref=Z74E3AD" for s in review["suggestions"])
    assert all(
        0 <= p[0] < result["width"] and 0 <= p[1] < result["height"]
        for line in result["lines"]
        for p in line["polygon"]
    )
