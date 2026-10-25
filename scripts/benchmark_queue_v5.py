"""Measure real HTTP admission -> Redis -> workers -> SQLite, on an isolated local stack."""

import argparse
import concurrent.futures
import json
import math
import os
import platform
import struct
import time
import uuid
import zlib
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8765"


def request(path, body=None, content_type="application/json"):
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    headers = {"Content-Type": content_type} if data is not None else {}
    with urlopen(Request(BASE + path, data=data, headers=headers), timeout=60) as response:
        return json.load(response)


def image_id(index):
    original = (Path(__file__).resolve().parents[1] / "datasets/evaluator-v4-smoke/material.png").read_bytes()
    # Distinct bytes, identical visual workload. No reuse of the OCR cache key.
    payload = b"Benchmark\0" + (str(index) + uuid.uuid4().hex).encode()
    kind = b"tEXt"
    chunk = struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    image = original[:-12] + chunk + original[-12:]
    boundary = uuid.uuid4().hex
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="benchmark.png"\r\nContent-Type: image/png\r\n\r\n').encode() + image
    data += f"\r\n--{boundary}--\r\n".encode()
    return request("/api/uploads", data, "multipart/form-data; boundary=" + boundary)["image_id"]


def quantile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))]


def batch(modality, count):
    materials = [{"image_id": image_id(i)} if modality == "image" else
                 {"text": f"Авторский замер {i}: Казино, регистрируйся и забирай бонус!"} for i in range(count)]
    def submit(material):
        return request("/api/cases", {"title": "Isolated throughput benchmark", "mode": "local", "materials": [material]})["id"]
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(submit, materials))
    outstanding, results = set(ids), []
    deadline = time.monotonic() + 600
    while outstanding and time.monotonic() < deadline:
        for case_id in list(outstanding):
            result = request("/api/cases/" + case_id)
            if result.get("queue_finished"):
                results.append(result)
                outstanding.remove(case_id)
        if outstanding:
            time.sleep(.1)
    if outstanding:
        raise TimeoutError(f"{len(outstanding)} jobs did not finish")
    elapsed = time.perf_counter() - started
    failures = [r["id"] for r in results if r["status"] not in {"completed", "partial"}]
    assert not failures, failures
    if modality == "image":
        assert all(r["materials"][0].get("ocr", {}).get("lines") for r in results), "Missing real OCR"
    processing = [r["queue_processing_ms"] for r in results]
    waiting = [(datetime.fromisoformat(r["queue_started_at"]) - datetime.fromisoformat(r["queue_submitted_at"])).total_seconds() * 1000 for r in results]
    complete = [(datetime.fromisoformat(r["queue_completed_at"]) - datetime.fromisoformat(r["queue_submitted_at"])).total_seconds() * 1000 for r in results]
    return {"modality": modality, "count": count, "errors": len(failures), "wall_seconds": elapsed,
            "throughput_per_second": count / elapsed, "workers_observed": sorted({r["queue_worker"] for r in results}),
            "processing_ms": {"p50": quantile(processing, .5), "p95": quantile(processing, .95)},
            "queue_wait_ms": {"p50": quantile(waiting, .5), "p95": quantile(waiting, .95)},
            "end_to_end_ms": {"p50": quantile(complete, .5), "p95": quantile(complete, .95)},
            "cases": [{k: r.get(k) for k in ("id", "status", "queue_worker", "queue_processing_ms", "queue_attempts", "queue_submitted_at", "queue_started_at", "queue_completed_at")} for r in results]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", required=True, type=int, choices=[1, 2, 4])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    warmup = batch("image", args.workers * 4)
    assert len(warmup["workers_observed"]) == args.workers, "Not all requested workers ran real OCR"
    report = {"workers": args.workers, "platform": platform.platform(), "logical_cpus": os.cpu_count(),
              "runner": os.getenv("RUNNER_NAME"), "run_id": os.getenv("GITHUB_RUN_ID"),
              "commit": os.getenv("GITHUB_SHA"), "health": request("/api/health"),
              "protocol": "96 short text messages, 24 images; 8 HTTP submitters; same authored image pixels with unique PNG bytes; warm OCR; cache misses; no external HTTP destinations",
              "scope": "Finite batch drain throughput including admission/poll overhead; not steady-state production capacity",
              "warmup": warmup, "measurements": [batch("text", 96), batch("image", 24)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"workers": args.workers, "results": [{k: v for k, v in row.items() if k != "cases"} for row in report["measurements"]]}))


if __name__ == "__main__":
    main()
