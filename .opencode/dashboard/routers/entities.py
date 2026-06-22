"""
实体相关路由 —— 从 app.py 迁移的 entities/factions/relationships/consistency/state-changes 端点。

共 10 个 GET 端点:
  GET /api/entities                  → list_entities
  GET /api/entities/{entity_id}      → get_entity
  GET /api/entities/{entity_id}/timeline → entity_timeline
  GET /api/entities/{entity_id}/knowledge → get_entity_knowledge
  GET /api/factions                  → list_factions
  GET /api/factions/{faction_id}     → get_faction
  GET /api/relationships             → list_relationships
  GET /api/relationship-events       → list_relationship_events
  GET /api/consistency/anomalies     → consistency_anomalies
  GET /api/state-changes             → list_state_changes
"""

from collections.abc import Generator
from pathlib import Path
from typing import Any, Optional

import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Query

from ..core.config import get_db_path, get_project_root
from ..services.db import get_db as _get_db_service
from ..schemas.entities import EntityTimeline

from data_modules.dao import get_dao
from data_modules.dao.entity_dao import EntityDAO
from data_modules.dao.faction_dao import FactionDAO
from data_modules.dao.knowledge_dao import KnowledgeDAO
from data_modules.dao.relationship_dao import RelationshipDAO

router = APIRouter(tags=["entities"])


