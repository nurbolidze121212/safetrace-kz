"""Authored development counterexamples before the v3 core freeze."""

import pytest

from backend import pipeline
from backend.analysis import local_context, verify_claims
from backend.links import SyntheticTransport
from backend.schemas import CaseInput, MaterialInput

NEGATIVES = [
    "Осторожно: казино опасно, но переходи к нашей памятке.",
    "Новость о казино, однако заходи на страницу расследования.",
    "Учебный разбор: казино обещает бонус, зато забирай наш конспект.",
    "Казино қауіпті, бірақ сабаққа тіркел.",
    "Бесплатная игра: виртуальное казино, но играйте без денежных ставок.",
    "Тегін ойын: казино, бірақ тіркел, ақшасыз ойна.",
    "Новость: «но играй в казино и забирай бонус» — цитата из рекламы.",
    "Осторожно: казино рекламируют мошенники, но не играй и не забирай бонус.",
]
POSITIVES = [
    "Осторожно с чужими сервисами, но играй в нашем казино и забирай бонус.",
    "Новость дня, однако регистрируйся в казино и забирай фриспины.",
    "Учебный урок окончен, зато играй в казино на деньги.",
    "Алаяқтардан сақ бол, бірақ біздің казиноға тіркел, бонус ал.",
    "Бесплатная игра закончилась, но теперь играй в казино на деньги.",
    "Тегін ойын аяқталды, бірақ енді казиноға тіркел, бонус ал.",
    "Осторожно: бывают проигрыши. Играй в нашем казино и забирай бонус.",
    "Переходи в казино, но осторожно: возможны проигрыши.",
]


@pytest.mark.parametrize("text", NEGATIVES)
def test_contrast_does_not_turn_information_call_into_promotion(text):
    result = local_context({"m": text})
    assert not result.contradictions
    valid, rejected = verify_claims(result, {"m": text})
    assert valid and not rejected
    doc = pipeline.new_case(
        CaseInput(title="Граница", mode="synthetic", materials=[MaterialInput(text=text)])
    )
    pipeline.analyze(doc)
    assert doc["score"]["value"] < 65


@pytest.mark.parametrize("text", POSITIVES)
def test_independent_game_call_in_own_clause_still_counts(text):
    result = local_context({"m": text})
    assert result.contradictions
    valid, rejected = verify_claims(result, {"m": text})
    assert valid and not rejected
    doc = pipeline.new_case(
        CaseInput(title="Граница", mode="synthetic", materials=[MaterialInput(text=text)])
    )
    pipeline.analyze(doc)
    assert doc["score"]["value"] >= 65


def test_information_contrast_on_destination_does_not_create_game_route():
    url = "https://contrast-dev.test/page"
    doc = pipeline.new_case(
        CaseInput(
            title="Граница страницы",
            mode="synthetic",
            materials=[MaterialInput(text="Переходи по ссылке, забирай бонус.", url=url)],
        )
    )
    pipeline.analyze(doc, fetch=SyntheticTransport({url: {"status": 200, "body": f"<p>{NEGATIVES[0]}</p>"}}))
    assert doc["score"]["value"] < 65
    assert not doc["trace"]["observations"][0]["context"]["contradictions"]
