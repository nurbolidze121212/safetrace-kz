"""Frozen, author-labeled 80-case text-only checks for each secondary track."""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluate_v5 import hashes  # noqa: E402
from report_v5 import confusion  # noqa: E402

from backend import pipeline, storage  # noqa: E402
from backend.schemas import CaseInput, MaterialInput  # noqa: E402

TEMPLATES = {
    "track1": {
        1: ["Взнос {amount} тг, колесо случайно выберет победителя.",
            "Купи номер за {amount} тг, розыгрыш приза проведём случайно.",
            "Оплати билет {amount} тг. Лотерея и жеребьёвка сегодня.",
            "Жарна {amount} тг, ұтысқа қатыс: кездейсоқ жеңімпаз.",
            "Прямой эфир: перевод на карту {amount} тг за слот в розыгрыше."],
        0: ["Бесплатный розыгрыш книги, взнос не нужен. Победитель случайный.",
            "Новости: организаторы брали взнос и проводили колесо, прокуратура расследует.",
            "Легальный концерт: купи билет {amount} тг, места по рядам.",
            "Тегін байқау, жарна жоқ, кітап сыйлығы бар.",
            "Магазин продаёт строительное колесо за {amount} тг. Оплата заказа."]},
    "track3": {
        1: ["Вложи {amount} тг, получи {return_amount} тг через неделю. Осталось 3 места, куратор.",
            "Қаржы сал {amount} тг, екі есе табыс ал. Бүгін ғана.",
            "Переводи на личную карту через Kaspi {amount} тг, гарантированная прибыль {return_amount} тг.",
            "Вложи {amount}, получи {return_amount}; пригласи друзей за бонус.",
            "Аqsha sal {amount}, alasyng {return_amount}. Oryn qaldy."],
        0: ["Банк объясняет процентную ставку по вкладу {amount} тг без обещания удвоения.",
            "Новости: мошенники писали «вложи {amount}, получи {return_amount}». Не переводите деньги.",
            "Магазин: цена товара {amount} тг, Kaspi оплата по чеку.",
            "Ескерту: қаржы салмаңыз, алаяққа сенбеңіз.",
            "Куратор учебной группы объясняет инвестиционный риск. Обещаний выплат нет."]}}


def main():
    target = ROOT / "reports/versions/synthetic-v5/track-extensions.json"
    if target.exists():
        raise FileExistsError(target)
    freeze = json.loads((ROOT / "reports/versions/synthetic-v5/core-freeze.json").read_text(encoding="utf-8"))
    assert freeze["analysis_hashes"] == hashes(ROOT), "Rules changed since freeze"
    cases, report = [], {"provenance": "80 authored synthetic texts and author intent per extension; not independent or human labels",
                         "frozen_at": freeze["at"], "tracks": {}}
    with tempfile.TemporaryDirectory(prefix="safetrace-extensions-") as directory:
        from backend import config

        old = config.DATA
        config.DATA = Path(directory)
        storage.DATA = Path(directory)
        storage.init()
        try:
            for track, labels in TEMPLATES.items():
                measured = []
                for truth, templates in labels.items():
                    for template in templates:
                        for variant in range(8):
                            text = template.format(amount=5000 + variant * 100, return_amount=10000 + variant * 200)
                            key = hashlib.sha256((track + text).encode()).hexdigest()[:20]
                            doc = pipeline.new_case(CaseInput(title="Authored secondary-track check", mode="synthetic",
                                                              materials=[MaterialInput(text=text)]))
                            pipeline.analyze(doc)
                            entry = doc["extensions"]["materials"][0][track]
                            predicted = int(entry["level"] == "high" and doc["sufficient_data"])
                            cases.append({"id": key, "track": track, "author_truth": truth, "text": text,
                                          "predicted": predicted, "level": entry["level"], "score": entry["value"],
                                          "sufficient": doc["sufficient_data"], "signals": entry["signals"]})
                            measured.append((truth, predicted, entry["level"], doc["sufficient_data"]))
                report["tracks"][track] = confusion(measured)
        finally:
            config.DATA = old
            storage.DATA = old
    assert len(cases) == 160 and freeze["analysis_hashes"] == hashes(ROOT)
    report["cases"] = cases
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report["tracks"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
