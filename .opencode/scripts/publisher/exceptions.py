#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说发布器异常定义
"""

from typing import Any, Dict, Optional


class PublisherError(Exception):
    """发布器基础异常"""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class AuthenticationError(PublisherError):
    """认证失败异常"""

    def __init__(self, message: str = "登录失败", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)


class BookCreationError(PublisherError):
    """书籍创建失败异常"""

    def __init__(self, message: str = "创建书籍失败", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)


class ChapterPublishError(PublisherError):
    """章节发布失败异常"""

    def __init__(self, message: str = "发布章节失败", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)


class NetworkError(PublisherError):
    """网络请求异常"""

    def __init__(self, message: str = "网络请求失败", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)


class BrowserError(PublisherError):
    """浏览器操作异常"""

    def __init__(self, message: str = "浏览器操作失败", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
