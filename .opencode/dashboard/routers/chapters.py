"""
章节相关 API 路由 —— 从 app.py 迁移的 7 个端点。

迁移端点：
  GET    /api/chapters                      → list_chapters
  GET    /api/chapters/search               → search_chapters
  POST   /api/chapters/import-existing      → import_existing_chapters
  GET    /api/scenes                        → list_scenes
  GET    /api/reading-power                 → list_reading_power
  GET    /api/review-metrics                → list_review_metrics
  GET    /api/chapters/{chapter}/trace      → get_chapter_trace

使用 Depends(get_db_dependency) 注入数据库连接，保留原始 Query 参数签名。
"""

import json
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlite3 import Connection

# ── 确保 scripts 目录在 sys.path 上（DAO 导入前） ──
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from dashboard.core.config import get_db_path, get_project_root  # noqa: E402
from dashboard.services.db import fetchall_safe, get_dao, get_db_dependency  # noqa: E402
from data_modules.dao.chapter_dao import ChapterDAO  # noqa: E402
from data_modules.dao.process_dao import ProcessDAO  # noqa: E402

router = APIRouter(tags=["chapters"])


# ── 模块级工具函数 ──


def _parse_json_value(raw: object, default):
    """安全解析 JSON 字段值（兼容 str|dict|list|None）。"""
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


# ── 端点：/api/chapters ──


@router.get("/api/chapters")
def list_chapters(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: Connection = Depends(get_db_dependency),
):
    """返回章节列表（按 chapter 升序），不含 content 字段，支持分页。"""
    rows = fetchall_safe(
        conn,
        "SELECT id, chapter, title, word_count, status, created_at, updated_at "
        "FROM chapters ORDER BY chapter ASC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return [
        {**r, "characters": _parse_json_value(r.get("characters"), [])}
        for r in rows
    ]


# ── 端点：/api/chapters/search ──


@router.get("/api/chapters/search")
def search_chapters(
    query: str = Query(..., min_length=1),
    exclude: int = Query(0, ge=0),
    limit: int = Query(5, ge=1, le=50),
):
    """搜索章节标题 / 内容，返回匹配片段列表。"""
    dao = get_dao(ChapterDAO, get_db_path())
    return dao.search_chapters(query=query, exclude_chapter=exclude, limit=limit)


# ── 端点：/api/chapters/import-existing ──


@router.post("/api/chapters/import-existing")
def import_existing_chapters():
    """从文件系统扫描现有章节并导入 index.db。"""
    dao = get_dao(ChapterDAO, get_db_path())
    return dao.batch_import_existing(str(get_project_root()))


# ── 端点：/api/chapters/{chapter_id}/content ──


@router.get("/api/chapters/{chapter_id}/content")
def get_chapter_content(chapter_id: int, conn: Connection = Depends(get_db_dependency)):
    """返回指定章节的完整正文内容。"""
    row = conn.execute(
        "SELECT id, content FROM chapters WHERE id = ?", (chapter_id,)
    ).fetchone()
    if row is None:
        return {"id": chapter_id, "content": ""}
    return {"id": row[0], "content": row[1] or ""}


# ── 端点：/api/scenes ──


@router.get("/api/scenes")
def list_scenes(
    chapter: Optional[int] = None,
    limit: int = 500,
    conn: Connection = Depends(get_db_dependency),
):
    """列出场景。可传 chapter 参数按章节过滤。"""
    if chapter is not None:
        return fetchall_safe(
            conn,
            "SELECT * FROM scenes WHERE chapter = ? ORDER BY scene_index ASC",
            (chapter,),
        )
    return fetchall_safe(
        conn,
        "SELECT * FROM scenes ORDER BY chapter ASC, scene_index ASC LIMIT ?",
        (limit,),
    )


# ── 端点：/api/reading-power ──


@router.get("/api/reading-power")
def list_reading_power(limit: int = 50, conn: Connection = Depends(get_db_dependency)):
    """返回阅读力数据（按 chapter 降序）。"""
    return fetchall_safe(
        conn,
        "SELECT * FROM chapter_reading_power ORDER BY chapter DESC LIMIT ?",
        (limit,),
    )


# ── 端点：/api/review-metrics ──


@router.get("/api/review-metrics")
def list_review_metrics(limit: int = 20, conn: Connection = Depends(get_db_dependency)):
    """返回审查指标列表（JSON 字段自动解析）。"""
    rows = fetchall_safe(
        conn,
        "SELECT * FROM review_metrics ORDER BY end_chapter DESC LIMIT ?",
        (limit,),
    )
    return [
        {
            **r,
            "dimension_scores": _parse_json_value(r.get("dimension_scores"), {}),
            "severity_counts": _parse_json_value(r.get("severity_counts"), {}),
            "critical_issues": _parse_json_value(r.get("critical_issues"), []),
        }
        for r in rows
    ]


# ── 端点：/api/chapters/{chapter}/trace ──


@router.get("/api/chapters/{chapter}/trace")
def get_chapter_trace(chapter: int):
    """返回章节写入过程的 trace + debates 信息。"""
    dao = get_dao(ProcessDAO, get_db_path())
    trace = dao.get_chapter_trace(chapter)
    debates = dao.get_chapter_debates(chapter)
    return {"trace": trace, "debates": debates}
