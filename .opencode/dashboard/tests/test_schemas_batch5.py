"""测试 schemas 第 5 批：upload / analysis / collect。"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# 确保 .opencode/ 在 sys.path 上
_opencode_dir = Path(__file__).resolve().parents[2]
if str(_opencode_dir) not in sys.path:
    sys.path.insert(0, str(_opencode_dir))

from dashboard.schemas.analysis import AnalysisResult, DimensionResult
from dashboard.schemas.collect import (
    ActiveTasksResponse,
    AuthorListResponse,
    ChapterFilter,
    ChapterListResponse,
    ReportListResponse,
    SummaryFilter,
    SummaryListResponse,
)
from dashboard.schemas.upload import UploadProgressResponse, UploadResponse


# ============================================================
# Upload schemas
# ============================================================


class TestUploadResponse:
    """UploadResponse 字段完整性与校验。"""

    def test_full_fields(self):
        """正常实例化应包含所有字段。"""
        obj = UploadResponse(
            task_id="t_001",
            author="金庸",
            work_title="射雕英雄传",
            chapters_detected=5,
            status="done",
        )
        assert obj.task_id == "t_001"
        assert obj.author == "金庸"
        assert obj.work_title == "射雕英雄传"
        assert obj.chapters_detected == 5
        assert obj.status == "done"

    @pytest.mark.parametrize("invalid_status", ["pending", "error", "running", ""])
    def test_invalid_status(self, invalid_status):
        """status 必须是合法枚举值。"""
        with pytest.raises(ValidationError):
            UploadResponse(
                task_id="t_001",
                author="金庸",
                work_title="射雕",
                chapters_detected=1,
                status=invalid_status,
            )

    @pytest.mark.parametrize("valid_status", ["uploading", "splitting", "analyzing", "summarizing", "done", "failed"])
    def test_valid_status_values(self, valid_status):
        """所有 6 种合法 status 都能通过校验。"""
        obj = UploadResponse(
            task_id="t_001",
            author="金庸",
            work_title="射雕",
            chapters_detected=1,
            status=valid_status,
        )
        assert obj.status == valid_status

    def test_chapters_detected_negative(self):
        """chapters_detected 不能为负数。"""
        with pytest.raises(ValidationError):
            UploadResponse(
                task_id="t_001",
                author="金庸",
                work_title="射雕",
                chapters_detected=-1,
                status="done",
            )

    def test_chapters_detected_zero(self):
        """chapters_detected 可以为 0。"""
        obj = UploadResponse(
            task_id="t_001",
            author="金庸",
            work_title="射雕",
            chapters_detected=0,
            status="done",
        )
        assert obj.chapters_detected == 0


class TestUploadProgressResponse:
    """UploadProgressResponse 字段完整性与校验。"""

    def test_full_fields(self):
        """正常实例化应包含所有字段。"""
        obj = UploadProgressResponse(
            task_id="t_001",
            status="analyzing",
            current_step=2,
            total_steps=5,
            message="正在分析第 3/40 章",
        )
        assert obj.task_id == "t_001"
        assert obj.status == "analyzing"
        assert obj.current_step == 2
        assert obj.total_steps == 5
        assert obj.message == "正在分析第 3/40 章"

    def test_message_default(self):
        """message 默认值为空字符串。"""
        obj = UploadProgressResponse(
            task_id="t_001",
            status="uploading",
            current_step=0,
            total_steps=5,
        )
        assert obj.message == ""

    @pytest.mark.parametrize("invalid_status", ["pending", "error", ""])
    def test_invalid_status(self, invalid_status):
        """status 必须是合法枚举值。"""
        with pytest.raises(ValidationError):
            UploadProgressResponse(
                task_id="t_001",
                status=invalid_status,
                current_step=0,
                total_steps=5,
            )

    def test_current_step_negative(self):
        """current_step 不能为负数。"""
        with pytest.raises(ValidationError):
            UploadProgressResponse(
                task_id="t_001",
                status="uploading",
                current_step=-1,
                total_steps=5,
            )

    def test_total_steps_must_be_positive(self):
        """total_steps 必须 >= 1。"""
        with pytest.raises(ValidationError):
            UploadProgressResponse(
                task_id="t_001",
                status="uploading",
                current_step=0,
                total_steps=0,
            )


# ============================================================
# Analysis schemas
# ============================================================


class TestDimensionResult:
    """DimensionResult 字段校验。"""

    def test_minimal(self):
        """最小实例化。"""
        obj = DimensionResult(summary="评论文本", score=0.5)
        assert obj.summary == "评论文本"
        assert obj.score == 0.5

    def test_score_below_zero(self):
        """score 不能小于 0。"""
        with pytest.raises(ValidationError):
            DimensionResult(summary="x", score=-0.01)

    def test_score_above_one(self):
        """score 不能大于 1。"""
        with pytest.raises(ValidationError):
            DimensionResult(summary="x", score=1.01)

    def test_score_zero(self):
        """score 可以为 0。"""
        obj = DimensionResult(summary="x", score=0.0)
        assert obj.score == 0.0

    def test_score_one(self):
        """score 可以为 1。"""
        obj = DimensionResult(summary="x", score=1.0)
        assert obj.score == 1.0


class TestAnalysisResult:
    """AnalysisResult —— 9 维度完整性。"""

    def make_dim(self, summary: str = "dim", score: float = 0.5) -> DimensionResult:
        return DimensionResult(summary=summary, score=score)

    def test_nine_dimensions_present(self):
        """实例化后 9 维度均不缺失。"""
        obj = AnalysisResult(
            sentence_style=self.make_dim("句式"),
            narrative_pov=self.make_dim("视角"),
            pacing_control=self.make_dim("节奏"),
            emotional_tension=self.make_dim("情感"),
            dialogue_style=self.make_dim("对白"),
            word_texture=self.make_dim("词汇"),
            rhetoric_devices=self.make_dim("修辞"),
            description_preference=self.make_dim("描写"),
            character_portrayal=self.make_dim("人物"),
        )
        all_dims = obj.all_dimensions
        assert len(all_dims) == 9, f"应为 9 维度，实际 {len(all_dims)}"

        expected_keys = {
            "sentence_style",
            "narrative_pov",
            "pacing_control",
            "emotional_tension",
            "dialogue_style",
            "word_texture",
            "rhetoric_devices",
            "description_preference",
            "character_portrayal",
        }
        assert set(all_dims.keys()) == expected_keys, f"维度键不匹配"

    def test_primary_dimensions_count(self):
        """primary_dimensions 应返回 5 个。"""
        obj = AnalysisResult(**{k: self.make_dim() for k in [
            "sentence_style", "narrative_pov", "pacing_control", "emotional_tension",
            "dialogue_style", "word_texture", "rhetoric_devices",
            "description_preference", "character_portrayal",
        ]})
        assert len(obj.primary_dimensions) == 5

    def test_secondary_dimensions_count(self):
        """secondary_dimensions 应返回 4 个。"""
        obj = AnalysisResult(**{k: self.make_dim() for k in [
            "sentence_style", "narrative_pov", "pacing_control", "emotional_tension",
            "dialogue_style", "word_texture", "rhetoric_devices",
            "description_preference", "character_portrayal",
        ]})
        assert len(obj.secondary_dimensions) == 4

    def test_average_score(self):
        """average_score 应返回 9 维度平均分。"""
        obj = AnalysisResult(
            sentence_style=self.make_dim(score=1.0),
            narrative_pov=self.make_dim(score=0.8),
            pacing_control=self.make_dim(score=0.6),
            emotional_tension=self.make_dim(score=0.4),
            dialogue_style=self.make_dim(score=0.2),
            word_texture=self.make_dim(score=0.0),
            rhetoric_devices=self.make_dim(score=1.0),
            description_preference=self.make_dim(score=0.5),
            character_portrayal=self.make_dim(score=0.5),
        )
        # (1.0+0.8+0.6+0.4+0.2+0.0+1.0+0.5+0.5) / 9 = 5.0/9 ≈ 0.5556
        assert abs(obj.average_score - 5.0 / 9) < 1e-6

    def test_serializes_to_json(self):
        """AnalysisResult 可 JSON 序列化（无复杂类型）。"""
        import json

        obj = AnalysisResult(**{k: self.make_dim() for k in [
            "sentence_style", "narrative_pov", "pacing_control", "emotional_tension",
            "dialogue_style", "word_texture", "rhetoric_devices",
            "description_preference", "character_portrayal",
        ]})
        data = json.loads(obj.model_dump_json())
        assert "sentence_style" in data
        assert "word_texture" in data
        assert data["sentence_style"]["score"] == 0.5
        assert len(data) == 9  # 9 个顶级字段


# ============================================================
# Collect schemas
# ============================================================


class TestAuthorListResponse:
    def test_authors_list(self):
        obj = AuthorListResponse(authors=["金庸", "古龙"])
        assert obj.authors == ["金庸", "古龙"]

    def test_empty(self):
        obj = AuthorListResponse(authors=[])
        assert obj.authors == []


class TestSummaryFilter:
    def test_all_none(self):
        obj = SummaryFilter()
        assert obj.author is None
        assert obj.category is None

    def test_with_values(self):
        obj = SummaryFilter(author="金庸", category="武侠")
        assert obj.author == "金庸"
        assert obj.category == "武侠"


class TestSummaryListResponse:
    def test_summaries_list(self):
        data = [{"author": "金庸", "category": "武侠", "content": "..."}]
        obj = SummaryListResponse(summaries=data)
        assert obj.summaries == data

    def test_empty(self):
        obj = SummaryListResponse(summaries=[])
        assert obj.summaries == []


class TestChapterFilter:
    def test_all_none(self):
        obj = ChapterFilter()
        assert obj.author is None
        assert obj.work_title is None

    def test_with_values(self):
        obj = ChapterFilter(author="古龙", work_title="绝代双骄")
        assert obj.author == "古龙"
        assert obj.work_title == "绝代双骄"


class TestChapterListResponse:
    def test_chapters_list(self):
        data = [{"author": "古龙", "title": "第一章"}]
        obj = ChapterListResponse(chapters=data)
        assert obj.chapters == data

    def test_empty(self):
        obj = ChapterListResponse(chapters=[])
        assert obj.chapters == []


class TestReportListResponse:
    def test_reports_list(self):
        data = [{"task_id": "r1", "author": "金庸"}]
        obj = ReportListResponse(reports=data)
        assert obj.reports == data


class TestActiveTasksResponse:
    def test_tasks_list(self):
        data = [{"task_id": "t1", "status": "running"}]
        obj = ActiveTasksResponse(tasks=data)
        assert obj.tasks == data
