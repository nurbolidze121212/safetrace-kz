"""Bounded, evidence-linked weak hypotheses and sparse exact relationships."""

import re
import zlib
from collections import defaultdict
from functools import lru_cache
from itertools import combinations
from urllib.parse import urlsplit

import networkx as nx
import numpy as np

VERSION = "network-signals-2.1"
MAX_BUCKET = 64
MAX_NEIGHBORS = 8
_A = np.array([2 * (i * 2654435761 % 2147483647) + 1 for i in range(1, 33)], dtype=np.uint64)
_B = np.array([i * 2246822519 % 4294967291 for i in range(1, 33)], dtype=np.uint64)


@lru_cache(maxsize=4096)
def shingles(text):
    text = re.sub(r"https?://\S+", " URL ", text.casefold())
    words = re.findall(r"[^\W\d_]+", text, re.UNICODE)
    return frozenset(" ".join(words[i:i + 3]) for i in range(max(0, len(words) - 2)))


def signature(tokens):
    values = np.array([zlib.crc32(t.encode()) for t in tokens], dtype=np.uint64)
    return tuple(int(v) for v in ((_A[:, None] * values[None, :] + _B[:, None]) & 0xFFFFFFFF).min(axis=1))


def build_signals(records, include_weak=True):
    records = sorted(records, key=lambda r: r["id"])
    by_id = {r["id"]: r for r in records}
    if len(by_id) != len(records):
        raise ValueError("Duplicate material ids")
    groups, lsh, tokens, edges, degrees = defaultdict(dict), defaultdict(list), {}, {}, defaultdict(int)
    skipped = defaultdict(int)

    def add(left, right, basis, strength, evidence_ids, similarity=None):
        if not evidence_ids or not by_id[left].get("evidence_ids") or not by_id[right].get("evidence_ids"):
            return
        if strength == "weak" and (degrees[left, basis] >= MAX_NEIGHBORS or degrees[right, basis] >= MAX_NEIGHBORS):
            skipped["neighbor_cap"] += 1
            return
        left, right = sorted((left, right))
        key = (left, right, basis)
        if key in edges:
            return
        edges[key] = {"source": left, "target": right, "basis": basis, "strength": strength,
                      "weight": 1.0 if strength == "strong" else .15,
                      "evidence_ids": sorted(set(evidence_ids)), "similarity": similarity,
                      "meaning": "exact scoped identifier" if strength == "strong" else "hypothesis; not ownership or risk"}
        degrees[left, basis] += 1
        degrees[right, basis] += 1

    for record in records:
        mid = record["id"]
        for scope in record.get("scopes", []):
            groups["scoped_identifier", scope["value"]][mid] = scope["evidence_ids"]
        if not include_weak:
            continue
        for ip in record.get("infrastructure", []):
            groups["shared_connected_ip", ip["value"]][mid] = ip["evidence_ids"]
        for code in record.get("promos", []):
            if len(code["value"]) >= 5 and code["value"].upper() not in {"BONUS", "PROMO", "WELCOME"}:
                groups["shared_promo", code["value"]][mid] = code["evidence_ids"]
        for entry in record.get("urls", []):
            host = urlsplit(entry["value"]).hostname or ""
            match = re.fullmatch(r"([a-z][a-z-]{3,})\d+(\.[a-z.]+)", host)
            if match:
                groups["numbered_domain", match.group(1) + "*" + match.group(2)][mid] = entry["evidence_ids"]
        own_tokens = shingles(record.get("text", ""))
        if len(own_tokens) >= 4:
            tokens[mid] = own_tokens
            sig = signature(own_tokens)
            for band in range(8):
                lsh[band, sig[band * 4:band * 4 + 4]].append(mid)

    for (basis, _), members in sorted(groups.items()):
        ids = sorted(members)
        strong = basis == "scoped_identifier"
        if not strong and len(ids) > MAX_BUCKET:
            skipped["uninformative_bucket"] += 1
            continue
        # Sparse star for large exact groups prevents quadratic expansion.
        pairs = ((ids[0], item) for item in ids[1:]) if strong and len(ids) > MAX_BUCKET else combinations(ids, 2)
        for left, right in pairs:
            if by_id[left].get("fingerprint") and by_id[left].get("fingerprint") == by_id[right].get("fingerprint"):
                continue
            add(left, right, basis, "strong" if strong else "weak", members[left] + members[right])
    compared = set()
    for members in lsh.values():
        if len(members) > MAX_BUCKET:
            skipped["uninformative_lsh_bucket"] += 1
            continue
        for left, right in combinations(members, 2):
            if (left, right) in compared or degrees[left, "similar_template"] >= MAX_NEIGHBORS:
                continue
            compared.add((left, right))
            intersection = len(tokens[left] & tokens[right])
            similarity = intersection / len(tokens[left] | tokens[right])
            if similarity >= .76:
                if by_id[left].get("fingerprint") and by_id[left].get("fingerprint") == by_id[right].get("fingerprint"):
                    continue
                add(left, right, "similar_template", "weak", by_id[left]["evidence_ids"] + by_id[right]["evidence_ids"], similarity)
    graph = nx.Graph()
    graph.add_nodes_from(by_id)
    for edge in edges.values():
        old = graph.get_edge_data(edge["source"], edge["target"], {}).get("weight", 0)
        graph.add_edge(edge["source"], edge["target"], weight=min(1, old + edge["weight"]))
    pagerank = nx.pagerank(graph, alpha=.85, max_iter=100, tol=1e-7) if graph else {}
    communities = (nx.community.louvain_communities(graph, resolution=1, seed=42)
                   if graph.number_of_edges() else [{n} for n in graph])
    # Common hosting and one shared code remain visible, but cannot alone merge
    # investigation groups. Require a template plus a second distinct basis.
    corroborated = nx.Graph()
    corroborated.add_nodes_from(by_id)
    pair_bases = defaultdict(set)
    for edge in edges.values():
        pair_bases[edge["source"], edge["target"]].add(edge["basis"])
    for (left, right), bases in pair_bases.items():
        if "scoped_identifier" in bases or ("similar_template" in bases and bases & {"shared_promo", "numbered_domain"}):
            corroborated.add_edge(left, right)
    return {"version": VERSION, "edges": list(edges.values()), "pagerank": pagerank,
            "communities": [sorted(g) for g in sorted(nx.connected_components(corroborated), key=lambda g: (-len(g), min(g)))],
            "community_method": "Components of exact or corroborated (template + code/domain family) pairs; exploratory hypotheses",
            "exploratory_louvain": [sorted(g) for g in sorted(communities, key=lambda g: (-len(g), min(g)))],
            "components": [sorted(g) for g in nx.connected_components(graph)],
            "counts": {"nodes": len(records), "edges": len(edges),
                       "strong": sum(e["strength"] == "strong" for e in edges.values()),
                       "weak": sum(e["strength"] == "weak" for e in edges.values())},
            "bounded_work": dict(skipped), "candidate_pairs": len(compared)}


