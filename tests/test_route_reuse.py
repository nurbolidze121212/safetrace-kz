"""Equivalent request URLs may reuse bytes without losing either material's path."""

import pytest

from backend import pipeline
from backend.links import SyntheticTransport, trace
from backend.schemas import CaseInput, MaterialInput


@pytest.mark.parametrize("redirect", [False, True])
def test_normalized_alias_keeps_source_url_and_outgoing_path(redirect):
    lower = "https://entry.test/"
    alias = "https://ENTRY.test/#offer"
    destination = "https://entry.test/game?ref=ONE"
    pages = {
        lower: {"status": 302, "headers": {"location": "/game?ref=ONE"}} if redirect else {
            "status": 200, "body": '<a href="/game?ref=ONE">Open offer</a>'
        },
        destination: {"status": 200, "body": "Казино: слоты, депозит."},
    }
    result = trace([lower, alias], SyntheticTransport(pages))
    alias_observation = next(o for o in result["observations"] if o.get("reused_from"))
    assert alias_observation["url"] == alias
    relation = next(r for r in result["relations"] if r["from"] == alias)
    assert relation["to"] == destination
    assert relation["type"] == ("redirects" if redirect else "page_link")
    assert relation["quote"] == ("/game?ref=ONE" if redirect else "Open offer")
    assert result["requests"] == 2
    assert not any(o["stop"] for o in result["observations"])


def test_two_materials_with_equivalent_entry_urls_both_reach_the_destination():
    lower = "https://entry.test/"
    alias = "https://ENTRY.test/#offer"
    destination = "https://entry.test/game?ref=ONE"
    pages = {
        lower: {"status": 200, "body": '<a href="/game?ref=ONE">Open offer</a>'},
        destination: {"status": 200, "body": "Казино: слоты, депозит."},
    }
    doc = pipeline.new_case(CaseInput(title="Aliases", mode="synthetic", materials=[
        MaterialInput(text="Переходи, забирай бонус!", url=url, source=f"source-{index}")
        for index, url in enumerate((lower, alias))
    ]))
    pipeline.analyze(doc, fetch=SyntheticTransport(pages))
    assert doc["status"] == "completed" and doc["sufficient_data"]
    assert all(destination in material["reachable_urls"] for material in doc["materials"])
    assert all(material["score"]["value"] >= 65 for material in doc["materials"])
    assert any(edge["type"] == "matching_identifier" for edge in doc["graph"]["edges"])


def test_synthetic_transport_uses_the_same_normalized_request_key():
    result = trace(["https://ENTRY.test#fragment"], SyntheticTransport({
        "https://entry.test/": {"status": 200, "body": "A page"}
    }))
    assert result["observations"][0]["status_code"] == 200


def test_query_values_remain_distinct_when_reusing_observations():
    urls = ["https://entry.test/?ref=ABC", "https://entry.test/?ref=abc"]
    result = trace(urls, SyntheticTransport({url: {"status": 200, "body": f"<p>{url}</p>"} for url in urls}))
    assert result["requests"] == 2
    assert not any(o.get("reused_from") for o in result["observations"])


def test_empty_query_delimiter_is_not_merged_with_an_absent_query():
    urls = ["https://entry.test/", "https://entry.test/?"]
    result = trace(urls, SyntheticTransport({
        url: {"status": 200, "body": f"<p>Page {index}</p>"} for index, url in enumerate(urls)
    }))
    assert result["requests"] == 2
    assert [o["text"] for o in result["observations"]] == ["Page 0", "Page 1"]


def test_reuse_does_not_bypass_the_depth_limit():
    pages = {"https://leaf.test/": {"status": 200, "body": "<p>Leaf</p>"}}
    pages.update({
        f"https://chain.test/{index}": {"status": 302, "headers": {
            "location": f"https://chain.test/{index + 1}" if index < 4 else "https://LEAF.test/#a"
        }} for index in range(5)
    })
    result = trace(["https://leaf.test/", "https://chain.test/0"], SyntheticTransport(pages))
    last = result["observations"][-1]
    assert last["depth"] == 5
    assert last["stop"] == "Лимит глубины"


def test_live_request_preserves_an_explicit_empty_query(monkeypatch):
    from urllib.parse import urlsplit

    from backend import links

    targets = []

    class Response:
        status = 200

        def getheaders(self):
            return [("content-type", "text/html")]

        def read1(self, size):
            return b""

    class Connection:
        def __init__(self, *args):
            pass

        def request(self, method, target, **kwargs):
            targets.append(target)

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(links, "offline", lambda: False)
    monkeypatch.setattr(links, "resolve_public", lambda url: (urlsplit(url), "8.8.8.8"))
    monkeypatch.setattr(links, "PinnedHTTP", Connection)
    links.live_fetch("https://entry.test/?#section")
    assert targets == ["/?"]


def test_relative_redirect_can_explicitly_clear_the_query():
    start, destination = "https://entry.test/offer?old=1", "https://entry.test/offer?"
    result = trace([start], SyntheticTransport({
        start: {"status": 302, "headers": {"location": "?"}},
        destination: {"status": 200, "body": "<p>Destination</p>"},
    }))
    assert result["requests"] == 2
    assert result["observations"][-1]["url"] == destination
    assert result["observations"][-1]["text"] == "Destination"
