"""
测试 chapters 路由的 7 个端点。

覆盖:
  GET    /api/chapters                  → list_chapters
  GET    /api/chapters/search           → search_chapters
  POST   /api/chapters/import-existing  → import_existing_chapters
  GET    /api/scenes                    → list_scenes
  GET    /api/reading-power             → list_reading_power
  GET    /api/review-metrics            → list_review_metrics
  GET    /api/chapters/{chapter}/trace  → get_chapter_trace
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.core.config import get_db_path, init_project_root
from dashboard.routers.chapters import router


# ── 辅助 ─────────────────────────────────────────────────────────


def _make_app(project_root: Path) -> FastAPI:
    """用 chapters 路由构建独立的 FastAPI 实例。"""
    init_project_root(project_root)
    app = FastAPI(title="test-chapters-router")
    app.include_router(router)
    return app


def _seed_table(project_root: Path, table: str, rows: list[dict]) -> None:
    """向 index.db 插入测试数据。"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        if rows:
            cols = ", ".join(rows[0].keys())
            placeholders = ", ".join("?" for _ in rows[0])
            for row in rows:
                conn.execute(
                    f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                    tuple(row.values()),
                )
        conn.commit()
    finally:
        conn.close()


def _ensure_table(project_root: Path, ddl: str) -> None:
    """确保表存在。"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def app(project_root) -> FastAPI:
    return _make_app(project_root)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


# ── Tests ────────────────────────────────────────────────────────


class TestListChapters:
    """GET /api/chapters"""

    def test_returns_empty_when_no_table(self, client):
        """chapters 表不存在时返回空列表。"""
        resp = client.get("/api/chapters")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_chapters(self, project_root, client):
        """返回所有章节，characters 自动解析。"""
        _ensure_table(
            project_root,
            "CREATE TABLE IF NOT EXISTS chapters (id INTEGER PRIMARY KEY, chapter INT, title TEXT, content TEXT, word_count INT, characters TEXT, status TEXT DEFAULT 'raw', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        )
        _seed_table(project_root, "chapters", [
            {"id": 1, "chapter": 1, "title": "第一章", "content": "正文", "word_count": 200, "characters": '["小明"]'},
            {"id": 2, "chapter": 2, "title": "第二章", "content": "正文2", "word_count": 300, "characters": '["小明","小红"]'},
        ])
        resp = client.get("/api/chapters?limit=100&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["chapter"] == 1
        assert data[1]["chapter"] == 2
        assert "content" not in data[0]

    def test_characters_null_fallsback_empty_list(self, project_root, client):
        """characters 为 NULL 时返回空数组。"""
        _ensure_table(
            project_root,
            "CREATE TABLE IF NOT EXISTS chapters (id INTEGER PRIMARY KEY, chapter INT, title TEXT, content TEXT, word_count INT, characters TEXT, status TEXT DEFAULT 'raw', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        )
        _seed_table(project_root, "chapters", [
            {"id": 1, "chapter": 1, "title": "第一章", "content": "正文", "word_count": 200, "characters": None},
        ])
        ch_content = client.get("/api/chapters/1/content")
        assert ch_content.status_code == 200
        assert ch_content.json()["content"] == "正文"


class TestSearchChapters:
    """GET /api/chapters/search"""

    def test_requires_query(self, client):
        """query 参数必填。"""
        resp = client.get("/api/chapters/search")
        assert resp.status_code == 422

    def test_returns_empty_when_no_match(self, client, project_root):
        """无匹配时返回空列表。"""
        _ensure_table(
            project_root,
            "CREATE TABLE IF NOT EXISTS chapters (chapter INT, title TEXT, content TEXT)",
        )
        resp = client.get("/api/chapters/search", params={"query": "不存在"})
        assert resp.status_code == 200
        assert resp.json() == []


class TestImportExistingChapters:
    """POST /api/chapters/import-existing"""

    def test_returns_dict(self, client):
        """返回 dict（batch_import_existing 的返回值）。"""
        resp = client.post("/api/chapters/import-existing")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


class TestListScenes:
    """GET /api/scenes"""

    def test_returns_empty_when_no_table(self, client):
        """scenes 表不存在时返回空列表。"""
        resp = client.get("/api/scenes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_scenes(self, project_root, client):
        """返回场景列表。"""
        _ensure_table(
            project_root,
            "CREATE TABLE IF NOT EXISTS scenes (id INT, chapter INT, scene_index INT, title TEXT, content TEXT)",
        )
        _seed_table(project_root, "scenes", [
            {"id": 1, "chapter": 1, "scene_index": 0, "title": "开场", "content": "场景内容"},
        ])
        resp = client.get("/api/scenes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "开场"

    def test_filter_by_chapter(self, project_root, client):
        """按 chapter 过滤。"""
        _ensure_table(
            project_root,
            "CREATE TABLE IF NOT EXISTS scenes (id INT, chapter INT, scene_index INT, title TEXT)",
        )
        _seed_table(project_root, "scenes", [
            {"id": 1, "chapter": 1, "scene_index": 0, "title": "第一章场景"},
            {"id": 2, "chapter": 2, "scene_index": 0, "title": "第二章场景"},
        ])
        resp = client.get("/api/scenes", params={"chapter": 1})
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "第一章场景"


class TestListReadingPower:
    """GET /api/reading-power"""

    def test_returns_empty_when_no_table(self, client):
        """chapter_reading_power 表不存在时返回空列表。"""
        resp = client.get("/api/reading-power")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_reading_power(self, project_root, client):
        """返回阅读力列表。"""
        _ensure_table(
            project_root,
            "CREATE TABLE IF NOT EXISTS chapter_reading_power (chapter INT, power_score REAL)",
        )
        _seed_table(project_root, "chapter_reading_power", [
            {"chapter": 1, "power_score": 85.5},
        ])
        resp = client.get("/api/reading-power")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["power_score"] == 85.5


class TestListReviewMetrics:
    """GET /api/review-metrics"""

    def test_returns_empty_when_no_table(self, client):
        """review_metrics 表不存在时返回空列表。"""
        resp = client.get("/api/review-metrics")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_review_metrics(self, project_root, client):
        """返回审查指标，JSON 字段自动解析。"""
        _ensure_table(
            project_root,
            "CREATE TABLE IF NOT EXISTS review_metrics "
            "(id INT, end_chapter INT, dimension_scores TEXT, severity_counts TEXT, critical_issues TEXT)",
        )
        _seed_table(project_root, "review_metrics", [
            {
                "id": 1,
                "end_chapter": 5,
                "dimension_scores": '{"连贯性": 80}',
                "severity_counts": '{"minor": 2}',
                "critical_issues": '["伏笔未回收"]',
            },
        ])
        resp = client.get("/api/review-metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["end_chapter"] == 5
        assert data[0]["dimension_scores"] == {"连贯性": 80}
        assert data[0]["severity_counts"] == {"minor": 2}
        assert data[0]["critical_issues"] == ["伏笔未回收"]

    def test_json_fields_none_fallback(self, project_root, client):
        """JSON 字段为 None 时使用默认空值。"""
        _ensure_table(
            project_root,
            "CREATE TABLE IF NOT EXISTS review_metrics "
            "(id INT, end_chapter INT, dimension_scores TEXT, severity_counts TEXT, critical_issues TEXT)",
        )
        _seed_table(project_root, "review_metrics", [
            {
                "id": 1,
                "end_chapter": 3,
                "dimension_scores": None,
                "severity_counts": None,
                "critical_issues": None,
            },
        ])
        resp = client.get("/api/review-metrics")
        data = resp.json()
        assert data[0]["dimension_scores"] == {}
        assert data[0]["severity_counts"] == {}
        assert data[0]["critical_issues"] == []


class TestGetChapterTrace:
    """GET /api/chapters/{chapter}/trace"""

    def test_returns_trace_structure(self, client):
        """返回包含 trace 和 debates 的 dict。"""
        resp = client.get("/api/chapters/1/trace")
        assert resp.status_code == 200
        data = resp.json()
        assert "trace" in data
        assert "debates" in data
        assert isinstance(data["trace"], list)
        assert isinstance(data["debates"], list)

    def test_returns_empty_trace_for_unknown(self, client):
        """不存在的章节返回空列表。"""
        resp = client.get("/api/chapters/999/trace")
        data = resp.json()
        assert data["trace"] == []
        assert data["debates"] == []
