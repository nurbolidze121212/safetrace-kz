"""An export must not silently omit or replace a saved original."""

import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import pipeline, storage
from backend.app import app
from backend.config import DATA
from backend.schemas import CaseInput, MaterialInput


@pytest.fixture
def image_case():
    path = DATA / "originals" / f"{uuid.uuid4().hex}.png"
    Image.new("RGB", (50, 50), "white").save(path)
    original = path.read_bytes()
    doc = pipeline.new_case(CaseInput(title="Integrity", materials=[MaterialInput(text="Input", image_id=path.name)]))
    return doc, path, original


def test_image_fingerprint_is_saved_at_creation(image_case):
    doc, _, original = image_case
    assert doc["materials"][0]["image_sha256"] == storage.digest(original)
    assert storage.get(doc["id"])["materials"][0]["image_sha256"] == storage.digest(original)


def test_export_does_not_silently_omit_missing_original(image_case):
    doc, path, _ = image_case
    path.unlink()
    with TestClient(app) as client:
        result = client.get(f"/api/cases/{doc['id']}/export")
    assert result.status_code == 409
    assert "оригинал" in result.json()["detail"].lower()


def test_export_rejects_changed_image_against_recorded_hash(image_case):
    doc, path, original = image_case
    doc["materials"][0]["image_sha256"] = storage.digest(original)
    storage.save(doc)
    Image.new("RGB", (50, 50), "blue").save(path)
    with TestClient(app) as client:
        result = client.get(f"/api/cases/{doc['id']}/export")
    assert result.status_code == 409
    assert "измен" in result.json()["detail"].lower()


def test_export_rejects_changed_text_against_recorded_hash():
    doc = pipeline.new_case(CaseInput(title="Integrity", materials=[MaterialInput(text="Original")]))
    doc["materials"][0]["text"] = "Replaced"
    storage.save(doc)
    with TestClient(app) as client:
        result = client.get(f"/api/cases/{doc['id']}/export")
    assert result.status_code == 409


def test_analysis_does_not_use_text_that_no_longer_matches_original():
    doc = pipeline.new_case(CaseInput(title="Integrity", materials=[MaterialInput(text="Original")]))
    original_hash = doc["materials"][0]["original_sha256"]
    doc["materials"][0]["text"] = "Переходи в казино, забирай бонус! https://go.safetrace.test/r/q7"
    pipeline.analyze(doc)
    assert doc["status"] == "partial"
    assert not doc["sufficient_data"]
    assert doc["stages"]["originals"] == "partial"
    assert doc["materials"][0]["original_sha256"] == original_hash
    assert not doc["claims"] and not doc["trace"]["observations"]


def test_unmodified_original_is_exported_byte_for_byte(image_case):
    doc, _, original = image_case
    with TestClient(app) as client:
        result = client.get(f"/api/cases/{doc['id']}/export")
    assert result.status_code == 200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert archive.read("originals/01.png") == original


@pytest.mark.parametrize("change", ["missing", "replaced"])
def test_analysis_keeps_saved_fingerprint_and_rejects_changed_pixels(image_case, monkeypatch, change):
    doc, path, original = image_case
    expected = storage.digest(original)
    doc["materials"][0]["image_sha256"] = expected
    if change == "missing":
        path.unlink()
    else:
        Image.new("RGB", (50, 50), "blue").save(path)
    calls = []

    def recognize(*args, **kwargs):
        calls.append(args)
        return {"text": "", "lines": []}

    monkeypatch.setattr(pipeline, "recognize", recognize)
    pipeline.analyze(doc)
    assert calls == []
    assert doc["materials"][0]["image_sha256"] == expected
    assert not doc["sufficient_data"]
    assert doc["status"] == "partial"
    assert doc["stages"]["ocr"] == "partial"
    assert "ocr" not in doc["materials"][0] and "qr" not in doc["materials"][0]
