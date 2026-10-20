"""A bounded route must report the work it could not inspect."""

from backend import pipeline
from backend.links import SyntheticTransport, trace
from backend.schemas import CaseInput, MaterialInput


def test_page_fanout_limit_is_visible_and_marks_analysis_partial():
    start = "https://branch.test/"
    pages = {
        start: {"status": 200, "body": "".join(f'<a href="/{i}">Offer {i}</a>' for i in range(4))},
        **{f"https://branch.test/{i}": {"status": 200, "body": "A normal page"} for i in range(4)},
    }
    doc = pipeline.new_case(CaseInput(title="Branches", materials=[MaterialInput(url=start)]))
    pipeline.analyze(doc, fetch=SyntheticTransport(pages))

    assert len(doc["trace"]["observations"]) == 4
    assert doc["status"] == "partial"
    assert doc["stages"]["links"] == "partial"
    assert not doc["sufficient_data"]
    assert doc["trace"]["unvisited"] == [
        {"url": "https://branch.test/3", "from": start, "type": "page_link", "reason": "page_link_limit"}
    ]
    assert any("3" in text and "ссыл" in text for text in doc["limitations"])


def test_initial_url_limit_records_skipped_material_addresses():
    urls = [f"https://start.test/{i}" for i in range(13)]
    pages = {url: {"status": 200, "body": "A page"} for url in urls}
    result = trace(urls, SyntheticTransport(pages))
    assert result["requests"] == 12
    assert len(result["observations"]) == 12
    assert result["unvisited"] == [
        {"url": urls[-1], "from": None, "type": "contains_link", "reason": "initial_url_limit"}
    ]
    assert result["observations"][-1]["budget_warning"]


def test_per_source_url_extraction_limit_does_not_look_complete():
    urls = [f"https://source.test/{i}" for i in range(13)]
    pages = {url: {"status": 200, "body": "A page"} for url in urls}
    doc = pipeline.new_case(CaseInput(title="Many URLs", materials=[MaterialInput(text="\n".join(urls))]))
    pipeline.analyze(doc, fetch=SyntheticTransport(pages))
    assert doc["status"] == "partial"
    assert doc["stages"]["features"] == "partial"
    assert not doc["sufficient_data"]
    assert any("12" in text and "ссыл" in text for text in doc["limitations"])


def test_single_route_does_not_report_a_false_budget_gap():
    result = trace(["https://go.safetrace.test/r/q7"], SyntheticTransport())
    assert result["unvisited"] == []
    assert not any(o.get("budget_warning") for o in result["observations"])
