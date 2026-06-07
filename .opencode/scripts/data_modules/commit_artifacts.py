#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified accessors for extraction data stored in commit payloads.

New commits store the extraction snapshot under ``extraction_result``.
Older commits stored these fields at top level.  These helpers keep
projections readable without preserving two write shapes.
"""
from __future__ import annotations

from typing import Any


EXTRACTION_FIELDS = (
    "accepted_events",
    "state_deltas",
    "entity_deltas",
    "entities_appeared",
    "scenes",
    "chapter_meta",
    "dominant_strand",
    "summary_text",
)


def extraction_result_from_commit(commit_payload: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical extraction artifact from a commit.

    If the nested ``extraction_result`` key exists, return it directly.
    Otherwise fall back to top-level fields (backward compat with old
    commit files).
    """
    nested = commit_payload.get("extraction_result")
    if isinstance(nested, dict):
        return dict(nested)

    result: dict[str, Any] = {}
    for field in EXTRACTION_FIELDS:
        if field in commit_payload:
            result[field] = commit_payload.get(field)
    return result


def extraction_list(commit_payload: dict[str, Any], field: str) -> list[Any]:
    """Return a list-valued extraction field, or ``[]`` if missing."""
    value = extraction_result_from_commit(commit_payload).get(field)
    return value if isinstance(value, list) else []


def extraction_dict(commit_payload: dict[str, Any], field: str) -> dict[str, Any]:
    """Return a dict-valued extraction field, or ``{}`` if missing."""
    value = extraction_result_from_commit(commit_payload).get(field)
    return value if isinstance(value, dict) else {}


def extraction_text(commit_payload: dict[str, Any], field: str) -> str:
    """Return a string-valued extraction field, or ``""`` if missing."""
    value = extraction_result_from_commit(commit_payload).get(field)
    return str(value or "").strip()
