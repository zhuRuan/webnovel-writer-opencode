#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异常基础层

定义统一的异常体系，便于错误追踪和渐进式统一。
"""


class WebnovelError(Exception):
    """基础异常，所有自定义异常的父类"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class StateManagerError(WebnovelError):
    """State Manager 相关错误"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, details)


class IndexManagerError(WebnovelError):
    """Index Manager 相关错误"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, details)


class APIClientError(WebnovelError):
    """API 客户端相关错误"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, details)


class ConfigError(WebnovelError):
    """配置相关错误"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, details)