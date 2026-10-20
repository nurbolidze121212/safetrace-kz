import io
import json
import time
import zipfile
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from backend import pipeline, storage
from backend.analysis import local_context, verify_claims
from backend.app import app
from backend.config import DATA, ROOT
from backend.graph import build_graph
from backend.links import (
    LinkBlocked,
    SyntheticTransport,
    identifiers,
    normalized,
    resolve_public,
    trace,
    visible_html,
)
from backend.ocr import recognize
from backend.schemas import CaseInput, ContextExtraction, MaterialInput


def make(text, mode="synthetic"):
    return pipeline.new_case(
        CaseInput(title="Проверка", mode=mode, materials=[MaterialInput(text=text, source="test")])
    )


def test_input_validation():
    with pytest.raises(ValidationError):
        MaterialInput()
    with pytest.raises(ValidationError):
        MaterialInput(text="a", published_at="2026-10-20T10:00:00")
    with pytest.raises(ValidationError):
        MaterialInput(text="a", image_id="../../.env")
    with pytest.raises(ValidationError):
        CaseInput(title="a", materials=[MaterialInput(text="a")] * 21)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/a",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest",
        "http://2130706433/",
        "http://0x7f000001/",
        "https://user:pass@example.com/",
        "http://example.com:22/",
        "http://example.com./",
        "http://example.com\\@localhost/",
        "http://[::ffff:127.0.0.1]/",
    ],
)
def test_ssrf_initial(url):
    with pytest.raises(LinkBlocked):
        resolve_public(url, {"example.com"})


def test_rebinding_and_allowlist():
    def resolver(*args, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 80))]

    with pytest.raises(LinkBlocked):
        resolve_public("http://allowed.example/", {"allowed.example"}, resolver)
    with pytest.raises(LinkBlocked):
        resolve_public("http://not-allowed.example/", {"allowed.example"}, resolver)


def test_redirect_ssrf_checked_at_next_hop():
    calls = []

    def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            return 302, {"location": "http://169.254.169.254/latest"}, b""
        resolve_public(url, {"allowed.example"})

    result = trace(["https://allowed.example/"], fetch)
    assert len(result["observations"]) == 2
    assert result["observations"][-1]["stop"]
    assert result["observations"][-1]["status_code"] is None


def test_live_pinning_uses_numeric_ip(monkeypatch):
    from backend.links import PinnedHTTP

    calls = []
    monkeypatch.setattr("socket.create_connection", lambda addr, timeout: calls.append(addr) or object())
    conn = PinnedHTTP("allowed.example", "8.8.8.8", 80, False)
    conn.connect()
    assert calls == [("8.8.8.8", 80)]


def test_routes_cycles_and_depth():
    result = trace(["https://go.safetrace.test/r/q7"], SyntheticTransport())
    assert [r["type"] for r in result["relations"]] == ["contains_link", "redirects", "page_link"]
    assert result["observations"][-1]["status_code"] == 200
    result = trace(["https://go.safetrace.test/loop"], SyntheticTransport())
    assert "Цикл" in result["observations"][-1]["stop"]
    pages = {
        f"https://d.test/{i}": {"status": 302, "headers": {"location": f"https://d.test/{i + 1}"}}
        for i in range(20)
    }
    result = trace(["https://d.test/0"], SyntheticTransport(pages))
    assert result["observations"][-1]["stop"] == "Лимит глубины"


def test_html_is_data_and_hidden_links_ignored():
    text, links = visible_html(
        b'<script>steal()</script><p>safe</p><a hidden href="/bad">hidden</a><a href="/ok">visible</a>',
        "https://a.test",
    )
    assert "steal" not in text and "hidden" not in text
    assert links == [{"url": "https://a.test/ok", "quote": "visible", "href": "/ok"}]


def test_url_identity_and_scope():
    assert normalized("https://EXAMPLE.com/a?ref=ABC&utm=1") == "https://example.com/a?ref=ABC&utm=1"
    a = identifiers("https://a.example/?ref=123")[0]
    b = identifiers("https://b.example/?ref=123")[0]
    assert a["scope"] != b["scope"]


def test_unverified_model_quotes_rejected():
    result = ContextExtraction(
        language="ru",
        context="promotion",
        contradictions=[],
        limitations=[],
        claims=[{"kind": "gambling", "quote": "казино", "source_id": "m1", "explanation": "test"}],
    )
    valid, rejected = verify_claims(result, {"m1": "Обычный текст"})
    assert not valid and len(rejected) == 1


def test_context_and_priority_combinations():
    d = make("Бонус QALA7")
    pipeline.analyze(d)
    assert d["score"]["value"] == 0
    d = make("Переходи, забирай бонус! https://go.safetrace.test/r/q7")
    pipeline.analyze(d)
    assert d["score"]["value"] >= 65
    warning = make(
        "Осторожно, мошенники: «переходи, забирай бонус». Это казино. "
        "Не переводите деньги. https://go.safetrace.test/r/q7"
    )
    pipeline.analyze(warning)
    assert warning["score"]["value"] < 65
    assert warning["context"]["context"] == "warning"
    ctx = local_context({"a": "Осторожно, но переходи и забирай бонус казино"})
    assert ctx.contradictions


