"""Render the saved final comparison and apply the predeclared release decision."""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/versions/synthetic-v4"


def read(name):
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def pct(value):
    return "—" if value is None else f"{100 * value:.2f}%"


def interval(values):
    return "—" if values is None else "–".join(pct(v) for v in values)


def row(name, m):
    return (
        "| "
        + " | ".join(
            [
                name,
                *[str(m[k]) for k in ("n", "tp", "fp", "tn", "fn")],
                *[pct(m[k]) for k in ("precision", "recall", "fpr", "f1")],
                f"{m['processed_n']}/{m['n']}",
            ]
        )
        + " |"
    )


def main():
    old, new, paired = read("v3-evaluation.json"), read("evaluation.json"), read("comparison.json")
    a, b = old["variants"]["full"], new["variants"]["full"]
    old_urls, new_urls = old["extraction"]["automatic_url"], new["extraction"]["automatic_url"]
    checks = {
        "fp_not_increased": b["fp"] <= a["fp"],
        "wrong_automatic_urls_not_increased": new_urls["fp"] <= old_urls["fp"],
        "measurable_advantage": new_urls["fp"] < old_urls["fp"] or b["tp"] + b["tn"] > a["tp"] + a["tn"],
        "recall_loss_at_most_one_positive": b["tp"] >= a["tp"] - 1,
    }
    decision = {
        "at": datetime.now(timezone.utc).isoformat(),
        "protocol": "docs/EVALUATION_PROTOCOL_V4.md",
        "checks": checks,
        "selected": "v4" if all(checks.values()) else "v3",
        "scope": "Predeclared metric selection for a local MVP, subject to final preservation/launch/transfer acceptance. No population-quality guarantee.",
    }
    with (BASE / "selection.json").open("x", encoding="utf-8") as file:
        json.dump(decision, file, ensure_ascii=False, indent=2)
    chosen = decision["selected"]
    lines = [
        "# Новое сравнение SafeTrace KZ: v3 и v4",
        "",
        f"Выбор по заранее зафиксированному правилу: **{chosen}**. "
        + (
            "V4 проходит количественные условия допуска; окончательная передача дополнительно требует сохранности данных и проверенного запуска."
            if chosen == "v4"
            else "V4 сохраняется как эксперимент, архивная v3 остаётся рекомендуемой стабильной конфигурацией. Условия не менялись после просмотра результата."
        ),
        "",
        "80 новых авторских синтетических случаев, 40+/40−, 32 изображения, 8 QR. Русский 28, казахский 19, смешанный 26, транслит 7. Автор данных и правил один; независимых разметчиков нет. Метки загружены агрегатором после сохранения обоих worker-выходов. Ручных уточнений в этих предсказаниях нет.",
        "",
        "Ядро 2.2.1 / rules-4.0 / pipeline-2.2.1 заморожено 22.10.2026 в 01:37:49 Asia/Qyzylorda, до генерации новых данных в 01:41:52. Численные веса прежние. Положительный результат требует индекса ≥65 и достаточных данных. Положительные отказы включены в FN. Полные хеши: core-freeze.json и data-freeze.json рядом с исходными предсказаниями.",
        "",
        "## Результаты на одинаковых входах",
        "",
        "| Вариант | N | TP | FP | TN | FN | Precision | Recall | FPR | F1 | Достаточно данных |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        row("v3 full", a),
        *[row("v4 " + k, m) for k, m in new["variants"].items()],
        "",
        f"Парно исправлено {paired['corrected']} классификаций, ухудшено {paired['regressed']}. "
        "Список изменений, включая достаточность данных, сохранён в comparison.json. Исторические TP32/FP1/FN8 v3 относятся к другому набору; прямое вычитание его процентов из новых некорректно.",
        "",
        "Baseline — ключевые слова без пикселей; OCR-вариант добавляет распознавание и локальный контекст, full — контролируемые назначения и граф. Сравнение этих вариантов не изолирует отдельный вклад графа или OCR.",
        "",
        "## Неопределённость и отказ от решения",
        "",
        "| Версия | 95% precision | 95% recall | 95% FPR | Без данных | Precision обработанных | Recall обработанных |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for name, m in [("v3", a), ("v4", b)]:
        lines.append(
            f"| {name} | {interval(m['precision_ci'])} | {interval(m['recall_ci'])} | {interval(m['fpr_ci'])} | {m['insufficient']} | {pct(m['processed_precision'])} | {pct(m['processed_recall'])} |"
        )
    lines += [
        "",
        "Wilson 95% отражает выборочную неопределённость при соответствующих предпосылках, но не устраняет авторский подбор и зависимости конструкций. Малые языковые группы не доказывают устойчивость на реальном потоке. Нулевой знаменатель обозначается отсутствием значения.",
        "",
        "## Точность извлечения из изображений",
        "",
        "| Извлечение | Версия | N изображений | Точных наборов | TP адресов/payload | FP | FN | Precision | Recall |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    fields = {
        "raw_url_expected": "Сырой URL, есть эталон",
        "automatic_url_expected": "Автоматический URL, есть эталон",
        "automatic_url": "Автоматический URL, все",
        "raw_domain": "Hostname, все",
        "raw_referral": "Непустой query",
        "qr_expected": "QR, есть эталон",
        "qr": "QR, все",
    }
    for key, label in fields.items():
        for version, report in [("v3", old), ("v4", new)]:
            m = report["extraction"][key]
            lines.append(
                f"| {label} | {version} | {m['n']} | {m['exact_sets']} | {m['tp']} | {m['fp']} | {m['fn']} | {pct(m['precision'])} | {pct(m['recall'])} |"
            )
    lines += [
        "",
        f"Наличие всех правильных видимых URL среди первичного чтения/подсказок v4: {new['extraction']['correct_candidate_available']}/{new['extraction']['candidate_denominator']}. Это возможность ручной сверки, не автоматический успех. Точное совпадение сохраняет символы URL. Query — полная упорядоченная последовательность непустых параметров, значение чувствительно к регистру. Пустые ожидаемые наборы отдельно видны в метриках всех изображений.",
        "",
        "## Срезы полного процесса v4",
        "",
        "| Срез | N | TP | FP | TN | FN | Precision | Recall | FPR | F1 | Достаточно данных |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        *[row(k, m) for k, m in new["slices"].items()],
        "",
        "Срезы v3 сохранены в v3-evaluation.json на тех же входах; не смешивать их с historical synthetic-v3.",
        "",
        "## Скорость",
        "",
        "| Версия | Загрузка основной модели, мс | Весь процесс на изображениях p50/p95, мс | OCR p50/p95, мс |",
        "|---|---:|---:|---:|",
    ]
    for version, report in [("v3", old), ("v4", new)]:
        m, t = report["slices"]["image"], report["ocr_timing"]
        lines.append(
            f"| {version} | {report['model_initialization_ms']:.1f} | {m['p50_ms']:.1f} / {m['p95_ms']:.1f} | {t['p50_ms']:.1f} / {t['p95_ms']:.1f} |"
        )
    lines += [
        "",
        "Windows, CPU, последовательные запуски, основной OCR предварительно загружен, кэш содержимого выключен. V4 full идёт после OCR-варианта; вторичная английская модель к этому времени может быть тёплой. Измерения не изолируют холодную стоимость предложения. Контролируемый транспорт не измеряет задержку интернета или Gemini. Холодный API, кэш и очередь: отдельный reports/acceptance-v4/runtime.json.",
        "",
        "## Решение о конфигурации",
        "",
        *[f"- {key}: {'пройдено' if value else 'не пройдено'}." for key, value in checks.items()],
        "",
        "Предел потери recall — один положительный из 40; допустимое снижение покрытия должно быть раскрыто. Условия выбраны до теста. Это инженерное правило выпуска ограниченного MVP, не доказательство статистического превосходства. Новые изменения ядра потребуют новой версии и свежей оценки.",
        "",
        "## Все ошибки v4",
        "",
        "| ID | Truth | Результат | Индекс | Достаточно |",
        "|---|---:|---:|---:|---|",
        *[
            f"| {r['id']} | {r['truth']} | {r['predicted']} | {r['score']} | {r['sufficient']} |"
            for r in new["errors"]
        ],
        "",
        "Построчный разбор причин сохраняется отдельно в ERROR_ANALYSIS_V4.md после чтения исходных наблюдений. Исправления по этому тесту в замороженное ядро не вносятся.",
        "",
        "## Воспроизведение и границы",
        "",
        "[Протокол](../docs/EVALUATION_PROTOCOL_V4.md), [данные и команды](../docs/DATASET_V4.md), [ограничения](../docs/LIMITATIONS.md). JSON/CSV предсказаний и полные случаи находятся в reports/versions/synthetic-v4. scripts/verify_version_v4.py сверяет хеши и независимо пересчитывает матрицы. Внешний live-пилот, Gemini, независимый аналитик, другая физическая машина, GPU и Linux не подтверждены.",
    ]
    with (ROOT / "reports/EVALUATION_V4.md").open("x", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    print(json.dumps(decision, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
