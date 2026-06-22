"""
测试 project 路由的 4 个 GET 端点。

覆盖:
  GET /api/project/info          → 200 (state.json 只读)
  GET /api/story-runtime/health  → 200 (运行时健康)
  GET /api/env-status            → 200 (环境状态)
  GET /api/env-status/probe      → 200 (全面检查)
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.core.config import init_project_root
from dashboard.routers.project import router


# ── 辅助 ─────────────────────────────────────────────────────────


def _make_app(project_root: Path) -> FastAPI:
    """用 project 路由构建独立的 FastAPI 实例。"""
    init_project_root(project_root)
    app = FastAPI(title="test-project-router")
    app.include_router(router)
    return app


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def app(project_root) -> FastAPI:
    """返回配置好的 FastAPI 实例。"""
    return _make_app(project_root)


@pytest.fixture
def client(app) -> TestClient:
    """返回 TestClient。"""
    return TestClient(app)


# ── Tests ────────────────────────────────────────────────────────


class TestProjectInfo:
    """GET /api/project/info"""

    def test_returns_state_json(self, client):
        """返回 state.json 内容。"""
        resp = client.get("/api/project/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_info"]["title"] == "test"

    def test_404_when_missing_state(self, project_root, client):
        """state.json 不存在时返回 404。"""
        state_path = project_root / ".webnovel" / "state.json"
        state_path.unlink()
        resp = client.get("/api/project/info")
        assert resp.status_code == 404
        assert "不存在" in resp.text


class TestStoryRuntimeHealth:
    """GET /api/story-runtime/health"""

    def test_returns_health_report(self, client):
        """委托 data_modules 构建健康报告。"""
        resp = client.get("/api/story-runtime/health")
        assert resp.status_code == 200
        data = resp.json()
        # 健康报告含基础字段
        assert "chapter" in data
        assert "mainline_ready" in data
        assert "fallback_sources" in data
        assert "latest_commit_status" in data


class TestEnvStatus:
    """GET /api/env-status"""

    def test_returns_env_status(self, client):
        """返回环境状态结构。"""
        resp = client.get("/api/env-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "embed" in data
        assert "rerank" in data
        assert "vector_db" in data
        assert "rag_mode" in data
        assert "api_key_present" in data["embed"]

    def test_embed_api_key_default_false(self, client):
        """未配置 .env 时 embed api_key_present 为 false。"""
        resp = client.get("/api/env-status")
        data = resp.json()
        assert data["embed"]["api_key_present"] is False
        assert data["rerank"]["api_key_present"] is False


class TestEnvStatusProbe:
    """GET /api/env-status/probe"""

    def test_returns_probe_structure(self, client):
        """返回全面健康检查结构。"""
        resp = client.get("/api/env-status/probe")
        assert resp.status_code == 200
        data = resp.json()
        assert "ok" in data
        assert "rag_mode" in data
        assert "checks" in data
        assert "checked_at" in data
        assert isinstance(data["checks"], list)
        # 4 项检查
        assert len(data["checks"]) == 4
        names = {c["name"] for c in data["checks"]}
        assert names == {"embed_api_key", "rerank_api_key", "vector_db", "story_runtime"}

    def test_ok_false_when_checks_fail(self, client):
        """环境未配置时 ok 为 false。"""
        resp = client.get("/api/env-status/probe")
        data = resp.json()
        assert data["ok"] is False
        assert data["rag_mode"] == "bm25_only"
