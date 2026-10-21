import hashlib
import json
import sqlite3
import zipfile
from contextlib import closing

import pytest

from scripts.backup_data import create_backup, restore_backup, verify_backup


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def stored_data(tmp_path):
    data = tmp_path / "live"
    originals = data / "originals"
    originals.mkdir(parents=True)
    current, historical = "a" * 32 + ".png", "b" * 32 + ".jpg"
    for name, content in ((current, b"current image"), (historical, b"historical image")):
        (originals / name).write_bytes(content)
    (originals / ("c" * 32 + ".png")).write_bytes(b"unused upload")
    document = {
        "id": "case-a",
        "status": "completed",
        "materials": [
            {
                "image_id": current,
                "image_sha256": fingerprint(b"current image"),
                "text": "Қазақша текст",
                "original_sha256": fingerprint("Қазақша текст".encode()),
            }
        ],
        "history": [
            {"materials": [{"image_id": historical, "image_sha256": fingerprint(b"historical image")}]}
        ],
    }
    with closing(sqlite3.connect(data / "safetrace.sqlite3")) as connection:
        connection.executescript("""
            CREATE TABLE cases(id TEXT PRIMARY KEY, document TEXT NOT NULL);
            CREATE TABLE decisions(id INTEGER PRIMARY KEY, case_id TEXT, comment TEXT);
            CREATE TABLE cache(key TEXT PRIMARY KEY, document TEXT);
        """)
        connection.execute("INSERT INTO cases VALUES (?,?)", ("case-a", json.dumps(document)))
        connection.execute("INSERT INTO decisions VALUES (1,'case-a','Проверено вручную')")
        connection.execute("INSERT INTO cache VALUES ('cached','{\"source\":\"saved\"}')")
        connection.commit()
    return data


def rewrite_zip(source, destination, change):
    with zipfile.ZipFile(source) as bundle:
        files = {name: bundle.read(name) for name in bundle.namelist()}
    change(files)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)


def change_document(data, change):
    with closing(sqlite3.connect(data / "safetrace.sqlite3")) as connection:
        doc = json.loads(connection.execute("SELECT document FROM cases").fetchone()[0])
        change(doc)
        connection.execute("UPDATE cases SET document=?", (json.dumps(doc),))
        connection.commit()


def test_roundtrip_preserves_database_history_originals_decisions_and_cache(stored_data, tmp_path):
    before = (stored_data / "safetrace.sqlite3").read_bytes()
    archive, restored = tmp_path / "backup.zip", tmp_path / "restored"
    result = create_backup(stored_data, archive)
    assert result["referenced_images"] == 2
    assert verify_backup(archive) == result == restore_backup(archive, restored)
    assert (stored_data / "safetrace.sqlite3").read_bytes() == before
    assert sorted(p.name for p in (restored / "originals").iterdir()) == [
        "a" * 32 + ".png",
        "b" * 32 + ".jpg",
    ]
    for name in ["a" * 32 + ".png", "b" * 32 + ".jpg"]:
        assert (stored_data / "originals" / name).read_bytes() == (restored / "originals" / name).read_bytes()
    with closing(sqlite3.connect(restored / "safetrace.sqlite3")) as connection:
        assert connection.execute("SELECT comment FROM decisions").fetchone()[0] == "Проверено вручную"
        assert json.loads(connection.execute("SELECT document FROM cache").fetchone()[0]) == {
            "source": "saved"
        }
        assert json.loads(connection.execute("SELECT document FROM cases").fetchone()[0])["history"]


def test_snapshot_contains_committed_wal_and_excludes_uncommitted_write(stored_data, tmp_path):
    with closing(sqlite3.connect(stored_data / "safetrace.sqlite3")) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute(
            "INSERT INTO cases VALUES ('case-b',?)", (json.dumps({"id": "case-b", "status": "pending"}),)
        )
        writer.commit()
        writer.execute("INSERT INTO cases VALUES ('case-c',?)", (json.dumps({"id": "case-c"}),))
        result = create_backup(stored_data, tmp_path / "wal.zip")
        assert result["database"]["cases"] == 2
        assert result["database"]["active_cases"] == 1
        writer.rollback()


@pytest.mark.parametrize("failure", ["missing", "changed", "text", "unsafe_id", "conflicting_history"])
def test_invalid_originals_cannot_create_a_successful_backup(stored_data, tmp_path, failure):
    if failure == "missing":
        (stored_data / "originals" / ("b" * 32 + ".jpg")).unlink()
    elif failure == "changed":
        (stored_data / "originals" / ("a" * 32 + ".png")).write_bytes(b"changed")
    elif failure == "text":
        change_document(stored_data, lambda d: d["materials"][0].update(text="changed"))
    elif failure == "unsafe_id":
        change_document(stored_data, lambda d: d["materials"][0].update(image_id="../outside.png"))
    else:
        change_document(
            stored_data,
            lambda d: d["history"][0]["materials"].append(
                {
                    "image_id": "a" * 32 + ".png",
                    "image_sha256": "0" * 64,
                }
            ),
        )
    archive = tmp_path / "invalid.zip"
    with pytest.raises((ValueError, FileNotFoundError)):
        create_backup(stored_data, archive)
    assert not archive.exists()


@pytest.mark.parametrize(
    "failure", ["changed_bytes", "changed_manifest_and_bytes", "missing", "traversal", "counts"]
)
def test_bad_archive_never_creates_restore_destination(stored_data, tmp_path, failure):
    archive, bad, destination = tmp_path / "good.zip", tmp_path / "bad.zip", tmp_path / "restore"
    create_backup(stored_data, archive)
    image_name = "originals/" + "a" * 32 + ".png"

    def corrupt(files):
        manifest = json.loads(files["manifest.json"])
        if failure in {"changed_bytes", "changed_manifest_and_bytes"}:
            files[image_name] = b"tampered"
            if failure == "changed_manifest_and_bytes":
                manifest["files"][image_name] = {"bytes": 8, "sha256": fingerprint(b"tampered")}
        elif failure == "missing":
            del files[image_name]
        elif failure == "traversal":
            files["../outside.txt"] = b"outside"
        else:
            manifest["database"]["cases"] += 1
        files["manifest.json"] = json.dumps(manifest).encode()

    rewrite_zip(archive, bad, corrupt)
    with pytest.raises(ValueError):
        restore_backup(bad, destination)
    assert not destination.exists()
    assert not (tmp_path / "outside.txt").exists()


def test_existing_archive_and_existing_restore_folder_are_preserved(stored_data, tmp_path):
    archive = tmp_path / "backup.zip"
    create_backup(stored_data, archive)
    original_archive = archive.read_bytes()
    with pytest.raises(FileExistsError):
        create_backup(stored_data, archive)
    assert archive.read_bytes() == original_archive
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep.txt").write_text("user file")
    with pytest.raises(FileExistsError):
        restore_backup(archive, destination)
    assert (destination / "keep.txt").read_text() == "user file"
    assert len(list(destination.iterdir())) == 1


def test_duplicate_zip_entry_is_rejected(stored_data, tmp_path):
    archive = tmp_path / "duplicate.zip"
    create_backup(stored_data, archive)
    with zipfile.ZipFile(archive, "a") as bundle, pytest.warns(UserWarning, match="Duplicate name"):
        bundle.writestr("manifest.json", "{}")
    with pytest.raises(ValueError, match="повторяющиеся"):
        verify_backup(archive)


def test_missing_database_is_not_silently_created(tmp_path):
    with pytest.raises(ValueError, match="не найдена"):
        create_backup(tmp_path / "missing", tmp_path / "backup.zip")
    assert not (tmp_path / "missing").exists()
