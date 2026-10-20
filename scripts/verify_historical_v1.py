"""Verify v1 against the preserved snapshot, independently of the working v2 core."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "reports" / "versions" / "synthetic-v1"


def verify():
    meta = json.loads((DEST / "archive-manifest.json").read_text(encoding="utf-8"))
    archive = DEST / "frozen-source.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == meta["archive_sha256"]
    frozen = json.loads((DEST / "test-freeze.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(archive) as z:
        for name, expected in frozen["hashes"].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == expected, name
    for name, expected in meta["report_hashes"].items():
        assert hashlib.sha256((DEST / name).read_bytes()).hexdigest() == expected, name
    return {"source_files": len(frozen["hashes"]), "reports": len(meta["report_hashes"]), "all_match": True}


if __name__ == "__main__":
    print(json.dumps(verify()))
