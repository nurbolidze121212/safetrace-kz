"""Re-run known v3 failures as regressions; never label them a fresh quality test."""

# ruff: noqa: E402
import argparse
import hashlib
import itertools
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "tmp/v4-known-error-data")
os.environ["SAFETRACE_OFFLINE"] = "1"
from backend import pipeline, storage
from backend.analysis import score
from backend.config import DATA
from backend.links import SyntheticTransport
from backend.schemas import CaseInput, MaterialInput
from scripts.evaluate_v4 import core_hashes, write


def main(label):
    target = ROOT / "reports/acceptance-v4" / ("known-errors-" + label + ".json")
    if target.exists():
        raise RuntimeError("Keep previous regression results")
    storage.init()
    before = core_hashes()
    dataset = ROOT / "datasets/synthetic-v3"
    inputs = {
        r["id"]: r for r in map(json.loads, (dataset / "test.jsonl").read_text(encoding="utf-8").splitlines())
    }
    errors = json.loads(
        (ROOT / "reports/versions/synthetic-v3/error-analysis.json").read_text(encoding="utf-8")
    )
    pages = json.loads((dataset / "test-pages.json").read_text(encoding="utf-8"))
    results = []
    for error in errors:
        materials = []
        for raw in inputs[error["id"]]["materials"]:
            mat = {k: v for k, v in raw.items() if k != "image"}
            if raw.get("image"):
                path = dataset / raw["image"]
                image_id = hashlib.sha256(path.read_bytes()).hexdigest()[:32] + path.suffix
                (DATA / "originals" / image_id).write_bytes(path.read_bytes())
                mat["image_id"] = image_id
            materials.append(MaterialInput(**mat))
        doc = pipeline.new_case(CaseInput(title="Known v3 regression", mode="synthetic", materials=materials))
        pipeline.analyze(doc, fetch=SyntheticTransport(pages), use_ocr_cache=False)
        results.append(
            {
                "id": error["id"],
                "truth": error["truth"],
                "prior_score": error["score"],
                "prior_sufficient": error["sufficient"],
                "prior_note": error["analysis_note"],
                "score": doc["score"]["value"],
                "sufficient": doc["sufficient_data"],
                "predicted": int(doc["score"]["value"] >= 65 and doc["sufficient_data"]),
                "url_reviews": [r for m in doc["materials"] for r in m.get("url_reviews", [])],
                "status": doc["status"],
                "limitations": doc["limitations"],
            }
        )
        print(
            json.dumps({k: results[-1][k] for k in ("id", "truth", "score", "sufficient", "predicted")}),
            flush=True,
        )
    possibilities = set()
    for direct, bonus, promise, repeated, alternative, contradiction in itertools.product(
        (False, True), repeat=6
    ):
        kinds = (
            (["gambling", "call_to_action"] if direct else [])
            + (["bonus"] if bonus else [])
            + (["promise"] if promise else [])
        )
        claims = [{"kind": kind, "evidence_id": kind} for kind in kinds]
        possibilities.add(
            score(
                claims,
                [],
                "free_game" if alternative else "promotion",
                repeated,
                ["x"] if contradiction else [],
            )["value"]
        )
    url = "https://score-dev.test/item?ref=T7"
    medium = pipeline.new_case(
        CaseInput(
            title="Проверка достижимости индекса",
            mode="synthetic",
            materials=[
                MaterialInput(text="Бесплатная игра. Заходи, забирай бонус и выигрыш.", url=url),
                MaterialInput(text="Тегін ойын. Тіркел, сыйлық пен ұтыс ал.", url=url),
            ],
        )
    )
    pipeline.analyze(medium, fetch=SyntheticTransport({url: {"status": 200, "body": "Казино и слоты."}}))
    assert before == core_hashes()
    write(
        target,
        {
            "provenance": "Known v3 errors, regression only; no new final accuracy claim",
            "core_hashes": before,
            "rows": results,
            "score_audit": {
                "algebraically_possible_values": sorted(possibilities),
                "medium_example_value": medium["score"]["value"],
                "medium_example_materials": [m["text"] for m in medium["materials"]],
                "medium_example_reasons": medium["score"]["contributions"],
                "meaning": "Discrete heuristic index; medium band is sparse, never a calibrated probability",
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum():
        raise SystemExit("Invalid run name")
    main(args.label)
