import hashlib
import json
import sqlite3
from contextlib import closing

import pytest

from scripts.preflight import (
    SOURCE_FILES,
    confined,
    digest,
    verify_database,
    verify_frontend,
    verify_model_path,
    verify_models,
)


def test_windows_model_path_rejects_cyrillic_before_reading_or_creating_files(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.preflight.platform.system", lambda: "Windows")
    root = tmp_path / "Передача проекта"
    with pytest.raises(ValueError, match="ASCII"):
        verify_model_path(root)
    assert not root.exists()


def test_windows_model_path_allows_spaces(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.preflight.platform.system", lambda: "Windows")
    assert "совместим" in verify_model_path(tmp_path / "Transfer check v3")


def test_windows_path_restriction_does_not_claim_other_platforms_tested(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.preflight.platform.system", lambda: "Linux")
    assert "отдельно не проверен" in verify_model_path(tmp_path / "Передача проекта")


@pytest.fixture
def built_frontend(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    sources = SOURCE_FILES | {"src/main.tsx", "scripts/write-build-info.mjs"}
    for name in sources:
        path = frontend / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source", encoding="utf-8")
    dist = frontend / "dist"
    outputs = {"index.html", "assets/main.js", "assets/GraphView.js"}
    for name in outputs:
        path = dist / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("built", encoding="utf-8")
    stamp = {
        "schema": "safetrace-frontend-build-1",
        "sources": {n: digest(frontend / n) for n in sources},
        "outputs": {n: digest(dist / n) for n in outputs},
    }
    (dist / "build-info.json").write_text(json.dumps(stamp), encoding="utf-8")
    return frontend


def test_complete_build_is_checked_without_modifying_files(built_frontend):
    before = {str(p): digest(p) for p in built_frontend.rglob("*") if p.is_file()}
    assert "3" in verify_frontend(built_frontend)
    assert before == {str(p): digest(p) for p in built_frontend.rglob("*") if p.is_file()}


@pytest.mark.parametrize("change", ["stale_source", "new_source", "missing_lazy_chunk", "changed_bundle"])
def test_frontend_damage_cannot_be_reported_ready(built_frontend, change):
    if change == "stale_source":
        (built_frontend / "src/main.tsx").write_text("changed", encoding="utf-8")
    elif change == "new_source":
        (built_frontend / "src/new.tsx").write_text("new", encoding="utf-8")
    elif change == "missing_lazy_chunk":
        (built_frontend / "dist/assets/GraphView.js").unlink()
    else:
        (built_frontend / "dist/assets/main.js").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError):
        verify_frontend(built_frontend)


def test_model_bytes_are_verified_not_just_the_directory(tmp_path):
    path = tmp_path / "models/model/weights"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"real fixture bytes")
    (tmp_path / "models-manifest.json").write_text(json.dumps({"files": {"model/weights": digest(path)}}))
    verify_models(tmp_path)
    path.write_bytes(b"truncated")
    with pytest.raises(ValueError, match="Хеш"):
        verify_models(tmp_path)
    with pytest.raises(ValueError, match="выходит"):
        confined(tmp_path / "models", "../../outside")


def test_database_check_reads_existing_records_and_does_not_create_a_missing_database(tmp_path):
    path = tmp_path / "safetrace.sqlite3"
    assert "Новая установка" in verify_database(path)
    assert not path.exists()
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            "CREATE TABLE cases(id TEXT); CREATE TABLE decisions(id INTEGER); INSERT INTO cases VALUES ('a');"
        )
        connection.commit()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert "случаев 1, решений 0" in verify_database(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    path.write_bytes(b"invalid sqlite database")
    with pytest.raises(sqlite3.DatabaseError):
        verify_database(path)
