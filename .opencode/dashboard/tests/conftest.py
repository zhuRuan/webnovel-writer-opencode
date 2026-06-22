"""Dashboard 测试依赖 —— project_root 与 test_app fixture。"""

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 确保 .opencode/ 在 sys.path 上，使 dashboard 包可被导入
# app.py 内部使用相对导入（from .path_guard import ...），必须以包成员方式导入
_opencode_dir = Path(__file__).resolve().parents[2]
if str(_opencode_dir) not in sys.path:
    sys.path.insert(0, str(_opencode_dir))

from dashboard.app import create_app  # noqa: E402
from dashboard.core.config import init_project_root  # noqa: E402


@pytest.fixture
def project_root():
    """创建临时项目根目录，包含 .webnovel/state.json 和 .webnovel/index.db。"""
    tmpdir = Path(tempfile.mkdtemp())
    webnovel_dir = tmpdir / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)

    # 写入 state.json
    (webnovel_dir / "state.json").write_text(
        json.dumps({"project_info": {"title": "test"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    # 创建空的 index.db（SQLite 文件锁 + WAL 模式由 app 内部处理）
    conn = sqlite3.connect(str(webnovel_dir / "index.db"))
    conn.close()

    init_project_root(tmpdir)

    yield tmpdir

    # 清理
    shutil.rmtree(tmpdir)


@pytest.fixture
def test_app(project_root):
    """用 create_app 工厂构建 FastAPI 实例，包装为 TestClient 返回。"""
    app = create_app(project_root)
    with TestClient(app) as client:
        yield client
