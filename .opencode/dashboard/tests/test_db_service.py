"""测试 services/db.py —— 数据库连接工厂、安全查询与 DAO 包装器。"""

import sqlite3
import sys
from pathlib import Path

import pytest

from dashboard.core.config import get_db_path, init_project_root
from dashboard.services.db import fetchall_safe, get_dao, get_db

# 确保 .opencode/scripts/ 在 sys.path 上，以供 data_modules.dao 导入
_scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))


class TestDbService:
    """services/db.py 单元测试。"""

    # ── get_db() ──────────────────────────────────────────────

    def test_get_db_returns_connection(self, project_root: Path) -> None:
        """验证 get_db() 生成器返回可用的 sqlite3.Connection。"""
        init_project_root(project_root)

        with get_db() as conn:
            assert isinstance(conn, sqlite3.Connection)
            row = conn.execute("SELECT 1 AS v").fetchone()
            assert row["v"] == 1

    # ── fetchall_safe() ───────────────────────────────────────

    def test_fetchall_safe_no_table_returns_empty(
        self, project_root: Path
    ) -> None:
        """验证不存在的表返回空列表而非抛异常。"""
        init_project_root(project_root)

        with get_db() as conn:
            result = fetchall_safe(conn, "SELECT * FROM nonexistent_table")
            assert result == []

    def test_fetchall_safe_with_data(self, project_root: Path) -> None:
        """验证正常查询返回正确的 dict 列表。"""
        init_project_root(project_root)

        with get_db() as conn:
            conn.execute("CREATE TABLE test_table (id INT, name TEXT)")
            conn.execute(
                "INSERT INTO test_table VALUES (1, 'hello'), (2, 'world')"
            )
            conn.commit()

            result = fetchall_safe(
                conn, "SELECT * FROM test_table ORDER BY id"
            )
            assert result == [
                {"id": 1, "name": "hello"},
                {"id": 2, "name": "world"},
            ]

    # ── get_dao() ─────────────────────────────────────────────

    def test_get_dao_returns_instance(self, project_root: Path) -> None:
        """验证 get_dao() 返回正确的 DAO 实例。"""
        init_project_root(project_root)
        from data_modules.dao.base import BaseDAO

        dao = get_dao(BaseDAO, get_db_path())
        assert isinstance(dao, BaseDAO)
        assert dao.db_path == get_db_path()
