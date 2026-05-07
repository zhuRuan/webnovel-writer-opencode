"""Tests for publisher module."""
from __future__ import annotations

import os
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


from publisher.base import BasePlatform, BookMeta, Chapter, UploadResult


class TestBaseInterface:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BasePlatform()

    def test_concrete_subclass_minimal(self):
        class MiniAdapter(BasePlatform):
            name = "mini"
            display_name = "Mini"
            login_url = "https://example.com"

            async def setup_auth(self, page):
                return True

            async def list_books(self, page):
                return []

            async def create_book(self, page, meta):
                return "book-1"

            async def upload_chapter(self, page, book_id, chapter):
                return UploadResult(success=True, chapter_index=chapter.index)

        adapter = MiniAdapter()
        assert adapter.name == "mini"


class TestBookMeta:
    def test_minimal(self):
        meta = BookMeta(title="测试书", genre="玄幻", synopsis="简介",
                        protagonist="主角", tags=["热血"])
        assert meta.title == "测试书"

    def test_tags_default(self):
        meta = BookMeta(title="T", genre="G", synopsis="S", protagonist="P")
        assert meta.tags == []


class TestChapter:
    def test_defaults(self):
        ch = Chapter(index=1, title="序章", content="正文内容")
        assert ch.index == 1
        assert ch.volume_title == ""


class TestUploadResult:
    def test_success(self):
        r = UploadResult(success=True, chapter_index=5)
        assert r.success is True

    def test_failure_with_message(self):
        r = UploadResult(success=False, chapter_index=3, message="超时")
        assert r.success is False
        assert "超时" in r.message


from publisher.browser import Browser, get_auth_dir


class TestGetAuthDir:
    def test_returns_path(self):
        path = get_auth_dir()
        assert path.name == "auth"
        assert ".webnovel-publish" in str(path)


class TestBrowserConfig:
    def test_default_headless(self):
        b = Browser(platform="test")
        assert b.headless is True

    def test_headed_mode(self):
        b = Browser(headless=False, platform="test")
        assert b.headless is False

    def test_auth_state_path(self, monkeypatch, tmp_path):
        auth_dir = tmp_path / "auth"
        auth_dir.mkdir(parents=True)
        b = Browser(platform="fanqie")
        monkeypatch.setattr(
            "publisher.browser.get_auth_dir", lambda: auth_dir)
        p = b._auth_state_path()
        assert p.name == "fanqie.json"

    def test_linux_root_no_sandbox(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        # 直接对 os 模块设置 geteuid（Windows 上该属性不存在）
        setattr(os, "geteuid", lambda: 0)
        try:
            b = Browser(platform="test")
            args = b._get_launch_args()
            assert "--no-sandbox" in args
        finally:
            delattr(os, "geteuid")

    def test_windows_no_sandbox_flag(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        b = Browser(platform="test")
        args = b._get_launch_args()
        assert "--no-sandbox" not in args
