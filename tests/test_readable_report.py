import io
import json
import zipfile

from bs4 import BeautifulSoup

from backend import pipeline, storage
from backend.exports import package
from backend.links import SyntheticTransport
from backend.schemas import CaseInput, MaterialInput


def unpack(doc):
    archive = zipfile.ZipFile(io.BytesIO(package(doc)))
    return archive, BeautifulSoup(archive.read("report.html").decode(), "html.parser")


def assert_links_resolve(archive, soup):
    ids = [item["id"] for item in soup.select("[id]")]
    assert len(ids) == len(set(ids))
    for link in soup.select("a[href]"):
        target = link["href"]
        if target.startswith("#"):
            assert target[1:] in ids
        else:
            assert target in archive.namelist()


def test_report_keeps_partial_status_and_attributes_priority():
    doc = pipeline.new_case(
        CaseInput(
            title="Три материала",
            mode="synthetic",
            materials=[
                MaterialInput(text="Осторожно: казино опасно.", source="Первый"),
                MaterialInput(text="Играй в казино, забирай бонус.", source="Второй"),
                MaterialInput(text="Переходи.", url="https://r31.test/a", source="Третий"),
            ],
        )
    )
    pipeline.analyze(doc, fetch=SyntheticTransport({}))
    archive, soup = unpack(doc)
    assert "80" in soup.select_one("#summary .priority-value").get_text()
    assert "Частично" in soup.select_one("#summary").get_text()
    assert soup.select_one("#summary a[href='#material-2']")
    assert "Недостаточно данных" in soup.select_one("#material-3").get_text()
    assert soup.select("#causes a[href^='#evidence-']")
    assert_links_resolve(archive, soup)
    assert json.loads(archive.read("case.json"))["score"] == doc["score"]


def test_report_does_not_present_insufficient_case_as_low_risk():
    doc = pipeline.new_case(
        CaseInput(
            title="Нет назначения",
            mode="synthetic",
            materials=[MaterialInput(text="Переходи, бонус.", url="https://q52.test/a")],
        )
    )
    pipeline.analyze(doc, fetch=SyntheticTransport({}))
    _, soup = unpack(doc)
    summary = soup.select_one("#summary")
    assert "Недостаточно данных" in summary.select_one(".priority-value").get_text()
    assert "Низкий" not in summary.get_text()


def test_untrusted_content_is_text_in_every_report_section():
    malicious = '<img src=x onerror="alert(1)"><script>alert(2)</script>'
    doc = pipeline.new_case(
        CaseInput(
            title=malicious,
            mode="synthetic",
            materials=[
                MaterialInput(
                    text=malicious + " Играй в казино.", source='javascript:alert(3) " onclick="alert(4)'
                )
            ],
        )
    )
    pipeline.analyze(doc)
    storage.save(doc)
    storage.add_decision(doc["id"], "needs_data", malicious)
    archive, soup = unpack(doc)
    assert not soup.select("script, iframe, object, embed, img")
    assert not any(name.lower().startswith("on") for item in soup.find_all(True) for name in item.attrs)
    assert malicious in soup.get_text()
    assert "default-src 'none'" in soup.select_one("meta[http-equiv='Content-Security-Policy']")["content"]
    assert_links_resolve(archive, soup)


def test_pending_and_older_cases_export_without_new_fields():
    doc = pipeline.new_case(
        CaseInput(title="Ожидает", mode="synthetic", materials=[MaterialInput(text="Материал")])
    )
    archive, soup = unpack(doc)
    assert "Еще не оценен" in soup.select_one("#summary").get_text()
    assert_links_resolve(archive, soup)
    pipeline.analyze(doc)
    doc["score"].pop("material_id")
    for mat in doc["materials"]:
        mat.pop("score", None)
        mat.pop("context", None)
        mat.pop("sufficient_data", None)
    archive, soup = unpack(doc)
    assert_links_resolve(archive, soup)


def test_cross_case_evidence_is_included_and_linked():
    docs = []
    for source in ("Публикация A", "Публикация B"):
        doc = pipeline.new_case(
            CaseInput(
                title=source,
                mode="synthetic",
                materials=[
                    MaterialInput(
                        text="Переходи, забирай бонус!", source=source, url="https://go.safetrace.test/r/q7"
                    )
                ],
            )
        )
        pipeline.analyze(doc)
        storage.save(doc)
        docs.append(doc)
    archive, soup = unpack(docs[0])
    exported = json.loads(archive.read("case.json"))
    assert len(exported["graph"]["evidence"]) > len(docs[0]["evidence"])
    assert len(soup.select("#evidence article")) == len(exported["graph"]["evidence"])
    assert soup.select_one("#relationships")
    assert_links_resolve(archive, soup)
