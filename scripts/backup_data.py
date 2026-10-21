"""Create, verify, or restore a complete local SafeTrace data snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "safetrace-backup-1"
IMAGE_ID = re.compile(r"[a-f0-9]{32}\.(png|jpg|webp)")
SHA256 = re.compile(r"[a-f0-9]{64}")
MAX_DATABASE = 512 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
MAX_MANIFEST = 2 * 1024 * 1024
MAX_FILES = 10000


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def readonly_database(path: Path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def inspect_database(path: Path) -> tuple[dict, dict[str, set[str]]]:
    """Read the snapshot, including original references inside analysis history."""
    references: dict[str, set[str]] = {}

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if value.get("image_id"):
                image_id = value["image_id"]
                if not isinstance(image_id, str) or not IMAGE_ID.fullmatch(image_id):
                    raise ValueError("Некорректный идентификатор оригинала в базе")
                expected = value.get("image_sha256")
                fingerprints = references.setdefault(image_id, set())
                if expected is not None:
                    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
                        raise ValueError("Некорректный SHA-256 оригинала в базе")
                    fingerprints.add(expected)
            if value.get("original_sha256") and "text" in value:
                text = value["text"]
                if (
                    not isinstance(text, str)
                    or hashlib.sha256(text.encode()).hexdigest() != value["original_sha256"]
                ):
                    raise ValueError("Текст оригинала не совпадает с сохраненным SHA-256")
            for item in value.values():
                visit(item)

    with closing(readonly_database(path)) as connection:
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite не прошла quick_check")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"cases", "decisions", "cache"}.issubset(tables):
            raise ValueError("В базе отсутствуют таблицы SafeTrace")
        cases, active = 0, 0
        for case_id, raw in connection.execute("SELECT id, document FROM cases"):
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get("id") != case_id:
                raise ValueError("Идентификатор случая не совпадает с документом")
            visit(document)
            cases += 1
            active += document.get("status") in {"pending", "running"}
        counts = {
            "cases": cases,
            "decisions": connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0],
            "cache_entries": connection.execute("SELECT COUNT(*) FROM cache").fetchone()[0],
            "active_cases": active,
        }
    if any(len(values) > 1 for values in references.values()):
        raise ValueError("Один оригинал имеет разные SHA-256 в истории")
    return counts, references


def copy_checked(source: Path, destination: Path, limit: int) -> dict:
    size = source.stat().st_size
    if size > limit:
        raise ValueError("Файл превышает лимит резервной копии")
    destination.parent.mkdir(parents=True, exist_ok=True)
    hasher, total = hashlib.sha256(), 0
    with source.open("rb") as incoming, destination.open("xb") as outgoing:
        while chunk := incoming.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise ValueError("Файл вырос сверх лимита при копировании")
            outgoing.write(chunk)
            hasher.update(chunk)
    return {"bytes": total, "sha256": hasher.hexdigest()}


def create_backup(data: Path, output: Path) -> dict:
    data, output = data.resolve(), output.absolute()
    if output.exists():
        raise FileExistsError("Архив уже существует; выберите новое имя")
    database = data / "safetrace.sqlite3"
    if not database.is_file():
        raise ValueError("База SafeTrace не найдена; пустая база не создается")
    if database.stat().st_size > MAX_DATABASE:
        raise ValueError("База превышает лимит резервной копии 512 MiB")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".safetrace-backup-", dir=output.parent) as scratch:
        stage = Path(scratch)
        snapshot = stage / "safetrace.sqlite3"
        # SQLite backup includes committed WAL records and yields one consistent snapshot.
        with closing(readonly_database(database)) as source, closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")
        counts, references = inspect_database(snapshot)
        records = {"safetrace.sqlite3": {"bytes": snapshot.stat().st_size, "sha256": digest(snapshot)}}
        for image_id, expected in sorted(references.items()):
            source = (data / "originals" / image_id).resolve(strict=True)
            if not source.is_relative_to(data) or source.parent != (data / "originals").resolve():
                raise ValueError("Оригинал находится вне папки данных")
            record = copy_checked(source, stage / "originals" / image_id, MAX_IMAGE)
            if expected and record["sha256"] not in expected:
                raise ValueError("Оригинал изображения изменен: SHA-256 не совпадает")
            records[f"originals/{image_id}"] = record
        if len(records) + 1 > MAX_FILES or sum(item["bytes"] for item in records.values()) > MAX_TOTAL:
            raise ValueError("Резервная копия превышает лимит 1 GiB / 10000 файлов")
        manifest = {
            "schema": SCHEMA,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": counts,
            "referenced_images": len(references),
            "scope": "SQLite snapshot and image originals referenced by cases and history; unused uploads excluded",
            "files": records,
        }
        archive = stage / "snapshot.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name in records:
                bundle.write(stage / name, name)
            bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        verify_backup(archive)
        # Exclusive creation: an existing user archive can never be overwritten.
        with archive.open("rb") as incoming, output.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
    return manifest


def unpack_verified(archive: Path, destination: Path) -> dict:
    """Extract only exact expected names into our private staging folder."""
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        names = [item.filename for item in infos]
        if len(infos) > MAX_FILES or len(names) != len(set(names)):
            raise ValueError("Слишком много файлов или повторяющиеся имена в ZIP")
        if "manifest.json" not in names:
            raise ValueError("В архиве отсутствует manifest.json")
        for item in infos:
            name = item.filename
            image_name = name.removeprefix("originals/") if name.startswith("originals/") else ""
            if name not in {"manifest.json", "safetrace.sqlite3"} and not IMAGE_ID.fullmatch(image_name):
                raise ValueError("В архиве есть недопустимый путь")
            if stat.S_ISLNK(item.external_attr >> 16) or item.is_dir() or item.flag_bits & 1:
                raise ValueError("Ссылки, папки и зашифрованные записи не поддерживаются")
            limit = (
                MAX_MANIFEST
                if name == "manifest.json"
                else MAX_DATABASE
                if name == "safetrace.sqlite3"
                else MAX_IMAGE
            )
            if item.file_size > limit:
                raise ValueError("Файл архива превышает допустимый размер")
        if sum(item.file_size for item in infos) > MAX_TOTAL:
            raise ValueError("Распакованный архив превышает 1 GiB")
        manifest = json.loads(bundle.read("manifest.json"))
        if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
            raise ValueError("Неизвестный формат резервной копии")
        records = manifest.get("files")
        if (
            not isinstance(records, dict)
            or set(records) != set(names) - {"manifest.json"}
            or "safetrace.sqlite3" not in records
        ):
            raise ValueError("Состав ZIP не совпадает с manifest")
        for name, record in records.items():
            if (
                not isinstance(record, dict)
                or not isinstance(record.get("sha256"), str)
                or not SHA256.fullmatch(record["sha256"])
            ):
                raise ValueError("Некорректный хеш в manifest")
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            hasher, total = hashlib.sha256(), 0
            with bundle.open(name) as incoming, target.open("xb") as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    total += len(chunk)
                    outgoing.write(chunk)
                    hasher.update(chunk)
            if total != record.get("bytes") or hasher.hexdigest() != record["sha256"]:
                raise ValueError("Размер или SHA-256 файла не совпадает с manifest")
    counts, references = inspect_database(destination / "safetrace.sqlite3")
    if counts != manifest.get("database") or len(references) != manifest.get("referenced_images"):
        raise ValueError("Сводка manifest не совпадает с содержимым базы")
    expected_files = {"safetrace.sqlite3"} | {f"originals/{name}" for name in references}
    if set(records) != expected_files:
        raise ValueError("Архив не содержит точный набор оригиналов из базы и истории")
    for image_id, expected in references.items():
        if expected and records[f"originals/{image_id}"]["sha256"] not in expected:
            raise ValueError("Хеш оригинала не совпадает с записью в базе")
    return manifest


def verify_backup(archive: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="safetrace-verify-") as scratch:
        return unpack_verified(archive, Path(scratch))


def restore_backup(archive: Path, destination: Path) -> dict:
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Папка восстановления уже существует; выберите новую")
    # Complete validation happens before creating the destination.
    with tempfile.TemporaryDirectory(prefix="safetrace-restore-") as scratch:
        stage = Path(scratch)
        manifest = unpack_verified(archive, stage)
        destination.mkdir(parents=True, exist_ok=False)
        for name in manifest["files"]:
            copy_checked(stage / name, destination / name, MAX_TOTAL)
        (destination / "originals").mkdir(exist_ok=True)
        (destination / "backup-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    return manifest


def default_data() -> Path:
    value = os.getenv("SAFETRACE_DATA_DIR")
    if not value and (ROOT / ".env").is_file():
        from dotenv import dotenv_values

        value = dotenv_values(ROOT / ".env").get("SAFETRACE_DATA_DIR")
    return Path(value).resolve() if value else ROOT / "data"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Согласованная копия базы и связанных оригиналов")
    create.add_argument("--data-dir", type=Path)
    create.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="Проверить ZIP, хеши, SQLite и все ссылки на оригиналы")
    verify.add_argument("archive", type=Path)
    restore = commands.add_parser("restore", help="Восстановить проверенный архив только в новую папку")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--to", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create_backup(args.data_dir or default_data(), args.output)
        elif args.command == "verify":
            result = verify_backup(args.archive)
        else:
            result = restore_backup(args.archive, args.to)
        print(
            json.dumps(
                {
                    "ok": True,
                    "command": args.command,
                    **result["database"],
                    "images": result["referenced_images"],
                },
                ensure_ascii=False,
            )
        )
        if result["database"]["active_cases"]:
            print(
                "Копия содержит незавершенные задачи; после восстановления приложение предложит повтор анализа."
            )
        return 0
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        sqlite3.Error,
        zipfile.BadZipFile,
    ) as error:
        print(f"Ошибка резервной копии: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
