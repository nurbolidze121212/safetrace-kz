"""Keep the submitted IRI while sending an unambiguous UTF-8 HTTP request target."""

from urllib.parse import urlsplit

import pytest

from backend import links, pipeline
from backend.schemas import CaseInput, MaterialInput


def test_live_request_encodes_unicode_path_and_query_without_double_encoding(monkeypatch):
    url = "https://entry.test/ұтыс/казино?ref=ӘЛІ&encoded=%2F&literal=+&next=/a?b=1#қазақ"
    targets = []

    class Response:
        status = 200

        def getheaders(self):
            return [("content-type", "text/plain; charset=utf-8")]

        def read1(self, size):
            return b""

    class Connection:
        def __init__(self, *args):
            pass

        def request(self, method, target, **kwargs):
            target.encode("ascii")  # Match http.client's wire constraint.
            targets.append(target)

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(links, "offline", lambda: False)
    monkeypatch.setattr(links, "resolve_public", lambda value: (urlsplit(value), "8.8.8.8"))
    monkeypatch.setattr(links, "PinnedHTTP", Connection)
    result = links.trace([url], links.live_fetch)
    assert not result["observations"][0]["stop"]
    assert result["observations"][0]["url"] == url
    assert targets == ["/%D2%B1%D1%82%D1%8B%D1%81/%D0%BA%D0%B0%D0%B7%D0%B8%D0%BD%D0%BE?ref=%D3%98%D0%9B%D0%86&encoded=%2F&literal=+&next=/a?b=1"]


def test_unicode_and_encoded_url_forms_share_the_same_actual_http_request():
    unicode_url = "https://entry.test/ұтыс?ref=ӘЛІ"
    encoded_url = "https://entry.test/%D2%B1%D1%82%D1%8B%D1%81?ref=%D3%98%D0%9B%D0%86"
    doc = pipeline.new_case(CaseInput(title="IRI", materials=[
        MaterialInput(text="Тіркел, бонус ал!", url=unicode_url),
        MaterialInput(text="Тіркел, бонус ал!", url=encoded_url),
    ]))
    pipeline.analyze(doc, fetch=links.SyntheticTransport({
        encoded_url: {"status": 200, "body": "Казино, слоты и депозит"}
    }))
    assert doc["status"] == "completed" and doc["trace"]["requests"] == 1
    assert [o["url"] for o in doc["trace"]["observations"]] == [unicode_url, encoded_url]
    assert len({item["scope"] for item in doc["identifiers"]}) == 1
    assert any(edge["type"] == "matching_identifier" for edge in doc["graph"]["edges"])


def test_literal_unicode_and_percent_encoded_delimiter_do_not_merge():
    urls = ["https://entry.test/ұтыс?ref=ABC", "https://entry.test/ұтыс%3Fref=ABC"]
    result = links.trace(urls, links.SyntheticTransport({url: {"status": 200, "body": "Page"} for url in urls}))
    assert result["requests"] == 2


def test_ref_parameter_names_are_not_assumed_case_insensitive():
    lower = links.identifiers("https://entry.test/?ref=ABC")[0]
    upper = links.identifiers("https://entry.test/?REF=ABC")[0]
    assert lower["scope"] != upper["scope"]
    assert upper["parameter"] == "REF"


def test_invalid_utf8_in_identifiers_does_not_create_a_false_match():
    first = links.identifiers("https://entry.test/?ref=%FF%FF")
    second = links.identifiers("https://entry.test/?ref=%FE%FE")
    assert first == second == []


@pytest.mark.parametrize("url", ["https://entry.test/%QQ", "https://entry.test/?ref=one%2", "https://entry.test/\ud800"])
def test_invalid_percent_or_unicode_is_rejected_before_becoming_evidence(url):
    with pytest.raises(links.LinkBlocked):
        links.validate_url(url)
