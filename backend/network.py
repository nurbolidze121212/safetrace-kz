"""Cross-case entity network. Communities are investigation aids, never score inputs."""

from collections import defaultdict
from itertools import combinations

import networkx as nx

from .graph import build_graph
from .material_identity import content_fingerprint
from .storage import digest

VERSION = "network-2.0"


def build_network(documents, include_weak=False):
    documents = sorted(documents, key=lambda d: d["id"])
    if len({d["mode"] for d in documents}) > 1:
        raise ValueError("Select one analysis mode; synthetic and local evidence must not mix")
    if sum(len(d.get("materials", [])) for d in documents) > 1000:
        raise ValueError("Network is limited to 1000 materials; narrow the selection")
    nodes, edges, evidence, members, matches = {}, {}, {}, {}, defaultdict(dict)
    projection = nx.Graph()
    for doc in documents:
        own = {e["id"]: {**e, "case_id": doc["id"]} for e in doc.get("evidence", [])}
        evidence.update(own)
        graph = build_graph(doc)
        for node in graph["nodes"]:
            target = nodes.setdefault(node["id"], {**node, "case_ids": [], "evidence_ids": []})
            target["case_ids"] = sorted(set(target["case_ids"]) | {doc["id"]})
            target["evidence_ids"] = sorted(set(target["evidence_ids"]) | set(node["evidence_ids"]))
        for edge in graph["edges"]:
            if not edge["evidence_ids"] or not set(edge["evidence_ids"]).issubset(own):
                continue
            target = edges.setdefault(edge["id"], {**edge, "evidence_ids": [], "case_ids": []})
            target["evidence_ids"] = sorted(set(target["evidence_ids"]) | set(edge["evidence_ids"]))
            target["case_ids"] = sorted(set(target["case_ids"]) | {doc["id"]})
        for mat in doc.get("materials", []):
            eid = mat.get("source_evidence_id")
            if eid not in own:
                continue
            mid = "material-" + digest(mat["id"])[:16]
            members[mid] = {"case_id": doc["id"], "material_id": mat["id"],
                            "fingerprint": content_fingerprint(mat), "source_evidence_id": eid}
            projection.add_node(mid)
            for item in doc.get("identifiers", []):
                if item["material_id"] == mat["id"] and item["evidence_id"] in own:
                    matches[item["scope"]][mid] = item["evidence_id"]
    for scope, group in sorted(matches.items()):
        for left, right in combinations(sorted(group), 2):
            if members[left]["fingerprint"] == members[right]["fingerprint"]:
                continue
            ids = sorted({group[left], group[right], members[left]["source_evidence_id"],
                          members[right]["source_evidence_id"]})
            if projection.has_edge(left, right):
                projection[left][right]["scopes"].append(scope)
                projection[left][right]["evidence_ids"].update(ids)
            else:
                projection.add_edge(left, right, scopes=[scope], evidence_ids=set(ids), weight=1)
    for left, right, data in projection.edges(data=True):
        data["weight"] = len(data["scopes"])
        edge_id = "network-" + digest(left + "|" + right)[:18]
        edges[edge_id] = {"id": edge_id, "source": left, "target": right, "type": "matching_identifier",
                          "label": "Совпадение в области домена", "status": "inferred",
                          "method": "scoped_exact_match", "strength": "strong", "evidence_ids": sorted(data["evidence_ids"]),
                          "scopes": data["scopes"],
                          "case_ids": sorted({members[left]["case_id"], members[right]["case_id"]})}

    matching_pairs = projection.number_of_edges()
    weak_count = 0
    if include_weak:
        from .network_signals import build_signals, from_documents

        signals = build_signals(from_documents(documents))
        for item in signals["edges"]:
            if item["strength"] != "weak" or item["source"] not in members or item["target"] not in members:
                continue
            left, right = item["source"], item["target"]
            edge_id = "weak-" + digest(left + right + item["basis"])[:18]
            edges[edge_id] = {**item, "id": edge_id, "type": "weak_hypothesis", "status": "hypothesis",
                              "method": item["basis"], "label": "Слабое основание: " + item["basis"],
                              "case_ids": sorted({members[left]["case_id"], members[right]["case_id"]})}
            old_weight = projection.get_edge_data(left, right, {}).get("weight", 0)
            projection.add_edge(left, right, weight=max(old_weight, item["weight"]))
            weak_count += 1
    rank = nx.pagerank(projection, alpha=.85, tol=1e-7) if projection else {}

    def partition(groups, prefix):
        output = []
        for group in sorted((sorted(g) for g in groups), key=lambda g: (-len(g), g)):
            group_id = prefix + "-" + digest("|".join(group))[:12]
            output.append({"id": group_id, "material_ids": group,
                           "case_ids": sorted({members[m]["case_id"] for m in group}),
                           "size": len(group),
                           "central_material": min(group, key=lambda m: (-rank[m], m))})
        return output

    components = partition(nx.connected_components(projection), "component")
    groups = (nx.community.louvain_communities(projection, seed=42, resolution=1)
              if projection.number_of_edges() else [{n} for n in projection])
    communities = partition(groups, "community")
    return {
        "version": VERSION, "mode": documents[0]["mode"] if documents else None,
        "nodes": list(nodes.values()), "edges": list(edges.values()), "evidence": list(evidence.values()),
        "components": components, "communities": communities, "pagerank": rank, "include_weak": include_weak,
        "counts": {"cases": len(documents), "materials": len(members), "entities": len(nodes),
                   "edges": len(edges), "matching_pairs": matching_pairs,
                   "components": len(components), "communities": len(communities), "weak": weak_count},
        "method": "Material projection; exact identifiers plus optional weak hypotheses; Louvain seed=42; PageRank alpha=.85",
        "limitations": [
            "Кластер — подсказка для проверки связи, а не общий владелец или подтверждение рекламы.",
            "Общий домен или заявленный источник сами по себе не создают сильной связи.",
            "Аккаунт или канал — заявленная подпись источника; принадлежность не проверена.",
            "Зеркала не подтверждаются автоматически; промокод вне общей области назначения — только слабая гипотеза.",
            "Слабые основания — гипотезы: похожий шаблон, промокод, цифровой суффикс домена, сохранённый IP. Общий CDN не доказывает связь владельцев.",
        ],
    }
