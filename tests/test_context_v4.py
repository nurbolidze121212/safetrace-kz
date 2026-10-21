"""New authored regressions; these are development data, not a final benchmark."""

import pytest

from backend import pipeline
from backend.analysis import local_context, verify_claims
from backend.graph import build_graph
from backend.links import SyntheticTransport
from backend.schemas import CaseInput, MaterialInput


def run_case(materials):
    doc = pipeline.new_case(CaseInput(title="DEV v4", mode="synthetic", materials=materials))
    pipeline.analyze(doc, fetch=SyntheticTransport({
        "https://v4-context.test/start?ref=DE42": {"status": 200, "body": "<p>Казино и слоты.</p>"},
    }))
    return doc


@pytest.mark.parametrize("text", [
    "Бесплатная игра завершилась, но теперь играй в нашем\nказино на деньги. Забирай бонус.",
    "Тегін ойын аяқталды, бірақ енді біздің\nказиноға тіркел, бонус ал.",
    "Осторожно с другими сервисами. Играй в нашем\nказино и забирай бонус.",
])
def test_wrapped_commercial_clause_remains_attributable(text):
    doc = run_case([MaterialInput(text=text)])
    assert doc["score"]["value"] >= 65
    claims, rejected = verify_claims(local_context({"m": text}), {"m": text})
    assert not rejected
    assert all(text[c["start"]:c["end"]] == c["quote"] for c in claims)


@pytest.mark.parametrize("text", [
    "Казино обещает выигрыш — заходи, но только за памяткой о рисках.",
    "Журналист описал казино. Переходи к нашей статье о расследовании.",
    "Казино қауіпті, бірақ сабаққа тіркел.",
])
def test_explicit_information_object_is_not_a_commercial_call(text):
    assert run_case([MaterialInput(text=text)])["score"]["value"] < 65


def test_information_call_does_not_hide_other_independent_game_call():
    text = "Переходи к памятке о рисках. Играй в нашем казино и забирай бонус!"
    assert run_case([MaterialInput(text=text)])["score"]["value"] >= 65


def test_identical_content_is_not_independent_referral_confirmation():
    url = "https://v4-context.test/start?ref=DE42"
    first = MaterialInput(text="Заходи, забирай бонус.", url=url, source="Первый импорт")
    duplicate = MaterialInput(text="Заходи,\nзабирай бонус.", url=url, source="Другое заявленное имя")
    single = run_case([first])
    both = run_case([first, duplicate])
    assert single["score"]["value"] == both["score"]["value"] == 80
    assert both["materials"][1]["duplicate_of"] == both["materials"][0]["id"]
    assert not any(e["type"] == "matching_identifier" for e in both["graph"]["edges"])
    assert not any(e["type"] == "matching_identifier" for e in build_graph(single, [both])["edges"])


def test_different_materials_still_provide_a_scoped_match():
    url = "https://v4-context.test/start?ref=DE42"
    doc = run_case([
        MaterialInput(text="Заходи, забирай бонус.", url=url),
        MaterialInput(text="Тіркел, сыйлық ал!", url=url),
    ])
    assert doc["score"]["value"] == 90
    assert any(e["type"] == "matching_identifier" for e in doc["graph"]["edges"])


def test_paragraph_boundary_does_not_join_unrelated_warning_and_call():
    text = "Осторожно: казино рекламирует бонус.\n\nПереходи к расписанию встреч."
    assert run_case([MaterialInput(text=text)])["score"]["value"] < 65
