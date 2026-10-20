import json

import cv2
import numpy as np
from PIL import Image

from backend import pipeline, storage
from backend.config import DATA
from backend.qr import decode
from backend.schemas import CaseInput, MaterialInput


def qr_pixels(value):
    encoded = cv2.QRCodeEncoder_create().encode(value)
    padded = cv2.copyMakeBorder(encoded, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    return np.repeat(np.repeat(padded, 8, axis=0), 8, axis=1)


def test_real_qr_multiple_payloads_and_coordinates(tmp_path):
    a, b = qr_pixels("https://go.safetrace.test/r/q7"), qr_pixels("javascript:alert(1)")
    canvas = Image.new("RGB", (1000, 500), "white")
    canvas.paste(Image.fromarray(a).convert("RGB"), (20, 30))
    canvas.paste(Image.fromarray(b).convert("RGB"), (550, 50))
    path = tmp_path / "pixels.png"
    canvas.save(path)
    result = decode(path, use_cache=False)
    codes = {code["text"]: code for code in result["codes"]}
    assert codes["https://go.safetrace.test/r/q7"]["valid_url"]
    assert not codes["javascript:alert(1)"]["valid_url"]
    assert all(0 <= p[0] < 1000 and 0 <= p[1] < 500 for code in codes.values() for p in code["polygon"])
    assert decode(path)["cache_hit"]


def make_case_with_qr(value, monkeypatch, mode="synthetic"):
    image_id = storage.digest(value)[:32] + ".png"
    pixels = qr_pixels(value)
    Image.fromarray(pixels).save(DATA / "originals" / image_id)
    monkeypatch.setattr(
        pipeline,
        "recognize",
        lambda *args, **kwargs: {
            "text": "",
            "lines": [],
            "width": pixels.shape[1],
            "height": pixels.shape[0],
            "model": "OCR omitted only in this QR integration test",
        },
    )
    return pipeline.new_case(
        CaseInput(
            title="QR",
            mode=mode,
            materials=[
                MaterialInput(text="Переходи и забирай бонус по QR.", image_id=image_id),
            ],
        )
    )


def test_decoded_url_uses_trace_and_qr_source_evidence(monkeypatch):
    doc = make_case_with_qr("https://go.safetrace.test/r/q7", monkeypatch)
    pipeline.analyze(doc)
    assert doc["trace"]["observations"][-1]["status_code"] == 200
    assert doc["score"]["value"] >= 65
    edge = next(e for e in doc["graph"]["edges"] if e["type"] == "contains_link")
    assert edge["method"] == "qr_decode"
    source = next(e for e in doc["evidence"] if e["id"] == edge["evidence_ids"][0])
    assert source["polygon"] and source["method"] == "qr_decode"
    assert json.loads(json.dumps(doc))["materials"][0]["qr"]["codes"][0]["text"].endswith("/q7")


def test_qr_does_not_bypass_ssrf_or_execute_other_schemes(monkeypatch):
    monkeypatch.setenv("SAFETRACE_OFFLINE", "0")
    monkeypatch.setenv("SAFETRACE_ALLOWED_HOSTS", "localhost")
    calls = []
    monkeypatch.setattr("socket.create_connection", lambda *args, **kwargs: calls.append(args))
    doc = make_case_with_qr("http://localhost/private", monkeypatch, mode="local")
    pipeline.analyze(doc)
    assert doc["trace"]["observations"][0]["stop"]
    assert not calls
    doc = make_case_with_qr("javascript:alert(1)", monkeypatch)
    pipeline.analyze(doc)
    assert not doc["trace"]["observations"] and not calls


def test_qr_payload_query_is_not_trimmed_as_sentence_punctuation(monkeypatch):
    from backend.links import SyntheticTransport

    url = "https://a.test/offer?ref=token!"
    doc = make_case_with_qr(url, monkeypatch)
    pipeline.analyze(doc, fetch=SyntheticTransport({url: {"status": 200, "body": "<p>Казино, рулетка.</p>"}}))
    assert doc["trace"]["observations"][0]["url"] == url
    assert doc["score"]["value"] >= 65
