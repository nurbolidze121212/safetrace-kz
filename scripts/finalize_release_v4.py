"""Verify final release bytes and unchanged tested runtime; write external release receipts."""

import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables/releases/v4"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    assert not (OUT / "release.json").exists(), "Retain an existing final receipt"
    with zipfile.ZipFile(OUT / "SafeTrace-KZ-v4-candidate.zip") as candidate:
        prior = json.loads(candidate.read("PACKAGE_MANIFEST.json"))["files"]
    with zipfile.ZipFile(OUT / "SafeTrace-KZ-v4-source.zip") as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("PACKAGE_MANIFEST.json"))
        current = manifest["files"]
        assert not manifest["git_status"], "Final source should come from a clean local commit"
        for name, entry in current.items():
            raw = archive.read(name)
            assert len(raw) == entry["bytes"] and sha(raw) == entry["sha256"]
            assert not any(p in (".venv", "node_modules", "models", "data", "tmp", "logs", ".git") for p in Path(name).parts)
            assert Path(name).name != ".env"
        prefixes = ("backend/", "frontend/", "fixtures/", "reports/versions/", "datasets/")
        exact = {"models-manifest.json", "requirements.txt", "requirements.lock.txt", ".env.example", "scripts/run_server.py", "scripts/start.ps1", "scripts/stop.ps1", "scripts/setup.ps1", "scripts/prepare_models.py", "scripts/preflight.py", "scripts/backup_data.py"}
        runtime = [name for name in set(prior) | set(current) if name.startswith(prefixes) or name in exact]
        assert all(name in current and name in prior and current[name] == prior[name] for name in runtime)
        changed = [name for name in current if name not in prior or current[name] != prior[name]]
        allowed = ("docs/", "reports/acceptance-v4/", "reports/ACCEPTANCE_V4.md", "reports/HANDOFF_V4.md", "reports/DIAGNOSIS_V4.md", "NEXT_ITERATION_", "output/pdf/", "scripts/verify_transfer_v4.py", "scripts/finalize_release_v4.py")
        assert all(name.startswith(allowed) for name in changed), changed
    for name in ("transfer-stage.json", "transfer-exercise.json", "transfer-restart.json", "main-original-data-preserved.json", "final-integrity.json", "documents-check.json"):
        src = ROOT / "reports/acceptance-v4" / name
        shutil.copy2(src, OUT / name)
    transfer = json.loads((OUT / "transfer-stage.json").read_text(encoding="utf-8"))
    exercise = json.loads((OUT / "transfer-exercise.json").read_text(encoding="utf-8"))
    restart = json.loads((OUT / "transfer-restart.json").read_text(encoding="utf-8"))
    assert transfer["ok"] and exercise["ok"] and restart["ok"]
    assert transfer["candidate_sha256"] == sha((OUT / "SafeTrace-KZ-v4-candidate.zip").read_bytes())
    names = ["SafeTrace-KZ-v4-source.zip", "SafeTrace-KZ-v4-demo-data.zip"]
    result = {"at": datetime.now(timezone.utc).isoformat(), "ok": True, "app_version": "2.2.1", "git_commit": manifest["git_commit"], "final_source_files_verified": len(current), "runtime_files_identical_to_tested_candidate": len(runtime), "changed_from_candidate": changed, "transfer_passed": True, "restore_and_restart_passed": True, "scope": "Actual candidate ZIP extracted and exercised with fresh OCR/export/restart on same Windows PC. Final ZIP runtime is byte-identical to that tested runtime. Documentation, receipts and acceptance helpers were finalized afterward. Shared installed Python environment; no other-machine/fresh-install claim.", "files": {name: {"bytes": (OUT / name).stat().st_size, "sha256": sha((OUT / name).read_bytes())} for name in names}}
    (OUT / "release.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    all_hashes = [(name, value["sha256"]) for name, value in result["files"].items()]
    all_hashes += [("../../SafeTrace-KZ-defense-v4.pptx", sha((ROOT / "deliverables/SafeTrace-KZ-defense-v4.pptx").read_bytes())), ("../../../output/pdf/SafeTrace-KZ-report-v4.pdf", sha((ROOT / "output/pdf/SafeTrace-KZ-report-v4.pdf").read_bytes()))]
    (OUT / "SHA256SUMS.txt").write_text("".join(f"{digest}  {name}\n" for name, digest in all_hashes), encoding="utf-8")
    (OUT / "START-HERE.md").write_text("""# SafeTrace KZ v4 · комплект передачи

Текущий выпуск: приложение 2.2.1, rules-4.0, pipeline-2.2.1.

1. Основной файл — **SafeTrace-KZ-v4-source.zip**. Распакуйте в новую ASCII-папку, например C:\\SafeTrace KZ. Прочитайте docs/HANDOFF_V4.md внутри.
2. **SafeTrace-KZ-v4-demo-data.zip** — отдельная проверенная копия 23 случаев, 8 решений и 8 оригиналов. Восстанавливайте штатным scripts/backup_data.py только в новую папку data.
3. **SHA256SUMS.txt** и **release.json** фиксируют точные байты выпуска и сравнение с испытанным runtime. PowerShell: Get-FileHash .\\SafeTrace-KZ-v4-source.zip -Algorithm SHA256.
4. Модели и зависимости устанавливаются отдельно через scripts/setup.ps1; ключ облака не нужен для локального режима. В архиве нет .env, окружений и моделей.
5. Внутри исходников: README.md; docs/DEMO_V4.md; docs/PITCH_V4.md; docs/FAQ_V4.md; deliverables/SafeTrace-KZ-defense-v4.pptx; output/pdf/SafeTrace-KZ-report-v4.pdf.

Candidate и candidate-release.json оставлены как свидетельство переноса. Для установки используйте source.zip. Проверен тот же ПК с другим каталогом, отдельной базой и скопированными моделями; Python-окружение переиспользовано. Другой физический ПК не проверен.

Новый авторский N=80: TP30/FP2/TN38/FN10, precision 93,75%, recall 75%, FPR 5%. Ложных тревог меньше, пропусков на один больше относительно v3 на тех же входах. Цели precision/recall не достигнуты; независимой оценки и live-пилота нет. Подробности в reports/EVALUATION_V4.md и reports/ERROR_ANALYSIS_V4.md.
""", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "git_commit", "final_source_files_verified", "runtime_files_identical_to_tested_candidate", "files")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
