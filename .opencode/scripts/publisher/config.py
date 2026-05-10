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
    payload = {
        "book_id": book_id,
        "book_name": book_name,
        "uploaded": sorted(uploaded),
        "last_upload": datetime.now(timezone.utc).isoformat(),
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
