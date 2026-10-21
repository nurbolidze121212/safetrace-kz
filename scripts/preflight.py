"""Check a local SafeTrace installation without starting analysis or changing cases."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import platform
import sqlite3
import struct
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = {"index.html", "package.json", "package-lock.json", "tsconfig.json", "vite.config.ts"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_model_path(root: Path) -> str:
    # The pinned Windows Paddle runtime fails inside create_predictor for a
    # non-ASCII model path, even when every file exists and its hash is valid.
    if platform.system() == "Windows" and not str(root.resolve() / "models").isascii():
        raise ValueError(
            "Windows OCR не загружает модели из этого пути с нелатинскими символами. "
            "Распакуйте проект в путь только с ASCII-символами, например C:\\SafeTrace-KZ, "
            "и выполните setup.ps1. Пробелы допустимы."
        )
    return (
        "Путь моделей совместим с проверенной Windows-сборкой"
        if platform.system() == "Windows"
        else "Ограничение Windows к этой ОС не применяется; OCR здесь отдельно не проверен"
    )


def confined(root: Path, name: str) -> Path:
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("Путь в manifest выходит за проверяемую папку")
    return candidate


def frontend_sources(frontend: Path) -> set[str]:
    names = set(SOURCE_FILES)
    for folder in ("src", "public", "scripts"):
        directory = frontend / folder
        if directory.exists():
            names.update(p.relative_to(frontend).as_posix() for p in directory.rglob("*") if p.is_file())
    return names


def verify_frontend(frontend: Path) -> str:
    dist = frontend / "dist"
    stamp = json.loads((dist / "build-info.json").read_text(encoding="utf-8"))
    if not isinstance(stamp, dict) or stamp.get("schema") != "safetrace-frontend-build-1":
        raise ValueError("Неизвестный формат отпечатка сборки")
    if not isinstance(stamp.get("sources"), dict) or not isinstance(stamp.get("outputs"), dict):
        raise ValueError("В отпечатке отсутствуют списки файлов")
    if set(stamp["sources"]) != frontend_sources(frontend):
        raise ValueError("Список исходников изменился после сборки")
    outputs = {p.relative_to(dist).as_posix() for p in dist.rglob("*") if p.is_file()}
    outputs.discard("build-info.json")
    if "index.html" not in outputs or set(stamp["outputs"]) != outputs:
        raise ValueError("Состав собранных файлов изменился")
    for base, records in ((frontend, stamp["sources"]), (dist, stamp["outputs"])):
        for name, expected in records.items():
            if digest(confined(base, name)) != expected:
                raise ValueError(f"Файл изменился после сборки: {name}")
    return f"Исходники и {len(outputs)} файлов сборки совпадают с отпечатком"


def verify_models(root: Path) -> str:
    manifest = json.loads((root / "models-manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Некорректный manifest моделей")
    records = manifest["files"]
    if not isinstance(records, dict) or not records:
        raise ValueError("Пустой manifest моделей")
    for name, expected in records.items():
        if digest(confined(root / "models", name)) != expected:
            raise ValueError(f"Хеш модели не совпал: {name}")
    return f"Проверены SHA-256 всех {len(records)} файлов OCR; распознавание не запускалось"


def verify_dependencies(root: Path) -> str:
    checked, problems = 0, []
    for line in (root / "requirements.lock.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, expected = line.partition("==")
        if not separator:
            raise ValueError("В lock-файле обнаружена незакрепленная зависимость")
        checked += 1
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{name}: не установлен")
        else:
            if actual != expected:
                problems.append(f"{name}: {actual}, нужен {expected}")
    if not checked:
        raise ValueError("Lock-файл зависимостей пуст")
    if problems:
        raise ValueError(
            "; ".join(problems[:6]) + (f"; еще {len(problems) - 6}" if len(problems) > 6 else "")
        )
    return f"Совпали версии {checked} пакетов; импорт ML-библиотек не выполнялся"


def verify_database(path: Path) -> str:
    if not path.exists():
        return "Новая установка: база будет создана при первом запуске"
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as connection:
        result = connection.execute("PRAGMA quick_check").fetchall()
        if result != [("ok",)]:
            raise ValueError("SQLite quick_check обнаружил повреждение")
        count = connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        decisions = connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    return f"SQLite quick_check: ok; случаев {count}, решений {decisions}; открыто только для чтения"


def expected_versions(root: Path) -> dict[str, str]:
    tree = ast.parse((root / "backend/config.py").read_text(encoding="utf-8"))
    wanted = {
        "RULE_VERSION": "rules",
        "PIPELINE_VERSION": "pipeline",
        "OCR_VERSION": "ocr",
        "QR_VERSION": "qr",
    }
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    result[wanted[target.id]] = node.value.value
    if set(result) != set(wanted.values()):
        raise ValueError("Не удалось прочитать версии локального ядра")
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_server(root: Path, port: int) -> str:
    request = Request(f"http://127.0.0.1:{port}/api/health", headers={"Accept": "application/json"})
    # Ignore external proxy settings and never follow redirects from a local port.
    from urllib.request import ProxyHandler

    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=3) as response:
        body = response.read(16_385)
        if len(body) > 16_384:
            raise ValueError("Ответ локального сервера превышает ожидаемый размер")
        health = json.loads(body)
    if (
        not isinstance(health, dict)
        or health.get("status") != "ok"
        or health.get("versions") != expected_versions(root)
    ):
        raise ValueError("На порту другая версия приложения; проверьте запущенный процесс")
    if not health.get("ocr_installed"):
        raise ValueError("Сервер не видит установленные модели OCR")
    mode = "офлайн" if health.get("offline") else "с разрешенными сетевыми запросами"
    return f"SafeTrace {health.get('app_version', '')}, {mode}; версии совпадают с локальным ядром"


def data_directory(root: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    value = os.getenv("SAFETRACE_DATA_DIR")
    if not value and (root / ".env").is_file():
        try:
            from dotenv import dotenv_values
        except ImportError:
            raise ValueError("Для чтения настроенного пути данных установите зависимости") from None
        value = dotenv_values(root / ".env").get("SAFETRACE_DATA_DIR")
    return Path(value).resolve() if value else root / "data"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", action="store_true", help="Также проверить уже запущенный localhost API")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", help="Явно выбрать используемую папку данных")
    parser.add_argument(
        "--report", type=Path, help="Сохранить JSON с результатами, без содержимого случаев и секретов"
    )
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Порт должен быть в диапазоне 1024–65535")
    checks = []

    def check(name, action, remedy):
        try:
            detail = action()
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, HTTPError, URLError) as error:
            # Do not include arbitrary response bodies or environment values.
            detail = str(error) if isinstance(error, ValueError) else type(error).__name__
            checks.append({"name": name, "ok": False, "detail": detail, "remedy": remedy})
        else:
            checks.append({"name": name, "ok": True, "detail": detail})

    def runtime():
        if sys.version_info[:2] not in ((3, 11), (3, 12)) or struct.calcsize("P") != 8:
            raise ValueError("Нужен Python 3.11/3.12 x64; проверенная версия — 3.12.14")
        return f"Python {platform.python_version()} x64; {platform.system()}"

    check("Python", runtime, "Запустите скрипт через .venv\\Scripts\\python.exe")
    check(
        "Путь OCR",
        lambda: verify_model_path(ROOT),
        "Используйте каталог с ASCII-путем и заново выполните setup.ps1",
    )
    check("Зависимости", lambda: verify_dependencies(ROOT), "Выполните scripts\\setup.ps1")
    check("Модели OCR", lambda: verify_models(ROOT), "Выполните scripts\\prepare_models.py через .venv")
    check(
        "Frontend",
        lambda: verify_frontend(ROOT / "frontend"),
        "Выполните npm.cmd --prefix frontend run build",
    )
    check(
        "База",
        lambda: verify_database(data_directory(ROOT, args.data_dir) / "safetrace.sqlite3"),
        "Проверьте путь данных; сохраните копию и восстановите проверенную резервную базу",
    )
    if args.server:
        check(
            "Локальный сервер",
            lambda: verify_server(ROOT, args.port),
            "Запустите scripts\\start.ps1 -Offline на нужном порту",
        )
    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "scope": "Установка и сохраненные файлы; не новый OCR, не оценка качества, не живой вызов облака",
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    for item in checks:
        print(f"{'OK' if item['ok'] else 'FAIL'} · {item['name']}: {item['detail']}")
        if not item["ok"]:
            print("  Исправление: " + item["remedy"])
    print("Проверка установки пройдена." if report["ok"] else "Перед показом исправьте отмеченные пункты.")
    print(report["scope"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
