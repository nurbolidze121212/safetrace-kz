"""Read-only verification of frozen v4 core/data, raw predictions and historical files."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    base = ROOT / "reports/versions/synthetic-v4"
    freeze = read(base / "core-freeze.json")
    for name, value in freeze["core_hashes"].items():
        assert sha(ROOT / name) == value, name
    assert sha(ROOT / "scripts/evaluate_v4.py") == freeze["evaluator_sha256"]
    assert sha(ROOT / "docs/EVALUATION_PROTOCOL_V4.md") == freeze["protocol_sha256"]
    assert sha(ROOT / "deliverables/releases/SafeTrace-KZ-v3-source.zip") == freeze["baseline_archive_sha256"]
    data = read(base / "data-freeze.json")["hashes"]
    for name, value in data.items():
        # The evaluator uses dataset-relative keys.
        assert sha(ROOT / "datasets/synthetic-v4" / name) == value, name
    historical = read(ROOT / "reports/acceptance-v4/historical-files.json")
    for name, value in historical.items():
        assert sha(ROOT / name) == value, name
    labels = {
        r["id"]: r["truth"]
        for r in map(
            json.loads,
            (ROOT / "datasets/synthetic-v4/annotations.jsonl").read_text(encoding="utf-8").splitlines(),
        )
    }
    counts = {}
    for version, filename in [("v3", "v3-evaluation.json"), ("v4", "evaluation.json")]:
        raw = read(base / (version + "-unlabelled.json"))
        assert raw["data_hashes"] == data
        assert all("truth" not in r and not r["analysis_assisted"] for r in raw["rows"])
        report = read(base / filename)
        full = [r for r in raw["rows"] if r["variant"] == "full"]
        assert len(full) == len(labels) == 80
        assert {r["id"] for r in full} == set(labels)
        matrix = dict(tp=0, fp=0, tn=0, fn=0)
        for row in full:
            predicted = int(row["score"] >= 65 and row["sufficient"])
            assert row["predicted"] == predicted
            key = (
                ("tp" if labels[row["id"]] else "fp") if predicted else ("fn" if labels[row["id"]] else "tn")
            )
            matrix[key] += 1
        assert all(report["variants"]["full"][k] == v for k, v in matrix.items())
        counts[version] = matrix
    result = {
        "at": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "core_files": len(freeze["core_hashes"]),
        "data_files": len(data),
        "historical_files": len(historical),
        "independently_recounted_confusion": counts,
        "scope": "File integrity and arithmetic, not independent labeling or external validation",
    }
    if args.report:
        with args.report.open("x", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
