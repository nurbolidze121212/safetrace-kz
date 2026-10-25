import pytest

from backend.track_extensions import analyze, from_materials


@pytest.mark.parametrize("text,track,level", [
    ("Взнос 500 тенге, колесо выберет победителя.", "track1", "high"),
    ("Тегін ұтыс, жарна жоқ.", "track1", "low"),
    ("Вложи 5000, получи 10000. Осталось 3 места. Куратор.", "track3", "high"),
    ("Оплата кафе через Kaspi, честная скидка 10%.", "track3", "low"),
    ("Не вкладывай деньги! Осторожно, мошенники обещают удвоить вклад.", "track3", "low"),
    ("Жаңа орын: қаржы сал, екі есе табыс ал!", "track3", "high"),
])
def test_extensions_keep_quotes_and_do_not_classify_payment_alone(text, track, level):
    result = analyze(text, "source")[track]
    assert result["level"] == level
    assert all(text[s["start"]:s["end"]] == s["quote"] for s in result["signals"])


def test_signs_from_different_materials_are_not_combined():
    result = from_materials([{"id": "a", "text": "Вложи 5000"}, {"id": "b", "text": "Получи 10000"}])
    assert all(m["track3"]["level"] == "low" for m in result["materials"])
