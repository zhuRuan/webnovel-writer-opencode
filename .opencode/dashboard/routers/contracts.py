"""Contracts router — commits, contracts summary, overrides, debts, debt-events.

Migrated from app.py:1292-1481. Uses Pydantic response models.
"""

import sqlite3
import json
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from dashboard.core.config import (
    build_story_runtime_health_report,
    extract_story_chapter,
    get_db_path,
    get_project_root,
    get_story_system_dir,
    load_state_payload,
    resolve_volume_for_chapter,
)
from dashboard.schemas.contracts import ContractSummary
from dashboard.services.db import fetchall_safe

router = APIRouter(tags=["contracts"])


# ── FastAPI dependency: raw generator (NOT decorated with @contextmanager) ──


def _get_db() -> Generator[sqlite3.Connection, None, None]:  # type: ignore[misc]
    """FastAPI-compatible DB connection dependency.

    Must be a raw generator (not @contextmanager-decorated) so FastAPI's
    dependency injection system can manage the context lifecycle.
    """
    db_path = get_db_path()
    if not __import__("pathlib").Path(db_path).is_file():
        raise HTTPException(404, "index.db 不存在")
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ── Pydantic response models ──────────────────────────────────


class CommitItem(BaseModel):
    """Single commit entry."""

    chapter: int
    status: str
    projection_status: dict
    write_fact_role: str
    contract_refs: dict
    path: str
    updated_at: str


class CommitListResponse(BaseModel):
    """Commit list response."""

    items: list[CommitItem]
    total: int
    limit: int


# ── Endpoints ─────────────────────────────────────────────────


@router.get("/api/commits", response_model=CommitListResponse)
def list_commits(limit: int = Query(20, ge=1, le=200)):
    commits_dir = get_story_system_dir() / "commits"
    if not commits_dir.is_dir():
        return CommitListResponse(items=[], total=0, limit=limit)

    items = []
    for path in commits_dir.glob("chapter_*.commit.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        meta = payload.get("meta") if isinstance(payload, dict) else {}
        provenance = payload.get("provenance") if isinstance(payload, dict) else {}
        chapter = int((meta or {}).get("chapter") or extract_story_chapter(path))
        items.append(
            CommitItem(
                chapter=chapter,
                status=str((meta or {}).get("status") or "missing"),
                projection_status=payload.get("projection_status") or {},
                write_fact_role=str((provenance or {}).get("write_fact_role") or ""),
                contract_refs=payload.get("contract_refs") or {},
                path=path.name,
                updated_at=datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            )
        )

    items.sort(key=lambda item: item.chapter, reverse=True)
    return CommitListResponse(items=items[:limit], total=len(items), limit=limit)


@router.get("/api/contracts/summary", response_model=ContractSummary)
def contracts_summary():
    from data_modules.story_contracts import StoryContractPaths, read_json_if_exists

    project_root = get_project_root()
    state = load_state_payload()
    runtime = build_story_runtime_health_report(project_root)
    chapter = int(
        runtime.get("chapter")
        or ((state.get("progress") or {}).get("current_chapter") or 0)
    )
    current_volume = resolve_volume_for_chapter(state, chapter) or int(
        ((state.get("progress") or {}).get("current_volume") or 1)
    )

    paths = StoryContractPaths.from_project_root(project_root)
    master_payload = read_json_if_exists(paths.master_json) or {}

    return ContractSummary(
        chapter=chapter,
        current_volume=current_volume,
        master={
            "exists": bool(master_payload),
            "primary_genre": str(
                ((master_payload.get("route") or {}).get("primary_genre") or "")
            ),
            "core_tone": str(
                ((master_payload.get("master_constraints") or {}).get("core_tone") or "")
            ),
        },
        counts={
            "volumes": len(list(paths.volumes_dir.glob("volume_*.json")))
            if paths.volumes_dir.is_dir()
            else 0,
            "chapters": len(list(paths.chapters_dir.glob("chapter_*.json")))
            if paths.chapters_dir.is_dir()
            else 0,
            "reviews": len(list(paths.reviews_dir.glob("chapter_*.review.json")))
            if paths.reviews_dir.is_dir()
            else 0,
            "commits": len(list(paths.commits_dir.glob("chapter_*.commit.json")))
            if paths.commits_dir.is_dir()
            else 0,
        },
        current_contracts={
            "volume": paths.volume_json(current_volume).is_file(),
            "chapter": paths.chapter_json(chapter).is_file() if chapter > 0 else False,
            "review": paths.review_json(chapter).is_file() if chapter > 0 else False,
            "commit": paths.commit_json(chapter).is_file() if chapter > 0 else False,
        },
    )


@router.get("/api/overrides")
def list_overrides(
    status: Optional[str] = None,
    limit: int = 100,
    conn: sqlite3.Connection = Depends(_get_db),
):
    if status:
        return fetchall_safe(
            conn,
            "SELECT * FROM override_contracts WHERE status = ? ORDER BY chapter DESC LIMIT ?",
            (status, limit),
        )
    return fetchall_safe(
        conn,
        "SELECT * FROM override_contracts ORDER BY chapter DESC LIMIT ?",
        (limit,),
    )


@router.get("/api/debts")
def list_debts(
    status: Optional[str] = None,
    limit: int = 100,
    conn: sqlite3.Connection = Depends(_get_db),
):
    if status:
        return fetchall_safe(
            conn,
            "SELECT * FROM chase_debt WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
            (status, limit),
        )
    return fetchall_safe(
        conn,
        "SELECT * FROM chase_debt ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    )


@router.get("/api/debt-events")
def list_debt_events(
    debt_id: Optional[int] = None,
    limit: int = 200,
    conn: sqlite3.Connection = Depends(_get_db),
):
    if debt_id is not None:
        return fetchall_safe(
            conn,
            "SELECT * FROM debt_events WHERE debt_id = ? ORDER BY chapter DESC, id DESC LIMIT ?",
            (debt_id, limit),
        )
    return fetchall_safe(
        conn,
        "SELECT * FROM debt_events ORDER BY chapter DESC, id DESC LIMIT ?",
        (limit,),
    )
