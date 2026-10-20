import argparse
import copy
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "data" / "evaluation-runtime")
os.environ["SAFETRACE_OFFLINE"] = "1"
from backend import pipeline, storage
from backend.config import DATA, OCR_VERSION, RULE_VERSION
from backend.links import SyntheticTransport
from backend.ocr import engine
from backend.schemas import CaseInput, MaterialInput

DATASET = ROOT / "datasets" / "synthetic-v1"


def wilson(success, total):
    if not total:
        return [0, 1]
    z = 1.959964
    p = success / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [max(0, center - half), min(1, center + half)]


def metrics(rows):
    tp = sum(r["truth"] == 1 and r["predicted"] == 1 for r in rows)
    fp = sum(r["truth"] == 0 and r["predicted"] == 1 for r in rows)
    tn = sum(r["truth"] == 0 and r["predicted"] == 0 for r in rows)
    fn = sum(r["truth"] == 1 and r["predicted"] == 0 for r in rows)
    n = len(rows)
    latency = sorted(r["elapsed_ms"] for r in rows)
    insufficient = sum(not r["sufficient"] for r in rows)
    processed = [r for r in rows if r["sufficient"]]
    ptp = sum(r["truth"] and r["predicted"] for r in processed)
    pfp = sum(not r["truth"] and r["predicted"] for r in processed)
    return {
        "n": n,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else 0,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
        "fpr": fp / (fp + tn) if fp + tn else 0,
        "coverage": (n - insufficient) / n if n else 0,
        "insufficient": insufficient,
        "precision_ci": wilson(tp, tp + fp),
        "fpr_ci": wilson(fp, fp + tn),
        "p50_ms": statistics.median(latency) if latency else 0,
        "p95_ms": latency[max(0, math.ceil(0.95 * n) - 1)] if latency else 0,
        "processed_n": len(processed),
        "processed_precision": ptp / (ptp + pfp) if ptp + pfp else None,
        "processed_recall": ptp / sum(r["truth"] for r in processed)
        if any(r["truth"] for r in processed)
        else 0,
    }


def freeze():
    paths = (
        list(DATASET.rglob("*"))
        + list((ROOT / "backend").glob("*.py"))
        + [
            ROOT / "backend/weights.json",
            ROOT / "models-manifest.json",
            ROOT / "requirements.lock.txt",
            ROOT / "scripts/evaluate.py",
        ]
    )
    return {
        str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths)
        if p.is_file()
    }


