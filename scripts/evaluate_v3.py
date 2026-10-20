"""Frozen v3 evaluation: old development data first, newly authored final data only after freeze."""

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
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "data/evaluation-v3")
os.environ["SAFETRACE_OFFLINE"] = "1"

from backend import pipeline, storage
from backend.config import DATA, OCR_VERSION, QR_VERSION, RULE_VERSION
from backend.links import SyntheticTransport
from backend.ocr import engine
from backend.schemas import CaseInput, MaterialInput

VERSION = "synthetic-v3"
REPORTS = ROOT / "reports/versions" / VERSION
THRESHOLD = 65


def hashes(paths):
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(set(paths))
        if p.is_file() and "__pycache__" not in p.parts
    }


def core_hashes():
    return hashes(
        [
            *(ROOT / "backend").glob("*.py"),
            ROOT / "backend/weights.json",
            ROOT / "models-manifest.json",
            ROOT / "requirements.lock.txt",
            Path(__file__),
        ]
    )


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def freeze_core():
    target = REPORTS / "core-freeze.json"
    if target.exists():
        raise RuntimeError("Core freeze already exists; use another evaluation version for changes.")
    if any("-dev" in version for version in (RULE_VERSION, OCR_VERSION, QR_VERSION)):
        raise RuntimeError("Choose final version identifiers before freezing.")
    if not any(
        json.loads(path.read_text(encoding="utf-8")).get("core_hashes") == core_hashes()
        for path in (ROOT / "reports/core-v3-dev").glob("*/evaluation.json")
    ):
        raise RuntimeError(
            "Run and inspect development evaluation with this exact configuration before core freeze."
        )
    backend_hashes = {name: value for name, value in core_hashes().items() if name.startswith("backend/")}
    if not any(
        {
            name: value
            for name, value in json.loads(path.read_text(encoding="utf-8"))["core_hashes"].items()
            if name.startswith("backend/")
        }
        == backend_hashes
        for path in (ROOT / "reports/context-v3-dev").glob("*/evaluation.json")
    ):
        raise RuntimeError(
            "Run and inspect context development evaluation on this exact backend before freeze."
        )
    if (ROOT / "datasets/synthetic-v3/test.jsonl").exists():
        raise RuntimeError("This protocol freezes the core before authoring the new final inputs.")
    write_json(
        target,
        {
            "at": storage.now(),
            "hashes": core_hashes(),
            "rules": RULE_VERSION,
            "ocr": OCR_VERSION,
            "qr": QR_VERSION,
            "threshold": THRESHOLD,
        },
    )
    print("Core frozen before creating/running the new final test.")


def wilson(success, total):
    if not total:
        return None
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
    processed = [r for r in rows if r["sufficient"]]
    ptp = sum(r["truth"] and r["predicted"] for r in processed)
    pfp = sum(not r["truth"] and r["predicted"] for r in processed)
    positive = sum(r["truth"] for r in processed)
    negative = len(processed) - positive
    return {
        "n": n,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "fpr": fp / (fp + tn) if fp + tn else None,
        "coverage": len(processed) / n if n else None,
        "insufficient": n - len(processed),
        "precision_ci": wilson(tp, tp + fp),
        "fpr_ci": wilson(fp, fp + tn),
        "p50_ms": statistics.median(latency) if latency else 0,
        "p95_ms": latency[max(0, math.ceil(0.95 * n) - 1)] if latency else 0,
        "processed_n": len(processed),
        "processed_precision": ptp / (ptp + pfp) if ptp + pfp else None,
        "processed_recall": ptp / positive if positive else None,
        "processed_fpr": pfp / negative if negative else None,
    }


