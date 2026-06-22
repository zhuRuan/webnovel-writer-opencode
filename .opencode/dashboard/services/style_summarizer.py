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


def save_summaries_to_db(summaries: list[dict], db_path: str) -> list[int]:
    """将维度总结写入 style_summaries 表。

    使用 StyleCollectorDAO.insert_summary() 写入。
    每个维度写入一条记录。

    Args:
        summaries: `summarize_by_dimension()` 的输出，每项需含
            dimension, display_name, summary, score 字段。
        db_path: SQLite 数据库路径。

    Returns:
        list[int]: 每条插入记录的 row id。
    """
    from data_modules.dao.style_collector_dao import StyleCollectorDAO

    dao = StyleCollectorDAO(db_path)
    inserted_ids: list[int] = []

    for s in summaries:
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
