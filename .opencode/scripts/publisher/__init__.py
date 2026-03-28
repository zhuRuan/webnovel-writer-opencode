#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说发布器模块

提供浏览器管理、登录认证和 HTTP API 客户端功能。
"""

from .auth import (
    check_auth_state,
    ensure_logged_in,
    get_default_auth_state_path,
    get_default_user_data_dir,
)
from .browser import BrowserManager
from .exceptions import (
    AuthenticationError,
    BookCreationError,
    BrowserError,
    ChapterPublishError,
    NetworkError,
    PublisherError,
)
from .fanqie_client import FanqieClient

__all__ = [
    "FanqieClient",
    "BrowserManager",
    "PublisherError",
    "AuthenticationError",
    "BookCreationError",
    "ChapterPublishError",
    "NetworkError",
    "BrowserError",
    "ensure_logged_in",
    "check_auth_state",
    "get_default_auth_state_path",
    "get_default_user_data_dir",
]
