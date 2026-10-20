"""Measure queue listing on disposable synthetic documents, never on the user's database."""

import argparse
import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--cases", type=int, default=150)
    parser.add_argument("--iterations", type=int, default=7)
    parser.add_argument("--target", choices=("queue", "graph"), default="queue")
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum() or not 1 <= args.cases <= 1000 or not 3 <= args.iterations <= 30:
        parser.error("Use an alphanumeric label, 1..1000 cases, 3..30 iterations")
    root = Path(__file__).resolve().parents[1]
    folder = root / "data/queue-benchmarks" / args.label
    folder.mkdir(parents=True, exist_ok=False)
    os.environ["SAFETRACE_DATA_DIR"] = str(folder)
    os.environ["SAFETRACE_OFFLINE"] = "1"
    sys.path.insert(0, str(root))
    from backend import storage
    from backend.app import cases, detail

    storage.init()
    history = [{"evidence": [{"quote": "DEMO source text. " * 2500}]} for _ in range(5)]
    for index in range(args.cases):
        case_id = f"{index:032x}"
        document = {
            "id": case_id, "title": f"Synthetic benchmark {index}", "mode": "synthetic",
            "status": "completed", "created_at": f"2026-01-01T00:{index // 60:02}:{index % 60:02}+00:00",
            "score": {"value": 50, "level": "medium", "contributions": []},
            "progress": 100, "stage": "priority", "sufficient_data": True,
            "materials": [{"text": "DEMO source", "source": "benchmark", "url": ""}], "history": history,
        }
        if args.target == "graph":
            material_id, evidence_id = f"material-{index}", f"evidence-{index}"
            document["materials"][0].update(
                id=material_id, source_evidence_id=evidence_id, content_evidence_ids=[evidence_id]
            )
            document["evidence"] = [{
                "id": evidence_id, "quote": "DEMO source", "source_id": material_id,
                "material_id": material_id, "method": "source_text", "at": document["created_at"],
            }]
            document["identifiers"] = [{
                "scope": f"benchmark|{index % 50}", "material_id": material_id, "evidence_id": evidence_id,
            }]
        storage.save(document)
        for _ in range(3):
            storage.add_decision(case_id, "needs_data", "Synthetic benchmark")

    def read_result():
        if args.target == "queue":
            return cases()
        result = detail(f"{0:032x}")
        result["graph"].pop("generated_at", None)
        return result

    expected = read_result()
    measurements = []
    for _ in range(args.iterations):
        started = time.perf_counter()
        assert read_result() == expected
        measurements.append((time.perf_counter() - started) * 1000)
    connections = 0
    original_connect = storage.connect

    def counted_connect():
        nonlocal connections
        connections += 1
        return original_connect()

    storage.connect = counted_connect
    tracemalloc.start()
    assert read_result() == expected
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result = {
        "label": args.label, "target": args.target, "cases": args.cases, "iterations": args.iterations,
        "history_quote_bytes_per_case": 5 * len(history[0]["evidence"][0]["quote"].encode()),
        "median_ms": round(statistics.median(measurements), 3), "max_ms": round(max(measurements), 3),
        "measurements_ms": [round(value, 3) for value in measurements],
        "sqlite_connections_per_listing": connections, "python_peak_allocated_bytes": peak,
        "result_bytes": len(json.dumps(expected, ensure_ascii=False).encode()),
        "database_bytes": (folder / "safetrace.sqlite3").stat().st_size,
        "note": "Synthetic stored documents; direct API handler, no OCR/network or browser timing.",
    }
    target = root / "reports/versions/backend-2.1" / f"queue-{args.label}.json"
    assert not target.exists(), target
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