def evaluate(split):
    storage.init()
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    if split == "test":
        if not (report_dir / "dev-evaluation.json").exists():
            raise RuntimeError("Run dev first; inspect results and freeze configuration.")
        frozen = {
            "at": storage.now(),
            "hashes": freeze(),
            "threshold": 65,
            "rules": RULE_VERSION,
            "ocr": OCR_VERSION,
        }
        freeze_path = report_dir / "test-freeze.json"
        if (
            freeze_path.exists()
            and json.loads(freeze_path.read_text(encoding="utf-8"))["hashes"] != frozen["hashes"]
        ):
            raise RuntimeError("Frozen test changed. Create a new named evaluation version.")
        if not freeze_path.exists():
            freeze_path.write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    inputs = [
        json.loads(line) for line in (DATASET / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    pages = json.loads((DATASET / f"{split}-pages.json").read_text(encoding="utf-8"))
    # Analyzer receives only input materials and the explicit synthetic transport.
    predictions = []
    initialization_started = time.perf_counter()
    engine()
    initialization_ms = (time.perf_counter() - initialization_started) * 1000
    for index, item in enumerate(inputs):
        materials = []
        for raw in item["materials"]:
            mat = {k: v for k, v in raw.items() if k != "image"}
            if raw["image"]:
                content = (DATASET / raw["image"]).read_bytes()
                image_id = hashlib.sha256(content).hexdigest()[:32] + ".jpg"
                (DATA / "originals" / image_id).write_bytes(content)
                mat["image_id"] = image_id
            materials.append(MaterialInput(**mat))
        base = pipeline.new_case(CaseInput(title="Материал", mode="synthetic", materials=materials))
        for variant in ("baseline", "ocr", "full"):
            doc = copy.deepcopy(base)
            start = time.perf_counter()
            pipeline.analyze(doc, variant=variant, fetch=SyntheticTransport(pages), use_ocr_cache=False)
            predictions.append(
                {
                    "id": item["id"],
                    "variant": variant,
                    "score": doc["score"]["value"],
                    "sufficient": doc["sufficient_data"],
                    "predicted": int(doc["score"]["value"] >= 65 and doc["sufficient_data"]),
                    "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
                    "status": doc["status"],
                    "ocr_used": any("ocr" in m for m in doc["materials"]),
                    "ocr_text": "\n".join(m.get("ocr", {}).get("text", "") for m in doc["materials"]),
                    "provider": "local_rule",
                    "rules": RULE_VERSION,
                    "ocr_model": OCR_VERSION,
                }
            )
        print(f"{split}: {index + 1}/{len(inputs)}", flush=True)
    # Labels are read only AFTER all predictions are fixed.
    labels = {
        row["id"]: row
        for row in [
            json.loads(line)
            for line in (DATASET / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if row["split"] == split
    }
    for row in predictions:
        label = labels[row["id"]]
        row.update(
            truth=label["truth"], category=label["category"], language=label["language"], image=label["image"]
        )
    variants = {
        v: metrics([r for r in predictions if r["variant"] == v]) for v in ("baseline", "ocr", "full")
    }
    full = [r for r in predictions if r["variant"] == "full"]
    slices = {
        name: metrics([r for r in full if r[field] == name])
        for field in ("category", "language")
        for name in sorted({r[field] for r in full})
    }
    slices["image"] = metrics([r for r in full if r["image"]])
    # All test domains are disjoint from dev; additionally expose that slice explicitly.
    slices["unseen_domains"] = (
        metrics([r for r in full if "https://" in labels[r["id"]]["reference_text"]])
        if split == "test"
        else metrics([])
    )
    errors = [
        {
            "id": r["id"],
            "truth": r["truth"],
            "predicted": r["predicted"],
            "title": labels[r["id"]]["reference_text"],
        }
        for r in full
        if r["truth"] != r["predicted"]
    ]
    from difflib import SequenceMatcher

    ocr_rows = [r for r in predictions if r["variant"] == "ocr" and r["image"]]
    fidelity = [
        SequenceMatcher(None, labels[r["id"]]["reference_text"], r["ocr_text"]).ratio() for r in ocr_rows
    ]
    result = {
        "dataset_version": "synthetic-v1",
        "split": split,
        "test_count": len(inputs),
        "image_count": sum(label["image"] for label in labels.values()),
        "frozen_at": storage.now(),
        "variants": variants,
        "slices": slices,
        "errors": errors,
        "threshold": 65,
        "ocr_mean_sequence_similarity": statistics.mean(fidelity) if fidelity else None,
        "model_initialization_ms": initialization_ms,
        "limitations": [
            "Разметка создана автором синтетического набора; независимой экспертной проверки нет.",
            "Это не доказательство качества на реальных соцсетях. Семейства, кампании и домены dev/test разделены.",
            "Precision и FPR: интервалы Wilson 95%. Зависимость двух вариантов внутри семейства может сужать интервалы.",
            "Отказы на положительных случаях включены в общий FN/recall. Качество обработанных записано в JSON.",
            "Baseline не читает изображения. В обоих OCR-вариантах кэш содержимого выключен; модель уже загружена. Время инициализации указано отдельно.",
            "Два локальных правила для одного признака не дают независимых доказательств. Gemini не оценивался без ключа.",
            "Порог 65 фиксирован до test; ошибки сохранены без подгонки правил под финальные результаты.",
        ],
        "versions": {"rules": RULE_VERSION, "ocr": OCR_VERSION},
        "runtime": "Windows / Python 3.12 / CPU",
    }
    name = "evaluation" if split == "test" else "dev-evaluation"
    (report_dir / f"{name}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / f"{name}-predictions.json").write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (report_dir / f"{name}-predictions.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    print(json.dumps(variants, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    evaluate(parser.parse_args().split)
