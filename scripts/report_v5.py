"""Join frozen predictions to three independent label records after adjudication."""

import json
import math
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "reports/versions/synthetic-v5"
DATA = ROOT / "datasets/synthetic-v5"
VARIANTS = ["baseline-2.4", "full", "without-normalization", "full-plus-char", "full-plus-embedding"]


def load_lines(path):
    values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(values) == 640 == len({row["id"] for row in values}), path
    return {row["id"]: row for row in values}


def wilson(num, den):
    if not den:
        return None
    z = 1.95996398454
    p = num / den
    center = (p + z * z / (2 * den)) / (1 + z * z / den)
    spread = z * math.sqrt(p * (1 - p) / den + z * z / (4 * den * den)) / (1 + z * z / den)
    return [max(0, center - spread), min(1, center + spread)]


def confusion(items):
    count = Counter((truth, pred) for truth, pred, *_ in items)
    tp, fp, tn, fn = count[1, 1], count[0, 1], count[0, 0], count[1, 0]
    def rate(a, b):
        return a / b if b else None
    return {"n": len(items), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": rate(tp, tp + fp), "precision_wilson95": wilson(tp, tp + fp),
            "recall": rate(tp, tp + fn), "recall_wilson95": wilson(tp, tp + fn),
            "fpr": rate(fp, fp + tn), "fpr_wilson95": wilson(fp, fp + tn),
            "f1": rate(2 * tp, 2 * tp + fp + fn),
            "coverage": rate(sum(sufficient for *_, sufficient in items), len(items)),
            "levels": dict(Counter(level for *_, level, sufficient in items if sufficient))}


