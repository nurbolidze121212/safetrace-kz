"""Prepare pinned official CPU model assets; runtime never auto-downloads."""

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
import uuid
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("PP-OCRv5_mobile_det", "cyrillic_PP-OCRv5_mobile_rec")
BASE = "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/"
MAX_ARCHIVE = 64 * 1024 * 1024


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def model_records(manifest, name):
    records = {}
    for key, value in manifest["files"].items():
        if not key.startswith(name + "/"):
            continue
        relative = PurePosixPath(key.removeprefix(name + "/"))
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in key
            or ":" in key
            or not relative.parts
        ):
            raise ValueError("Unsafe path in models-manifest.json")
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("Invalid SHA-256 in models-manifest.json")
        records[relative.as_posix()] = value
    if not {"inference.json", "inference.pdiparams", "inference.yml"}.issubset(records):
        raise ValueError(
            f"Incomplete pinned manifest for {name}; restore models-manifest.json from the project"
        )
    return records


def matches(folder, records):
    try:
        return all(
            (folder / name).is_file()
            and not (folder / name).is_symlink()
            and digest(folder / name) == expected
            for name, expected in records.items()
        )
    except OSError:
        return False


def extract_model(archive, destination, records):
    # Read only the pinned files, never arbitrary archive paths or links.
    with tarfile.open(archive) as tar:
        entries = tar.getmembers()
        candidates = [m for m in entries if PurePosixPath(m.name).name == "inference.json"]
        if len(candidates) != 1:
            raise ValueError("Official archive has an ambiguous model directory")
        parent = PurePosixPath(candidates[0].name).parent
        if parent.is_absolute() or ".." in parent.parts:
            raise ValueError("Unsafe model directory in archive")
        members = {PurePosixPath(m.name).as_posix(): m for m in entries}
        if len(members) != len(entries):
            raise ValueError("Duplicate archive entries")
        selected = [members.get(str(parent / name)) for name in records]
        if any(m is None or not m.isfile() or m.size > MAX_ARCHIVE for m in selected):
            raise ValueError("Archive is missing a regular pinned model file")
        if sum(m.size for m in selected) > MAX_ARCHIVE:
            raise ValueError("Expanded model exceeds 64 MiB")
        for name, member in zip(records, selected):
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, path.open("xb") as output:
                shutil.copyfileobj(source, output)


def download_model(name, destination, records):
    print("Downloading pinned official model:", name, flush=True)
    with tempfile.TemporaryDirectory(prefix="safetrace-download-") as folder:
        archive = Path(folder) / "model.tar"
        with (
            urllib.request.urlopen(BASE + name + "_infer.tar", timeout=90) as response,
            archive.open("xb") as output,
        ):
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE:
                    raise ValueError("Model download exceeds 64 MiB")
                output.write(chunk)
        extract_model(archive, destination, records)


def prepare(root=ROOT, *, cache_root=None, repair=False):
    manifest = json.loads((root / "models-manifest.json").read_text(encoding="utf-8"))
    expected = {name: model_records(manifest, name) for name in NAMES}
    models = root / "models"
    models.mkdir(exist_ok=True)
    cache_root = cache_root if cache_root is not None else Path.home() / ".paddlex/official_models"
    results = []
    for name, records in expected.items():
        target = models / name
        if target.is_symlink():
            raise ValueError("Model target must be a regular directory, not a symbolic link")
        if matches(target, records):
            results.append({"model": name, "action": "verified"})
            continue
        if target.exists() and not repair:
            raise ValueError(
                f"Model {name} is incomplete or changed. Stop SafeTrace and run "
                "scripts/prepare_models.py --repair; previous files will be preserved."
            )
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=models) as folder:
            staged = Path(folder) / name
            staged.mkdir()
            cache = cache_root / name
            if matches(cache, records):
                for relative in records:
                    output = staged / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(cache / relative, output)
                source = "verified cache"
            else:
                download_model(name, staged, records)
                source = "official download"
            if not matches(staged, records):
                raise ValueError(
                    f"Downloaded/copied {name} differs from pinned hashes; existing files were not replaced"
                )
            backup = None
            if target.exists():
                backup = models / f".replaced-{name}-{uuid.uuid4().hex}"
                target.rename(backup)
            try:
                staged.rename(target)
            except OSError:
                if backup is not None and not target.exists():
                    backup.rename(target)
                raise
            result = {"model": name, "action": "repaired" if backup else "installed", "source": source}
            if backup:
                result["previous_files"] = str(backup)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Restore pinned files, preserving replaced directories; stop the server first",
    )
    args = parser.parse_args()
    try:
        prepare(repair=args.repair)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        print(f"Model preparation failed: {error}")
        return 1
    print("Models ready; hashes verified. Existing valid models were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
