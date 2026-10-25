"""Bounded network projection, with no histories or original file bytes loaded."""

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from . import storage
from .network import build_network

router = APIRouter()


@router.get("/api/network")
def network(mode: Literal["local", "synthetic", "cloud", "replay"] = "local",
            limit: int = Query(default=100, ge=1, le=200), weak: bool = False):
    fields = ("id", "title", "mode", "created_at", "analyzed_at", "materials", "evidence", "identifiers", "trace")
    with storage.connect() as conn:
        rows = conn.execute("""
            SELECT json_extract(document, '$.id', '$.title', '$.mode', '$.created_at', '$.analyzed_at',
                '$.materials', '$.evidence', '$.identifiers', '$.trace') AS projection
            FROM cases WHERE json_extract(document, '$.mode') = ?
                AND json_array_length(document, '$.evidence') > 0
            ORDER BY json_extract(document, '$.created_at') DESC, id LIMIT ?
        """, (mode, limit + 1)).fetchall()
    documents = [dict(zip(fields, json.loads(row["projection"]), strict=True)) for row in rows[:limit]]
    for document in documents:
        # SQL projections represent absent legacy fields as null, unlike dict.get defaults.
        document["trace"] = document["trace"] or {}
        document["identifiers"] = document["identifiers"] or []
    try:
        result = build_network(documents, include_weak=weak)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {**result, "truncated": len(rows) > limit, "limit": limit}