# ── 数据库依赖注入 ──────────────────────────────────────────────


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI 依赖：提供 index.db 数据库连接。"""
    with _get_db_service() as conn:
        yield conn


# ── 辅助函数（从 app.py 迁移） ─────────────────────────────────


def _theater_actors_as_entities(project_root: Path) -> list[dict]:
    """将 theater/actors/ 注册的角色转换为 entities 格式（通过 KnowledgeDAO）。

    当 index.db entities 表为空时，作为 fallback 数据源。
    """
    try:
        dao = get_dao(KnowledgeDAO, get_db_path())
        theater_list = dao.get_theater_actors_list(project_root)
    except Exception:
        return []
    result: list[dict] = []
    for item in theater_list:
        result.append({**item, "id": item.get("actor_id", "")})
    return result


# ── 实体端点 ────────────────────────────────────────────────────


@router.get("/api/entities")
def list_entities(
    entity_type: Optional[str] = Query(None, alias="type"),
    include_archived: bool = False,
    db: sqlite3.Connection = Depends(get_db),
) -> list[dict[str, Any]]:
    """列出所有实体（index.db + theater actors 合并）。"""
    dao = get_dao(EntityDAO, get_db_path())
    db_entities = dao.list_entities(entity_type=entity_type, include_archived=include_archived)

    db_ids = {e.get("id") for e in db_entities if e.get("id")}

    # 合并 theater actors（仅补充 index.db 中不存在的）
    theater_entities = _theater_actors_as_entities(get_project_root())
    for te in theater_entities:
        if te["id"] not in db_ids:
            if entity_type and te["type"] != entity_type:
                continue
            db_entities.append(te)

    return db_entities


@router.get("/api/entities/{entity_id}")
def get_entity(
    entity_id: str,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """获取单个实体详情，回退到 theater actors。"""
    dao = get_dao(EntityDAO, get_db_path())
    entity = dao.get_entity(entity_id)
    if entity:
        return entity

    # 回退到 theater actors
    theater_entities = _theater_actors_as_entities(get_project_root())
    for te in theater_entities:
        if te["id"] == entity_id:
            return te

    raise HTTPException(404, "实体不存在")


@router.get("/api/entities/{entity_id}/timeline")
def entity_timeline(
    entity_id: str,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """返回实体的完整状态变化时间线。"""
    dao = get_dao(EntityDAO, get_db_path())
    result = dao.get_entity_timeline(entity_id)
    return {"changes": result["state_changes"], "appearances": result["appearances"]}


@router.get("/api/entities/{entity_id}/knowledge")
def get_entity_knowledge(
    entity_id: str,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """获取角色知识库：已知域、技能、核心欲望（优雅降级）。"""
    try:
        dao = get_dao(KnowledgeDAO, get_db_path())
        result = dao.get_entity_knowledge(entity_id, get_project_root())
        if result is None:
            raise HTTPException(404, "实体不存在")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        import traceback

        raise HTTPException(
            status_code=500,
            detail=f"知识查询异常: {exc} — {traceback.format_exc()[-200:]}",
        ) from exc


# ── 势力端点 ────────────────────────────────────────────────────


@router.get("/api/factions")
def list_factions(
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """列出所有势力。"""
    dao = get_dao(FactionDAO, get_db_path())
    result = dao.list_factions()
    for faction in result["factions"]:
        faction["name"] = faction.pop("canonical_name", faction.get("id", ""))
        faction["type"] = "势力"
    return result


@router.get("/api/factions/{faction_id}")
def get_faction(
    faction_id: str,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """获取单个势力详情。"""
    dao = get_dao(FactionDAO, get_db_path())
    result = dao.get_faction(faction_id)
    if result is None:
        raise HTTPException(404, "势力不存在")
    result["name"] = result.pop("canonical_name", faction_id)
    result["type"] = "势力"
    return result


# ── 关系端点 ────────────────────────────────────────────────────


@router.get("/api/relationships")
def list_relationships(
    entity: Optional[str] = None,
    limit: int = 200,
    db: sqlite3.Connection = Depends(get_db),
) -> list[dict[str, Any]]:
    """列出所有关系，可指定实体筛选。"""
    dao = get_dao(RelationshipDAO, get_db_path())
    return dao.list_relationships(entity_id=entity, limit=limit)


@router.get("/api/relationship-events")
def list_relationship_events(
    entity: Optional[str] = None,
    from_chapter: Optional[int] = None,
    to_chapter: Optional[int] = None,
    limit: int = 200,
    db: sqlite3.Connection = Depends(get_db),
) -> list[dict[str, Any]]:
    """列出关系事件，支持章节范围筛选。"""
    dao = get_dao(RelationshipDAO, get_db_path())
    events = dao.list_relationship_events(entity_id=entity, limit=5000)
    if from_chapter is not None:
        events = [e for e in events if int(e.get("chapter") or 0) >= from_chapter]
    if to_chapter is not None:
        events = [e for e in events if int(e.get("chapter") or 0) <= to_chapter]
    return events[:limit]


# ── 一致性端点 ──────────────────────────────────────────────────


@router.get("/api/consistency/anomalies")
def consistency_anomalies(
    chapter: Optional[int] = None,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """检测实体状态异常跳变（多值冲突）。"""
    dao = get_dao(EntityDAO, get_db_path())
    if chapter is not None:
        rows = dao.get_state_changes(limit=5000)
        rows = [r for r in rows if int(r.get("chapter") or 0) <= chapter]
    else:
        rows = dao.get_consistency_anomalies()
        anomalies = []
        for row in rows:
            anomalies.append({
                "type": "value_conflict",
                "entity_id": row["entity_id"],
                "field": row["field"],
                "chapter": row["last_chapter"],
                "detail": (
                    f"{row['field']} 存在 {row['val_count']} 种不同值: "
                    f"{row['all_values']}（第 {row['first_chapter']}-{row['last_chapter']} 章）"
                ),
            })
        return {"anomalies": anomalies, "total": len(anomalies)}

    anomalies = []
    entity_states = {}
    for row in rows:
        eid = row.get("entity_id")
        field = row.get("field")
        old_val = row.get("old_value")
        new_val = row.get("new_value")
        row_chapter = row.get("chapter")
        if eid not in entity_states:
            entity_states[eid] = {}
        prev = entity_states[eid].get(field)
        if prev is not None and new_val == prev:
            anomalies.append({
                "type": "no_change",
                "entity_id": eid,
                "field": field,
                "chapter": row_chapter,
                "detail": f"{field} 从 {old_val} 变为 {new_val}，但值未实际改变",
            })
        elif prev is not None and old_val is not None and new_val == old_val and new_val != prev:
            anomalies.append({
                "type": "value_reverted",
                "entity_id": eid,
                "field": field,
                "chapter": row_chapter,
                "detail": f"{field} 回退到 {new_val}（之前是 {prev}）",
            })
        entity_states[eid][field] = new_val
    return {"anomalies": anomalies, "total": len(anomalies)}


@router.get("/api/state-changes")
def list_state_changes(
    entity: Optional[str] = None,
    limit: int = 100,
    db: sqlite3.Connection = Depends(get_db),
) -> list[dict[str, Any]]:
    """列出实体状态变更历史。"""
    dao = get_dao(EntityDAO, get_db_path())
    return dao.get_state_changes(entity_id=entity, limit=limit)