def test_changed_target_changes_analysis():
    doc = make("Переходи, забирай бонус! https://go.safetrace.test/r/q7")
    pipeline.analyze(doc)
    before = doc["score"]["value"]
    pages = json.loads((ROOT / "fixtures/pages.json").read_text(encoding="utf-8"))
    pages["https://arena.safetrace.test/welcome?ref=QALA7"]["body"] = "<p>Книжный магазин</p>"
    pipeline.analyze(doc, fetch=SyntheticTransport(pages))
    assert doc["score"]["value"] < before
    assert "Книжный" in doc["trace"]["observations"][-1]["text"]


def test_graph_evidence_and_related_domain_scope():
    doc = make("Переходи, бонус! https://go.safetrace.test/r/q7")
    other = make("Тіркел, бонус ал. https://go.safetrace.test/r/second")
    shop = make("Переходи, бонус! https://shop.safetrace.test/items?ref=QALA7")
    for d in (doc, other, shop):
        pipeline.analyze(d)
    graph = build_graph(doc, [other, shop])
    matches = [e for e in graph["edges"] if e["type"] == "matching_identifier"]
    assert matches
    assert other["id"] in {n.get("case_id") for n in graph["nodes"]}
    assert shop["id"] not in {n.get("case_id") for n in graph["nodes"]}
    known = {e["id"] for e in graph["evidence"]}
    assert all(e["evidence_ids"] and set(e["evidence_ids"]) <= known for e in graph["edges"])


def test_cloud_failure_and_cancel(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    doc = make("Переходи в казино, бонус.", "cloud")
    pipeline.analyze(doc)
    assert doc["provider"] == "local_rule"
    assert doc["status"] == "partial"
    doc = make("Тест")
    pipeline.analyze(doc, cancelled=lambda: True)
    assert doc["status"] == "cancelled"


def test_real_ocr_pixels_and_boxes():
    path = DATA / "originals" / "ocr-test.png"
    im = Image.new("RGB", (900, 220), "white")
    draw = ImageDraw.Draw(im)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 34)
    draw.text((30, 25), "Қазақша: қауіпсіздік және ұтыс.", font=font, fill="black")
    draw.text((30, 90), "Промокод TEST77. Не переводите деньги.", font=font, fill="black")
    im.save(path)
    result = recognize(path, use_cache=False)
    assert result["width"] == 900 and result["height"] == 220
    assert "Қазақша" in result["text"] and "деньги" in result["text"]
    assert all(len(line["polygon"]) == 4 for line in result["lines"])
    assert all(0 <= line["confidence"] <= 1 for line in result["lines"])


