"""Bound a call to an observed URL branch without merging unrelated targets."""

import re

from .analysis import ALTERNATIVES, contrast_clause_span, information_call


def attribute(material, sources, claims, page_claims, trace, evidence):
    roots = list(dict.fromkeys(material.get("urls", [])))
    quoted = {
        key: [m.span() for m in re.finditer(r'«[^»]*»|“[^”]*”|"[^\"]*"', text)]
        for key, text in sources.items()
    }
    bindings, direct, destination_calls, selected_pages, route_ids = [], [], [], [], []
    independent_destination = False
    for call in (c for c in claims if c["kind"] == "call_to_action"):
        source_id = call["source_id"]
        text = sources[source_id]
        if any(a <= call["start"] < b for a, b in quoted[source_id]):
            continue
        if re.search(r"\b(?:не|никогда\s+не|ешқашан)\s+$", text[: call["start"]], re.I):
            continue
        if information_call(text, call["start"], call["end"]):
            continue
        start, end = contrast_clause_span(text, call["start"], quoted[source_id])
        scoped = [c for c in claims if c["source_id"] == source_id and start <= c["start"] < end]
        games = [
            c
            for c in scoped
            if c["kind"] == "gambling" and not any(a <= c["start"] < b for a, b in quoted[source_id])
        ]
        if games:
            direct.extend([call, *games])
        aliases = {url: [url] for url in roots}
        if source_id.endswith("-ocr"):
            for reading in material.get("url_reviews", []):
                if reading.get("selected_url") in aliases:
                    aliases[reading["selected_url"]].append(reading["raw_url"])
        candidates = [
            url
            for url in roots
            if any(
                start <= m.start() < end
                for alias in aliases[url]
                for m in re.finditer(re.escape(alias), text)
            )
        ]
        method = "same_clause"
        if not candidates and len(roots) == 1:
            # A sole URL supplied with a caption / QR remains a material-level
            # inference. Record that assumption rather than claiming adjacency.
            candidates, method = roots, "single_material_target"
        if not roots:
            continue
        binding = {
            "call_evidence_id": call["evidence_id"],
            "source_id": source_id,
            "start": call["start"],
            "end": call["end"],
            "quote": call["quote"],
            "scope_start": start,
            "scope_end": end,
            "method": method,
            "status": "bound" if len(candidates) == 1 else "unresolved",
            "candidate_urls": candidates,
            "root_url": None,
            "root_evidence_ids": [],
            "route_evidence_ids": [],
            "destination_evidence_ids": [],
            "reachable_urls": [],
        }
        bindings.append(binding)
        if len(candidates) != 1:
            binding["method"] = "ambiguous_or_missing_target"
            continue
        root = candidates[0]
        binding["root_url"] = root
        binding["root_evidence_ids"] = [
            e["id"] for e in evidence if e.get("material_id") == material["id"] and e["quote"] == root
        ]
        reachable = {root}
        relations = trace.get("relations", [])
        for _ in range(len(relations) + 1):
            extended = reachable | {r["to"] for r in relations if r["from"] in reachable}
            if extended == reachable:
                break
            reachable = extended
        binding["reachable_urls"] = sorted(reachable)
        branch_pages = [c for c in page_claims if c["source_id"] in reachable]
        selected_pages.extend(branch_pages)
        game_pages = [
            c
            for c in branch_pages
            if c["kind"] == "gambling" and (c.get("context") not in ALTERNATIVES or c.get("contradictions"))
        ]
        binding["destination_evidence_ids"] = [c["evidence_id"] for c in game_pages]
        binding["route_evidence_ids"] = list(
            dict.fromkeys(
                [r["evidence_id"] for r in relations if r["from"] in reachable]
                + [o["evidence_id"] for o in trace.get("observations", []) if o["url"] in reachable]
            )
        )
        if game_pages:
            destination_calls.append(call)
            route_ids.extend(binding["root_evidence_ids"] + binding["route_evidence_ids"])
            no_scoped_alternative = not any(c["kind"] in ALTERNATIVES for c in scoped)
            free_game = any(c["kind"] == "free_game" for c in claims)
            money_transition = re.search(
                r"\b(?:теперь|енді|реальн[а-я]*\s+деньг[а-я]*|на\s+деньги)\b", text[start:end], re.I
            )
            binding["independent_commercial_call"] = bool(
                no_scoped_alternative and (not free_game or money_transition)
            )
            independent_destination |= binding["independent_commercial_call"]
    return {
        "bindings": bindings,
        "direct_claims": list({c["evidence_id"]: c for c in direct}.values()),
        "destination_calls": list({c["evidence_id"]: c for c in destination_calls}.values()),
        "page_claims": list({c["evidence_id"]: c for c in selected_pages}.values()),
        "route_evidence_ids": list(dict.fromkeys(route_ids)),
        "incomplete": any(b["status"] == "unresolved" for b in bindings),
        "independent_destination": independent_destination,
    }
