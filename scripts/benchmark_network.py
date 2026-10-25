"""Structural synthetic benchmark; does not measure detection of real campaigns."""

import json
import statistics
import sys
import time
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fixtures():
    from backend.links import identifiers

    documents, truth = [], {}
    for campaign in range(12):
        for post in range(8):
            cid = f"{campaign * 8 + post + 1:032x}"
            mid, source_id = "m-" + cid, "e-" + cid
            url = f"https://n{campaign:02}.test/landing?ref=COMMON&post={post}"
            hub = "https://hub.test/go"
            evidence = [{"id": source_id, "quote": f"Authored campaign {campaign}, post {post}",
                         "method": "source_text", "material_id": mid}]
            observations = []
            for index, address in enumerate([hub, url]):
                eid = source_id + f"-{index}"
                evidence.append({"id": eid, "quote": address, "method": "synthetic_transport", "material_id": mid})
                observations.append({"id": cid + f"-{index}", "url": address, "evidence_id": eid,
                                     "method": "synthetic_transport", "status_code": 200, "stop": None})
            docs_ids = [{**i, "material_id": mid, "evidence_id": source_id + "-1"} for i in identifiers(url)]
            # Three known campaigns contain a member without a readable referral.
            # Keep it in the truth denominator instead of silently dropping a difficult input.
            if post == 7 and campaign in {2, 6, 10}:
                docs_ids = []
            doc = {"id": cid, "title": f"Synthetic network material {campaign}/{post}", "mode": "synthetic",
                   "created_at": "2026-10-25T00:00:00Z", "status": "completed",
                   "materials": [{"id": mid, "source": f"tg:channel:demo-{campaign}-{post % 3}",
                                  "text": f"Authored structural fixture {campaign}/{post}",
                                  "urls": [hub, url], "source_evidence_id": source_id,
                                  "content_evidence_ids": [source_id]}],
                   "evidence": evidence, "identifiers": docs_ids,
                   "trace": {"observations": observations, "relations": [
                       {"from": hub, "to": url, "type": "page_link", "evidence_id": source_id + "-1",
                        "method": "synthetic_transport"}]}}
            documents.append(doc)
            truth[cid] = campaign
    return documents, truth


def main():
    from backend.network import build_network

    docs, truth = fixtures()
    elapsed = []
    for _ in range(5):
        started = time.perf_counter()
        network = build_network(docs)
        elapsed.append((time.perf_counter() - started) * 1000)
    assignment = {cid: g["id"] for g in network["communities"] for cid in g["case_ids"]}
    tp = fp = fn = 0
    for left, right in combinations(truth, 2):
        same_truth, same_group = truth[left] == truth[right], assignment[left] == assignment[right]
        tp += same_truth and same_group
        fp += not same_truth and same_group
        fn += same_truth and not same_group
    result = {"schema": "network-structural-benchmark-1", "counts": network["counts"],
              "truth_campaigns": 12, "missing_referral_members": 3, "pair_tp": tp, "pair_fp": fp,
              "pair_fn": fn, "pair_precision": tp / (tp + fp), "pair_recall": tp / (tp + fn),
              "pair_f1": 2 * tp / (2 * tp + fp + fn), "median_ms": statistics.median(elapsed),
              "max_ms": max(elapsed), "runs_ms": elapsed,
              "scope": "Authored structural fixtures with known scoped IDs, one common hub, identical ref values across domains and three missing IDs. Not an independent or real-campaign evaluation."}
    folder = ROOT / "reports/release-2.4"
    folder.mkdir(exist_ok=True, parents=True)
    (folder / "network-benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (ROOT / "site/network.json").write_text(json.dumps(network, ensure_ascii=False), encoding="utf-8")
    source = ROOT / "datasets/network-dev"
    source.mkdir(exist_ok=True)
    (source / "cases.json").write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    (source / "truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
