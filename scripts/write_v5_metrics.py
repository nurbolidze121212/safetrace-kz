"""Render the committed v5 evaluation as a readable, reproducible report."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/versions/synthetic-v5/evaluation.json"
TARGET = ROOT / "docs/METRICS.md"


def percentage(value):
    return "—" if value is None else f"{100 * value:.1f}%"


def interval(row, metric):
    confidence = row[f"{metric}_wilson95"]
    return f"{percentage(row[metric])} [{percentage(confidence[0])}–{percentage(confidence[1])}]" if confidence else "—"


def table(rows):
    lines = ["| Срез | N | TP / FP / TN / FN | Precision [95% Wilson] | Recall [95% Wilson] | FPR [95% Wilson] |",
             "|---|---:|---|---:|---:|---:|"]
    for name, row in rows:
        counts = " / ".join(str(row[key]) for key in ("tp", "fp", "tn", "fn"))
        lines.append(f"| {name} | {row['n']} | {counts} | {interval(row, 'precision')} | {interval(row, 'recall')} | {interval(row, 'fpr')} |")
    return "\n".join(lines)


def main():
    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    variants = report["variants"]
    full = variants["full"]
    ml = variants["full-plus-embedding"]["overall"]
    text = f"""# Метрики: SafeTrace KZ, Track 2

**{report['provenance']}**. Это стресс-тест на 640 новых авторских случаях (220 положительных, 420 трудных отрицательных), включая 160 скриншотов. Все адреса в наборе синтетические `.test`. Полученные проценты не подтверждают качество на реальных сообщениях, неизвестных кампаниях или реальных зеркалах.

## Заморозка и разметка

Правила, нормализация, OCR, пороги, ML-артефакты и код оценки зафиксированы [до генерации теста](../reports/versions/synthetic-v5/core-freeze.json); исходные изображения и входы затем зафиксированы [отдельно](../reports/versions/synthetic-v5/data-freeze.json). [Протокол](EVALUATION_PROTOCOL_V5.md) определяет цель и срезы. Две слепые LLM-разметки совпали на всех 640 случаях; Cohen’s κ = {report['labels']['cohen_kappa']:.2f}, разногласий 0, поэтому третья разметка не запускалась. Проверить фактические идентификаторы обслуживающих моделей невозможно; файлы указывают только настроенные модели. Совпадение LLM между собой и с авторскими метками не заменяет независимую человеческую оценку: шаблоны родственны, а для изображений разметчикам передавалась авторская транскрипция.

## Основной результат: полный локальный процесс

{table([('Все случаи', full['overall'])])}

Положительное решение: достаточно данных и индекс ≥65. Необработанные положительные случаи входят в FN. Индекс — приоритет ручной проверки, **не калиброванная вероятность**. Уровни: низкий {full['overall']['levels'].get('low', 0)}, средний {full['overall']['levels'].get('medium', 0)}, высокий {full['overall']['levels'].get('high', 0)}; без достаточных данных {full['overall']['n']-round(full['overall']['coverage']*full['overall']['n'])}. Нулевой средний уровень на этом наборе показывает, что распределение индекса ещё надо калибровать на новых данных.

## Язык и модальность

{table([(name, row) for name, row in full['language'].items()] + [(name, row) for name, row in full['modality'].items()])}

## Способ маскировки / контекст

{table([(name, row) for name, row in full['masking'].items()])}

Срезы пересекаются и состоят из авторских семейств. Узкие интервалы внутри повторяющихся шаблонов не измеряют устойчивость к новым семействам. Особенно заметны 20 ложных срабатываний на транслитерированных образовательных отрицательных случаях и 23 пропуска среди 76 положительных изображений.

## Абляции на одинаковых входах

{table([(name, row['overall']) for name, row in variants.items()])}

Без нормализации найдено {variants['without-normalization']['overall']['tp']} положительных вместо {full['overall']['tp']}. Char n-gram слой на наблюдаемых признаках не изменил решения. Мультиязычный embedding слой дал на этом тесте {ml['tp']} TP и {ml['fp']} FP (F1 {percentage(ml['f1'])}) против {full['overall']['tp']} TP и {full['overall']['fp']} FP (F1 {percentage(full['overall']['f1'])}). **Он не включён в продукт**: при выборе на dev улучшения не было; решение включить его после просмотра v5 было бы настройкой под тест. Нужен следующий замороженный hold-out. Выход модели не калиброван как вероятность. [Все предсказания и кривые порога](../reports/versions/synthetic-v5/evaluation.json).

## Проблема восьми скриншотов

В восьми авторских JPEG с emoji-маскировкой выбранный шрифт отрисовал пустые квадраты вместо emoji; LLM видели авторскую транскрипцию. Первичный результат выше включает их без исправления. Если исключить только эти восемь, оставив те же правила и предсказания: {table([('632 без дефекта исходника', report['screenshot_source_audit']['sensitivity_excluding_affected'])]).splitlines()[-1]}. Это чувствительность к дефекту генерации, не замена основной метрики. Список ID и формулировка — в [JSON](../reports/versions/synthetic-v5/evaluation.json).

## Отдельные измерения системы

- [Структурный граф](NETWORK_V5.md): 5000 известных сущностей, затем время на 10k/100k. Качество кластеров измерено на авторской искусственной сети.
- [Очередь и реальный OCR](SCALE_BENCHMARK_V5.md): GitHub runner, 1/2/4 воркера, пропускная способность и p50/p95.
- [Треки 1 и 3](../reports/versions/synthetic-v5/track-extensions.json): по 80 авторских текстовых случаев; это экспериментальные расширения, не часть измеренного результата Track 2.
- [Ограничения](LIMITATIONS.md): единственное описание границ интерпретации.

Предыдущая версия v4 с 80 случаями и её файлы сохранены в [истории измерений](../reports/versions/synthetic-v4/evaluation.json); проценты разных наборов нельзя напрямую вычитать как прирост качества.
"""
    TARGET.write_text(text, encoding="utf-8")
    print(TARGET)


if __name__ == "__main__":
    main()
