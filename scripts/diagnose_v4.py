"""Authored development probes. Never a held-out quality evaluation."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum():
        parser.error("Use a short alphanumeric label")
    data = ROOT / "tmp" / ("v4-probes-" + args.label)
    os.environ["SAFETRACE_DATA_DIR"] = str(data)
    os.environ["SAFETRACE_OFFLINE"] = "1"
    from backend import pipeline, storage
    from backend.analysis import WEIGHTS
    from backend.config import PIPELINE_VERSION, RULE_VERSION
    from backend.links import SyntheticTransport
    from backend.schemas import CaseInput, MaterialInput

    storage.init()
    guide = "https://guide-v4.test/notes"
    game = "https://arena-v4.test/play?ref=DEV41"
    pages = {
        guide: {"status": 200, "body": "<p>Расписание встреч библиотеки.</p>"},
        game: {"status": 200, "body": "<p>Казино. Слоты и рулетка.</p>"},
    }
    probes = [
        ("unrelated_branch", False, [MaterialInput(text=f"Заходи к расписанию: {guide}.\nАдрес из приложения к документу: {game}")]),
        ("own_branch", True, [MaterialInput(text=f"Расписание: {guide}.\nЗаходи и забирай бонус: {game}")]),
        ("wrapped_money_transition", True, [MaterialInput(text="Тегін ойын завершён, но теперь играй в нашем\nказино на деньги. Забирай бонус.")]),
        ("information_object", False, [MaterialInput(text="Казино обещает выигрыш — заходи, но только за памяткой о рисках.")]),
        ("quoted_warning", False, [MaterialInput(text="Предупреждение: «Играй в казино, забирай бонус» — так выглядит опасное приглашение. Не переходите.")]),
        ("separate_promotion", True, [MaterialInput(text="Осторожно с чужими предложениями. Играй в нашем казино, забирай бонус.")]),
        ("single", True, [MaterialInput(text="Заходи, забирай бонус.", url=game)]),
        ("duplicate", True, [MaterialInput(text="Заходи, забирай бонус.", url=game), MaterialInput(text="Заходи, забирай бонус.", url=game)]),
        ("different", True, [MaterialInput(text="Заходи, забирай бонус.", url=game), MaterialInput(text="Тіркел, сыйлық ал.", url=game)]),
    ]
    results = []
    for name, expected, materials in probes:
        doc = pipeline.new_case(CaseInput(title="DEV v4: " + name, mode="synthetic", materials=materials))
        pipeline.analyze(doc, fetch=SyntheticTransport(pages))
        storage.save(doc)
        predicted = doc["score"]["value"] >= WEIGHTS["high_threshold"] and doc["sufficient_data"]
        results.append({
            "id": name, "expected": expected, "predicted": predicted,
            "score": doc["score"]["value"], "sufficient": doc["sufficient_data"],
            "contributions": doc["score"]["contributions"], "case_id": doc["id"],
        })
    out = ROOT / "reports" / "acceptance-v4"
    out.mkdir(parents=True, exist_ok=True)
    result = {"kind": "authored-development-probes", "label": args.label,
              "at": storage.now(), "versions": {"rules": RULE_VERSION, "pipeline": PIPELINE_VERSION},
              "automatic_positive": "score >= high_threshold AND sufficient_data",
              "probes": results}
    (out / ("probes-" + args.label + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.label == "baseline":
        protected = {}
        for folder in ("reports/versions", "datasets", "fixtures/replays", "deliverables/releases"):
            for path in (ROOT / folder).rglob("*"):
                if path.is_file():
                    protected[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        (out / "historical-files.json").write_text(json.dumps(protected, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{k: r[k] for k in ("id", "expected", "predicted", "score", "sufficient")} for r in results], ensure_ascii=False))


if __name__ == "__main__":
    main()
