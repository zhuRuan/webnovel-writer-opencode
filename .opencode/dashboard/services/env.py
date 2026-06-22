"""
环境状态构建服务 —— 从项目根目录探测 embedding / rerank / vector DB 状态。

从 app.py _build_env_status() / _inspect_vector_db() 迁移。
"""

import sqlite3
from pathlib import Path


def _inspect_vector_db(project_root: Path) -> dict:
    """检查向量数据库文件的存在性、大小和记录数。"""
    from data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(project_root)
    vector_db = cfg.vector_db
    exists = vector_db.is_file()
    size_bytes = vector_db.stat().st_size if exists else 0
    record_count = 0
    error = ""

    if exists and size_bytes > 0:
        try:
            with sqlite3.connect(str(vector_db)) as conn:
                cursor = conn.cursor()
                table_exists = cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'vectors'"
                ).fetchone()
                if table_exists:
                    row = cursor.execute("SELECT COUNT(*) FROM vectors").fetchone()
                    record_count = int(row[0] or 0) if row else 0
        except sqlite3.Error as exc:
            error = str(exc)

    return {
        "path": str(vector_db),
        "exists": exists,
        "size_bytes": size_bytes,
        "record_count": record_count,
        "error": error,
    }


def build_env_status(project_root: Path) -> dict:
    """构建环境状态字典，包含 embed/rerank/vector DB 信息和 rag_mode。

    返回:
        {
            "embed": { "base_url": str, "model": str, "api_key_present": bool },
            "rerank": { "base_url": str, "model": str, "api_key_present": bool },
            "vector_db": { "path": str, "exists": bool, "size_bytes": int,
                           "record_count": int, "error": str },
            "rag_mode": "full" | "embed_only" | "bm25_only",
        }
    """
    from data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(project_root)
    vector_info = _inspect_vector_db(project_root)

    embed_ready = bool(str(cfg.embed_api_key or "").strip())
    rerank_ready = bool(str(cfg.rerank_api_key or "").strip())
    vector_ready = bool(vector_info["exists"] and vector_info["size_bytes"] > 0)

    if vector_ready and embed_ready and rerank_ready:
        rag_mode = "full"
    elif vector_ready and embed_ready:
        rag_mode = "embed_only"
    else:
        rag_mode = "bm25_only"

    return {
        "embed": {
            "base_url": cfg.embed_base_url,
            "model": cfg.embed_model,
            "api_key_present": embed_ready,
        },
        "rerank": {
            "base_url": cfg.rerank_base_url,
            "model": cfg.rerank_model,
            "api_key_present": rerank_ready,
        },
        "vector_db": vector_info,
        "rag_mode": rag_mode,
    }
