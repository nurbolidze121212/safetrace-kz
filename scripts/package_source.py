"""Create/verify a source snapshot from tracked files plus the current frontend build."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = {".git", ".venv", "node_modules", "data", "models", "logs", "tmp", "__pycache__"}


def safe_path(name):
    path = PurePosixPath(name)
    return (not path.is_absolute() and ".." not in path.parts and "\\" not in name
            and ":" not in name and not BLOCKED.intersection(path.parts)
            and (not path.name.startswith(".env") or path.name == ".env.example") and not path.name.endswith((".sqlite3", ".pyc")))


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not all(safe_path(n) for n in names):
            raise ValueError("Unsafe or duplicate archive paths")
        manifest = json.loads(archive.read("PACKAGE_MANIFEST.json"))
        if set(names) != set(manifest["files"]) | {"PACKAGE_MANIFEST.json"}:
            raise ValueError("Manifest inventory mismatch")
        for name, expected in manifest["files"].items():
            data = archive.read(name)
            if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                raise ValueError("Content mismatch: " + name)
    return {"files": len(manifest["files"]), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def create(output):
    from scripts.preflight import verify_frontend

    verify_frontend(ROOT / "frontend")
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    names = {n for n in tracked if n and safe_path(n)}
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "frontend/dist").rglob("*") if p.is_file())
    manifest = {"schema": "safetrace-source-1", "created_at": datetime.now(timezone.utc).isoformat(),
                "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
                "working_tree_changes": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
                "scope": "Tracked working files and verified frontend build; no working database, keys, models or environments", "files": {}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            path = ROOT / name
            if not safe_path(name) or path.is_symlink() or not path.is_file():
                raise ValueError("Unsafe or missing file: " + name)
            data = path.read_bytes()
            manifest["files"][name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            archive.writestr(name, data)
        archive.writestr("PACKAGE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return verify(output)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--verify", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.verify) if args.verify else create(args.output), ensure_ascii=False))
