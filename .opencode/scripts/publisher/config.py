# .opencode/scripts/publisher/config.py
"""发布配置与上传进度追踪。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class PublishConfig:
    mode: str = "draft"          # draft | publish
    headless: bool = True
    retry_count: int = 2
    retry_delay: float = 3.0     # 秒
    chapter_gap: float = 5.0     # 章间间隔，避免触发反爬
    timeout: float = 30.0        # 单次操作超时


def get_upload_log_dir() -> Path:
    return Path.home() / ".webnovel-publish" / "upload_log"


def _log_path(platform: str, book_id: str) -> Path:
    d = get_upload_log_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{platform}_{book_id}.json"


def get_log_path(platform: str, book_id: str) -> Path:
    """公开接口：获取上传日志文件路径。"""
    return _log_path(platform, book_id)


def load_upload_log(platform: str, book_id: str) -> set[int]:
    p = _log_path(platform, book_id)
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("uploaded", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def save_upload_log(platform: str, book_id: str, uploaded: set[int], book_name: str = ""):
    p = _log_path(platform, book_id)
    # 先读出已有数据，合并 upload 列表（防止多进程竞态覆盖）
    existing = set()
    try:
        if p.is_file():
            existing = set(json.loads(p.read_text(encoding="utf-8")).get("uploaded", []))
    except (json.JSONDecodeError, KeyError):
        pass
    merged = sorted(existing | uploaded)
    payload = {
        "book_id": book_id,
        "book_name": book_name,
        "uploaded": merged,
        "last_upload": datetime.now(timezone.utc).isoformat(),
    }
    # 原子写入：先写临时文件，再 rename（跨平台原子操作）
    import os
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
