"""Synthetic sparse relationship benchmark; no OCR, scraping, or real campaigns."""

import gc
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fixture(count):
    records, truth = [], {}
    for i in range(count):
        group, position = divmod(i, 10)
        tag = "".join(chr(97 + ((group // 26 ** n) % 26)) for n in range(5))
        key, evidence = f"m{i:08}", [f"synthetic-evidence-{i}"]
        record = {"id": key, "fingerprint": hashlib.sha256(str(i).encode()).hexdigest(),
                  "text": f"Учебная группа {tag} сообщает: новый проект {tag} для участников {tag} доступен сегодня вариант {chr(97 + position)}",
                  "evidence_ids": evidence,
                  "scopes": [{"value": f"group-{group}|ref|q", "evidence_ids": evidence}] if position < 6 else [],
                  "urls": [{"value": f"https://campaign{tag}{position}.test/", "evidence_ids": evidence}],
                  "promos": [{"value": f"CODE{group if i % 11 else group + 1}", "evidence_ids": evidence}],
                  "infrastructure": [{"value": f"authored-ip-{group // 3}", "evidence_ids": evidence}]}
        records.append(record)
        truth[key] = group
    return records, truth


def clustering(groups, truth):
    tp = sum(sum(math.comb(n, 2) for n in Counter(truth[key] for key in group).values()) for group in groups)
    predicted = sum(math.comb(len(group), 2) for group in groups)
    expected = sum(math.comb(n, 2) for n in Counter(truth.values()).values())
    fp, fn = predicted - tp, expected - tp
    return {"tp": tp, "fp": fp, "fn": fn, "precision": tp / predicted if predicted else None,
            "recall": tp / expected if expected else None, "f1": 2 * tp / (2 * tp + fp + fn)}


def main():
    from backend.network_signals import build_signals, shingles

    output = ROOT / "reports/v5-network"
    output.mkdir(parents=True, exist_ok=True)
    target = output / "benchmark.json"
    if target.exists():
        raise FileExistsError(target)
    report = {"scope": "Material entities with authored strong and noisy weak observations; graph build only",
              "platform": platform.platform(), "cpu": platform.processor(), "logical_cpus": os.cpu_count(),
              "repetitions": 3, "measurements": []}
    for count in (5000, 10000, 100000):
        records, truth = fixture(count)
        times = []
        for _ in range(3):
            shingles.cache_clear()
            gc.collect()
            started = time.perf_counter()
            result = build_signals(records)
            times.append(time.perf_counter() - started)
        row = {"entities": count, "seconds": times, "median_seconds": statistics.median(times),
               "counts": result["counts"], "communities": len(result["communities"]),
               "candidate_pairs": result["candidate_pairs"], "bounded_work": result["bounded_work"],
               "pairwise_cluster_quality": clustering(result["communities"], truth),
               "central_node": max(result["pagerank"], key=result["pagerank"].get)}
        report["measurements"].append(row)
        print(json.dumps(row), flush=True)
        if count == 5000:
            (output / "authored-fixture.json").write_text(json.dumps({"records": records, "truth": truth}, ensure_ascii=False), encoding="utf-8")
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
