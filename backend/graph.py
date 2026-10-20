from .links import identifiers
from .storage import digest, now


def build_graph(doc, peers=()):
    nodes, edges, evidence = {}, [], {e["id"]: e for e in doc.get("evidence", [])}
    at = doc.get("analyzed_at", doc["created_at"])

    def node(kind, value, label=None, evidence_ids=None, **extra):
        nid = kind + "-" + digest(value)[:16]
        if nid not in nodes:
            nodes[nid] = {
                "id": nid,
                "type": kind,
                "label": label or value,
                "evidence_ids": evidence_ids or [],
                **extra,
            }
        else:
            nodes[nid]["evidence_ids"] = list(
                dict.fromkeys(nodes[nid]["evidence_ids"] + (evidence_ids or []))
            )
        return nid

    def edge(source, target, kind, ids, method="local_rule", status="observed"):
        eid = "edge-" + digest(f"{source}|{target}|{kind}")[:18]
        if not any(e["id"] == eid for e in edges):
            edges.append(
                {
                    "id": eid,
                    "source": source,
                    "target": target,
                    "type": kind,
                    "label": kind,
                    "evidence_ids": ids,
                    "at": at,
                    "method": method,
                    "status": status,
                }
            )

    materials = {}
    for mat in doc["materials"]:
        if not mat.get("source_evidence_id"):
            continue
        mid = node(
            "material",
            mat["id"],
            mat["source"],
            [mat["source_evidence_id"]],
            case_id=doc["id"],
            material_id=mat["id"],
        )
        materials[mat["id"]] = mid
        sid = node("source", mat["source"], mat["source"], [mat["source_evidence_id"]])
        edge(sid, mid, "published", [mat["source_evidence_id"]], "user_supplied")
        for url in mat.get("urls", []):
            ids = [
                e["id"]
                for e in evidence.values()
                if e.get("material_id") == mat["id"] and e.get("quote") == url
            ]
            if ids:
                uid = node("url", url, url, ids)
                extraction_methods = {evidence[eid]["method"] for eid in ids}
                method = next(iter(extraction_methods)) if len(extraction_methods) == 1 else "source_extraction"
                edge(mid, uid, "contains_link", ids, method)
        for promo in mat.get("promo_codes", []):
            # No verified destination scope: do not merge this code across materials.
            ids = [promo["evidence_id"]]
            iid = node("identifier", mat["id"] + "|" + promo["value"], "код " + promo["value"], ids)
            edge(mid, iid, "contains_identifier", ids, "source_text")
    for obs in doc.get("trace", {}).get("observations", []):
        ids = [obs["evidence_id"]]
        uid = node("url", obs["url"], obs["url"], ids, stopped=bool(obs.get("stop")))
        oid = node(
            "observation",
            obs["id"] + doc["id"],
            f"HTTP {obs['status_code']}" if obs["status_code"] else "Разрыв маршрута",
            ids,
            stopped=bool(obs.get("stop")),
        )
        edge(uid, oid, "observed", ids, obs["method"])
        from urllib.parse import urlsplit

        try:
            host = urlsplit(obs["url"]).hostname
        except ValueError:
            host = None
        if host:
            domain = node("domain", host, host, ids)
            edge(uid, domain, "on_domain", ids, "url_parser")
        for token in identifiers(obs["url"]):
            iid = node(
                "identifier",
                token["scope"],
                f"{token['parameter']}={token['value']}",
                ids,
                scope=token["scope"],
            )
            edge(uid, iid, "contains_identifier", ids, "url_parser")
    for rel in doc.get("trace", {}).get("relations", []):
        if rel["from"]:
            source = node("url", rel["from"])
            target = node("url", rel["to"])
            edge(source, target, rel["type"], [rel["evidence_id"]], rel["method"])
    groups = {}
    contents = {
        m["id"]: m.get("content_evidence_ids", [m.get("source_evidence_id")]) for m in doc["materials"]
    }
    for item in doc.get("identifiers", []):
        groups.setdefault(item["scope"], []).append(item)
    for scope, members in groups.items():
        for left in members:
            for right in members:
                if left["material_id"] < right["material_id"]:
                    edge(
                        materials[left["material_id"]],
                        materials[right["material_id"]],
                        "matching_identifier",
                        list(
                            dict.fromkeys(
                                [
                                    left["evidence_id"],
                                    right["evidence_id"],
                                    *contents[left["material_id"]],
                                    *contents[right["material_id"]],
                                ]
                            )
                        ),
                        "scoped_exact_match",
                        "inferred",
                    )
    for peer in peers:
        if peer["id"] == doc["id"] or peer["mode"] != doc["mode"]:
            continue
        for item in peer.get("identifiers", []):
            for own in groups.get(item["scope"], []):
                peer_evidence = next(
                    (e for e in peer.get("evidence", []) if e["id"] == item["evidence_id"]), None
                )
                if peer_evidence:
                    evidence[peer_evidence["id"]] = {**peer_evidence, "case_id": peer["id"]}
                    peer_material = next(m for m in peer["materials"] if m["id"] == item["material_id"])
                    peer_content_ids = peer_material.get(
                        "content_evidence_ids", [peer_material.get("source_evidence_id")]
                    )
                    for pe in peer.get("evidence", []):
                        if pe["id"] in peer_content_ids:
                            evidence[pe["id"]] = {**pe, "case_id": peer["id"]}
                    pid = node(
                        "material",
                        item["material_id"],
                        peer["title"],
                        [item["evidence_id"]],
                        case_id=peer["id"],
                        material_id=item["material_id"],
                    )
                    edge(
                        materials[own["material_id"]],
                        pid,
                        "matching_identifier",
                        list(
                            dict.fromkeys(
                                [
                                    own["evidence_id"],
                                    item["evidence_id"],
                                    *contents[own["material_id"]],
                                    *peer_content_ids,
                                ]
                            )
                        ),
                        "scoped_exact_match",
                        "inferred",
                    )
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "evidence": list(evidence.values()),
        "generated_at": now(),
        "limitation": "Совпадение идентификатора — основание проверить связь, не доказательство общего владельца.",
    }
