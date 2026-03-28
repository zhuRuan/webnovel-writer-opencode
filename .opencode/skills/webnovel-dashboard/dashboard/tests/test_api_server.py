#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API 服务器单元测试
"""

import json
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api_server import (
    APIHandler,
    ProjectInfo,
    ProgressInfo,
    HealthInfo,
    ForeshadowingInfo,
    OverviewResponse,
)


class TestOverviewResponse:
    """测试 OverviewResponse 数据类"""

    def test_to_dict_returns_valid_json(self):
        """验证 to_dict 返回有效的 JSON 结构"""
        project = ProjectInfo(
            title="测试小说",
            genre="玄幻",
            target_words=2000000,
            target_chapters=1000,
        )
        progress = ProgressInfo(
            current_chapter=100,
            total_words=300000,
            avg_words_per_chapter=3000.0,
            percent=15.0,
        )
        health = HealthInfo(
            score=90,
            issues=[],
            last_check="2026-03-28 10:00:00",
        )
        foreshadowing = ForeshadowingInfo(
            total=10,
            unresolved=3,
            overdue=1,
            recent=[],
        )

        response = OverviewResponse(
            project=project,
            progress=progress,
            health=health,
            foreshadowing=foreshadowing,
            updated_at="2026-03-28T10:00:00",
        )

        result = response.to_dict()

        assert "project" in result
        assert result["project"]["title"] == "测试小说"
        assert result["progress"]["current_chapter"] == 100
        assert result["health"]["score"] == 90
        assert result["foreshadowing"]["unresolved"] == 3

        json_str = json.dumps(result, ensure_ascii=False)
        assert json_str is not None


class TestAPIHandler:
    """测试 APIHandler 类"""

    def test_handle_overview_with_missing_project(self):
        """验证项目未初始化时的错误处理"""
        from api_server import PROJECT_ROOT
        global PROJECT_ROOT
        PROJECT_ROOT_backup = PROJECT_ROOT
        PROJECT_ROOT = None

        try:
            class MockRequest:
                wfile = MagicMock()

            handler = APIHandler.__new__(APIHandler)
            handler.wfile = MagicMock()
            handler.send_json = MagicMock()

            handler.handle_overview()

            handler.send_json.assert_called_once()
            call_args = handler.send_json.call_args
            assert call_args[0][1] == 500

        finally:
            PROJECT_ROOT = PROJECT_ROOT_backup

    def test_handle_overview_with_missing_state_file(self):
        """验证 state.json 不存在时的错误处理"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            from api_server import PROJECT_ROOT
            global PROJECT_ROOT
            PROJECT_ROOT_backup = PROJECT_ROOT
            PROJECT_ROOT = project_root

            try:
                class MockRequest:
                    wfile = MagicMock()

                handler = APIHandler.__new__(APIHandler)
                handler.wfile = MagicMock()
                handler.send_json = MagicMock()

                handler.handle_overview()

                handler.send_json.assert_called_once()
                call_args = handler.send_json.call_args
                assert call_args[0][1] == 500

            finally:
                PROJECT_ROOT = PROJECT_ROOT_backup

    @patch('api_server.PROJECT_ROOT', new=None)
    def test_handle_overview_with_valid_state(self):
        """验证有效 state.json 的处理"""
        import api_server as api_module

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            webnovel_dir = project_root / ".webnovel"
            webnovel_dir.mkdir(parents=True)

            state = {
                "progress": {
                    "current_chapter": 100,
                    "total_words": 300000,
                },
                "project_info": {
                    "title": "测试小说",
                    "genre": "玄幻",
                    "target_words": 1000000,
                    "target_chapters": 500,
                },
                "plot_threads": {
                    "foreshadowing": [
                        {
                            "content": "测试伏笔1",
                            "status": "未回收",
                            "planted_chapter": 10,
                        },
                        {
                            "content": "测试伏笔2",
                            "status": "已回收",
                            "planted_chapter": 20,
                        },
                    ]
                },
            }

            (webnovel_dir / "state.json").write_text(
                json.dumps(state, ensure_ascii=False),
                encoding="utf-8",
            )

            api_module.PROJECT_ROOT = project_root

            try:
                class MockRequest:
                    wfile = MagicMock()

                handler = APIHandler.__new__(APIHandler)
                handler.wfile = MagicMock()
                handler.send_json = MagicMock()

                handler.handle_overview()

                handler.send_json.assert_called_once()
                call_args = handler.send_json.call_args
                result = call_args[0][0]

                assert result["project"]["title"] == "测试小说"
                assert result["progress"]["current_chapter"] == 100
                assert result["health"]["score"] >= 0
                assert result["foreshadowing"]["unresolved"] == 1

            finally:
                api_module.PROJECT_ROOT = None


class TestDataclasses:
    """测试 dataclass 定义"""

    def test_project_info_fields(self):
        """验证 ProjectInfo 字段"""
        p = ProjectInfo(title="x", genre="y", target_words=100, target_chapters=10)
        assert p.title == "x"
        assert p.genre == "y"
        assert p.target_words == 100
        assert p.target_chapters == 10

    def test_progress_info_fields(self):
        """验证 ProgressInfo 字段"""
        p = ProgressInfo(current_chapter=50, total_words=100000, avg_words_per_chapter=2000.0, percent=10.0)
        assert p.current_chapter == 50
        assert p.total_words == 100000

    def test_health_info_fields(self):
        """验证 HealthInfo 字段"""
        h = HealthInfo(score=80, issues=["issue1"], last_check="2026-01-01")
        assert h.score == 80
        assert len(h.issues) == 1

    def test_foreshadowing_info_fields(self):
        """验证 ForeshadowingInfo 字段"""
        f = ForeshadowingInfo(total=5, unresolved=2, overdue=1, recent=[])
        assert f.total == 5
        assert f.unresolved == 2
