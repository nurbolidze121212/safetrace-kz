import pytest

from backend import pipeline
from backend.analysis import local_context, verify_claims
from backend.config import RULE_VERSION
from backend.links import SyntheticTransport, extract_urls
from backend.schemas import CaseInput, ContextExtraction, MaterialInput


@pytest.mark.parametrize(
    "text",
    [
        "Это новый материал для проверки. Казино упоминается в названии.",
        "Музыкальный фестиваль и выставка начинаются завтра.",
        "Кітапхананың жаңа сабағы ертең өтеді.",
        "https://casino.example/play?bonus=100&ref=tirkel",
        "Не играйте в казино, не забирайте бонус.",
        "Тіркелмеңіз, қосылмаңыз! Бонус дегенге сенбеңіз.",
    ],
)
def test_no_incidental_or_negated_call(text):
    assert not [c for c in local_context({"m": text}).claims if c.kind == "call_to_action"]


@pytest.mark.parametrize(
    "text",
    [
        "Тіркел де сыйлығыңды ал! Құмар ойын.",
        "Zaregaysya v kazino, bonus gotov.",
        "Переходите, забирайте бонус в казино!",
    ],
)
def test_explicit_calls_keep_exact_source(text):
    ctx = local_context({"m": text})
    valid, rejected = verify_claims(ctx, {"m": text})
    assert not rejected
    assert any(c["kind"] == "call_to_action" for c in valid)
    assert all(text[c["start"] : c["end"]] == c["quote"] for c in valid)


def test_education_inflection_and_banking_context():
    assert local_context({"m": "Бұл медиасауат сабағы: «Тіркел, бонус ал»."}).context == "education"
    assert not any(c.kind == "gambling" for c in local_context({"m": "Открой депозит, бонус банка."}).claims)


def test_contradiction_is_not_quoted_or_negated():
    assert local_context({"m": "Осторожно. Но переходи в казино, бонус!"}).contradictions
    assert not local_context({"m": "Урок: «Но переходи в казино» — пример манипуляции."}).contradictions
    assert not local_context({"m": "Осторожно, но не переходи в казино."}).contradictions


def test_repeated_quote_points_to_actual_nonnegative_occurrence():
    text = "Не переходи. Но переходи, если проверен источник."
    valid, _ = verify_claims(local_context({"m": text}), {"m": text})
    calls = [c for c in valid if c["kind"] == "call_to_action"]
    assert len(calls) == 1
    assert calls[0]["start"] == text.rfind("переходи")


def test_model_supplied_incorrect_offsets_are_rejected():
    value = ContextExtraction(
        language="ru",
        context="promotion",
        contradictions=[],
        limitations=[],
        claims=[
            {
                "kind": "gambling",
                "quote": "казино",
                "source_id": "m",
                "explanation": "test",
                "start": 0,
                "end": 6,
            }
        ],
    )
    valid, rejected = verify_claims(value, {"m": "Это казино"})
    assert not valid and len(rejected) == 1


def test_reanalysis_updates_version():
    doc = pipeline.new_case(
        CaseInput(title="Версия", mode="synthetic", materials=[MaterialInput(text="Материал")])
    )
    doc["versions"]["rules"] = "rules-1.0"
    pipeline.analyze(doc)
    assert doc["versions"]["rules"] == RULE_VERSION
    assert doc["score"]["version"] == RULE_VERSION


@pytest.mark.parametrize(
    "text,expected_high",
    [
        ("Переходи в казино, играйте сегодня.", True),
        ("Осторожно с чужой рекламой. Но переходи в казино, бонус для тебя.", True),
        ("Сақ болыңыз: «Қосыл, бонус ал». Құмар ойынға тіркелмеңіз.", False),
        ("Играй в спектакле «Казино» нашего театра, бонус участникам.", False),
        ("Переходи за компьютером: слоты оперативной памяти и бонус.", False),
        ("Фильм «Казино» закончился. Но переходи в казино, бонус ждет.", True),
    ],
)
def test_development_semantic_counterexamples(text, expected_high):
    doc = pipeline.new_case(
        CaseInput(title="Контекст", mode="synthetic", materials=[MaterialInput(text=text)])
    )
    pipeline.analyze(doc)
    assert (doc["score"]["value"] >= 65) == expected_high


def test_long_destination_url_does_not_break_quote_validation():
    url = "https://long.test/welcome?campaign=" + "a" * 220
    doc = pipeline.new_case(
        CaseInput(
            title="Длинный адрес",
            mode="synthetic",
            materials=[
                MaterialInput(text="Переходи и забирай бонус.", url=url),
            ],
        )
    )
    pipeline.analyze(
        doc, fetch=SyntheticTransport({url: {"status": 200, "body": "<p>Казино, слоты и рулетка.</p>"}})
    )
    assert doc["status"] == "completed" and doc["score"]["value"] >= 65


def test_quote_budget_preserves_alternative_evidence_in_second_source():
    text = "Казино, слоты, рулетка. Играй, переходи, забирай бонус, промокод, фриспины. Выиграй, заработай, ұтыс. Осторожно, мошенники, скам. Новость, журналист, корреспондент. Учебный урок, образовательный разбор. Без ставок, ақшасыз, тегін ойын."
    result = local_context({"first": text, "second": "Медиасауат сабағы. Түсіндіреміз."})
    assert len(result.claims) <= 30
    assert any(c.source_id == "second" and c.kind == "education" for c in result.claims)


def test_explicit_url_keeps_query_punctuation_and_balanced_text_parentheses():
    url = "https://a.test/offer?ref=code!(x)"
    doc = pipeline.new_case(
        CaseInput(
            title="URL",
            mode="synthetic",
            materials=[
                MaterialInput(text="Переходи и забирай бонус.", url=url),
            ],
        )
    )
    pipeline.analyze(doc, fetch=SyntheticTransport({url: {"status": 200, "body": "<p>Казино и слоты.</p>"}}))
    assert doc["trace"]["observations"][0]["url"] == url
    assert doc["score"]["value"] >= 65
    assert extract_urls("Пример: https://a.test/offer?q=(x).") == ["https://a.test/offer?q=(x)"]
