import pytest

from backend import pipeline
from backend.analysis import local_context, verify_claims
from backend.links import SyntheticTransport
from backend.schemas import CaseInput, MaterialInput


def analyze(text, page=None):
    url = "https://c34a.test/page" if page else ""
    doc = pipeline.new_case(
        CaseInput(title="Контекст", mode="synthetic", materials=[MaterialInput(text=text, url=url)])
    )
    pipeline.analyze(doc, fetch=SyntheticTransport({url: {"status": 200, "body": page}} if page else {}))
    return doc


@pytest.mark.parametrize(
    "page",
    [
        "<p>Осторожно: казино рекламирует бонус. Не играйте.</p>",
        "<p>Новость: журналист расследует рекламу казино.</p>",
        "<p>Учебный пример: «Играй в казино, забирай бонус».</p>",
        "<p>Тегін ойын: казино, ақшасыз ойын.</p>",
    ],
)
def test_destination_context_prevents_false_promotion(page):
    doc = analyze("Переходи по ссылке и забирай бонус.", page)
    assert doc["score"]["value"] < 65
    observation = doc["trace"]["observations"][0]
    assert observation["context"]["context"] in {"warning", "news", "education", "free_game"}
    reasons = doc["score"]["contributions"]
    assert any(c["key"] == "destination_alternative_context" and c["evidence_ids"] for c in reasons)
    known = {e["id"] for e in doc["evidence"]}
    assert all(eid in known for c in reasons for eid in c["evidence_ids"])


@pytest.mark.parametrize(
    "text",
    [
        "Осторожно с другими сервисами. Играй в нашем казино, забирай бонус.",
        "Новости казино. Регистрируйся, забирай фриспины.",
        "Урок закончился. Играй в казино и получай бонус.",
        "Тегін ойын аяқталды. Енді казиноға тіркел, бонус ал!",
    ],
)
def test_independent_commercial_call_survives_alternative_prefix(text):
    doc = analyze(text)
    assert doc["score"]["value"] >= 65
    assert doc["materials"][0]["context"]["contradictions"]


@pytest.mark.parametrize(
    "text",
    [
        "Урок: «Играй в казино и забирай бонус». Пример для разбора.",
        "Осторожно! Не играй в казино, не забирай бонус.",
        "Тегін ойын. Казиноға тіркел, виртуалды бонус ал. Ақшасыз, ақша шығару жоқ.",
        "Новости: журналист пишет о казино. Переходи к статье о расследовании.",
    ],
)
def test_alternative_is_not_cancelled_by_any_imperative(text):
    assert analyze(text)["score"]["value"] < 65


@pytest.mark.parametrize(
    "text",
    [
        "Переходи за строительной рулеткой, лентой и бонусом.",
        "Переходи в банк: процентная ставка и бонус за депозит.",
        "Переходи: свободный слот для записи на прием.",
        "Переходи, здесь нет казино, слотов и ставок на деньги.",
    ],
)
def test_explicit_other_meanings_and_negation_do_not_create_gambling(text):
    assert analyze(text)["score"]["value"] < 65


def test_local_disambiguation_does_not_erase_separate_real_gambling():
    text = "Процентная ставка банка. Но переходи в казино: ставки на спорт и бонус."
    doc = analyze(text)
    assert doc["score"]["value"] >= 65
    claims, rejected = verify_claims(local_context({"m": text}), {"m": text})
    assert not rejected
    assert all(text[c["start"] : c["end"]] == c["quote"] for c in claims)
    assert any(c["quote"] == "ставки" for c in claims)
    assert not any(c["quote"] == "ставка" for c in claims)


def test_destination_disclaimer_does_not_hide_independent_promotion():
    doc = analyze(
        "Переходи и забирай бонус.", "<p>Осторожно: бывают проигрыши. Играй в нашем казино на деньги.</p>"
    )
    assert doc["score"]["value"] >= 65


def test_warning_page_does_not_lower_explicit_source_promotion():
    doc = analyze("Играй в казино и забирай бонус!", "<p>Осторожно: казино и мошенники.</p>")
    assert doc["score"]["value"] >= 65
    assert any(c["key"] == "gambling_and_call" for c in doc["score"]["contributions"])


def test_negative_scope_ends_at_contrast_clause():
    doc = analyze("Здесь нет казино, но играй в слоты на деньги, бонус уже готов.")
    assert doc["score"]["value"] >= 65
