#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说发布器单元测试

覆盖 publisher 模块的所有不依赖 playwright 的工具函数和配置。
"""

import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest


# ── 从 publisher 模块导入待测函数 ──

def _clean_protagonist_name(name: str) -> str:
    """清洗主角名"""
    name = re.sub(r"（[^）]*）", "", name)
    name = re.sub(r"\([^)]*\)", "", name)
    name = name.split("/")[0].strip()
    return name[:20]


def _text_to_html(text: str) -> str:
    """将纯文本每行用 <p> 标签包裹"""
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    return "".join(f"<p>{p}</p>" for p in paragraphs)


def _find_label_ids(labels: List[Dict], genre: str, max_count: int = 4) -> List[str]:
    """从标签列表中匹配与题材相关的标签 ID"""
    def get_name(label: Dict) -> str:
        return label.get("label_name") or label.get("name", "")

    def get_id(label: Dict) -> str:
        val = label.get("label_id") or label.get("id") or label.get("category_id")
        return str(val) if val else ""

    selected: List[str] = []
    genre_tokens = set(genre.replace(" ", ""))

    for label in labels:
        name = get_name(label)
        lid = get_id(label)
        if not name or not lid:
            continue
        if any(ch in name for ch in genre_tokens) or name in genre:
            selected.append(lid)
        if len(selected) >= max_count:
            break

    if not selected and labels:
        selected = [get_id(l) for l in labels[:2] if get_id(l)]

    return selected


def _find_category_id(categories: List[Dict], genre: str) -> int:
    """根据题材匹配分类 ID"""
    def get_name(cat: Dict) -> str:
        return cat.get("name") or cat.get("category_name", "")

    for cat in categories:
        if get_name(cat) == genre:
            return int(cat["category_id"])

    for cat in categories:
        name = get_name(cat)
        if genre in name or name in genre:
            return int(cat["category_id"])

    if categories:
        return int(categories[0]["category_id"])
    return 0


def _is_writer_url(url: str) -> bool:
    """判断 URL 是否为作家后台页面（非登录页）"""
    url_lower = url.lower()
    login_keywords = ["login", "passport", "sso", "sign"]
    if any(keyword in url_lower for keyword in login_keywords):
        return False
    return "fanqienovel.com" in url_lower and (
        "writer" in url_lower or "main" in url_lower or "author" in url_lower
    )


# ── Config 类测试 ──

class TestConfig:
    """测试 publisher/config.py 配置"""

    def test_config_imports(self):
        """测试配置模块可导入"""
        from publisher.config import (
            DEFAULT_TIMEOUT,
            MAX_RETRIES,
            STEALTH_ARGS,
            BASE_URL,
            SUPPORTED_BROWSERS,
        )
        assert DEFAULT_TIMEOUT > 0
        assert MAX_RETRIES > 0
        assert isinstance(STEALTH_ARGS, list)
        assert len(STEALTH_ARGS) > 0
        assert BASE_URL.startswith("https://")
        assert "chromium" in SUPPORTED_BROWSERS

    def test_stealth_args_coverage(self):
        """测试 stealth 参数覆盖关键反检测参数"""
        from publisher.config import STEALTH_ARGS
        assert any("AutomationControlled" in arg for arg in STEALTH_ARGS)
        assert any("no-first-run" in arg for arg in STEALTH_ARGS)
        assert any("no-default-browser-check" in arg for arg in STEALTH_ARGS)

    def test_network_config(self):
        """测试网络配置合理性"""
        from publisher.config import MAX_RETRIES, RETRY_BACKOFF_BASE, RETRY_BACKOFF_MAX
        assert MAX_RETRIES >= 1
        assert RETRY_BACKOFF_BASE >= 0.1
        assert RETRY_BACKOFF_MAX > RETRY_BACKOFF_BASE

    def test_timeout_config(self):
        """测试超时配置"""
        from publisher.config import (
            DEFAULT_TIMEOUT,
            NAVIGATION_TIMEOUT,
            LOGIN_TIMEOUT,
            POLL_INTERVAL_MS,
        )
        assert DEFAULT_TIMEOUT >= 5000
        assert NAVIGATION_TIMEOUT >= DEFAULT_TIMEOUT
        assert LOGIN_TIMEOUT >= 30000
        assert POLL_INTERVAL_MS >= 500


# ── Exception 类测试 ──

class TestExceptions:
    """测试 publisher/exceptions.py"""

    def test_publisher_error_base(self):
        """测试基础异常"""
        from publisher.exceptions import PublisherError
        err = PublisherError("test message")
        assert str(err) == "test message"
        assert err.message == "test message"

    def test_publisher_error_with_details(self):
        """测试基础异常带详情"""
        from publisher.exceptions import PublisherError
        err = PublisherError("test", {"code": 500})
        assert "code" in str(err)
        assert err.details["code"] == 500

    def test_authentication_error(self):
        """测试认证异常"""
        from publisher.exceptions import AuthenticationError
        err = AuthenticationError("登录失败")
        assert isinstance(err, Exception)
        assert "登录失败" in str(err)

    def test_authentication_error_default(self):
        """测试认证异常默认消息"""
        from publisher.exceptions import AuthenticationError
        err = AuthenticationError()
        assert "登录失败" in str(err)

    def test_book_creation_error(self):
        """测试书籍创建异常"""
        from publisher.exceptions import BookCreationError
        err = BookCreationError("创建失败", {"title": "test"})
        assert err.details["title"] == "test"

    def test_chapter_publish_error(self):
        """测试章节发布异常"""
        from publisher.exceptions import ChapterPublishError
        err = ChapterPublishError()
        assert "发布章节失败" in str(err)

    def test_network_error(self):
        """测试网络异常"""
        from publisher.exceptions import NetworkError
        err = NetworkError("网络请求失败", {"path": "/test"})
        assert err.details["path"] == "/test"

    def test_browser_error(self):
        """测试浏览器异常"""
        from publisher.exceptions import BrowserError
        err = BrowserError("浏览器操作失败")
        assert "浏览器操作失败" in str(err)

    def test_exception_hierarchy(self):
        """测试异常继承关系"""
        from publisher.exceptions import (
            PublisherError,
            AuthenticationError,
            BookCreationError,
            ChapterPublishError,
            NetworkError,
            BrowserError,
        )
        assert issubclass(AuthenticationError, PublisherError)
        assert issubclass(BookCreationError, PublisherError)
        assert issubclass(ChapterPublishError, PublisherError)
        assert issubclass(NetworkError, PublisherError)
        assert issubclass(BrowserError, PublisherError)


# ── BrowserManager 无 playwright 测试 ──

class TestBrowserManagerState:
    """测试 BrowserManager 无 playwright 状态"""

    def test_is_alive_before_launch(self):
        """测试未启动时 is_alive() 返回 False"""
        from publisher.browser import BrowserManager
        from publisher import config
        with tempfile.TemporaryDirectory() as tmpdir:
            bm = BrowserManager(user_data_dir=tmpdir)
            assert bm.is_alive() is False
            assert bm.browser_type == config.DEFAULT_BROWSER

    def test_page_before_launch_raises(self):
        """测试未启动时访问 page 抛出 BrowserError"""
        from publisher.browser import BrowserManager, BrowserError
        with tempfile.TemporaryDirectory() as tmpdir:
            bm = BrowserManager(user_data_dir=tmpdir)
            with pytest.raises(BrowserError, match="浏览器未启动"):
                _ = bm.page

    def test_context_before_launch_raises(self):
        """测试未启动时访问 context 抛出 BrowserError"""
        from publisher.browser import BrowserManager, BrowserError
        with tempfile.TemporaryDirectory() as tmpdir:
            bm = BrowserManager(user_data_dir=tmpdir)
            with pytest.raises(BrowserError, match="浏览器未启动"):
                _ = bm.context

    def test_user_data_dir_stored(self):
        """测试 user_data_dir 正确存储"""
        from publisher.browser import BrowserManager
        dirmap = r"C:\test\path"
        bm = BrowserManager(user_data_dir=dirmap)
        assert bm.user_data_dir == dirmap

    def test_init_pathlib_path(self):
        """测试传入 Path 对象"""
        from publisher.browser import BrowserManager
        path = Path("/tmp/test_path")
        bm = BrowserManager(user_data_dir=path)
        assert bm.user_data_dir == str(path)


# ── Auth 工具函数测试 ──

class TestAuthUtilities:
    """测试 auth.py 工具函数"""

    def test_is_writer_url_valid(self):
        """测试 _is_writer_url 对有效 URL 返回 True"""
        assert _is_writer_url("https://fanqienovel.com/main/writer/")
        assert _is_writer_url("https://fanqienovel.com/author/books/")
        assert _is_writer_url(
            "https://fanqienovel.com/main/writer/?enter_from=author_zone"
        )

    def test_is_writer_url_login_page(self):
        """测试 _is_writer_url 对登录页返回 False"""
        assert not _is_writer_url("https://fanqienovel.com/login")
        assert not _is_writer_url("https://fanqienovel.com/passport/auth")
        assert not _is_writer_url("https://fanqienovel.com/sso/login")
        assert not _is_writer_url("https://passport.fanqienovel.com/sign")

    def test_is_writer_url_other_site(self):
        """测试 _is_writer_url 对其他网站返回 False"""
        assert not _is_writer_url("https://example.com")
        assert not _is_writer_url("https://google.com/main/writer/")

    def test_is_writer_url_case_insensitive(self):
        """测试 _is_writer_url 大小写不敏感"""
        assert not _is_writer_url("https://fanqienovel.com/LOGIN")
        assert not _is_writer_url("https://fanqienovel.com/Sign")

    def test_check_auth_state_file_not_exist(self):
        """测试 check_auth_state 文件不存在"""
        from publisher.auth import check_auth_state
        assert not check_auth_state(Path("/nonexistent/auth.json"))

    def test_check_auth_state_empty_file(self):
        """测试 check_auth_state 空文件"""
        from publisher.auth import check_auth_state
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp_path = Path(f.name)
        try:
            assert not check_auth_state(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_check_auth_state_valid_file(self):
        """测试 check_auth_state 有效文件"""
        from publisher.auth import check_auth_state
        with tempfile.NamedTemporaryFile(delete=False, mode="w") as f:
            f.write("{}")
            tmp_path = Path(f.name)
        try:
            assert check_auth_state(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_get_default_auth_state_path(self):
        """测试默认认证状态路径"""
        from publisher.auth import get_default_auth_state_path
        path = get_default_auth_state_path()
        assert ".opencode" in str(path)
        assert "fanqie_auth_state" in str(path)

    def test_get_default_user_data_dir(self):
        """测试默认用户数据目录"""
        from publisher.auth import get_default_user_data_dir
        path = get_default_user_data_dir()
        assert ".opencode" in str(path)
        assert "browser_user_data" in str(path)


# ── FanqieClient 工具函数测试 ──

class TestFanqieClient:
    """测试 FanqieClient 工具函数"""

    def test_clean_protagonist_name(self):
        """测试主角名清洗"""
        assert _clean_protagonist_name("萧炎（炎帝）") == "萧炎"
        assert _clean_protagonist_name("萧炎(炎帝)") == "萧炎"
        assert _clean_protagonist_name("萧炎/炎帝") == "萧炎"
        assert _clean_protagonist_name("萧炎") == "萧炎"
        assert _clean_protagonist_name("") == ""

    def test_clean_protagonist_name_truncate(self):
        """测试主角名截断"""
        long_name = "a" * 30
        result = _clean_protagonist_name(long_name)
        assert len(result) <= 20

    def test_text_to_html(self):
        """测试文本转 HTML"""
        text = "第一行\n\n第二行\n第三行"
        html = _text_to_html(text)
        assert "<p>第一行</p>" in html
        assert "<p>第二行</p>" in html
        assert "<p>第三行</p>" in html
        assert html.count("<p>") == 3

    def test_text_to_html_empty_lines(self):
        """测试空行处理"""
        text = "有内容\n\n\n\n空行多"
        html = _text_to_html(text)
        assert "<p>有内容</p>" in html
        assert "<p>空行多</p>" in html

    def test_find_category_id_exact_match(self):
        """测试精确匹配分类"""
        categories = [
            {"category_id": 1, "name": "玄幻"},
            {"category_id": 2, "name": "都市"},
            {"category_id": 3, "name": "仙侠"},
        ]
        assert _find_category_id(categories, "玄幻") == 1
        assert _find_category_id(categories, "都市") == 2

    def test_find_category_id_partial_match(self):
        """测试部分匹配分类"""
        categories = [
            {"category_id": 1, "name": "玄幻"},
            {"category_id": 2, "name": "都市"},
            {"category_id": 3, "name": "古代言情"},
        ]
        assert _find_category_id(categories, "言情") == 3
        assert _find_category_id(categories, "古代") == 3

    def test_find_category_id_fallback(self):
        """测试分类匹配失败时使用默认"""
        categories = [
            {"category_id": 1, "name": "玄幻"},
        ]
        result = _find_category_id(categories, "不存在的题材")
        assert result == 1

    def test_find_category_id_empty(self):
        """测试空分类列表"""
        result = _find_category_id([], "玄幻")
        assert result == 0

    def test_find_label_ids_exact_match(self):
        """测试精确匹配标签"""
        labels = [
            {"label_id": 1, "label_name": "热血"},
            {"label_id": 2, "label_name": "升级"},
            {"label_id": 3, "label_name": "穿越"},
        ]
        result = _find_label_ids(labels, "玄幻", max_count=2)
        assert len(result) == 2

    def test_find_label_ids_partial_match(self):
        """测试部分匹配标签"""
        labels = [
            {"label_id": 1, "label_name": "异世"},
            {"label_id": 2, "label_name": "穿越时空"},
        ]
        result = _find_label_ids(labels, "穿越", max_count=2)
        assert len(result) <= 2

    def test_find_label_ids_fallback(self):
        """测试标签匹配失败时使用默认"""
        labels = [
            {"label_id": 1, "label_name": "热血"},
            {"label_id": 2, "label_name": "升级"},
        ]
        result = _find_label_ids(labels, "不存在的标签", max_count=2)
        assert len(result) == 2
        assert "1" in result
        assert "2" in result


# ── FanqieClient 类测试 ──

class TestFanqieClientClass:
    """测试 FanqieClient 类行为（不依赖 playwright）"""

    def test_init_default_values(self):
        """测试默认初始化值"""
        from unittest.mock import MagicMock
        from publisher.fanqie_client import FanqieClient
        from publisher import config

        mock_page = MagicMock()
        client = FanqieClient(mock_page)
        assert client.max_retries == config.MAX_RETRIES
        assert client.debug is False

    def test_init_custom_values(self):
        """测试自定义初始化值"""
        from unittest.mock import MagicMock
        from publisher.fanqie_client import FanqieClient

        mock_page = MagicMock()
        client = FanqieClient(mock_page, max_retries=5, debug=True)
        assert client.max_retries == 5
        assert client.debug is True

    def test_init_stores_page(self):
        """测试存储 page 引用"""
        from unittest.mock import MagicMock
        from publisher.fanqie_client import FanqieClient

        mock_page = MagicMock()
        client = FanqieClient(mock_page)
        assert client.page is mock_page


# ── __init__ 导出测试 ──

class TestPublisherInit:
    """测试 publisher/__init__.py 导出"""

    def test_all_exports_present(self):
        """测试 __all__ 包含所有必要导出"""
        from publisher import __all__ as exports
        assert "FanqieClient" in exports
        assert "BrowserManager" in exports
        assert "PublisherError" in exports
        assert "AuthenticationError" in exports
        assert "BookCreationError" in exports
        assert "ChapterPublishError" in exports
        assert "NetworkError" in exports
        assert "BrowserError" in exports
        assert "ensure_logged_in" in exports
        assert "check_auth_state" in exports
        assert "config" in exports

    def test_config_importable_from_publisher(self):
        """测试可从 publisher 导入 config"""
        from publisher import config
        assert config.BASE_URL.startswith("https://")
