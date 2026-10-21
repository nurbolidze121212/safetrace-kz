"""Create a new local source release without environment, secrets, models or mutable data."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables/releases/v4"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main(candidate=False):
    target = OUT / ("SafeTrace-KZ-v4-candidate.zip" if candidate else "SafeTrace-KZ-v4-source.zip")
    assert not target.exists(), "Never replace an existing release"
    # Enumerate Git-visible files, including newly created work. Never traverse tmp junctions.
    listed = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT
        )
        .decode("utf-8")
        .split("\0")
    )
    names = set(filter(None, listed))
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "frontend/dist").rglob("*") if p.is_file())
    names.add("deliverables/releases/SafeTrace-KZ-v3-source.zip")
    forbidden = {
        ".git",
        ".venv",
        ".venv-setup-check",
        "node_modules",
        "models",
        "data",
        "tmp",
        "logs",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
    }
    files = {}
    for name in sorted(names):
        parts = PurePosixPath(name).parts
        if (
            any(part in forbidden for part in parts)
            or name == ".env"
            or name.startswith("deliverables/releases/v4/")
        ):
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        assert path.resolve().is_relative_to(ROOT.resolve())
        files[name] = path.read_bytes()
    required = [
        "docs/HANDOFF_V4.md",
        "docs/DEMO_V4.md",
        "reports/EVALUATION_V4.md",
        "reports/ERROR_ANALYSIS_V4.md",
        "deliverables/SafeTrace-KZ-defense-v4.pptx",
        "output/pdf/SafeTrace-KZ-report-v4.pdf",
    ]
    assert all(name in files for name in required), [name for name in required if name not in files]
    selection = json.loads(files["reports/versions/synthetic-v4/selection.json"])
    manifest = {
        "schema": "safetrace-source-release-1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_status": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip(),
        "app_version": "2.2.1",
        "metric_selected_configuration": selection["selected"],
        "scope": "Local source and built frontend; install pinned runtime dependencies/models separately. Includes preserved v3 source archive for comparison. Mutable user data is a separate verified backup.",
        "files": {name: {"bytes": len(data), "sha256": sha(data)} for name, data in files.items()},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr("PACKAGE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for name, item in manifest["files"].items():
            data = archive.read(name)
            assert len(data) == item["bytes"] and sha(data) == item["sha256"]
    result = {
        "source": target.name,
        "sha256": sha(target.read_bytes()),
        "bytes": target.stat().st_size,
        "files_verified": len(files),
        "commit": manifest["git_commit"],
    }
    with (OUT / ("candidate-release.json" if candidate else "source-release.json")).open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", action="store_true")
    main(parser.parse_args().candidate)
