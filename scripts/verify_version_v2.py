"""Read-only integrity verification of the frozen v2 core, data and reports."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/versions/synthetic-v2"
checked = {}
for name in ("core-freeze.json", "data-freeze.json"):
    manifest = json.loads((REPORTS / name).read_text(encoding="utf-8"))
    for path, digest in manifest["hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    checked[name] = len(manifest["hashes"])
for prefix in ("evaluation", "regression-v1"):
    result = json.loads((REPORTS / (prefix + ".json")).read_text(encoding="utf-8"))
    with zipfile.ZipFile(REPORTS / (prefix + "-core-source.zip")) as archive:
        for path, digest in result["core_hashes"].items():
            assert hashlib.sha256(archive.read(path)).hexdigest() == digest, path
    for path, digest in result["data_hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    checked[prefix + "-archive"] = len(result["core_hashes"])
    rows = json.loads((REPORTS / (prefix + "-predictions.json")).read_text(encoding="utf-8"))
    for variant, metrics in result["variants"].items():
        selected = [row for row in rows if row["variant"] == variant]
        assert len(selected) == metrics["n"]
        for key, truth, predicted in (("tp", 1, 1), ("fp", 0, 1), ("tn", 0, 0), ("fn", 1, 0)):
            assert sum(r["truth"] == truth and r["predicted"] == predicted for r in selected) == metrics[key]
checked["all_match"] = True
(ROOT / "reports/acceptance-v2/freeze-check.json").write_text(json.dumps(checked, indent=2), encoding="utf-8")
print(json.dumps(checked))