def from_documents(documents):
    from .material_identity import content_fingerprint
    from .storage import digest

    records = []
    for doc in documents:
        known = {e["id"] for e in doc.get("evidence", [])}
        for material in doc.get("materials", []):
            evidence_ids = [e for e in material.get("content_evidence_ids", []) if e in known]
            if not evidence_ids:
                continue
            reached = set(material.get("reachable_urls", material.get("urls", [])))
            observations = [o for o in (doc.get("trace") or {}).get("observations", [])
                            if o.get("url") in reached and o.get("evidence_id") in known]
            records.append({"id": "material-" + digest(material["id"])[:16], "case_id": doc["id"],
                            "text": material.get("text", "") + "\n" + material.get("ocr", {}).get("text", ""),
                            "fingerprint": content_fingerprint(material), "evidence_ids": evidence_ids,
                            "scopes": [{"value": s["scope"], "evidence_ids": [s["evidence_id"]]}
                                       for s in doc.get("identifiers", []) if s["material_id"] == material["id"] and s["evidence_id"] in known],
                            "urls": [{"value": o["url"], "evidence_ids": [o["evidence_id"]]} for o in observations],
                            "infrastructure": [{"value": o["connected_ip"], "evidence_ids": [o["evidence_id"]]}
                                               for o in observations if o.get("connected_ip")],
                            "promos": [{"value": p["value"], "evidence_ids": [p["evidence_id"]]}
                                       for p in material.get("promo_codes", []) if p["evidence_id"] in known]})
    return records
