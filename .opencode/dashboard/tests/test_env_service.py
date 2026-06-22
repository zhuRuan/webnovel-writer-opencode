"""测试 services/env.py —— 环境状态构建服务。"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dashboard.services.env import _inspect_vector_db, build_env_status


# ---------------------------------------------------------------------------
# _inspect_vector_db
# ---------------------------------------------------------------------------


def _mock_data_modules_config(vector_db_path: Path) -> MagicMock:
    """构造一个 DataModulesConfig 的 mock，使其 vector_db 属性指向给定路径。"""
    cfg = MagicMock()
    cfg.vector_db = vector_db_path
    return cfg


class TestInspectVectorDb:
    """_inspect_vector_db 函数测试。"""

    def test_file_not_exists(self, tmp_path: Path) -> None:
        """向量数据库文件不存在 → exists=False, record_count=0。"""
        nonexistent = tmp_path / "nonexistent.db"
        cfg_mock = _mock_data_modules_config(nonexistent)

        with patch("data_modules.config.DataModulesConfig") as MockCls:
            MockCls.from_project_root.return_value = cfg_mock
            result = _inspect_vector_db(tmp_path)

        assert result["exists"] is False
        assert result["size_bytes"] == 0
        assert result["record_count"] == 0
        assert result["error"] == ""

    def test_empty_file_no_vectors_table(self, tmp_path: Path) -> None:
        """文件存在但无 vectors 表 → record_count=0。"""
        db_path = tmp_path / "vectors.db"
        # 创建空 SQLite 文件（无表）
        conn = sqlite3.connect(str(db_path))
        conn.close()

        cfg_mock = _mock_data_modules_config(db_path)

        with patch("data_modules.config.DataModulesConfig") as MockCls:
            MockCls.from_project_root.return_value = cfg_mock
            result = _inspect_vector_db(tmp_path)

        assert result["exists"] is True
        assert result["record_count"] == 0
        assert result["error"] == ""

    def test_file_with_vectors(self, tmp_path: Path) -> None:
        """文件存在且有 vectors 表 → record_count > 0。"""
        db_path = tmp_path / "vectors.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE vectors (id INTEGER PRIMARY KEY, v BLOB)")
        conn.execute("INSERT INTO vectors (v) VALUES (x'00')")
        conn.execute("INSERT INTO vectors (v) VALUES (x'01')")
        conn.commit()
        conn.close()

        cfg_mock = _mock_data_modules_config(db_path)

        with patch("data_modules.config.DataModulesConfig") as MockCls:
            MockCls.from_project_root.return_value = cfg_mock
            result = _inspect_vector_db(tmp_path)

        assert result["exists"] is True
        assert result["record_count"] == 2
        assert result["error"] == ""


# ---------------------------------------------------------------------------
# build_env_status
# ---------------------------------------------------------------------------


class TestBuildEnvStatus:
    """build_env_status 函数测试。"""

    def _make_config_mock(
        self,
        embed_api_key: str = "",
        rerank_api_key: str = "",
        vector_exists: bool = False,
        vector_size: int = 0,
        tmp_path: Path | None = None,
    ) -> MagicMock:
        """构造一个 DataModulesConfig mock，可控 embed/rerank/vector_db 状态。"""
        cfg = MagicMock()
        cfg.embed_base_url = "https://embed.example.com/v1"
        cfg.embed_model = "test-embed-model"
        cfg.embed_api_key = embed_api_key
        cfg.rerank_base_url = "https://rerank.example.com/v1"
        cfg.rerank_model = "test-rerank-model"
        cfg.rerank_api_key = rerank_api_key

        if tmp_path is not None:
            db_path = tmp_path / "vectors.db"
            if vector_exists:
                conn = sqlite3.connect(str(db_path))
                # 写入一些数据使 size_bytes > 0
                conn.execute("CREATE TABLE vectors (id INTEGER PRIMARY KEY, v BLOB)")
                conn.execute("INSERT INTO vectors (v) VALUES (x'00')")
                conn.commit()
                conn.close()
            cfg.vector_db = db_path
        else:
            cfg.vector_db = tmp_path / "vectors.db" if tmp_path else Path("/nonexistent")

        return cfg

    def test_returns_expected_structure(self, tmp_path: Path) -> None:
        """build_env_status 返回正确的顶层结构。"""
        cfg_mock = self._make_config_mock(tmp_path=tmp_path)

        with patch("data_modules.config.DataModulesConfig") as MockCls:
            MockCls.from_project_root.return_value = cfg_mock
            result = build_env_status(tmp_path)

        assert "embed" in result
        assert "rerank" in result
        assert "vector_db" in result
        assert "rag_mode" in result
        # 子字段
        assert set(result["embed"].keys()) == {"base_url", "model", "api_key_present"}
        assert set(result["rerank"].keys()) == {"base_url", "model", "api_key_present"}
        assert set(result["vector_db"].keys()) == {
            "path", "exists", "size_bytes", "record_count", "error",
        }

    def test_rag_mode_full(self, tmp_path: Path) -> None:
        """embed + rerank + vector 全就绪 → 'full'。"""
        cfg_mock = self._make_config_mock(
            embed_api_key="sk-embed",
            rerank_api_key="sk-rerank",
            vector_exists=True,
            tmp_path=tmp_path,
        )

        with patch("data_modules.config.DataModulesConfig") as MockCls:
            MockCls.from_project_root.return_value = cfg_mock
            result = build_env_status(tmp_path)

        assert result["rag_mode"] == "full"
        assert result["embed"]["api_key_present"] is True
        assert result["rerank"]["api_key_present"] is True
        assert result["vector_db"]["exists"] is True
        assert result["vector_db"]["record_count"] == 1

    def test_rag_mode_embed_only(self, tmp_path: Path) -> None:
        """embed + vector 就绪，但 rerank 无 key → 'embed_only'。"""
        cfg_mock = self._make_config_mock(
            embed_api_key="sk-embed",
            rerank_api_key="",
            vector_exists=True,
            tmp_path=tmp_path,
        )

        with patch("data_modules.config.DataModulesConfig") as MockCls:
            MockCls.from_project_root.return_value = cfg_mock
            result = build_env_status(tmp_path)

        assert result["rag_mode"] == "embed_only"
        assert result["embed"]["api_key_present"] is True
        assert result["rerank"]["api_key_present"] is False

    def test_rag_mode_bm25_only(self, tmp_path: Path) -> None:
        """什么都不就绪（或仅 rerank）→ 'bm25_only'。"""
        cfg_mock = self._make_config_mock(
            embed_api_key="",
            rerank_api_key="",
            vector_exists=False,
            tmp_path=tmp_path,
        )

        with patch("data_modules.config.DataModulesConfig") as MockCls:
            MockCls.from_project_root.return_value = cfg_mock
            result = build_env_status(tmp_path)

        assert result["rag_mode"] == "bm25_only"
        assert result["embed"]["api_key_present"] is False
        assert result["rerank"]["api_key_present"] is False
