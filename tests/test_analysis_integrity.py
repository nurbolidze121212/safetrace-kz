"""Interrupted retries must not mix current evidence with a previous analysis."""

from copy import deepcopy

import pytest

from backend import pipeline
from backend.graph import build_graph
from backend.schemas import CaseInput, MaterialInput


@pytest.mark.parametrize("stop_after", [None, "originals", "ocr", "features", "links", "graph"])
def test_cancelled_reanalysis_has_no_stale_results_or_dangling_evidence(stop_after):
    doc = pipeline.new_case(
        CaseInput(
            title="Повтор",
            mode="synthetic",
            materials=[
                MaterialInput(text="Переходи, бонус! Промокод QALA7. https://go.safetrace.test/r/q7"),
                MaterialInput(text="Тіркел, бонус! https://go.safetrace.test/r/second"),
            ],
        )
    )
    pipeline.analyze(doc)
    assert doc["status"] == "completed"
    previous = deepcopy(doc)
    originals = [{k: mat[k] for k in ("id", "text", "source", "url", "original_sha256")} for mat in doc["materials"]]
    stop = stop_after is None

    def checkpoint(current):
        nonlocal stop
        if current["stage"] == stop_after:
            stop = True

    pipeline.analyze(doc, cancelled=lambda: stop, checkpoint=checkpoint)

    assert doc["status"] == "cancelled"
    assert "score" not in doc
    assert "sufficient_data" not in doc
    assert "elapsed_ms" not in doc
    assert all("score" not in mat and "sufficient_data" not in mat for mat in doc["materials"])
    assert all(value != "running" and value != "pending" for value in doc["stages"].values())
    known = {e["id"] for e in doc["evidence"]}
    previous_ids = {e["id"] for e in previous["evidence"]}
    assert not known & previous_ids
    for graph in (build_graph(doc), doc.get("graph", {"nodes": [], "edges": []})):
        for element in graph["nodes"] + graph["edges"]:
            assert set(element["evidence_ids"]) <= known
    assert originals == [{k: mat[k] for k in originals[0]} for mat in doc["materials"]]
