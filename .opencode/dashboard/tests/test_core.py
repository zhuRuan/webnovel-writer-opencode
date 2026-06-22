"""测试 core/config.py 与 core/database.py。"""

import sqlite3
from pathlib import Path

import pytest

from dashboard.core.config import (
    get_db_path,
    get_project_root,
    get_story_system_dir,
    get_webnovel_dir,
    init_project_root,
)
from dashboard.core.database import fetchall_safe, get_db


class TestConfig:
    """core/config.py 路径函数测试。"""

    def test_get_project_root_raises_before_init(self) -> None:
        with pytest.raises(RuntimeError, match="未配置"):
            get_project_root()

    def test_config_returns_paths(self, project_root: Path) -> None:
        init_project_root(project_root)

        assert get_project_root() == project_root.resolve()
        assert get_webnovel_dir() == project_root / ".webnovel"
        assert get_story_system_dir() == project_root / ".story-system"
        assert get_db_path() == str(project_root / ".webnovel" / "index.db")


class TestDatabase:
    """core/database.py 数据库函数测试。"""

    def test_get_db_returns_connection(self, project_root: Path) -> None:
        init_project_root(project_root)

        with get_db() as conn:
            assert isinstance(conn, sqlite3.Connection)
            # 验证连接可用
            row = conn.execute("SELECT 1 AS v").fetchone()
            assert row["v"] == 1

    def test_fetchall_safe_no_table_returns_empty(self, project_root: Path) -> None:
        init_project_root(project_root)

        with get_db() as conn:
            result = fetchall_safe(conn, "SELECT * FROM nonexistent_table")
            assert result == []
