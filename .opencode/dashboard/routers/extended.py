"""
Dashboard 扩展 API 路由 —— 从 app.py 迁移的 7 个端点。

端点列表：
  GET /api/aliases            — 别名列表
  GET /api/invalid-facts      — 无效事实列表
  GET /api/rag-queries        — RAG 查询日志
  GET /api/tool-stats         — 工具调用统计
  GET /api/checklist-scores   — 写作清单评分
  GET /api/story-events       — 故事事件列表
  GET /api/story-events/health — 故事事件健康检查
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query

from dashboard.core.config import get_db_path, get_story_system_dir
from dashboard.services.db import fetchall_safe, get_dao, get_db_dependency

router = APIRouter(prefix="/api", tags=["extended"])


# ── helpers ──────────────────────────────────────────────────

def _to_int(value) -> int:
    """安全地将值转换为整数；转换失败时返回 0。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ── endpoints ────────────────────────────────────────────────

@router.get("/aliases")
def list_aliases(entity: Optional[str] = None):
    """返回别名列表（可选的实体 ID 筛选）。"""
    from data_modules.dao.entity_dao import EntityDAO

    dao = get_dao(EntityDAO, get_db_path())
    return dao.list_aliases(entity_id=entity)


@router.get("/invalid-facts")
def list_invalid_facts(
    status: Optional[str] = None,
    limit: int = 100,
    conn=Depends(get_db_dependency),
):
    """返回无效事实列表。"""
    if status:
        return fetchall_safe(
            conn,
            "SELECT * FROM invalid_facts WHERE status = ? ORDER BY marked_at DESC LIMIT ?",
            (status, limit),
        )
    return fetchall_safe(
        conn,
        "SELECT * FROM invalid_facts ORDER BY marked_at DESC LIMIT ?",
        (limit,),
    )


@router.get("/rag-queries")
def list_rag_queries(
    query_type: Optional[str] = None,
    limit: int = 100,
    conn=Depends(get_db_dependency),
):
    """返回 RAG 查询日志列表。"""
    if query_type:
        return fetchall_safe(
            conn,
            "SELECT * FROM rag_query_log WHERE query_type = ? ORDER BY created_at DESC LIMIT ?",
            (query_type, limit),
        )
    return fetchall_safe(
        conn,
        "SELECT * FROM rag_query_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


@router.get("/tool-stats")
def list_tool_stats(
    tool_name: Optional[str] = None,
    limit: int = 200,
    conn=Depends(get_db_dependency),
):
    """返回工具调用统计列表。"""
    if tool_name:
        return fetchall_safe(
            conn,
            "SELECT * FROM tool_call_stats WHERE tool_name = ? ORDER BY created_at DESC LIMIT ?",
            (tool_name, limit),
        )
    return fetchall_safe(
        conn,
        "SELECT * FROM tool_call_stats ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


@router.get("/checklist-scores")
def list_checklist_scores(
    limit: int = 100,
    conn=Depends(get_db_dependency),
):
    """返回写作清单评分列表。"""
    return fetchall_safe(
        conn,
        "SELECT * FROM writing_checklist_scores ORDER BY chapter DESC LIMIT ?",
        (limit,),
    )


@router.get("/story-events")
def list_story_events(
    chapter: Optional[int] = None,
    limit: int = 200,
    conn=Depends(get_db_dependency),
):
    """返回故事事件列表，包含解析后的 payload 字段。"""
    if chapter is not None:
        rows = fetchall_safe(
            conn,
            """
            SELECT event_id, chapter, event_type, subject, payload_json, created_at
            FROM story_events
            WHERE chapter = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chapter, limit),
        )
    else:
        rows = fetchall_safe(
            conn,
            """
            SELECT event_id, chapter, event_type, subject, payload_json, created_at
            FROM story_events
            ORDER BY chapter DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )

    normalized = []
    for row in rows:
        payload = {}
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        normalized.append({**row, "payload": payload})
    return normalized


@router.get("/story-events/health")
def story_event_health(
    conn=Depends(get_db_dependency),
):
    """返回故事事件健康状态。"""
    event_rows = fetchall_safe(conn, "SELECT COUNT(*) AS count FROM story_events")
    proposal_rows = fetchall_safe(
        conn,
        """
        SELECT COUNT(*) AS count
        FROM override_contracts
        WHERE record_type = 'amend_proposal' AND status = 'pending'
        """,
    )

    events_dir = get_story_system_dir() / "events"
    file_count = (
        len(list(events_dir.glob("chapter_*.events.json")))
        if events_dir.is_dir()
        else 0
    )
    return {
        "story_events": event_rows[0]["count"] if event_rows else 0,
        "pending_amend_proposals": proposal_rows[0]["count"] if proposal_rows else 0,
        "event_files": file_count,
    }
