"""Reproducible v3/v4 comparison. Workers save predictions before annotations are read."""

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
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/versions/synthetic-v4"
DATASET = ROOT / "datasets/synthetic-v4"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def core_hashes(root=ROOT):
    paths = [
        *(root / "backend").glob("*.py"),
        root / "backend/weights.json",
        root / "models-manifest.json",
        root / "requirements.lock.txt",
    ]
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(paths)}


def data_hashes(dataset=DATASET):
    return {p.relative_to(dataset).as_posix(): sha(p) for p in sorted(dataset.rglob("*")) if p.is_file()}


def freeze():
    if (DATASET / "inputs.jsonl").exists():
        raise RuntimeError("Freeze configuration before authoring final inputs")
    if "-dev" in (ROOT / "backend/config.py").read_text(encoding="utf-8"):
        raise RuntimeError("Finalize version identifiers before freezing")
    protocol = ROOT / "docs/EVALUATION_PROTOCOL_V4.md"
    baseline = ROOT / "deliverables/releases/SafeTrace-KZ-v3-source.zip"
    manifest = {
        "at": datetime.now(timezone.utc).isoformat(),
        "core_hashes": core_hashes(),
        "protocol_sha256": sha(protocol),
        "evaluator_sha256": sha(Path(__file__)),
        "baseline_archive_sha256": sha(baseline),
        "threshold": 65,
        "positive_rule": "score >= 65 AND sufficient_data",
        "purpose": "Frozen before authoring new final pixels, texts and labels",
    }
    write(REPORT / "core-freeze.json", manifest)
    with zipfile.ZipFile(REPORT / "core-source.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for name in manifest["core_hashes"]:
            archive.write(ROOT / name, name)
        archive.write(Path(__file__), "scripts/evaluate_v4.py")
        archive.write(protocol, "docs/EVALUATION_PROTOCOL_V4.md")
    print("v4 core and protocol frozen")


def worker(version, source, dataset, output, diagnostic=False):
    source, dataset, output = source.resolve(), dataset.resolve(), output.resolve()
    if output.exists():
        raise RuntimeError("Predictions already exist; do not overwrite")
    before, inputs_before = core_hashes(source), data_hashes(dataset)
    if not diagnostic:
        freeze_record = json.loads((REPORT / "core-freeze.json").read_text(encoding="utf-8"))
        assert sha(Path(__file__)) == freeze_record["evaluator_sha256"], "Evaluator changed after freeze"
        if version == "v4":
            assert before == freeze_record["core_hashes"], "Core changed after freeze"
        else:
            archive_path = ROOT / "deliverables/releases/SafeTrace-KZ-v3-source.zip"
            assert sha(archive_path) == freeze_record["baseline_archive_sha256"]
            with zipfile.ZipFile(archive_path) as archive:
                assert all(
                    hashlib.sha256(archive.read(name)).hexdigest() == value for name, value in before.items()
                ), "v3 source differs from archived release"
        frozen_data = REPORT / "data-freeze.json"
        if frozen_data.exists():
            assert json.loads(frozen_data.read_text(encoding="utf-8"))["hashes"] == inputs_before
        else:
            write(frozen_data, {"hashes": inputs_before, "provenance": "author_synthetic_final"})
    os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "tmp" / ("evaluation-v4-" + version + "-" + output.stem))
    os.environ["SAFETRACE_OFFLINE"] = "1"
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ["FLAGS_enable_pir_api"] = "0"
    sys.path.insert(0, str(source))
    from backend import pipeline, storage
    from backend.config import DATA, OCR_VERSION, PIPELINE_VERSION, QR_VERSION, RULE_VERSION
    from backend.links import SyntheticTransport, extract_urls
    from backend.ocr import engine
    from backend.schemas import CaseInput, MaterialInput

    storage.init()
    inputs = [
        json.loads(line) for line in (dataset / "inputs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    pages = json.loads((dataset / "pages.json").read_text(encoding="utf-8"))
    start = time.perf_counter()
    engine()
    initialization_ms = (time.perf_counter() - start) * 1000
    predictions = []
    snapshots = output.with_name(output.stem + "-cases")
    snapshots.mkdir(parents=True, exist_ok=False)
    for index, item in enumerate(inputs):
        materials = []
        for raw in item["materials"]:
            mat = {k: v for k, v in raw.items() if k != "image"}
            if raw.get("image"):
                path = dataset / raw["image"]
                image_id = sha(path)[:32] + path.suffix
                (DATA / "originals" / image_id).write_bytes(path.read_bytes())
                mat["image_id"] = image_id
            materials.append(MaterialInput(**mat))
        base = pipeline.new_case(CaseInput(title="Материал", mode="synthetic", materials=materials))
        variants = ("baseline", "ocr", "full") if version == "v4" and not diagnostic else ("full",)
        for variant in variants:
            doc = copy.deepcopy(base)
            ocr_times = []
            original_recognize = pipeline.recognize

            def timed(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return original_recognize(*args, **kwargs)
                finally:
                    ocr_times.append((time.perf_counter() - start) * 1000)

            started = time.perf_counter()
            with patch.object(pipeline, "recognize", timed):
                pipeline.analyze(doc, variant=variant, fetch=SyntheticTransport(pages), use_ocr_cache=False)
            elapsed = (time.perf_counter() - started) * 1000
            observed = []
            for material in doc["materials"]:
                ocr = material.get("ocr", {})
                raw_urls = extract_urls(ocr.get("text", ""))
                if "url_readings" in ocr:
                    automatic = [r["raw_url"] for r in ocr["url_readings"] if r["auto_follow"]]
                    candidates = list(
                        dict.fromkeys(
                            raw_urls + [s["url"] for r in ocr["url_readings"] for s in r["suggestions"]]
                        )
                    )
                else:
                    automatic, candidates = raw_urls, raw_urls
                observed.append(
                    {
                        "image": bool(material.get("image_id")),
                        "raw_text": ocr.get("raw_text", ocr.get("text", "")),
                        "text": ocr.get("text", ""),
                        "raw_urls": raw_urls,
                        "automatic_urls": automatic,
                        "candidates": candidates,
                        "roots": material.get("urls", []),
                        "qr_payloads": [c["text"] for c in material.get("qr", {}).get("codes", [])],
                        "url_reviews": material.get("url_reviews", []),
                        "rotation_ccw": ocr.get("rotation_ccw", 0),
                    }
                )
            predictions.append(
                {
                    "id": item["id"],
                    "variant": variant,
                    "score": doc["score"]["value"],
                    "sufficient": doc["sufficient_data"],
                    "predicted": int(doc["score"]["value"] >= 65 and doc["sufficient_data"]),
                    "status": doc["status"],
                    "elapsed_ms": round(elapsed, 3),
                    "ocr_elapsed_ms": round(sum(ocr_times), 3),
                    "analysis_assisted": doc.get("analysis_assisted", False),
                    "materials": observed,
                    "contributions": doc["score"]["contributions"],
                    "limitations": doc["limitations"],
                }
            )
            if variant == "full":
                write(snapshots / (item["id"] + ".json"), doc)
        print(f"{version}: {index + 1}/{len(inputs)}", flush=True)
    assert before == core_hashes(source), "Code changed during evaluation"
    assert inputs_before == data_hashes(dataset), "Data changed during evaluation"
    write(
        output,
        {
            "version": version,
            "core_hashes": before,
            "data_hashes": inputs_before,
            "versions": {
                "rules": RULE_VERSION,
                "ocr": OCR_VERSION,
                "pipeline": PIPELINE_VERSION,
                "qr": QR_VERSION,
            },
            "model_initialization_ms": initialization_ms,
            "rows": predictions,
        },
    )


def wilson(k, n):
    if not n:
        return None
    z, p = 1.959964, k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [max(0, center - half), min(1, center + half)]


def timing(values):
    values = sorted(values)
    return {
        "n": len(values),
        "p50_ms": statistics.median(values) if values else None,
        "p95_ms": values[math.ceil(0.95 * len(values)) - 1] if values else None,
    }


def metrics(rows):
    tp = sum(r["truth"] == 1 and r["predicted"] == 1 for r in rows)
    fp = sum(r["truth"] == 0 and r["predicted"] == 1 for r in rows)
    tn = sum(r["truth"] == 0 and r["predicted"] == 0 for r in rows)
    fn = sum(r["truth"] == 1 and r["predicted"] == 0 for r in rows)
    covered = [r for r in rows if r["sufficient"]]
    ptp = sum(r["truth"] and r["predicted"] for r in covered)
    pfp = sum(not r["truth"] and r["predicted"] for r in covered)
    pos = sum(r["truth"] for r in covered)
    neg = len(covered) - pos
    return {
        **timing([r["elapsed_ms"] for r in rows]),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "fpr": fp / (fp + tn) if fp + tn else None,
        "coverage": len(covered) / len(rows) if rows else None,
        "insufficient": len(rows) - len(covered),
        "precision_ci": wilson(tp, tp + fp),
        "recall_ci": wilson(tp, tp + fn),
        "fpr_ci": wilson(fp, fp + tn),
        "processed_n": len(covered),
        "processed_precision": ptp / (ptp + pfp) if ptp + pfp else None,
        "processed_recall": ptp / pos if pos else None,
        "processed_fpr": pfp / neg if neg else None,
    }


def extraction(rows, labels):
    pairs = [
        (m, labels[row["id"]]["materials"][i])
        for row in rows
        for i, m in enumerate(row["materials"])
        if m["image"]
    ]

    def sets(field, truth_field, transform=lambda x: x, expected_only=False, keep=lambda x: True):
        selected = [(m, t) for m, t in pairs if not expected_only or any(keep(u) for u in t[truth_field])]
        tp = fp = fn = exact = accepted = 0
        for m, t in selected:
            actual, expected = (
                {transform(u) for u in m[field] if keep(u)},
                {transform(u) for u in t[truth_field] if keep(u)},
            )
            tp += len(actual & expected)
            fp += len(actual - expected)
            fn += len(expected - actual)
            exact += actual == expected
            accepted += bool(actual)
        return {
            "n": len(selected),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "exact_sets": exact,
            "accepted": accepted,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
        }

    return {
        "raw_url": sets("raw_urls", "ocr_urls"),
        "automatic_url": sets("automatic_urls", "ocr_urls"),
        "raw_url_expected": sets("raw_urls", "ocr_urls", expected_only=True),
        "automatic_url_expected": sets("automatic_urls", "ocr_urls", expected_only=True),
        "raw_domain": sets("raw_urls", "ocr_urls", lambda u: urlsplit(u).hostname),
        "raw_referral": sets(
            "raw_urls",
            "ocr_urls",
            lambda u: tuple(parse_qsl(urlsplit(u).query)),
            True,
            lambda u: bool(urlsplit(u).query),
        ),
        "qr": sets("qr_payloads", "qr_payloads"),
        "qr_expected": sets("qr_payloads", "qr_payloads", expected_only=True),
        "correct_candidate_available": sum(
            set(t["ocr_urls"]) <= set(m["candidates"]) for m, t in pairs if t["ocr_urls"]
        ),
        "candidate_denominator": sum(bool(t["ocr_urls"]) for _, t in pairs),
        "definition": "Exact character-preserving URL sets per image; hostname lowercased by urlsplit; referral is the full ordered query-pair tuple. Candidate availability is assisted-review potential, never automatic success.",
    }


def aggregate():
    labels = {
        r["id"]: r
        for r in map(json.loads, (DATASET / "annotations.jsonl").read_text(encoding="utf-8").splitlines())
    }
    reports, full_by_version = {}, {}
    for version in ("v3", "v4"):
        raw = json.loads((REPORT / (version + "-unlabelled.json")).read_text(encoding="utf-8"))
        assert raw["data_hashes"] == data_hashes()
        rows = raw["rows"]
        assert {r["id"] for r in rows} == set(labels)
        for row in rows:
            row.update(
                {key: labels[row["id"]][key] for key in ("truth", "language", "category", "image", "qr")}
            )
            assert not row["analysis_assisted"]
        full = [r for r in rows if r["variant"] == "full"]
        full_by_version[version] = {r["id"]: r for r in full}
        slices = {
            f"{field}:{value}": metrics([r for r in full if r[field] == value])
            for field in ("language", "category")
            for value in sorted({r[field] for r in full})
        }
        slices.update(
            {
                "image": metrics([r for r in full if r["image"]]),
                "text": metrics([r for r in full if not r["image"]]),
                "qr": metrics([r for r in full if r["qr"]]),
            }
        )
        image_rows = [r for r in full if r["image"]]
        reports[version] = {
            "dataset_version": "synthetic-v4",
            "evaluation_version": version + "-on-v4",
            "test_count": len(full),
            "image_count": len(image_rows),
            "threshold": 65,
            "frozen_at": json.loads((REPORT / "core-freeze.json").read_text(encoding="utf-8"))["at"],
            "versions": raw["versions"],
            "core_hashes": raw["core_hashes"],
            "data_hashes": raw["data_hashes"],
            "variants": {
                v: metrics([r for r in rows if r["variant"] == v])
                for v in dict.fromkeys(r["variant"] for r in rows)
            },
            "slices": slices,
            "extraction": extraction(full, labels),
            "model_initialization_ms": raw["model_initialization_ms"],
            "ocr_timing": {
                **timing([r["ocr_elapsed_ms"] for r in image_rows]),
                "share_of_full_image_time": sum(r["ocr_elapsed_ms"] for r in image_rows)
                / sum(r["elapsed_ms"] for r in image_rows)
                if image_rows
                else None,
            },
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
            "limitations": [
                "Авторская синтетическая разметка; автор данных и правил один. Независимой человеческой оценки нет.",
                "Порог 65 и обязательная достаточность данных зафиксированы до теста. Положительные отказы включены в FN.",
                "Внешние сайты и Gemini не оценивались; маршруты предоставлены отдельным синтетическим транспортом.",
                "95% Wilson не учитывает все зависимости авторского набора; маленькие языковые срезы не доказывают устойчивость.",
                "OCR-кэш выключен; основная модель загружена заранее. Холодная загрузка, кэш и очередь измерены отдельно.",
                "Подсказки OCR не исправляют URL автоматически. Ручных исправлений в этих предсказаниях нет.",
            ],
        }
        write(REPORT / (version + "-predictions.json"), rows)
        with (REPORT / (version + "-predictions.csv")).open("x", newline="", encoding="utf-8-sig") as file:
            fields = [
                "id",
                "variant",
                "truth",
                "predicted",
                "score",
                "sufficient",
                "status",
                "language",
                "category",
                "image",
                "qr",
                "elapsed_ms",
                "ocr_elapsed_ms",
            ]
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    old, new = full_by_version["v3"], full_by_version["v4"]
    changed = [
        {
            "id": key,
            "truth": labels[key]["truth"],
            "v3": old[key]["predicted"],
            "v4": new[key]["predicted"],
            "v3_sufficient": old[key]["sufficient"],
            "v4_sufficient": new[key]["sufficient"],
        }
        for key in labels
        if old[key]["predicted"] != new[key]["predicted"] or old[key]["sufficient"] != new[key]["sufficient"]
    ]
    comparison = {
        "same_inputs": True,
        "v3": reports["v3"]["variants"]["full"],
        "v4": reports["v4"]["variants"]["full"],
        "corrected": sum(
            old[k]["predicted"] != labels[k]["truth"] and new[k]["predicted"] == labels[k]["truth"]
            for k in labels
        ),
        "regressed": sum(
            old[k]["predicted"] == labels[k]["truth"] and new[k]["predicted"] != labels[k]["truth"]
            for k in labels
        ),
        "changes": changed,
    }
    reports["v4"]["comparison"] = comparison
    write(REPORT / "v3-evaluation.json", reports["v3"])
    write(REPORT / "evaluation.json", reports["v4"])
    write(REPORT / "comparison.json", comparison)
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["freeze", "worker", "aggregate"])
    parser.add_argument("--version", choices=["v3", "v4"], default="v4")
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.action == "freeze":
        freeze()
    elif args.action == "aggregate":
        aggregate()
    else:
        worker(
            args.version,
            args.source,
            args.dataset,
            args.output or REPORT / (args.version + "-unlabelled.json"),
            args.diagnostic,
        )
