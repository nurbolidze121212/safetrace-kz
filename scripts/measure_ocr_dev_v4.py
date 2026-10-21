"""Measure the product's address policy on all previously authored v4 dev pixels."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "tmp/v4-ocr-measure-data")
os.environ["SAFETRACE_OFFLINE"] = "1"
from backend import storage
from backend.config import OCR_VERSION
from backend.links import extract_urls
from backend.ocr import engine, recognize


def measure(label):
    out = ROOT / "reports/acceptance-v4" / f"ocr-dev-product-{label}.json"
    if out.exists():
        raise RuntimeError("Keep existing measurements; choose a new run name")
    rows = {}
    for name in (
        "ocr-dev-initial.json",
        "ocr-dev-english-experiment.json",
        "ocr-dev-embedded-experiment.json",
    ):
        report = json.loads((out.parent / name).read_text(encoding="utf-8"))
        for row in report["rows"]:
            rows[row["id"]] = {
                k: v for k, v in row.items() if k not in ("base", "english", "full_scale2", "crops_scale2")
            }
    storage.init()
    started = time.perf_counter()
    engine()
    cold_ms = (time.perf_counter() - started) * 1000
    predictions = []
    for row in rows.values():
        path = ROOT / "datasets/ocr-dev-v4" / row["image"]
        started = time.perf_counter()
        result = recognize(path, use_cache=False)
        elapsed = (time.perf_counter() - started) * 1000
        raw = extract_urls(result["text"])
        automatic = [r["raw_url"] for r in result["url_readings"] if r["auto_follow"]]
        candidates = list(
            dict.fromkeys(raw + [s["url"] for r in result["url_readings"] for s in r["suggestions"]])
        )
        expected = row["url"]
        predictions.append(
            {
                **row,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "raw_urls": raw,
                "automatic_urls": automatic,
                "candidates": candidates,
                "raw_exact": expected in raw,
                "automatic_exact": expected in automatic,
                "automatic_wrong": [u for u in automatic if u != expected],
                "candidate_exact": expected in candidates,
                "domain_exact": urlsplit(expected).hostname in [urlsplit(u).hostname for u in raw],
                "referral_exact": any(
                    parse_qsl(urlsplit(expected).query) == parse_qsl(urlsplit(u).query) for u in raw
                ),
                "elapsed_ms": round(elapsed, 3),
                "readings": result["url_readings"],
                "raw_text": result["raw_text"],
                "rotation_ccw": result["rotation_ccw"],
            }
        )
        print(
            json.dumps(
                {
                    "id": row["id"],
                    "raw": expected in raw,
                    "automatic": expected in automatic,
                    "candidate": expected in candidates,
                }
            ),
            flush=True,
        )
    elapsed = sorted(r["elapsed_ms"] for r in predictions)
    summary = {
        "n": len(predictions),
        "raw_exact": sum(r["raw_exact"] for r in predictions),
        "automatic_exact": sum(r["automatic_exact"] for r in predictions),
        "raw_wrong_addresses": sum(len([u for u in r["raw_urls"] if u != r["url"]]) for r in predictions),
        "automatic_wrong_addresses": sum(len(r["automatic_wrong"]) for r in predictions),
        "automatic_abstentions": sum(not r["automatic_urls"] for r in predictions),
        "candidate_exact": sum(r["candidate_exact"] for r in predictions),
        "domain_exact": sum(r["domain_exact"] for r in predictions),
        "referral_exact": sum(r["referral_exact"] for r in predictions),
        "p50_ms": statistics.median(elapsed),
        "p95_ms": elapsed[math.ceil(0.95 * len(elapsed)) - 1],
    }
    out.write_text(
        json.dumps(
            {
                "at": storage.now(),
                "ocr_version": OCR_VERSION,
                "provenance": "author_synthetic_development; previously inspected and used for development",
                "definitions": "One expected URL per image. Exact comparisons preserve characters. Candidates are not automatically followed or counted as automatic successes. Timings include bounded English reading when triggered; primary engine preloaded, English initially cold.",
                "cold_primary_engine_ms": cold_ms,
                "summary": summary,
                "rows": predictions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum():
        raise SystemExit("Invalid run name")
    measure(args.label)
