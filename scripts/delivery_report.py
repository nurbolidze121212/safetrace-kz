"""Render measured evaluation and verify the immutable test manifest."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def percent(value):
    return "—" if value is None else f"{100 * value:.2f}%"


def main():
    report = json.loads((REPORTS / "evaluation.json").read_text(encoding="utf-8"))
    frozen = json.loads((REPORTS / "test-freeze.json").read_text(encoding="utf-8"))
    for name, expected in frozen["hashes"].items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert actual == expected, f"Frozen artifact changed: {name}"
    lines = [
        "# Финальная оценка synthetic-v1",
        "",
        f"Результат: {report['frozen_at']}. Windows, Python 3.12.14, CPU. "
        f"Порог {report['threshold']}, правила rules-1.0, веса weights-1.0. "
        "PaddleOCR 3.7.0 / PaddlePaddle 3.3.1; cyrillic_PP-OCRv5_mobile_rec + PP-OCRv5_mobile_det. "
        "Провайдер local_rule; Gemini не оценивался.",
        "",
        "80 случаев: 40 положительных, 40 отрицательных, 27 изображений; "
        "предшествующий dev — 40 случаев. Всего в корпусе 41 изображение. "
        "Авторская синтетическая разметка, без независимой экспертной проверки. "
        "Это не измерение качества на реальных соцсетях.",
        "",
        "## Одинаковые входы, три варианта",
        "",
        "| Вариант | N | TP | FP | TN | FN | Precision | Recall | F1 | FPR | Покрытие | Без данных |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, m in report["variants"].items():
        values = [name, *[str(m[k]) for k in ("n", "tp", "fp", "tn", "fn")]]
        values += [percent(m[k]) for k in ("precision", "recall", "f1", "fpr", "coverage")]
        lines.append("| " + " | ".join(values + [str(m["insufficient"])]) + " |")
    lines += [
        "",
        "Цели precision ≥95% и recall ≥80% **не достигнуты**; FPR ≤5% достигнут "
        "только по точечной оценке. Интервалы широкие, поэтому соответствие цели в популяции не доказано. "
        "Правила после просмотра test не изменялись.",
        "",
        "Baseline использует ключевые слова без изображения и контекста; вариант ocr добавляет "
        "пиксели и локальные контекстные правила, full добавляет переходы и граф. "
        "Поэтому разницу baseline→ocr нельзя целиком приписать OCR. "
        "На изображениях полная система: TP10 FP1 TN12 FN4. "
        "Вспомогательная средняя SequenceMatcher-схожесть OCR с эталонным текстом — "
        f"{report['ocr_mean_sequence_similarity']:.4f}; это не CER и не точность классификации.",
        "",
        "## Неопределенность и задержка",
        "",
        "| Вариант | 95% Wilson precision | 95% Wilson FPR | p50, мс | p95, мс | N обработанных | Precision обработанных | Recall обработанных |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for name, m in report["variants"].items():
        lines.append(
            f"| {name} | {'–'.join(map(percent, m['precision_ci']))} | "
            f"{'–'.join(map(percent, m['fpr_ci']))} | {m['p50_ms']:.3f} | {m['p95_ms']:.3f} | "
            f"{m['processed_n']} | {percent(m['processed_precision'])} | "
            f"{percent(m['processed_recall'])} |"
        )
    lines += [
        "",
        f"Инициализация OCR отдельно: {report['model_initialization_ms']:.1f} мс. "
        "В обоих OCR-вариантах кэш содержимого выключен, модель уже загружена. "
        "У большинства случаев нет изображения, поэтому общий p50 мал. "
        f"Для 27 изображений full p50={report['slices']['image']['p50_ms']:.1f} мс, "
        f"p95={report['slices']['image']['p95_ms']:.1f} мс. "
        "Это синтетический транспорт без интернета; задержку реального HTTP/Gemini эти числа не характеризуют.",
        "",
        "Четыре положительных отказа остаются в FN; общий recall 30/40. "
        "На 72 обработанных случаях recall 30/36. Еще четыре отказа — неоднозначные отрицательные. "
        "Покрытие не используется для исключения сложных примеров из общего результата. "
        "Wilson рассчитан по случаям; два варианта одного семейства зависимы, "
        "поэтому интервалы могут быть слишком узкими.",
        "",
        "## Срезы полного процесса",
        "",
        "| Срез | N | TP | FP | TN | FN | Precision | Recall | FPR | Покрытие |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, m in report["slices"].items():
        values = [name, *[str(m[k]) for k in ("n", "tp", "fp", "tn", "fn")]]
        values += [percent(m[k]) for k in ("precision", "recall", "fpr", "coverage")]
        lines.append("| " + " | ".join(values) + " |")
    lines += [
        "",
        "В JSON recall/FPR без соответствующего класса обозначен 0 по соглашению реализации; "
        "при нулевом знаменателе метрика не имеет содержательного смысла. "
        "Срез unfamiliar/unseen_domains содержит только 52 случая с URL; все домены test отсутствуют в dev.",
        "",
        "## Разбор ошибок, без подгонки test",
        "",
        "- Два FP: казахский учебный разбор цитирует призыв; словарь не распознал образовательный контекст.",
        "- Четыре FN: назначение недоступно; система обоснованно просит данные, но в метрике это пропуски.",
        "- Два FN: транслитерированный призыв «Zaregaysya» не распознан.",
        "- Два FN: многошаговые примеры не набрали порог; требуется расширение контекстных признаков на новых dev-данных.",
        "- Два FN: предупреждение с противоречащим рекламным призывом осталось ниже порога. "
        "Предупреждение не безусловный whitelist, но текущих правил недостаточно.",
        "",
        "Для следующей версии: независимые KK-разметчики, новые образовательные/противоречивые примеры, "
        "словарь транслита, оценка доступного облачного адаптера, новый закрытый test. "
        "Не исправлять эти двенадцать примеров и затем называть старый test независимым.",
        "",
        "## Все ошибочные случаи",
        "",
    ]
    for item in report["errors"]:
        lines += [f"- `{item['id']}` — {'FN' if item['truth'] else 'FP'}: {item['title']}"]
    lines += [
        "",
        "## Воспроизводимость",
        "",
        f"`test-freeze.json`: проверено {len(frozen['hashes'])} SHA-256; ядро, данные и оценщик "
        "совпадают с зафиксированной версией. Frontend и документация могут уточняться без изменения предсказаний.",
        "",
        "Исходные результаты: [evaluation.json](evaluation.json), "
        "[evaluation-predictions.json](evaluation-predictions.json), "
        "[evaluation-predictions.csv](evaluation-predictions.csv). "
        "Разработка: [dev-evaluation.json](dev-evaluation.json). "
        "Методика: [DATASET.md](../docs/DATASET.md), [METHODOLOGY.md](../docs/METHODOLOGY.md).",
        "",
        "Проверки устойчивости OCR: [ocr-robustness.json](technical/ocr-robustness.json). "
        "Поворот на 90° без отдельного классификатора ориентации резко снижает качество; "
        "распознавание отдельных казахских букв и смешанных алфавитов остается несовершенным.",
    ]
    (REPORTS / "EVALUATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report rendered; {len(frozen['hashes'])} frozen hashes verified.")


if __name__ == "__main__":
    main()