def edit_distance(left, right):
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def evaluate(split, run, reproduce=False):
    storage.init()
    before = core_hashes()
    dataset = ROOT / "datasets" / ("synthetic-v2" if split == "dev" else VERSION)
    input_split = split
    prefix = "evaluation"
    data_before = hashes(dataset.rglob("*"))
    output = (
        ROOT / "reports/core-v3-dev" / run
        if split == "dev"
        else REPORTS / "reproductions" / run
        if reproduce
        else REPORTS
    )
    target = output / (prefix + ".json")
    if target.exists():
        raise RuntimeError("Result already exists; keep it and select a new named development run.")
    output.mkdir(parents=True, exist_ok=True)
    if split != "dev":
        frozen_core = json.loads((REPORTS / "core-freeze.json").read_text(encoding="utf-8"))
        if frozen_core["hashes"] != before:
            raise RuntimeError("Core changed after freeze. Use a new named evaluation version.")
    if split == "test":
        frozen_data = REPORTS / "data-freeze.json"
        current_data = hashes(dataset.rglob("*"))
        if frozen_data.exists():
            if json.loads(frozen_data.read_text(encoding="utf-8"))["hashes"] != current_data:
                raise RuntimeError("Final data changed after freeze.")
        else:
            write_json(
                frozen_data,
                {
                    "at": storage.now(),
                    "hashes": current_data,
                    "purpose": "Author-created final synthetic set; not independent expert validation.",
                },
            )
    inputs = [
        json.loads(line)
        for line in (dataset / (input_split + ".jsonl")).read_text(encoding="utf-8").splitlines()
    ]
    pages = json.loads((dataset / (input_split + "-pages.json")).read_text(encoding="utf-8"))
    predictions = []
    start = time.perf_counter()
    engine()
    initialization_ms = (time.perf_counter() - start) * 1000
    for index, item in enumerate(inputs):
        materials = []
        for raw in item["materials"]:
            mat = {k: v for k, v in raw.items() if k != "image"}
            if raw.get("image"):
                content = (dataset / raw["image"]).read_bytes()
                image_id = hashlib.sha256(content).hexdigest()[:32] + Path(raw["image"]).suffix
                (DATA / "originals" / image_id).write_bytes(content)
                mat["image_id"] = image_id
            materials.append(MaterialInput(**mat))
        base = pipeline.new_case(CaseInput(title="Материал", mode="synthetic", materials=materials))
        for variant in ("baseline", "ocr", "full"):
            doc = copy.deepcopy(base)
            started = time.perf_counter()
            ocr_ms = []
            original_recognize = pipeline.recognize

            def timed_recognize(*args, **kwargs):
                ocr_start = time.perf_counter()
                try:
                    return original_recognize(*args, **kwargs)
                finally:
                    ocr_ms.append((time.perf_counter() - ocr_start) * 1000)

            with patch.object(pipeline, "recognize", timed_recognize):
                pipeline.analyze(doc, variant=variant, fetch=SyntheticTransport(pages), use_ocr_cache=False)
            predictions.append(
                {
                    "id": item["id"],
                    "variant": variant,
                    "score": doc["score"]["value"],
                    "sufficient": doc["sufficient_data"],
                    "predicted": int(doc["score"]["value"] >= THRESHOLD and doc["sufficient_data"]),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "status": doc["status"],
                    "ocr_elapsed_ms": round(sum(ocr_ms), 3),
                    "ocr_text": "\n".join(m.get("ocr", {}).get("text", "") for m in doc["materials"]),
                    "ocr_rotations": [
                        m["ocr"].get("rotation_ccw", 0) for m in doc["materials"] if "ocr" in m
                    ],
                    "provider": "local_rule",
                    "rules": RULE_VERSION,
                    "ocr_model": OCR_VERSION,
                    "qr_version": QR_VERSION,
                    "qr_decoded_count": sum(len(m.get("qr", {}).get("codes", [])) for m in doc["materials"]),
                    "contributions": [c["key"] for c in doc["score"]["contributions"]],
                }
            )
        if (index + 1) % 5 == 0:
            print(f"{split}: {index + 1}/{len(inputs)}", flush=True)
    if data_before != hashes(dataset.rglob("*")):
        raise RuntimeError("Dataset changed during evaluation; results were not accepted.")
    if before != core_hashes():
        raise RuntimeError("Analysis code changed during evaluation; results were not accepted.")
    with zipfile.ZipFile(
        output / (prefix + "-core-source.zip"), "x", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for name in before:
            archive.write(ROOT / name, name)
    # Predictions are persisted before labels are loaded or merged.
    write_json(output / (prefix + "-unlabelled-predictions.json"), predictions)
    label_file = dataset / (input_split + "-annotations.jsonl")
    labels = {
        row["id"]: row
        for row in (json.loads(line) for line in label_file.read_text(encoding="utf-8").splitlines())
        if row["split"] == input_split
    }
    if set(labels) != {item["id"] for item in inputs}:
        raise RuntimeError("Inputs and labels do not match exactly.")
    for row in predictions:
        label = labels[row["id"]]
        row.update(
            truth=label["truth"], category=label["category"], language=label["language"], image=label["image"]
        )
    full = [r for r in predictions if r["variant"] == "full"]
    variants = {
        v: metrics([r for r in predictions if r["variant"] == v]) for v in ("baseline", "ocr", "full")
    }
    slices = {
        name: metrics([r for r in full if r[field] == name])
        for field in ("category", "language")
        for name in sorted({r[field] for r in full})
    }
    slices["image"] = metrics([r for r in full if r["image"]])
    slices["text"] = metrics([r for r in full if not r["image"]])
    if any(label.get("qr") for label in labels.values()):
        slices["qr"] = metrics([r for r in full if labels[r["id"]].get("qr")])
    ocr_rows = [r for r in predictions if r["variant"] == "ocr" and r["image"]]
    edit_errors, reference_characters = 0, 0
    for row in ocr_rows:
        reference = " ".join(
            labels[row["id"]].get("ocr_reference", labels[row["id"]]["reference_text"]).split()
        )
        actual = " ".join(row["ocr_text"].split())
        edit_errors += edit_distance(reference, actual)
        reference_characters += len(reference)
    full_image = [r for r in full if r["image"]]
    ocr_times = sorted(r["ocr_elapsed_ms"] for r in full_image)
    result = {
        "dataset_version": "synthetic-v2 (development)" if split == "dev" else VERSION,
        "evaluation_version": "core-v3",
        "split": split,
        "test_count": len(inputs),
        "image_count": sum(label["image"] for label in labels.values()),
        "frozen_at": storage.now(),
        "threshold": THRESHOLD,
        "variants": variants,
        "slices": slices,
        "versions": {"rules": RULE_VERSION, "ocr": OCR_VERSION, "qr": QR_VERSION},
        "errors": [
            {
                "id": r["id"],
                "truth": r["truth"],
                "predicted": r["predicted"],
                "score": r["score"],
                "sufficient": r["sufficient"],
                "title": labels[r["id"]]["reference_text"],
            }
            for r in full
            if r["truth"] != r["predicted"]
        ],
        "ocr_cer": edit_errors / reference_characters if reference_characters else None,
        "ocr_cer_definition": "Levenshtein character edits / reference characters; whitespace collapsed, case retained; can exceed 1.",
        "model_initialization_ms": initialization_ms,
        "ocr_timing": {
            "n": len(full_image),
            "p50_ms": statistics.median(ocr_times) if ocr_times else None,
            "p95_ms": ocr_times[math.ceil(0.95 * len(ocr_times)) - 1] if ocr_times else None,
            "share_of_full_image_time": sum(ocr_times) / sum(r["elapsed_ms"] for r in full_image)
            if full_image
            else None,
            "definition": "Wall time inside recognize(), including orientation passes; content cache off, model preloaded. QR/links/other stages excluded.",
        },
        "core_hashes": before,
        "data_hashes": hashes(
            [
                dataset / (input_split + ".jsonl"),
                dataset / (input_split + "-pages.json"),
                label_file,
                *[dataset / m["image"] for item in inputs for m in item["materials"] if m["image"]],
            ]
        ),
        "limitations": [
            "Авторская синтетическая разметка; независимой экспертной проверки и реального пилота нет.",
            "Dev-v2 и context-v3-dev доступны для настройки; это не итоговая оценка."
            if split == "dev"
            else "Новые final-входы созданы после фиксации ядра. Автор данных и правил один; это не независимая экспертная проверка.",
            "Отказы на положительных случаях остаются в FN и общем recall; покрытие и показатели обработанных приведены отдельно.",
            "Wilson 95%: интервалы не учитывают всю зависимость авторских шаблонов; это не гарантия качества.",
            "Baseline не читает изображения. В OCR/full кэш содержимого выключен, модель предварительно загружена.",
            "Gemini не оценивался без ключа. Все страницы — собственный синтетический транспорт без сетевых запросов.",
        ],
        "runtime": "Windows / Python 3.12 / CPU",
    }
    write_json(target, result)
    write_json(output / (prefix + "-predictions.json"), predictions)
    with (output / (prefix + "-predictions.csv")).open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    print(
        json.dumps(
            {"output": str(target), "full": variants["full"], "ocr_cer": result["ocr_cer"]},
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"])
    parser.add_argument("--run", default="round-01")
    parser.add_argument("--freeze-core", action="store_true")
    parser.add_argument(
        "--reproduce",
        action="store_true",
        help="Keep official results unchanged; write a named reproduction.",
    )
    args = parser.parse_args()
    if args.freeze_core:
        freeze_core()
    elif args.split:
        evaluate(args.split, args.run, args.reproduce)
    else:
        parser.error("Select --split or --freeze-core.")
