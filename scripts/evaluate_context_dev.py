"""Diagnostic development comparison; never an independent final test."""

import argparse
import copy
import hashlib
import json
import math
import os
import statistics
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "data/context-v3-dev")
os.environ["SAFETRACE_OFFLINE"] = "1"

from backend import pipeline, storage  # noqa: E402
from backend.config import PIPELINE_VERSION, RULE_VERSION  # noqa: E402
from backend.links import SyntheticTransport  # noqa: E402
from backend.schemas import CaseInput, MaterialInput  # noqa: E402


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def hashes(paths):
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths)
        if p.is_file()
    }


def interval(success, n):
    if not n:
        return None
    z = 1.959964
    p = success / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [max(0, center - half), min(1, center + half)]


def metrics(rows):
    tp = sum(r["truth"] == 1 and r["predicted"] == 1 for r in rows)
    fp = sum(r["truth"] == 0 and r["predicted"] == 1 for r in rows)
    tn = sum(r["truth"] == 0 and r["predicted"] == 0 for r in rows)
    fn = sum(r["truth"] == 1 and r["predicted"] == 0 for r in rows)
    covered = [r for r in rows if r["sufficient"]]
    latency = sorted(r["elapsed_ms"] for r in rows)
    ptp = sum(r["truth"] == 1 and r["predicted"] == 1 for r in covered)
    pfp = sum(r["truth"] == 0 and r["predicted"] == 1 for r in covered)
    positives = sum(r["truth"] for r in covered)
    negatives = len(covered) - positives
    return dict(
        n=len(rows),
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
        f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        fpr=fp / (fp + tn) if fp + tn else None,
        precision_ci=interval(tp, tp + fp),
        fpr_ci=interval(fp, fp + tn),
        coverage=len(covered) / len(rows) if rows else None,
        insufficient=len(rows) - len(covered),
        processed_n=len(covered),
        processed_precision=ptp / (ptp + pfp) if ptp + pfp else None,
        processed_recall=ptp / positives if positives else None,
        processed_fpr=pfp / negatives if negatives else None,
        p50_ms=statistics.median(latency) if latency else None,
        p95_ms=latency[math.ceil(0.95 * len(latency)) - 1] if latency else None,
    )


def main(run):
    dataset = ROOT / "datasets/context-v3-dev"
    output = ROOT / "reports/context-v3-dev" / run
    output.mkdir(parents=True, exist_ok=False)
    core = [
        *(ROOT / "backend").glob("*.py"),
        ROOT / "backend/weights.json",
        ROOT / "requirements.lock.txt",
        Path(__file__),
    ]
    before, data_before = hashes(core), hashes(dataset.glob("*"))
    storage.init()
    inputs = [
        json.loads(line) for line in (dataset / "inputs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    pages = json.loads((dataset / "pages.json").read_text(encoding="utf-8"))
    rows = []
    for item in inputs:
        base = pipeline.new_case(
            CaseInput(
                title="Материал", mode="synthetic", materials=[MaterialInput(**m) for m in item["materials"]]
            )
        )
        for variant, implementation in [("keywords", "baseline"), ("text", "ocr"), ("full", "full")]:
            doc = copy.deepcopy(base)
            start = time.perf_counter()
            pipeline.analyze(doc, variant=implementation, fetch=SyntheticTransport(pages))
            rows.append(
                dict(
                    id=item["id"],
                    variant=variant,
                    score=doc["score"]["value"],
                    sufficient=doc["sufficient_data"],
                    predicted=int(doc["score"]["value"] >= 65 and doc["sufficient_data"]),
                    elapsed_ms=round((time.perf_counter() - start) * 1000, 3),
                    status=doc["status"],
                    contributions=doc["score"]["contributions"],
                    context=doc["context"],
                    pages=[
                        {k: o[k] for k in ("url", "text", "context") if k in o}
                        for o in doc["trace"]["observations"]
                    ],
                )
            )
    if before != hashes(core) or data_before != hashes(dataset.glob("*")):
        raise RuntimeError("Code or dataset changed during evaluation.")
    write(output / "unlabelled-predictions.json", rows)
    with zipfile.ZipFile(output / "core-source.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in before:
            archive.write(ROOT / name, name)
    # Labels become available only after all predictions have been saved.
    labels = {
        r["id"]: r
        for r in map(json.loads, (dataset / "annotations.jsonl").read_text(encoding="utf-8").splitlines())
    }
    assert len(inputs) == len(labels) and set(labels) == {r["id"] for r in inputs}
    for row in rows:
        row.update({k: v for k, v in labels[row["id"]].items() if k != "id"})
    full = [r for r in rows if r["variant"] == "full"]
    result = dict(
        purpose="Author-created diagnostic DEVELOPMENT data, not independent final accuracy.",
        created_at=storage.now(),
        threshold=65,
        rules=RULE_VERSION,
        pipeline=PIPELINE_VERSION,
        core_hashes=before,
        data_hashes=data_before,
        variants={v: metrics([r for r in rows if r["variant"] == v]) for v in ("keywords", "text", "full")},
        slices={
            field: {
                value: metrics([r for r in full if r[field] == value])
                for value in sorted({r[field] for r in full})
            }
            for field in ("category", "surface", "language")
        },
        errors=[
            {k: r[k] for k in ("id", "truth", "score", "sufficient", "category", "surface")}
            for r in full
            if r["truth"] != r["predicted"]
        ],
    )
    write(output / "predictions.json", rows)
    write(output / "evaluation.json", result)
    print(json.dumps(result["variants"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    if not args.run.replace("-", "").replace("_", "").isalnum():
        parser.error("Use a simple unique run name.")
    main(args.run)
