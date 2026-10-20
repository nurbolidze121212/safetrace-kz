"""Decode captured page bytes without inventing readable evidence from damaged text."""

import codecs
from urllib.parse import urlsplit

import pytest

from backend import links, pipeline
from backend.schemas import CaseInput, MaterialInput


def observe(body, content_type="text/html"):
    return links.trace(["https://page.test/"], lambda url: (200, {"content-type": content_type}, body))[
        "observations"
    ][0]


@pytest.mark.parametrize("declaration", ["header", "meta", "http-equiv"])
def test_declared_cyrillic_encoding_preserves_text_and_link_quotes(declaration):
    text = "Казино: слоты, депозит."
    meta = {
        "header": "",
        "meta": '<meta charset="windows-1251">',
        "http-equiv": '<meta http-equiv="Content-Type" content="text/html; charset=windows-1251">',
    }[declaration]
    body = (meta + f'<p>{text}</p><a href="/offer">Получить бонус</a>').encode("cp1251")
    content_type = 'text/html; charset="windows-1251"' if declaration == "header" else "text/html"
    obs = observe(body, content_type)
    assert obs["text"] == text + " Получить бонус"
    assert obs["links"][0] == {"url": "https://page.test/offer", "quote": "Получить бонус"}
    assert obs["encoding"] == "cp1251"
    assert obs["encoding_source"] == ("http" if declaration == "header" else "meta")
    assert not obs["stop"]


def test_http_charset_takes_precedence_over_meta():
    obs = observe('<meta charset="utf-8"><p>Слоты и депозит</p>'.encode("cp1251"),
                  "text/html; charset=windows-1251")
    assert obs["text"] == "Слоты и депозит"
    assert obs["encoding_source"] == "http"


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_bom_takes_precedence_over_http_charset(encoding):
    obs = observe("<p>Әғқңөұүһі</p>".encode(encoding), "text/html; charset=windows-1251")
    assert obs["text"] == "Әғқңөұүһі"
    assert obs["encoding_source"] == "bom"


def test_plain_text_is_not_interpreted_as_html_or_a_link():
    text = '<p>Не играть</p>\n<bonus>не выплачен</bonus> &amp; <a href="https://else.test">ссылка</a>'
    obs = observe(text.encode(), "text/plain; charset=utf-8")
    assert obs["text"] == text
    assert obs["links"] == []


@pytest.mark.parametrize("content_type,body", [
    ("text/html; charset=unknown-encoding", b"<p>Visible</p>"),
    ("text/html; charset=utf-8", b"<p>broken \xff</p>"),
    ("text/html", "<p>Слоты</p>".encode("cp1251")),
    ("text/html; charset=unicode-escape", b"<p>\\u0441\\u043b\\u043e\\u0442\\u044b</p>"),
    ("text/html", codecs.BOM_UTF32_LE + "<p>Text</p>".encode("utf-32-le")),
])
def test_unsupported_or_corrupt_encoding_is_an_explicit_gap(content_type, body):
    obs = observe(body, content_type)
    assert obs["stop"] and "кодиров" in obs["stop"].lower()
    assert obs["text"] == ""
    assert obs["body_sha256"]


def test_literal_replacement_character_is_preserved_in_valid_utf8():
    obs = observe("<p>Исходный символ � и ә</p>".encode())
    assert obs["text"] == "Исходный символ � и ә"
    assert not obs["stop"]


def test_charset_text_in_comments_and_scripts_is_not_a_declaration():
    body = '<!-- <meta charset="windows-1251"> --><script>"<meta charset=cp866>"</script><p>Әңгімені оқы</p>'
    obs = observe(body.encode())
    assert obs["text"] == "Әңгімені оқы"
    assert obs["encoding"] == "utf-8" and obs["encoding_source"] == "default"


def test_undecodable_destination_does_not_become_a_complete_low_priority_result():
    start, destination = "https://page.test/", "https://page.test/end"

    def fetch(url):
        body = b'<p>Start</p><a href="/end">Open</a>' if url == start else b"<p>\xff</p>"
        return 200, {"content-type": "text/html; charset=utf-8"}, body

    doc = pipeline.new_case(CaseInput(title="Broken page", materials=[MaterialInput(
        text="Посмотри предложение по ссылке", url=start
    )]))
    pipeline.analyze(doc, fetch=fetch)
    assert doc["status"] == "partial"
    assert doc["stages"]["links"] == "partial"
    assert not doc["sufficient_data"]
    assert doc["trace"]["observations"][-1]["url"] == destination


def test_text_budget_is_visible_when_a_page_was_truncated():
    obs = observe(("<p>" + "a" * 20001 + "</p>").encode())
    assert len(obs["text"]) == 20000
    assert obs["text_truncated"] and obs["content_warning"]


def test_truncated_destination_is_not_reported_as_sufficient():
    body = ("<p>" + "a" * 20001 + "</p>").encode()
    doc = pipeline.new_case(CaseInput(title="Long page", materials=[MaterialInput(url="https://page.test/")]))
    pipeline.analyze(doc, fetch=lambda url: (200, {"content-type": "text/html"}, body))
    assert doc["status"] == "partial" and doc["stages"]["links"] == "partial"
    assert not doc["sufficient_data"]
    assert any("20 000" in item for item in doc["limitations"])


def test_live_fetch_preserves_the_declared_charset(monkeypatch):
    class Response:
        status = 200

        def getheaders(self):
            return [("Content-Type", "text/html; charset=windows-1251")]

        def read1(self, size):
            return b""

    class Connection:
        def __init__(self, *args):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(links, "offline", lambda: False)
    monkeypatch.setattr(links, "resolve_public", lambda url: (urlsplit(url), "8.8.8.8"))
    monkeypatch.setattr(links, "PinnedHTTP", Connection)
    _, headers, _ = links.live_fetch("https://page.test/")
    assert headers["content-type"] == "text/html; charset=windows-1251"
