"""Build human-readable tables from preserved measured reports; no evaluation."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports"
v1 = json.loads((OUT / "versions/synthetic-v1/evaluation.json").read_text(encoding="utf-8"))
v2 = json.loads((OUT / "versions/synthetic-v2/evaluation.json").read_text(encoding="utf-8"))
reg = json.loads((OUT / "versions/synthetic-v2/regression-v1.json").read_text(encoding="utf-8"))


def pct(number):
    return "—" if number is None else f"{number * 100:.2f}%"


def row(name, m):
    return f"| {name} | {m['n']} | {m['tp']}/{m['fp']}/{m['tn']}/{m['fn']} | {pct(m['precision'])} | {pct(m['recall'])} | {pct(m['f1'])} | {pct(m['fpr'])} | {pct(m['coverage'])} | {m['p95_ms'] / 1000:.3f} |"


header = "| Оценка | N | TP/FP/TN/FN | Precision | Recall | F1 | FPR | Покрытие | p95, с |\n|---|---:|---|---:|---:|---:|---:|---:|---:|"
content = [
    "# Измеренная оценка v2",
    "Конфигурация rules-2.0 / weights-2.0 / layout-rotation-2.0 / qr-1.0. Ядро зафиксировано до создания нового final test; после результатов не изменялось. Порог 65.",
    "## История",
    header,
    row("v1 · исторический test-v1", v1["variants"]["full"]),
    row("v2 · регрессия на test-v1", reg["variants"]["full"]),
    row("v2 · новый test-v2", v2["variants"]["full"]),
    "Только первые две строки используют одинаковые входы. Старый test уже был просмотрен, поэтому регрессия не является независимым итоговым тестом. Новый test-v2 имеет другой состав; разность его метрик с v1 нельзя интерпретировать как прямой прирост или падение на одинаковой выборке.",
    "## Новый test-v2",
    "80 авторских синтетических случаев: 40 положительных / 40 отрицательных, 32 изображения, четыре QR. Разметка не подтверждена независимыми экспертами. 40 dev-случаев использованы для настройки; они не входят в таблицу итогового теста.",
    header,
    *[row(name, m) for name, m in v2["variants"].items()],
    f"Wilson 95% полного процесса: precision {'–'.join(map(pct, v2['variants']['full']['precision_ci']))}; FPR {'–'.join(map(pct, v2['variants']['full']['fpr_ci']))}. Цели precision ≥95%, recall ≥80% не достигнуты. Интервалы не учитывают всю зависимость авторских шаблонов.",
    f"Покрытие 72/80. Четыре положительных отказа включены в десять FN общего recall. На обработанных 72 случаях recall {pct(v2['variants']['full']['processed_recall'])}, но это не замена общего recall 75%.",
    f"Настоящий OCR: CER {pct(v2['ocr_cer'])} на 32 изображениях. Формула: расстояние Левенштейна / число символов эталона, пробелы свернуты, регистр сохранен. Это не доля безошибочных URL. Инициализация модели {v2['model_initialization_ms'] / 1000:.3f} с учитывается отдельно.",
    "Время измерено на Windows/CPU, OCR-кэш содержимого выключен, модель предварительно загружена, собственный синтетический транспорт без сети. Медиана текстовых случаев меньше 1 мс; p95 включает повторные проходы OCR. В это время выполнялась обычная браузерная проверка, выделенный изолированный бенчмарк не заявляется.",
    "## Ошибки и пределы",
    "Десять пропусков: четыре недоступных назначения, непокрытые формы призыва/казахской морфологии, неявные приглашения и сложное противоречие. Пять ложных срабатываний: два предупреждения, цитата в репортаже, образовательный разбор и бесплатная игра. Это реальные недостатки локальных правил, сохраненные для следующей версии; ядро под этот тест не дорабатывалось.",
    "| Истина → ответ | Индекс | Материал |\n|---|---:|---|",
    *[
        f"| {e['truth']} → {e['predicted']} | {e['score']} | {e['title'].replace('|', '/')} |"
        for e in v2["errors"]
    ],
    "## Воспроизводимость",
    "reports/versions/synthetic-v2 содержит core-freeze.json, data-freeze.json, evaluation.json, regression-v1.json, исходные JSON/CSV предсказаний и архивы фактического ядра. datasets/synthetic-v2/separation-audit.json фиксирует отсутствие пересечений доменов и шаблонных семейств. Общее авторство и классы сценариев ограничивают независимость.",
    "Повтор без перезаписи официальных результатов: python scripts/evaluate_v2.py --split test --reproduce --run local-01. Для регрессии замените split на regression-v1 и используйте новое имя прогона. При изменении ядра/набора требуется новая версия; не удалять фиксацию.",
    "История v1: reports/versions/synthetic-v1/frozen-source.zip, восемь исходных отчетов; scripts/verify_historical_v1.py сверяет SHA. Старый scripts/evaluate.py защищен исходной фиксацией и намеренно не принимает измененное ядро.",
    "Живой Gemini, независимые реальные данные, GPU и Linux не проверены. Результат выбирает приоритет ручной проверки и не является юридической квалификацией.",
]
(OUT / "EVALUATION_V2.md").write_text("\n\n".join(content).replace("|\n\n|", "|\n|") + "\n", encoding="utf-8")
print(OUT / "EVALUATION_V2.md")
