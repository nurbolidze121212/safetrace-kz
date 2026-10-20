"""Static HTML navigation must resolve against the document base without wasting its budget."""

import pytest

from backend import links, pipeline
from backend.schemas import CaseInput, MaterialInput


@pytest.mark.parametrize("base_href,destination", [
    ("https://destination.test/offers/", "https://destination.test/offers/play?ref=ONE"),
    ("../offers/", "https://entry.test/offers/play?ref=ONE"),
])
def test_document_base_resolves_relative_links_and_keeps_source_attributes(base_href, destination):
    start = "https://entry.test/start/page"
    result = links.trace([start], links.SyntheticTransport({
        start: {"status": 200, "body": f'<base href="{base_href}"><a href="play?ref=ONE">Предложение</a>'},
        destination: {"status": 200, "body": "Слоты и депозит"},
    }))
    assert [o["url"] for o in result["observations"]] == [start, destination]
    assert not any(o["stop"] for o in result["observations"])
    relation = result["relations"][-1]
    assert relation["href"] == "play?ref=ONE" and relation["base_href"] == base_href
    assert relation["quote"] == "Предложение"


def test_only_the_first_real_base_href_is_used():
    body = '<template><base href="https://ignored.test/"></template><base target="_self">'
    body += '<base href="/first/"><base href="/second/"><a href="next">Open</a>'
    result = links.page_content(body.encode(), "https://entry.test/start")
    assert result["links"][0]["url"] == "https://entry.test/first/next"


def test_duplicate_anchors_do_not_hide_a_later_unique_destination():
    start, destination = "https://entry.test/", "https://entry.test/game"
    body = '<a href="/about">About</a>' * 10 + '<a href="/game">Предложение</a>'
    result = links.trace([start], links.SyntheticTransport({
        start: {"status": 200, "body": body},
        "https://entry.test/about": {"status": 200, "body": "About"},
        destination: {"status": 200, "body": "Слоты и депозит"},
    }))
    assert result["requests"] == 3
    assert [o["url"] for o in result["observations"]] == [start, "https://entry.test/about", destination]
    assert not result["unvisited"]


def test_contact_links_do_not_spend_the_web_route_budget():
    start = "https://entry.test/"
    body = '<a href="mailto:a@example.test">Email</a><a href="tel:+70000000000">Phone</a>'
    body += '<a href="mailto:b@example.test">Contact</a><a href="/game">Open</a>'
    result = links.trace([start], links.SyntheticTransport({
        start: {"status": 200, "body": body},
        "https://entry.test/game": {"status": 200, "body": "Destination"},
    }))
    assert result["requests"] == 2 and len(result["observations"]) == 2
    assert result["observations"][0]["non_web_link_count"] == 3
    assert not result["unvisited"] and not any(o["stop"] for o in result["observations"])


def test_a_malformed_link_does_not_discard_the_page_or_its_other_links():
    start = "https://entry.test/"
    result = links.trace([start], links.SyntheticTransport({
        start: {"status": 200, "body": '<a href="http://[broken">Bad</a><a href="/game">Open</a>'},
        "https://entry.test/game": {"status": 200, "body": "Destination"},
    }))
    assert result["observations"][0]["text"] == "Bad Open"
    assert result["observations"][1]["stop"] == "Некорректный URL"
    assert result["observations"][2]["text"] == "Destination"


def test_local_fragment_navigation_does_not_create_a_false_cycle():
    start = "https://entry.test/"
    result = links.trace([start], links.SyntheticTransport({
        start: {"status": 200, "body": '<a href="#content">Content</a><a href="/game">Open</a>'},
        "https://entry.test/game": {"status": 200, "body": "Content"},
    }))
    assert result["requests"] == 2
    assert len(result["observations"]) == 2
    assert not any(o["stop"] for o in result["observations"])


def test_fragment_reference_with_another_document_base_is_a_real_destination():
    start, destination = "https://entry.test/", "https://destination.test/offer#content"
    result = links.trace([start], links.SyntheticTransport({
        start: {"status": 200, "body": '<base href="https://destination.test/offer"><a href="#content">Open</a>'},
        destination: {"status": 200, "body": "Destination"},
    }))
    assert result["observations"][-1]["url"] == destination
    assert not result["observations"][-1]["stop"]


def test_private_destination_in_base_is_blocked_before_connection(monkeypatch):
    start = "https://entry.test/"
    monkeypatch.setattr(links, "offline", lambda: False)

    def no_connection(*args):
        raise AssertionError("A private destination must never reach a socket")

    monkeypatch.setattr(links, "PinnedHTTP", no_connection)

    def fetch(url):
        if url == start:
            return 200, {"content-type": "text/html"}, b'<base href="http://127.0.0.1/"><a href="private">Open</a>'
        return links.live_fetch(url)

    result = links.trace([start], fetch)
    assert result["observations"][-1]["url"] == "http://127.0.0.1/private"
    assert result["observations"][-1]["stop"] == "IP-адреса в URL не разрешены в live-режиме"


def test_page_link_evidence_contains_raw_href_and_resolved_base():
    start, destination = "https://entry.test/", "https://destination.test/offer"
    doc = pipeline.new_case(CaseInput(title="Base", materials=[MaterialInput(url=start)]))
    pipeline.analyze(doc, fetch=links.SyntheticTransport({
        start: {"status": 200, "body": '<base href="https://destination.test/"><a href="offer">Open</a>'},
        destination: {"status": 200, "body": "Казино, слоты, депозит"},
    }))
    relation = next(r for r in doc["trace"]["relations"] if r["type"] == "page_link")
    evidence = next(e for e in doc["evidence"] if e["id"] == relation["evidence_id"])
    assert evidence["href"] == "offer" and evidence["base_href"] == "https://destination.test/"
    assert evidence["document_base"] == "https://destination.test/"
    assert evidence["quote"] == "Open" and evidence["url"] == start
