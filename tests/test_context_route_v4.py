import pytest

from backend import pipeline
from backend.links import SyntheticTransport
from backend.schemas import CaseInput, MaterialInput

URL = "https://t6d48.test/offer"


def analyze(text):
    doc = pipeline.new_case(
        CaseInput(title="Область контекста", mode="synthetic", materials=[MaterialInput(text=text, url=URL)])
    )
    pipeline.analyze(
        doc, fetch=SyntheticTransport({URL: {"status": 200, "body": "Казино, слоты, депозит и бонус."}})
    )
    return doc


@pytest.mark.parametrize(
    "text",
    [
        "Осторожно с чужими сервисами. Заходи к нам и забирай бонус: " + URL,
        "Учебный урок окончен. Переходи в личный кабинет и забирай бонус: " + URL,
        "Алаяқтардан сақ болыңыз. Біздің клубқа қосыл, сыйлық ал: " + URL,
        "Новость: компания выступила с отчётом. Но регистрируйся у нас: " + URL,
    ],
)
def test_independent_call_and_observed_destination_survive_unrelated_disclaimer(text):
    doc = analyze(text)
    assert doc["score"]["value"] >= 65
    assert doc["materials"][0]["context"]["contradictions"]


@pytest.mark.parametrize(
    "text",
    [
        "Для учебного разбора переходи на страницу казино: " + URL,
        "Осторожно: не заходи и не регистрируйся здесь: " + URL,
        "Новость: «Заходи и забирай бонус» — цитата рекламного сообщения. " + URL,
        "Бесплатная игра. Казиноға тіркел, виртуалды бонус ал. Ақшасыз ойын. " + URL,
        "Казино обещает выигрыши, но заходи к нам только за памяткой о рисках. " + URL,
        "Реклама казино есть в архиве; заходи к нам за конспектом исследования. " + URL,
    ],
)
def test_information_and_negative_calls_do_not_borrow_gambling_destination(text):
    assert analyze(text)["score"]["value"] < 65
