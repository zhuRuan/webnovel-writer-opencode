"""
Dashboard 审查与统计 API 路由 —— 从 app.py 迁移的 4 个端点。

端点列表：
  GET /api/review/analytics      — 审查深度分析（聚合）
  GET /api/review-reports        — 审查报告列表（文件系统）
  GET /api/review-report         — 审查报告内容（文件系统）
  GET /api/stats/chapter-trend   — 章节趋势（含读写力和审查评分）
"""

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.core.config import get_project_root, get_webnovel_dir
from dashboard.services.db import fetchall_safe, get_db

router = APIRouter(prefix="/api", tags=["review"])


# ── helpers ───────────────────────────────────────────────────


def _parse_json_value(raw, default):
    """安全解析 JSON 值；非 JSON 或解析失败时返回 default。"""
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


def _load_state_payload(*, required: bool = False) -> dict:
    """加载 state.json 的内容。"""
    state_path = get_webnovel_dir() / "state.json"
    if not state_path.is_file():
        if required:
            raise HTTPException(404, "state.json 不存在")
        return {}

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500, detail=f"state.json 读取失败: {exc}"
        ) from exc

    return payload if isinstance(payload, dict) else {}


def _build_strand_map(state: dict) -> dict[int, str]:
    """从 state 中提取 strand_tracker.history，构建章节→支线映射。"""
    tracker = state.get("strand_tracker") if isinstance(state, dict) else {}
    history = tracker.get("history") if isinstance(tracker, dict) else []
    if not isinstance(history, list):
        return {}

    strand_map: dict[int, str] = {}
    for index, entry in enumerate(history, start=1):
        if not isinstance(entry, dict):
            continue
        chapter_value = entry.get("chapter", index)
        try:
            chapter = int(chapter_value)
        except (TypeError, ValueError):
            chapter = index
        strand = (
            str(entry.get("strand") or entry.get("dominant") or "")
            .strip()
            .lower()
        )
        if chapter > 0 and strand and chapter not in strand_map:
            strand_map[chapter] = strand
    return strand_map


def _resolve_volume_for_chapter(state: dict, chapter: int) -> int | None:
    """从 state.progress.volumes_planned 中反查章节所属卷号。"""
    progress = state.get("progress") if isinstance(state, dict) else {}
    if not isinstance(progress, dict):
        return None
    volumes_planned = progress.get("volumes_planned")
    if not isinstance(volumes_planned, list):
        return None

    best: tuple[int, int] | None = None
    for item in volumes_planned:
        if not isinstance(item, dict):
            continue
        volume = item.get("volume")
        if not isinstance(volume, int) or volume <= 0:
            continue
        chapter_range = str(item.get("chapters_range") or "").strip()
        if "-" not in chapter_range:
            continue
        left, _, right = chapter_range.partition("-")
        try:
            start = int(left.strip())
            end = int(right.strip())
        except ValueError:
            continue
        if start <= 0 or end <= 0 or start > end:
            continue
        if start <= chapter <= end:
            candidate = (start, volume)
            if best is None or candidate[0] > best[0] or (
                candidate[0] == best[0] and candidate[1] < best[1]
            ):
                best = candidate
    return best[1] if best else None


# ── endpoints ─────────────────────────────────────────────────


@router.get("/review/analytics")
def review_analytics(
    limit: int = Query(50, ge=1, le=200),
):
    """返回审查结果的深度分析（维度趋势、严重度统计等）。"""
    with get_db() as conn:
        rows = fetchall_safe(
            conn,
            "SELECT * FROM review_metrics ORDER BY end_chapter DESC LIMIT ?",
            (limit,),
        )

    if not rows:
        return {"items": [], "summary": {}}

    dimension_trends: dict[str, list] = {}
    severity_totals: dict[str, int] = {}
    all_critical_issues: list = []

    for row in rows:
        chapter = row.get("end_chapter", 0)
        scores = _parse_json_value(row.get("dimension_scores"), {})
        for dim, score in scores.items():
            if dim not in dimension_trends:
                dimension_trends[dim] = []
            dimension_trends[dim].append({"chapter": chapter, "score": score})

        sev = _parse_json_value(row.get("severity_counts"), {})
        for s, count in sev.items():
            severity_totals[s] = severity_totals.get(s, 0) + count

        issues = _parse_json_value(row.get("critical_issues"), [])
        all_critical_issues.extend(issues)

    dimension_averages: dict[str, float] = {}
    for dim, points in dimension_trends.items():
        valid_scores = [p["score"] for p in points if p["score"] is not None]
        dimension_averages[dim] = (
            sum(valid_scores) / len(valid_scores) if valid_scores else 0
        )

    weakest = sorted(dimension_averages.items(), key=lambda x: x[1])[:3]

    return {
        "dimension_trends": dimension_trends,
        "dimension_averages": dimension_averages,
        "weakest_dimensions": [
            {"dimension": d, "avg_score": s} for d, s in weakest
        ],
        "severity_totals": severity_totals,
        "critical_issues": all_critical_issues[:20],
        "total_reviews": len(rows),
    }


