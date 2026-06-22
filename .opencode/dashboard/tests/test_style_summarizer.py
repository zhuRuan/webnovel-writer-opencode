"""测试 services/style_summarizer.py。

覆盖：
  - summarize_by_dimension: 空输入、单章、多章聚合
  - generate_author_summary: primary/secondary 分组、章节数估算
  - save_summaries_to_db: 写入 style_summaries 表
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from dashboard.services.style_summarizer import (
    DIMENSION_MAP,
    generate_author_summary,
    save_summaries_to_db,
    summarize_by_dimension,
)

# ── 辅助：构建单章分析 dict ──


def _make_analysis(
    sentence_score=0.8,
    pov_score=0.7,
    pacing_score=0.75,
    tension_score=0.85,
    dialogue_score=0.6,
    word_score=0.72,
    rhetoric_score=0.65,
    desc_score=0.78,
    char_score=0.9,
    suffix: str = "",
) -> dict:
    """生成一个 AnalysisResult 风格的 dict。"""
    return {
        "sentence_style": {"summary": f"句式简洁{suffix}", "score": sentence_score},
        "narrative_pov": {"summary": f"第三人称限知视角{suffix}", "score": pov_score},
        "pacing_control": {"summary": f"节奏张弛有度{suffix}", "score": pacing_score},
        "emotional_tension": {"summary": f"情感层层递进{suffix}", "score": tension_score},
        "dialogue_style": {"summary": f"对白生动自然{suffix}", "score": dialogue_score},
        "word_texture": {"summary": f"用词精准{suffix}", "score": word_score},
        "rhetoric_devices": {"summary": f"善用比喻{suffix}", "score": rhetoric_score},
        "description_preference": {"summary": f"侧重动作描写{suffix}", "score": desc_score},
        "character_portrayal": {"summary": f"人物立体鲜明{suffix}", "score": char_score},
    }


def _create_db_with_schema(db_path: str | Path) -> sqlite3.Connection:
    """创建临时数据库并初始化 style_summaries 表。"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS style_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            work_title TEXT,
            summary_title TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            examples TEXT DEFAULT '[]',
            keywords TEXT DEFAULT '[]',
            quality_score REAL DEFAULT 0,
            chapter_range TEXT,
            model_used TEXT DEFAULT 'qwen3.5_9B_Q4',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


# ============================================================
# summarize_by_dimension
# ============================================================


class TestSummarizeByDimension:
    def test_empty_analyses_returns_empty_list(self):
        """空输入 → 空列表。"""
        assert summarize_by_dimension([]) == []

    def test_single_analysis_returns_all_dimensions(self):
        """单章分析 → 返回所有 9 个维度。"""
        analysis = _make_analysis(suffix="")
        result = summarize_by_dimension([analysis])

        assert len(result) == 9
        for item in result:
            assert "dimension" in item
            assert "display_name" in item
            assert "is_primary" in item
            assert "summary" in item
            assert "score" in item
            # 验证中文显示名存在
            assert item["display_name"] in [v["display_name"] for v in DIMENSION_MAP.values()]

    def test_multi_chapter_aggregation(self):
        """多章分析 → 维度 summary 合并、score 取平均。"""
        ch1 = _make_analysis(sentence_score=0.8, suffix="【第一章】")
        ch2 = _make_analysis(sentence_score=0.9, suffix="【第二章】")

        result = summarize_by_dimension([ch1, ch2])

        # 查找 sentence_style 维度
        sentence = next(r for r in result if r["dimension"] == "sentence_style")
        # summary 应合并两章内容
        assert "【第一章】" in sentence["summary"]
        assert "【第二章】" in sentence["summary"]
        # score 应为 (0.8 + 0.9) / 2 = 0.85
        assert sentence["score"] == 0.85

    def test_partial_dimension_data(self):
        """某些维度缺失 → 仅返回有数据的维度。"""
        analysis = {
            "sentence_style": {"summary": "仅此维度", "score": 0.5},
            # 其他维度缺失
        }
        result = summarize_by_dimension([analysis])
        assert len(result) == 1
        assert result[0]["dimension"] == "sentence_style"

    def test_score_rounding(self):
        """分数保留 4 位小数。"""
        ch1 = _make_analysis(sentence_score=0.12345, suffix="")
        ch2 = _make_analysis(sentence_score=0.54321, suffix="")
        result = summarize_by_dimension([ch1, ch2])
        sentence = next(r for r in result if r["dimension"] == "sentence_style")
        # (0.12345 + 0.54321) / 2 = 0.33333 → round 4 = 0.3333
        assert sentence["score"] == 0.3333


