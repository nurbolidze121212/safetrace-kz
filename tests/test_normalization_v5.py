import pytest

from backend.analysis import local_context, verify_claims
from backend.normalization import lexical_view


@pytest.mark.parametrize("word", ["к@зино", "к а з и н о", "kаzиno", "к🅰️зино", "казин🅾️", "kazino"])
def test_obfuscated_gambling_retains_original_evidence(word):
    text = "Сообщение 🙂: Играй в " + word + ", забирай бонус."
    claims, rejected = verify_claims(local_context({"s": text}), {"s": text})
    assert not rejected
    game = next(c for c in claims if c["kind"] == "gambling")
    assert game["quote"] == word and text[game["start"]:game["end"]] == word


def test_normalizer_does_not_rewrite_url_or_infer_from_single_emoji():
    address = "https://k@zino.example/a?ref=A0"
    value, _ = lexical_view(address + " 🅰️ 🅾️")
    assert value.startswith(address.casefold())
    assert not local_context({"s": address + " 🅰️ 🅾️"}).claims


@pytest.mark.parametrize("text", [
    "Казиноға тіркелмеңіз, ақша салмаңыз!",
    "Құмар ойын ойнамаңыз, бұл қауіпті.",
    "Ал казино туралы жаңалықты редакция хабарлайды.",
    "Бұл казино емес. Дүкенге тіркел, бонус ал.",
    "Kazino emes. Qosylmanyz!",
])
def test_kazakh_negative_context_does_not_become_positive_call(text):
    context = local_context({"s": text})
    assert not context.contradictions
    if "емес" in text or "emes" in text:
        assert not any(c.kind == "gambling" for c in context.claims)


def test_kazakh_al_conjunction_is_not_a_commercial_call():
    context = local_context({"s": "Ал казино туралы бәрі біледі."})
    assert not any(c.kind == "call_to_action" for c in context.claims)


def test_kazakh_positive_imperative_still_matches():
    result = local_context({"s": "Казиноға тіркел, ақшаға ойнаңыз, бонус алыңыз."})
    assert {"gambling", "call_to_action", "bonus"} <= {c.kind for c in result.claims}