def test_api_persistence_export_and_security(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret-never-export")
    with TestClient(app) as client:
        assert client.post("/api/cases", json={}).status_code == 422
        assert (
            client.post("/api/cases", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
        )
        image = io.BytesIO()
        Image.new("RGB", (50, 50), "white").save(image, format="PNG")
        up = client.post("/api/uploads", files={"file": ("a.png", image.getvalue(), "image/png")})
        assert up.status_code == 200
        result = client.post(
            "/api/cases",
            json={
                "title": "Новый случай",
                "mode": "synthetic",
                "materials": [{"text": "Переходи, бонус! https://go.safetrace.test/r/q7"}],
            },
        )
        assert result.status_code == 201
        cid = result.json()["id"]
        for _ in range(100):
            d = client.get(f"/api/cases/{cid}").json()
            if d["status"] not in ("running", "pending"):
                break
            time.sleep(0.05)
        assert d["status"] == "completed"
        original_score = deepcopy(d["score"])
        assert (
            client.post(
                f"/api/cases/{cid}/decision",
                json={"decision": "false_positive", "comment": "<script>alert(1)</script>"},
            ).status_code
            == 200
        )
        assert client.get(f"/api/cases/{cid}").json()["score"] == original_score
        archive = client.get(f"/api/cases/{cid}/export")
        with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
            manifest = json.loads(z.read("manifest.json"))
            for item in manifest["files"]:
                assert storage.digest(z.read(item["path"])) == item["sha256"]
            assert b"test-secret-never-export" not in z.read("case.json")
            assert b"<script>alert" not in z.read("report.html")
        assert storage.decisions(cid)[-1]["decision"] == "false_positive"
    with TestClient(app) as restarted:
        assert restarted.get(f"/api/cases/{cid}").json()["decisions"][-1]["decision"] == "false_positive"


def test_recover_pending_job():
    doc = make("Прерванный ввод")
    doc["status"] = "running"
    storage.save(doc)
    pipeline.recover()
    recovered = storage.get(doc["id"])
    assert recovered["status"] == "partial"
    assert recovered["stage"] == "interrupted"


def test_features_do_not_mix_across_materials():
    doc = pipeline.new_case(
        CaseInput(
            title="Разные материалы",
            mode="synthetic",
            materials=[
                MaterialInput(text="На лекции изучаем слово казино."),
                MaterialInput(text="Переходи в библиотеку, бонус за книгу."),
            ],
        )
    )
    pipeline.analyze(doc)
    assert doc["score"]["value"] == 0


def test_two_routes_converging_are_not_a_cycle():
    doc = pipeline.new_case(
        CaseInput(
            title="Общий адрес",
            mode="synthetic",
            materials=[
                MaterialInput(text="Переходи, бонус! https://go.safetrace.test/r/q7"),
                MaterialInput(text="Тіркел, бонус! https://go.safetrace.test/r/second"),
            ],
        )
    )
    pipeline.analyze(doc)
    assert doc["status"] == "completed"
    assert any(o.get("reused_from") for o in doc["trace"]["observations"])
    assert not any(o.get("stop") for o in doc["trace"]["observations"])
    match = next(e for e in doc["graph"]["edges"] if e["type"] == "matching_identifier")
    evidence = [e for e in doc["evidence"] if e["id"] in match["evidence_ids"]]
    assert len({e.get("material_id") for e in evidence if e.get("material_id")}) == 2


def test_warning_does_not_whitelist_another_material():
    doc = pipeline.new_case(
        CaseInput(
            title="Смешанный случай",
            mode="synthetic",
            materials=[
                MaterialInput(text="Осторожно, мошенники рекламируют казино."),
                MaterialInput(text="Переходи, забирай бонус! https://go.safetrace.test/r/q7"),
            ],
        )
    )
    pipeline.analyze(doc)
    assert doc["score"]["value"] >= 65


def test_http_transient_retry_is_bounded_and_auth_not_retried():
    calls = []

    def temporary(url):
        calls.append(url)
        return (503 if len(calls) == 1 else 200), {}, b"<p>OK</p>"

    result = trace(["https://a.test/"], temporary)
    assert result["requests"] == 2
    assert result["observations"][0]["status_code"] == 200
    calls.clear()

    def unauthorized(url):
        calls.append(url)
        return 401, {}, b""

    result = trace(["https://a.test/"], unauthorized)
    assert len(calls) == 1 and result["observations"][0]["stop"] == "HTTP 401"


def test_missing_destination_is_not_a_low_risk_verdict():
    doc = make("Переходи, бонус для друзей! https://not-present.test/")
    pipeline.analyze(doc)
    assert not doc["sufficient_data"] and doc["status"] == "partial"


def test_arbitrary_image_bytes_and_chunked_limit():
    with TestClient(app) as client:
        bad = client.post("/api/uploads", files={"file": ("a.png", b"fake", "image/png")})
        assert bad.status_code == 422
        large = client.post("/api/cases", content=iter([b"x" * (1024 * 1024)] * 10))
        assert large.status_code == 413
        unsafe = client.post(
            "/api/cases", json={"title": "bad", "materials": [{"url": "file:///C:/Windows"}]}
        )
        assert unsafe.status_code == 422


def test_replay_is_labeled_and_immutable():
    with TestClient(app) as client:
        response = client.post("/api/demos/route?replay=true")
        assert response.status_code == 200
        cid = response.json()["id"]
        result = client.get(f"/api/cases/{cid}").json()
        assert result["mode"] == "replay"
        assert "ПОВТОР" in result["limitations"][0]
        assert client.post(f"/api/cases/{cid}/retry").status_code == 409
        assert client.post(f"/api/cases/{cid}/materials", json={"text": "new"}).status_code == 409


def test_data_split_has_no_domain_or_family_leakage():
    folder = ROOT / "datasets" / "synthetic-v1"
    dev = json.loads((folder / "dev-pages.json").read_text(encoding="utf-8"))
    test = json.loads((folder / "test-pages.json").read_text(encoding="utf-8"))
    from urllib.parse import urlsplit

    assert not {urlsplit(u).hostname for u in dev} & {urlsplit(u).hostname for u in test}
    rows = [
        json.loads(line) for line in (folder / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert sum(r["split"] == "dev" for r in rows) == 40
    assert sum(r["split"] == "test" for r in rows) == 80
    assert sum(r["image"] for r in rows) >= 30
    assert not {r["family"] for r in rows if r["split"] == "dev"} & {
        r["family"] for r in rows if r["split"] == "test"
    }
    for split in ("dev", "test"):
        inputs = [
            json.loads(line) for line in (folder / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert all(set(row) == {"id", "materials"} for row in inputs)
        assert all(
            not ({"truth", "category", "family", "reference_text"} & set(mat))
            for row in inputs
            for mat in row["materials"]
        )