def main():
    output = DIR / "evaluation.json"
    if output.exists():
        raise FileExistsError(output)
    first = load_lines(DIR / "llm-labels/model-a.jsonl")
    second = load_lines(DIR / "llm-labels/model-b.jsonl")
    authored = load_lines(DATA / "annotations.jsonl")
    assert set(first) == set(second) == set(authored)
    disagree = {key for key in authored if first[key]["label"] != second[key]["label"]}
    adjudication_path = DIR / "llm-labels/model-c.jsonl"
    if disagree:
        third = {row["id"]: row for row in map(json.loads, adjudication_path.read_text(encoding="utf-8").splitlines())}
        assert set(third) == disagree
    else:
        third = {}
    assert all(r["label"] in {0, 1} for r in list(first.values()) + list(second.values()) + list(third.values()))
    labels = {key: third[key]["label"] if key in third else first[key]["label"] for key in authored}
    observed = sum(first[key]["label"] == second[key]["label"] for key in authored) / 640
    marginal_a = sum(r["label"] for r in first.values()) / 640
    marginal_b = sum(r["label"] for r in second.values()) / 640
    expected = marginal_a * marginal_b + (1 - marginal_a) * (1 - marginal_b)
    kappa = (observed - expected) / (1 - expected) if expected < 1 else None
    freeze = json.loads((DIR / "core-freeze.json").read_text(encoding="utf-8"))
    report = {"provenance": "авторский синтетический набор, разметка LLM, не человеческая",
              "independence_limit": "Templates are related; screenshot transcripts are authored. Different configured models cannot establish human independence.",
              "freeze_at": freeze["at"], "primary_variant": freeze["selected"],
              "labels": {"author_intended_positive": sum(r["truth"] for r in authored.values()),
                         "llm_adjudicated_positive": sum(labels.values()), "adjudicated_disagreements": len(disagree),
                         "author_vs_llm_disagreements": sum(authored[k]["truth"] != labels[k] for k in authored),
                         "agreement_before_adjudication": observed, "cohen_kappa": kappa,
                         "configured_models": [json.loads((DIR / f"llm-labels/model-{m}-meta.json").read_text(encoding="utf-8")) for m in ("a", "b")],
                         "third_pass": json.loads((DIR / "llm-labels/model-c-meta.json").read_text(encoding="utf-8")) if disagree else None},
              "variants": {}, "threshold_curve": []}
    for variant in VARIANTS:
        data = json.loads((DIR / (variant + ".json")).read_text(encoding="utf-8"))
        records = {r["id"]: r for r in data["records"]}
        assert set(records) == set(labels)
        if variant != "baseline-2.4":
            assert data["analysis_hashes"] == freeze["analysis_hashes"], variant
        items = [(labels[key], int(records[key]["predicted"]), records[key]["level"], bool(records[key]["sufficient"])) for key in authored]
        rows = {"overall": confusion(items), "language": {}, "modality": {}, "masking": {}}
        for field, values in (("language", ["ru", "kk", "translit", "mixed"]),
                              ("modality", ["text", "image"]),
                              ("masking", sorted({r["masking"] for r in authored.values()}))):
            for value in values:
                selection = [item for key, item in zip(authored, items, strict=True) if authored[key][field] == value]
                rows[field][value] = confusion(selection)
        rows["errors"] = [{"id": key, "title": authored[key].get("family", key), "truth": labels[key], "predicted": records[key]["predicted"],
                            "language": authored[key]["language"], "modality": authored[key]["modality"],
                            "masking": authored[key]["masking"], "sufficient": records[key]["sufficient"]}
                           for key in authored if records[key]["predicted"] != labels[key]]
        report["variants"][variant] = rows
    full = {r["id"]: r for r in json.loads((DIR / "full.json").read_text(encoding="utf-8"))["records"]}
    glyph_cases = [key for key, row in authored.items() if row["image"] and row["masking"] == "emoji"]
    assert len(glyph_cases) == 8
    clean_items = [(labels[key], int(full[key]["predicted"]), full[key]["level"], bool(full[key]["sufficient"]))
                   for key in authored if key not in glyph_cases]
    report["screenshot_source_audit"] = {
        "finding": "Eight authored emoji-word screenshots rendered with empty glyph boxes in Arial; author transcripts show emoji instead. Four languages and the shared generator/font were visually checked. Original pixels and predictions preserved.",
        "affected_ids": glyph_cases, "primary_includes_affected": True,
        "sensitivity_excluding_affected": confusion(clean_items)}
    for threshold in range(0, 101, 5):
        items = [(labels[key], int(full[key]["sufficient"] and full[key]["score"] >= threshold), full[key]["level"], bool(full[key]["sufficient"])) for key in authored]
        report["threshold_curve"].append({"threshold": threshold, **confusion(items)})
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    def ui_metric(variant):
        item = report["variants"][variant]["overall"]
        source = {r["id"]: r for r in json.loads((DIR / (variant + ".json")).read_text(encoding="utf-8"))["records"]}
        timings = sorted(r["elapsed_ms"] for r in source.values() if r.get("elapsed_ms") is not None)
        return {**item, "precision_ci": item["precision_wilson95"], "fpr_ci": item["fpr_wilson95"],
                "insufficient": sum(not r["sufficient"] for r in source.values()),
                "p50_ms": statistics.median(timings) if timings else None,
                "p95_ms": timings[math.ceil(.95 * len(timings)) - 1] if timings else None}

    original_full = ui_metric("full")
    ui = {"dataset_version": "synthetic-v5", "test_count": 640, "image_count": 160,
          "frozen_at": freeze["at"], "provenance": report["provenance"],
          "versions": {"rules": "rules-5.0", "pipeline": "pipeline-3.0"},
          "variants": {"baseline": ui_metric("baseline-2.4"), "full": original_full,
                       "without_normalization": ui_metric("without-normalization"),
                       "char": ui_metric("full-plus-char"), "embedding": ui_metric("full-plus-embedding")},
          "slices": {**{"language:" + key: value for key, value in report["variants"]["full"]["language"].items()},
                     **{"format:" + key: value for key, value in report["variants"]["full"]["modality"].items()},
                     **{"scenario:" + key: value for key, value in report["variants"]["full"]["masking"].items()}},
          "risk_levels": original_full["levels"],
          "errors": report["variants"]["full"]["errors"],
          "limitations": ["Авторский синтетический набор с родственными шаблонами; два LLM с разными настроенными моделями, не человеческая разметка.",
                          "Скриншоты размечены по авторской транскрипции; реальную ошибку OCR показывает прогон приложения.",
                          "Только синтетические .test-адреса. Качество на реальных сообщениях и зеркалах неизвестно.",
                          "Индекс приоритета не является калиброванной вероятностью или юридическим вердиктом."]}
    (DIR / "evaluator-summary.json").write_text(json.dumps(ui, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": 640, "disagreement": len(disagree), "kappa": kappa,
                      "primary": report["variants"]["full"]["overall"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