# ============================================================
# generate_author_summary
# ============================================================


class TestGenerateAuthorSummary:
    def test_basic_structure(self):
        """返回结构包含 author/primary/secondary/total_chapters/average_scores。"""
        analyses = [_make_analysis(suffix="")]
        dim_summaries = summarize_by_dimension(analyses)
        result = generate_author_summary("测试作家", dim_summaries)

        assert result["author"] == "测试作家"
        assert "primary_summary" in result
        assert "secondary_summary" in result
        assert "total_chapters" in result
        assert "average_scores" in result

    def test_primary_secondary_grouping(self):
        """primary 5 个 + secondary 4 个维度。"""
        analyses = [_make_analysis(suffix="")]
        dim_summaries = summarize_by_dimension(analyses)
        result = generate_author_summary("测试作家", dim_summaries)

        assert len(result["primary_summary"]) == 5
        assert len(result["secondary_summary"]) == 4

        # primary 应包含 sentence_style 等
        assert "sentence_style" in result["primary_summary"]
        assert "narrative_pov" in result["primary_summary"]
        assert "word_texture" in result["secondary_summary"]
        assert "character_portrayal" in result["secondary_summary"]

    def test_total_chapters_estimation(self):
        """多章输入 → 正确估算章节数。"""
        ch1 = _make_analysis(suffix="-1")
        ch2 = _make_analysis(suffix="-2")
        ch3 = _make_analysis(suffix="-3")
        dim_summaries = summarize_by_dimension([ch1, ch2, ch3])
        result = generate_author_summary("测试作家", dim_summaries)
        assert result["total_chapters"] == 3

    def test_average_scores_present(self):
        """average_scores 包含所有维度的平均值。"""
        ch1 = _make_analysis(sentence_score=0.8, suffix="")
        ch2 = _make_analysis(sentence_score=0.6, suffix="")
        dim_summaries = summarize_by_dimension([ch1, ch2])
        result = generate_author_summary("测试作家", dim_summaries)

        assert "sentence_style" in result["average_scores"]
        # sentence_style = (0.8 + 0.6) / 2 = 0.7
        assert result["average_scores"]["sentence_style"] == 0.7


# ============================================================
# save_summaries_to_db
# ============================================================


class TestSaveSummariesToDb:
    def test_inserts_one_row_per_dimension(self):
        """每个维度写入一条记录到 style_summaries 表。"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            _create_db_with_schema(db_path)

            analyses = [_make_analysis(suffix="")]
            dim_summaries = summarize_by_dimension(analyses)
            # 注入 author 字段
            for s in dim_summaries:
                s["author"] = "鲁迅"
                s["work_title"] = "朝花夕拾"

            ids = save_summaries_to_db(dim_summaries, db_path)
            assert len(ids) == 9  # 9 个维度
            assert all(isinstance(i, int) and i > 0 for i in ids)

            # 验证数据
            conn = sqlite3.connect(db_path)
            rows = conn.execute("SELECT * FROM style_summaries").fetchall()
            conn.close()
            assert len(rows) == 9

            # 检查 author 字段
            authors = {r[1] for r in rows}
            assert authors == {"鲁迅"}

            # 检查 category 是否包含中文维度名
            categories = [r[4] for r in rows]
            assert "句式风格" in categories
            assert "人物刻画" in categories
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_keywords_and_examples_as_json(self):
        """keywords 和 examples 以 JSON 字符串存入。"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            _create_db_with_schema(db_path)

            analyses = [_make_analysis(suffix="")]
            dim_summaries = summarize_by_dimension(analyses)
            for s in dim_summaries:
                s["author"] = "测试"
                s["keywords"] = ["简洁", "有力"]
                s["examples"] = ["例句1", "例句2"]

            save_summaries_to_db(dim_summaries, db_path)

            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT keywords, examples FROM style_summaries LIMIT 1"
            ).fetchone()
            conn.close()

            keywords = json.loads(row[0])
            examples = json.loads(row[1])
            assert keywords == ["简洁", "有力"]
            assert examples == ["例句1", "例句2"]
        finally:
            Path(db_path).unlink(missing_ok=True)
