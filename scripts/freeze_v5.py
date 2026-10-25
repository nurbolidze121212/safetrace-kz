"""Commit the inference contract before authoring the new hold-out."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from evaluate_v5 import hashes

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (ROOT / "datasets/synthetic-v5").exists(), "Hold-out already exists"
    target = ROOT / "reports/versions/synthetic-v5"
    target.mkdir(parents=True, exist_ok=True)
    assert not (target / "core-freeze.json").exists(), "Freeze already recorded"
    names = ["requirements.lock.txt", "requirements-research.txt", "models-manifest.json",
             "scripts/evaluate_v5.py", "scripts/fit_v5_ml.py", "docs/EVALUATION_PROTOCOL_V5.md",
             "reports/v5-dev/ml/selection.json", "reports/v5-dev/ml/char.joblib", "reports/v5-dev/ml/embedding.joblib",
             "site/text-score.mjs", "backend/network_signals.py"]
    selection = json.loads((ROOT / "reports/v5-dev/ml/selection.json").read_text())
    manifest = {"at": datetime.now(UTC).isoformat(),
                "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "analysis_hashes": hashes(ROOT), "supporting_hashes": {name: digest(ROOT / name) for name in names},
                "model_hashes": {p.relative_to(ROOT).as_posix(): digest(p) for p in (ROOT / "models").rglob("*")
                                 if p.is_file() and "research" not in p.parts and p.suffix not in {".lock"}},
                "environment": {"platform": platform.platform(), "python": platform.python_version(),
                                "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}},
                "selected": selection["selected"], "thresholds": {"medium": 35, "high": 65},
                "ablations": ["baseline_2_4", "full", "without_normalization", "full_plus_char", "full_plus_embedding"],
                "labels_or_holdout_seen": False,
                "protocol": "No classifier/model/threshold changes after this freeze; publish failures unchanged"}
    (target / "core-freeze.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (target / "baseline-freeze.json").write_text(json.dumps({"at": manifest["at"], "analysis_hashes": hashes(ROOT / "tmp/v5-baseline"),
        "source": "v2.4.0 verified source release, 1b26a89139e5831070a8883b958b99d8adb36e43"}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"at": manifest["at"], "selected": manifest["selected"], "analysis_files": len(manifest["analysis_hashes"])}))


if __name__ == "__main__":
    main()