@router.get("/review-reports")
def list_review_reports():
    """列出审查报告目录中所有报告。"""
    reports_dir = get_project_root() / "审查报告"
    if not reports_dir.is_dir():
        return {"reports": []}
    reports = []
    for f in sorted(reports_dir.glob("第*章审查报告.md")):
        m = re.match(r"第(\d+)章", f.name)
        chapter = int(m.group(1)) if m else 0
        reports.append(
            {
                "chapter": chapter,
                "name": f.name,
                "path": str(f.relative_to(get_project_root())),
            }
        )
    return {"reports": reports}


@router.get("/review-report")
def get_review_report(chapter: int = Query(...)):
    """读取指定章节的审查报告 Markdown 内容。"""
    reports_dir = get_project_root() / "审查报告"
    # 尝试固定宽度（4 位补零）
    for f in reports_dir.glob(f"第{chapter:04d}章审查报告.md"):
        content = f.read_text(encoding="utf-8")
        return {"chapter": chapter, "content": content}
    # 尝试可变宽度
    for f in reports_dir.glob(f"第{chapter}章审查报告.md"):
        content = f.read_text(encoding="utf-8")
        return {"chapter": chapter, "content": content}
    raise HTTPException(404, f"第{chapter}章审查报告不存在")


@router.get("/stats/chapter-trend")
def chapter_trend(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """返回章节趋势数据（含读写力钩子强度、审查评分、支线归属等）。"""
    state = _load_state_payload()
    strand_map = _build_strand_map(state)

    with get_db() as conn:
        total_rows = fetchall_safe(conn, "SELECT COUNT(*) AS count FROM chapters")
        latest_rows = fetchall_safe(
            conn, "SELECT MAX(chapter) AS chapter FROM chapters"
        )
        rows = fetchall_safe(
            conn,
            """
        WITH selected_chapters AS (
            SELECT chapter, title, location, word_count, characters, summary
            FROM chapters
            ORDER BY chapter DESC
            LIMIT ? OFFSET ?
        )
        SELECT
            c.chapter,
            c.title,
            c.location,
            c.word_count,
            c.characters,
            c.summary,
            rp.hook_type,
            rp.hook_strength,
            rp.is_transition,
            rp.override_count,
            rp.debt_balance,
            rm.overall_score AS review_score,
            rm.severity_counts
        FROM selected_chapters c
        LEFT JOIN chapter_reading_power rp ON rp.chapter = c.chapter
        LEFT JOIN review_metrics rm ON rm.end_chapter = c.chapter
        ORDER BY c.chapter ASC
        """,
            (limit, offset),
        )

    hook_strength_value = {"weak": 1, "medium": 3, "strong": 5}
    items = []
    for row in rows:
        chapter = int(row.get("chapter") or 0)
        hook_strength = str(row.get("hook_strength") or "").strip().lower()
        items.append(
            {
                "chapter": chapter,
                "title": row.get("title") or "",
                "location": row.get("location") or "",
                "word_count": int(row.get("word_count") or 0),
                "characters": _parse_json_value(row.get("characters"), []),
                "summary": row.get("summary") or "",
                "review_score": row.get("review_score"),
                "review_severity_counts": _parse_json_value(
                    row.get("severity_counts"), {}
                ),
                "hook_type": row.get("hook_type") or "",
                "hook_strength": hook_strength,
                "hook_strength_value": hook_strength_value.get(hook_strength, 0),
                "is_transition": bool(row.get("is_transition")),
                "override_count": int(row.get("override_count") or 0),
                "debt_balance": float(row.get("debt_balance") or 0.0),
                "strand": strand_map.get(chapter, ""),
                "volume": _resolve_volume_for_chapter(state, chapter),
            }
        )

    return {
        "items": items,
        "total": int(total_rows[0]["count"] or 0) if total_rows else 0,
        "latest_chapter": (
            int(latest_rows[0]["chapter"] or 0) if latest_rows else 0
        ),
        "limit": limit,
        "offset": offset,
    }
