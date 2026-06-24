"""
文风总结生成服务。

按 9 维度聚合多章分析结果，生成作家级别总结，存入 SQLite。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ── 维度映射：内部字段名 → 中文显示名 ──
DIMENSION_MAP: dict[str, dict[str, Any]] = {
    "sentence_style": {"display_name": "句式风格", "is_primary": True},
    "narrative_pov": {"display_name": "叙事视角", "is_primary": True},
    "pacing_control": {"display_name": "节奏控制", "is_primary": True},
    "emotional_tension": {"display_name": "情感张力", "is_primary": True},
    "dialogue_style": {"display_name": "对白风格", "is_primary": True},
    "word_texture": {"display_name": "词汇质地", "is_primary": False},
    "rhetoric_devices": {"display_name": "修辞手法", "is_primary": False},
    "description_preference": {"display_name": "描写偏好", "is_primary": False},
    "character_portrayal": {"display_name": "人物刻画", "is_primary": False},
}

# ── 确保 scripts 目录在 sys.path 上 ──
_SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[2] / "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def summarize_by_dimension(analyses: list[dict]) -> list[dict]:
    """按 9 维度聚合多章分析结果。

    输入 `analyses` 是一个列表，每项为 AnalysisResult 的 dict 表示
    （含 sentence_style/narrative_pov/... 等维度的 {summary, score}）。

    返回列表，每项含：
      - dimension: 内部字段名（如 "sentence_style"）
      - display_name: 中文显示名（如 "句式风格"）
      - is_primary: 是否为主要维度
      - summary: 合并后的文风总结文本
      - score: 所有章节该维度的平均分
    """
    if not analyses:
        return []

    # 收集每个维度所有章节的 summary 和 score
    dimension_data: dict[str, dict[str, list]] = {
        key: {"summaries": [], "scores": []}
        for key in DIMENSION_MAP
    }

    for analysis in analyses:
        for key in DIMENSION_MAP:
            dim = analysis.get(key)
            if not isinstance(dim, dict):
                continue
            summary = dim.get("summary", "")
            score = dim.get("score")
            if summary:
                dimension_data[key]["summaries"].append(summary)
            if score is not None:
                try:
                    dimension_data[key]["scores"].append(float(score))
                except (ValueError, TypeError):
                    pass

    # 生成输出
    result: list[dict] = []
    for key, info in DIMENSION_MAP.items():
        data = dimension_data[key]
        if not data["summaries"] and not data["scores"]:
            # 没有该维度数据的章节，跳过
            continue

        # 合并 summaries（用换行分隔）
        merged_summary = "\n".join(data["summaries"])

        # 平均分
        avg_score = 0.0
        if data["scores"]:
            avg_score = sum(data["scores"]) / len(data["scores"])

        result.append({
            "dimension": key,
            "display_name": info["display_name"],
            "is_primary": info["is_primary"],
            "summary": merged_summary,
            "score": round(avg_score, 4),
        })

    return result


def generate_author_summary(author: str, summaries: list[dict]) -> dict:
    """生成作家级别文风总结。

    Args:
        author: 作家名称。
        summaries: `summarize_by_dimension()` 的输出。

    Returns:
        dict 含 author, primary_summary, secondary_summary,
        total_chapters, average_scores。
    """
    primary_summary: dict[str, dict] = {}
    secondary_summary: dict[str, dict] = {}
    average_scores: dict[str, float] = {}

    for s in summaries:
        dim = s["dimension"]
        entry = {"summary": s["summary"], "score": s["score"]}
        if s["is_primary"]:
            primary_summary[dim] = entry
        else:
            secondary_summary[dim] = entry
        average_scores[dim] = s["score"]

    # 估算章节数：取 summaries 中任意维度含有的 summary 数量
    # 从第一个 summary 中的换行符数量推断
    total_chapters = _estimate_chapter_count(summaries)

    return {
        "author": author,
        "primary_summary": primary_summary,
        "secondary_summary": secondary_summary,
        "total_chapters": total_chapters,
        "average_scores": average_scores,
    }


def _estimate_chapter_count(summaries: list[dict]) -> int:
    """从合并后的 summaries 中估算原始章节数。"""
    for s in summaries:
        summary_text = s.get("summary", "")
        if summary_text:
            # 每条 summary 来自一个章节，合并时用换行分隔
            count = summary_text.count("\n") + 1
            return count
    return 0


def cluster_techniques(analyses: list[dict]) -> list[dict]:
    """Cluster extracted techniques by category → sub_category → technique name.

    Each analysis entry may have "techniques" key (list) from the new format
    or dimension keys (dict) from the old format.

    Returns:
        [{
            "category": "人物",
            "technique_count": 5,
            "total_occurrences": 12,
            "techniques": [{
                "technique": "配角番外补完法",
                "count": 12,
                "description": "merged best description",
                "examples": ["原文例1", "原文例2", ...],
                "all_examples": 50,
                "scenes": ["高人气配角外传", ...],
                "sub_categories": ["配角塑造", ...]
            }]
        }, ...]
    """
    from collections import defaultdict

    import logging

    logger = logging.getLogger(__name__)

    # Cluster: technique_name → {descriptions, examples, scenes, sub_categories, count}
    clusters: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "technique": "",
        "descriptions": [],
        "examples": [],
        "scenes": set(),
        "sub_categories": set(),
        "count": 0,
    })

    for analysis in analyses:
        if not analysis:
            continue
        # New format: has "techniques" key
        if "techniques" in analysis and isinstance(analysis["techniques"], list):
            for t in analysis["techniques"]:
                if not isinstance(t, dict):
                    continue
                name = t.get("technique", "").strip()
                if not name:
                    continue
                c = clusters[name]
                c["technique"] = name
                c["count"] += 1
                if t.get("description"):
                    c["descriptions"].append(t["description"])
                if t.get("text_example"):
                    c["examples"].append(t["text_example"])
                if t.get("category"):
                    c["category"] = t["category"]  # last writer wins
                if t.get("sub_category"):
                    c["sub_categories"].add(t["sub_category"])
                for scene in t.get("applicable_scenes", []):
                    if scene:
                        c["scenes"].add(scene)
        # Old format: has dimension keys (skip — old format doesn't have techniques)
        else:
            pass

    if not clusters:
        logger.warning("cluster_techniques: no techniques found in %d analyses", len(analyses))
        return []

    # Sort by frequency descending
    all_techniques = sorted(clusters.values(), key=lambda x: -x["count"])

    # Group by category
    by_category: dict[str, list] = {}
    for t in all_techniques:
        cat = t.get("category") or "其他"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append({
            "technique": t["technique"],
            "count": t["count"],
            "description": t["descriptions"][0] if t["descriptions"] else "",
            "examples": t["examples"][:5],  # top 5 examples
            "all_examples": len(t["examples"]),
            "scenes": sorted(t["scenes"]),
            "sub_categories": sorted(t["sub_categories"]),
        })

    result: list[dict] = []
    for cat, techniques in sorted(by_category.items()):
        result.append({
            "category": cat,
            "technique_count": len(techniques),
            "total_occurrences": sum(t["count"] for t in techniques),
            "techniques": techniques,
        })

    return result


def _format_category_summary(cat_group: dict) -> str:
    """Format category group as structured JSON (replaces legacy markdown format).

    Stores the full clustered technique data as JSON so downstream consumers
    (publish pipeline, agent AI summary) can read structured fields directly
    instead of fragile regex-parsing of markdown headers.
    """
    import json as _json
    structured = {
        "format": "technique-cluster-v2",
        "category": cat_group.get("category", ""),
        "technique_count": cat_group.get("technique_count", 0),
        "total_occurrences": cat_group.get("total_occurrences", 0),
        "techniques": [
            {
                "name": t["technique"],
                "occurrence_count": t["count"],
                "description": t.get("description", ""),
                "examples": t.get("examples", []),
                "all_examples": t.get("all_examples", 0),
                "applicable_scenes": t.get("scenes", []),
                "sub_categories": t.get("sub_categories", []),
            }
            for t in cat_group.get("techniques", [])
        ],
    }
    return _json.dumps(structured, ensure_ascii=False, indent=2)


def save_summaries_to_db(summaries: list[dict], db_path: str) -> list[int]:
    """Save summaries to style_summaries table.

    Supports both dimension format (from summarize_by_dimension) and
    cluster format (from cluster_techniques). Detects format automatically.

    Args:
        summaries: Either dimension summaries (each has 'dimension', 'display_name',
            'summary') or clustered categories (each has 'category', 'techniques').
        db_path: SQLite 数据库路径。

    Returns:
        list[int]: Row IDs of each inserted record.
    """
    from data_modules.dao.style_collector_dao import StyleCollectorDAO

    dao = StyleCollectorDAO(db_path)
    inserted_ids: list[int] = []

    for s in summaries:
        if not isinstance(s, dict):
            continue

        # Detect format: cluster format has "techniques" key
        if "techniques" in s:
            # ── New cluster format (from cluster_techniques) ──
            record = {
                "author": s.get("author", ""),
                "work_title": s.get("work_title", ""),
                "summary_title": f"技法聚类 - {s['category']}",
                "category": s["category"],
                "content": _format_category_summary(s),
                "examples": s.get("techniques", []),
                "keywords": [t["technique"] for t in s.get("techniques", [])],
                "chapter_range": s.get("chapter_range", ""),
            }
        else:
            # ── Old dimension format (from summarize_by_dimension) ──
            record = {
                "author": s.get("author", ""),
                "work_title": s.get("work_title", ""),
                "summary_title": f"{s.get('author', '')} - {s['display_name']}",
                "category": s["display_name"],
                "content": s["summary"],
                "examples": s.get("examples", []),
                "keywords": s.get("keywords", []),
                "chapter_range": s.get("chapter_range", ""),
            }
        row_id = dao.insert_summary(record)
        inserted_ids.append(row_id)

    return inserted_ids
