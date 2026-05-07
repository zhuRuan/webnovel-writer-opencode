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
from publisher.formatter import to_plain_text, to_html, format_for_platform


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


class TestToPlainText:
    def test_strips_bold(self):
        assert to_plain_text("这是**重点**内容") == "这是重点内容"

    def test_strips_italic(self):
        assert to_plain_text("这是*斜体*文字") == "这是斜体文字"

    def test_strips_headers(self):
        assert to_plain_text("# 标题\n\n正文") == "标题\n\n正文"

    def test_strips_separator(self):
        assert to_plain_text("段落一\n\n---\n\n段落二") == "段落一\n\n***\n\n段落二"

    def test_preserves_paragraphs(self):
        md = "段落一\n\n段落二"
        result = to_plain_text(md)
        assert "段落一" in result
        assert "段落二" in result

    def test_removes_links(self):
        assert to_plain_text("看[这里](http://example.com)") == "看这里"


class TestToHTML:
    def test_bold(self):
        assert to_html("**重点**") == "<p><b>重点</b></p>"

    def test_paragraphs(self):
        assert to_html("段一\n\n段二") == "<p>段一</p>\n<p>段二</p>"

    def test_italic(self):
        assert to_html("*斜体*") == "<p><i>斜体</i></p>"


class TestFormatForPlatform:
    def test_default_indent(self):
        md = "这是测试段落"
        result = format_for_platform(md, "fanqie")
        assert "　　这是测试段落" in result

    def test_custom_indent_hint(self):
        md = "测试"
        result = format_for_platform(md, "fanqie", hints={"indent": "  "})
        assert "  测试" in result and "　　" not in result

    def test_chapter_title_preserved(self):
        md = "# 第5章 出发\n\n正文内容"
        result = format_for_platform(md, "fanqie")
        assert "第5章 出发" in result
        assert "正文内容" in result
