"""
Dashboard 数据库服务模块 —— 连接工厂、安全查询工具与 DAO 包装器。

将 app.py 中的 _get_db / _fetchall_safe / _get_db_path 重构为依赖注入形式。
服务层通过本模块统一管理数据库连接与 DAO 实例。
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from dashboard.core.config import get_db_path

T = TypeVar("T")


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """生成器：打开 index.db 连接，yield 后自动关闭。

    使用 WAL 模式 + sqlite3.Row 行工厂。
    在使用前需先调用 core.config.init_project_root()。
    """
    conn = sqlite3.connect(get_db_path(), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA mmap_size = 1073741824")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def fetchall_safe(
    conn: sqlite3.Connection, query: str, params: tuple = ()
) -> list[dict]:
    """执行只读查询；若目标表/列不存在，返回空列表。

    仅捕获 OperationalError 中的 "no such table" / "no such column"，
    其余数据库异常原样抛出（不封装 HTTP 错误）。

    Args:
        conn: 数据库连接。
        query: SQL 查询语句。
        params: 查询参数元组。

    Returns:
        list[dict]: 查询结果行列表。
    """
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as exc:
        exc_msg = str(exc).lower()
        if "no such table" in exc_msg or "no such column" in exc_msg:
            return []
        raise


def get_db_dependency():
    """FastAPI Depends 兼容的数据库连接生成器。

    使用 with get_db() 包装 context manager，使 FastAPI 能正确处理连接生命周期。
    用法：conn: sqlite3.Connection = Depends(get_db_dependency)
    """
    with get_db() as conn:
        yield conn


def get_dao(dao_class: type[T], db_path: str | Path) -> T:
    """从 data_modules.dao 获取 DAO 实例（带缓存）。

    透传给 data_modules.dao.get_dao()；需确保 .opencode/scripts/ 在 sys.path 上。

    Args:
        dao_class: DAO 类（如 EntityDAO, StateDAO）。
        db_path: 数据库路径。

    Returns:
        DAO 实例。
    """
    from data_modules.dao import get_dao as _get_dao_impl

    return _get_dao_impl(dao_class, db_path)
