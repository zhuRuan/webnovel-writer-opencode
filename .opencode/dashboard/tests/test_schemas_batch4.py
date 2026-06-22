"""Batch 4 — schemas/files.py, context.py, alerts.py, workflow.py"""

import pytest
from pydantic import ValidationError

from dashboard.schemas.files import FileReadQuery, FileWriteRequest, FileNormalizeRequest, FileTreeResponse
from dashboard.schemas.context import ContextHealthResponse, ContextBudgetResponse, ContextHistoryFilter
from dashboard.schemas.alerts import AlertResponse, AlertsListResponse
from dashboard.schemas.workflow import WorkflowStatusResponse


# ── files.py ──────────────────────────────────────────────────────────

class TestFileReadQuery:
    def test_valid_path(self):
        m = FileReadQuery(path="正文/ch001.md")
        assert m.path == "正文/ch001.md"

    def test_empty_path_raises(self):
        with pytest.raises(ValidationError):
            FileReadQuery(path="")

    def test_whitespace_path_passes(self):
        """min_length=1 只检查长度，空白字符串本身也算非空。"""
        m = FileReadQuery(path="   ")
        assert m.path == "   "


class TestFileWriteRequest:
    def test_both_fields(self):
        m = FileWriteRequest(path="a.txt", content="hello")
        assert m.path == "a.txt"
        assert m.content == "hello"

    def test_missing_path_raises(self):
        with pytest.raises(ValidationError):
            FileWriteRequest(content="hello")

    def test_missing_content_raises(self):
        with pytest.raises(ValidationError):
            FileWriteRequest(path="a.txt")

    def test_empty_path_allowed(self):
        """FileWriteRequest 的 path 无 min_length，允许空字符串。"""
        m = FileWriteRequest(path="", content="x")
        assert m.path == ""


class TestFileNormalizeRequest:
    def test_valid_path(self):
        m = FileNormalizeRequest(path="正文/ch001.md")
        assert m.path == "正文/ch001.md"

    def test_missing_path_raises(self):
        with pytest.raises(ValidationError):
            FileNormalizeRequest()

    def test_empty_path_allowed(self):
        """FileNormalizeRequest 的 path 无 min_length，允许空字符串。"""
        m = FileNormalizeRequest(path="")
        assert m.path == ""


class TestFileTreeResponse:
    def test_valid_structure(self):
        data = {
            "正文": [{"name": "ch001.md", "type": "file", "path": "正文/ch001.md", "size": 100}],
            "大纲": [],
            "设定集": [],
        }
        m = FileTreeResponse(data)
        assert "正文" in m.root
        assert m.root["正文"][0]["name"] == "ch001.md"

    def test_empty_tree(self):
        m = FileTreeResponse({})
        assert m.root == {}


# ── context.py ────────────────────────────────────────────────────────

class TestContextHealthResponse:
    def test_full_data(self):
        data = {
            "chapter": 3,
            "stage": "writing",
            "template": "default",
            "included": ["core", "scene"],
            "excluded": ["user_prompts"],
            "critical_excluded": ["user_prompts"],
            "section_tokens": {"core": 500, "scene": 300},
            "total_tokens": 800,
            "health_score": 80,
            "weights_used": {"core": 1.0},
            "ranker_enabled": True,
        }
        m = ContextHealthResponse(**data)
        assert m.chapter == 3
        assert m.health_score == 80
        assert m.ranker_enabled is True

    def test_health_score_validation(self):
        with pytest.raises(ValidationError):
            ContextHealthResponse(
                chapter=1, stage="s", template="t",
                included=[], excluded=[], critical_excluded=[],
                section_tokens={}, total_tokens=0,
                health_score=150,  # 超出 0-100
                weights_used={}, ranker_enabled=False,
            )


class TestContextBudgetResponse:
    def test_valid_dict(self):
        m = ContextBudgetResponse({"key": "value", "nested": {"a": 1}})
        assert m.root["key"] == "value"
        assert m.root["nested"]["a"] == 1

    def test_empty_dict(self):
        m = ContextBudgetResponse({})
        assert m.root == {}


class TestContextHistoryFilter:
    def test_default_limit(self):
        f = ContextHistoryFilter()
        assert f.limit == 20

    def test_custom_limit(self):
        f = ContextHistoryFilter(limit=5)
        assert f.limit == 5

    def test_zero_limit_raises(self):
        with pytest.raises(ValidationError):
            ContextHistoryFilter(limit=0)

    def test_large_limit(self):
        f = ContextHistoryFilter(limit=100)
        assert f.limit == 100

    def test_too_large_limit_raises(self):
        with pytest.raises(ValidationError):
            ContextHistoryFilter(limit=101)


# ── alerts.py ─────────────────────────────────────────────────────────

class TestAlertResponse:
    def test_minimal(self):
        a = AlertResponse(type="info", severity="info", detail="test")
        assert a.type == "info"
        assert a.chapters is None
        assert a.due_chapter is None

    def test_with_chapters(self):
        a = AlertResponse(
            type="score_decline", severity="warning",
            detail="连续下降", chapters=[{"chapter": 1, "score": 80}],
        )
        assert len(a.chapters) == 1

    def test_with_due_chapter(self):
        a = AlertResponse(
            type="debt_overdue", severity="critical",
            detail="伏笔逾期", due_chapter=10,
        )
        assert a.due_chapter == 10


class TestAlertsListResponse:
    def test_empty(self):
        r = AlertsListResponse(alerts=[], updated_at="2025-01-01T00:00:00")
        assert r.alerts == []
        assert r.updated_at == "2025-01-01T00:00:00"

    def test_with_alerts(self):
        r = AlertsListResponse(
            alerts=[
                AlertResponse(type="info", severity="info", detail="x"),
                AlertResponse(type="warning", severity="warning", detail="y"),
            ],
            updated_at="2025-06-18T12:00:00Z",
        )
        assert len(r.alerts) == 2


# ── workflow.py ───────────────────────────────────────────────────────

class TestWorkflowStatusResponse:
    def test_valid_dict(self):
        m = WorkflowStatusResponse({"progress": 0.5, "chapters": []})
        assert m.root["progress"] == 0.5

    def test_empty_dict(self):
        m = WorkflowStatusResponse({})
        assert m.root == {}
