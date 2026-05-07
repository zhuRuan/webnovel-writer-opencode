"""Tests for publisher module."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parents[2]
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from publisher.config import (
    PublishConfig,
    load_upload_log,
    save_upload_log,
    get_upload_log_dir,
)


class TestPublishConfig:
    def test_defaults(self):
        cfg = PublishConfig()
        assert cfg.mode == "draft"
        assert cfg.headless is True
        assert cfg.retry_count == 2
        assert cfg.retry_delay == 3.0
        assert cfg.chapter_gap == 5.0

    def test_custom(self):
        cfg = PublishConfig(mode="publish", retry_count=5)
        assert cfg.mode == "publish"
        assert cfg.retry_count == 5
        assert cfg.headless is True  # unchanged default


class TestUploadLog:
    def test_roundtrip(self, tmp_path):
        log_dir = tmp_path / "upload_log"
        log_dir.mkdir(parents=True)
        book_id = "test123"

        import publisher.config as mod
        original = get_upload_log_dir
        mod.get_upload_log_dir = lambda: log_dir
        try:
            save_upload_log("fanqie", book_id, {1, 2, 3})
            loaded = load_upload_log("fanqie", book_id)
            assert loaded == {1, 2, 3}
        finally:
            mod.get_upload_log_dir = original

    def test_load_nonexistent_returns_empty(self, tmp_path):
        log_dir = tmp_path / "empty_log"
        log_dir.mkdir(parents=True)

        import publisher.config as mod
        original = mod.get_upload_log_dir
        mod.get_upload_log_dir = lambda: log_dir
        try:
            loaded = load_upload_log("nonexistent", "no_book")
            assert loaded == set()
        finally:
            mod.get_upload_log_dir = original

    def test_append_chapters(self, tmp_path):
        log_dir = tmp_path / "append_log"
        log_dir.mkdir(parents=True)

        import publisher.config as mod
        original = mod.get_upload_log_dir
        mod.get_upload_log_dir = lambda: log_dir
        try:
            save_upload_log("fanqie", "b1", {1, 2})
            save_upload_log("fanqie", "b1", {1, 2, 3, 4})
            loaded = load_upload_log("fanqie", "b1")
            assert loaded == {1, 2, 3, 4}
        finally:
            mod.get_upload_log_dir = original
