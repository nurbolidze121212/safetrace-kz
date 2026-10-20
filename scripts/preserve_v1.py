"""One-time preservation of the frozen v1 sources and measured results."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "reports" / "versions" / "synthetic-v1"
REPORTS = [
    "reports/test-freeze.json",
    "reports/evaluation.json",
    "reports/evaluation-predictions.csv",
    "reports/evaluation-predictions.json",
    "reports/dev-evaluation-predictions.csv",
    "reports/dev-evaluation-predictions.json",
    "reports/dev-evaluation.json",
    "reports/EVALUATION.md",
]


def main():
    frozen = json.loads((ROOT / REPORTS[0]).read_text(encoding="utf-8"))
    for name, expected in frozen["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST / "frozen-source.zip"
    if archive.exists():
        raise RuntimeError("Historical archive already exists; verify it instead of replacing it.")
    files = dict.fromkeys([*frozen["hashes"], *REPORTS])
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for name in files:
            if (ROOT / name).is_file():
                z.write(ROOT / name, name)
    for name in REPORTS:
        source = ROOT / name
        if source.is_file():
            (DEST / source.name).write_bytes(source.read_bytes())
    meta = {
        "dataset": "synthetic-v1",
        "source_git_commit": "a47f1f2",
        "purpose": "Historical frozen result; test-v1 is a regression set for later configurations.",
        "source_hash_count": len(frozen["hashes"]),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "report_hashes": {
            Path(n).name: hashlib.sha256((ROOT / n).read_bytes()).hexdigest()
            for n in REPORTS
            if (ROOT / n).is_file()
        },
    }
    (DEST / "archive-manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Preserved {len(frozen['hashes'])} frozen files and historical reports in {archive}")


if __name__ == "__main__":
    main()
