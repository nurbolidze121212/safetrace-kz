import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest

from scripts import prepare_models as preparation


@pytest.fixture
def model_tree(tmp_path):
    root, cache = tmp_path / "project", tmp_path / "cache"
    root.mkdir()
    files = {}
    for name in preparation.NAMES:
        for filename in ("inference.json", "inference.pdiparams", "inference.yml"):
            data = (name + ":" + filename).encode()
            path = cache / name / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            files[name + "/" + filename] = hashlib.sha256(data).hexdigest()
    (root / "models-manifest.json").write_text(json.dumps({"files": files}))
    shutil.copytree(cache, root / "models")
    return root, cache


def forbid_download(*args):
    pytest.fail("A verified local model must not make a download request")


def test_valid_models_remain_byte_and_timestamp_identical_without_network(model_tree, monkeypatch):
    root, cache = model_tree
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (root / "models").rglob("*") if p.is_file()}
    monkeypatch.setattr(preparation, "download_model", forbid_download)
    assert all(r["action"] == "verified" for r in preparation.prepare(root, cache_root=cache, repair=True))
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}


def test_incomplete_model_needs_explicit_repair_and_preserves_old_files(model_tree, monkeypatch):
    root, cache = model_tree
    target = root / "models" / preparation.NAMES[0]
    (target / "inference.pdiparams").write_bytes(b"interrupted copy")
    monkeypatch.setattr(preparation, "download_model", forbid_download)
    with pytest.raises(ValueError, match="--repair"):
        preparation.prepare(root, cache_root=cache)
    assert (target / "inference.pdiparams").read_bytes() == b"interrupted copy"
    results = preparation.prepare(root, cache_root=cache, repair=True)
    backup = Path(results[0]["previous_files"])
    assert (backup / "inference.pdiparams").read_bytes() == b"interrupted copy"
    assert (target / "inference.pdiparams").read_bytes() == (
        cache / target.name / "inference.pdiparams"
    ).read_bytes()
    assert results[0]["source"] == "verified cache" and results[1]["action"] == "verified"


def test_bad_cache_is_skipped_and_only_verified_download_is_installed(model_tree, monkeypatch, tmp_path):
    root, cache = model_tree
    target = root / "models" / preparation.NAMES[0]
    (target / "inference.json").unlink()
    bad_cache = tmp_path / "bad-cache"
    shutil.copytree(cache, bad_cache)
    (bad_cache / target.name / "inference.json").write_bytes(b"different upstream model")
    downloaded = []

    def download(name, destination, records):
        downloaded.append(name)
        for filename in records:
            shutil.copy2(cache / name / filename, destination / filename)

    monkeypatch.setattr(preparation, "download_model", download)
    result = preparation.prepare(root, cache_root=bad_cache, repair=True)
    assert downloaded == [target.name] and result[0]["source"] == "official download"
    assert (target / "inference.json").read_bytes() == (cache / target.name / "inference.json").read_bytes()


def test_unverified_download_does_not_replace_existing_directory(model_tree, monkeypatch, tmp_path):
    root, _ = model_tree
    target = root / "models" / preparation.NAMES[0]
    (target / "inference.json").write_bytes(b"old broken file")

    def wrong_download(name, destination, records):
        for filename in records:
            (destination / filename).write_bytes(b"wrong version")

    monkeypatch.setattr(preparation, "download_model", wrong_download)
    with pytest.raises(ValueError, match="pinned hashes"):
        preparation.prepare(root, cache_root=tmp_path / "empty", repair=True)
    assert (target / "inference.json").read_bytes() == b"old broken file"
    assert not list((root / "models").glob(".replaced-*"))
    assert not list((root / "models").glob(".prepare-*"))


def test_failed_directory_install_restores_previous_directory(model_tree, monkeypatch):
    root, cache = model_tree
    target = root / "models" / preparation.NAMES[0]
    (target / "inference.json").write_bytes(b"original incomplete file")
    rename = Path.rename

    def fail_stage(self, destination):
        if self.parent.name.startswith(".prepare-"):
            raise OSError("simulated filesystem failure")
        return rename(self, destination)

    monkeypatch.setattr(Path, "rename", fail_stage)
    with pytest.raises(OSError, match="simulated"):
        preparation.prepare(root, cache_root=cache, repair=True)
    assert (target / "inference.json").read_bytes() == b"original incomplete file"
    assert not list((root / "models").glob(".replaced-*"))


@pytest.mark.parametrize("bad_entry", ["traversal", "symlink", "duplicate"])
def test_archive_cannot_supply_unsafe_or_ambiguous_pinned_files(tmp_path, bad_entry):
    archive = tmp_path / "model.tar"
    records = {name: "0" * 64 for name in ("inference.json", "inference.pdiparams", "inference.yml")}
    with tarfile.open(archive, "w") as tar:
        for name in records:
            path = ("../model/" if bad_entry == "traversal" else "model/") + name
            info = tarfile.TarInfo(path)
            if bad_entry == "symlink" and name == "inference.pdiparams":
                info.type = tarfile.SYMTYPE
                info.linkname = "../../outside"
                tar.addfile(info)
            else:
                info.size = 3
                tar.addfile(info, io.BytesIO(b"abc"))
                if bad_entry == "duplicate" and name == "inference.pdiparams":
                    tar.addfile(info, io.BytesIO(b"abc"))
    with pytest.raises(ValueError):
        preparation.extract_model(archive, tmp_path / "staged", records)
    assert not (tmp_path / "staged").exists()


def test_missing_manifest_is_not_regenerated_from_untrusted_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        preparation.prepare(tmp_path)
    assert not (tmp_path / "models-manifest.json").exists()
    assert not (tmp_path / "models").exists()


def test_archive_extracts_only_pinned_files_with_dot_prefix(tmp_path):
    archive = tmp_path / "model.tar"
    records = {
        name: hashlib.sha256(b"abc").hexdigest()
        for name in ("inference.json", "inference.pdiparams", "inference.yml")
    }
    with tarfile.open(archive, "w") as tar:
        for name in ["./model/" + name for name in records] + ["../../outside"]:
            info = tarfile.TarInfo(name)
            info.size = 3
            tar.addfile(info, io.BytesIO(b"abc"))
    preparation.extract_model(archive, tmp_path / "staged", records)
    assert preparation.matches(tmp_path / "staged", records)
    assert {p.name for p in (tmp_path / "staged").iterdir()} == set(records)


def test_manifest_rejects_windows_drive_paths_before_creating_models(model_tree):
    root, _ = model_tree
    manifest = json.loads((root / "models-manifest.json").read_text())
    manifest["files"][preparation.NAMES[0] + "/C:/outside"] = "0" * 64
    with pytest.raises(ValueError, match="Unsafe path"):
        preparation.model_records(manifest, preparation.NAMES[0])
