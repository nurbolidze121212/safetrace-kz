"""Verify archived v2 independently of the actively maintained backend."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/versions/synthetic-v2"
BASELINE = ROOT / "reports/versions/backend-2.1/v2-baseline.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    for path, expected in baseline["report_hashes"].items():
        assert sha(ROOT / path) == expected, path
    frozen = json.loads((REPORTS / "core-freeze.json").read_text(encoding="utf-8"))
    data = json.loads((REPORTS / "data-freeze.json").read_text(encoding="utf-8"))
    for path, expected in data["hashes"].items():
        assert sha(ROOT / path) == expected, path
    archives = {}
    for prefix in ("evaluation", "regression-v1"):
        result = json.loads((REPORTS / f"{prefix}.json").read_text(encoding="utf-8"))
        assert result["core_hashes"] == frozen["hashes"], prefix
        with zipfile.ZipFile(REPORTS / f"{prefix}-core-source.zip") as archive:
            for path, expected in frozen["hashes"].items():
                assert hashlib.sha256(archive.read(path)).hexdigest() == expected, path
        for path, expected in result["data_hashes"].items():
            assert sha(ROOT / path) == expected, path
        rows = json.loads((REPORTS / f"{prefix}-predictions.json").read_text(encoding="utf-8"))
        for variant, metrics in result["variants"].items():
            selected = [row for row in rows if row["variant"] == variant]
            assert len(selected) == metrics["n"]
            for key, truth, predicted in (("tp", 1, 1), ("fp", 0, 1), ("tn", 0, 0), ("fn", 1, 0)):
                assert sum(r["truth"] == truth and r["predicted"] == predicted for r in selected) == metrics[key]
        archives[prefix] = len(frozen["hashes"])
    return {
        "historical_reports": len(baseline["report_hashes"]),
        "frozen_data": len(data["hashes"]),
        "archived_source_files": archives,
        "historical_all_match": True,
        "working_core_differences": [
            path for path, expected in frozen["hashes"].items() if sha(ROOT / path) != expected
        ],
        "note": "Historical metrics describe the archived v2 core, not the maintained working backend.",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False))
