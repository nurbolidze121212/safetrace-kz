"""Verify frozen v3 sources/data and independently recount stored predictions."""

import hashlib
import json
import math
import statistics
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/versions/synthetic-v3"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    core, data = read(REPORTS / "core-freeze.json"), read(REPORTS / "data-freeze.json")
    report = read(REPORTS / "evaluation.json")
    raw = read(REPORTS / "evaluation-unlabelled-predictions.json")
    labelled = read(REPORTS / "evaluation-predictions.json")
    assert core["hashes"] == report["core_hashes"]
    for group in (core["hashes"], data["hashes"]):
        for name, expected in group.items():
            assert sha(ROOT / name) == expected, name
    with zipfile.ZipFile(REPORTS / "evaluation-core-source.zip") as archive:
        assert set(archive.namelist()) == set(core["hashes"])
        for name, expected in core["hashes"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected, name
    manifest = read(ROOT / "models-manifest.json")
    for name, expected in manifest["files"].items():
        assert sha(ROOT / "models" / name) == expected, name
    inputs = [
        json.loads(line)
        for line in (ROOT / "datasets/synthetic-v3/test.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    annotations = {
        row["id"]: row
        for row in map(
            json.loads,
            (ROOT / "datasets/synthetic-v3/test-annotations.jsonl").read_text(encoding="utf-8").splitlines(),
        )
    }
    assert len(inputs) == len(annotations) == report["test_count"] == 80
    assert len(raw) == len(labelled) == 240
    assert not any("truth" in row or "category" in row or "reference_text" in row for row in raw)
    raw_by_key = {(row["id"], row["variant"]): row for row in raw}
    assert len(raw_by_key) == 240
    for row in labelled:
        assert all(row[key] == value for key, value in raw_by_key[row["id"], row["variant"]].items())
        assert row["truth"] == annotations[row["id"]]["truth"]
        assert row["predicted"] == int(row["score"] >= report["threshold"] and row["sufficient"])
    checks = {}
    for variant in ("baseline", "ocr", "full"):
        rows = [row for row in labelled if row["variant"] == variant]
        assert {row["id"] for row in rows} == set(annotations)
        counts = Counter((row["truth"], row["predicted"]) for row in rows)
        tp, fp, tn, fn = counts[1, 1], counts[0, 1], counts[0, 0], counts[1, 0]
        sufficient = [row for row in rows if row["sufficient"]]
        elapsed = sorted(row["elapsed_ms"] for row in rows)
        calculated = {
            "n": 80,
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn),
            "fpr": fp / (fp + tn),
            "coverage": len(sufficient) / len(rows),
            "insufficient": 80 - len(sufficient),
            "processed_n": len(sufficient),
            "p50_ms": statistics.median(elapsed),
            "p95_ms": elapsed[math.ceil(0.95 * len(rows)) - 1],
        }
        assert all(report["variants"][variant][key] == value for key, value in calculated.items())
        checks[variant] = calculated
    full = [row for row in labelled if row["variant"] == "full"]
    assert {row["id"] for row in full if row["truth"] != row["predicted"]} == {
        row["id"] for row in report["errors"]
    }
    result = {
        "core_files": len(core["hashes"]),
        "data_files": len(data["hashes"]),
        "model_files": len(manifest["files"]),
        "archive_matches_frozen_core": True,
        "working_core_matches": True,
        "input_count": 80,
        "prediction_count": 240,
        "unlabelled_predictions_do_not_contain_truth": True,
        "metrics_recount": checks,
        "evaluation_sha256": sha(REPORTS / "evaluation.json"),
    }
    out = ROOT / "reports/acceptance-v3"
    out.mkdir(exist_ok=True, parents=True)
    (out / "freeze-check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "metrics_recount"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
