#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插件基类接口定义

定义 Agent、Skill、Checker、Publisher 四种扩展点的抽象基类，
插件开发者通过继承这些基类来实现自定义功能。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseAgent(ABC):
    """Agent 抽象基类

    Agent 是智能代理，负责处理特定创作任务（如上下文检索、风格分析等）。
    插件可通过继承此类并注册到 manifest.json 来添加自定义 Agent。
    """

    def __init__(self, context: Dict[str, Any]):
        """
        初始化 Agent

        Args:
            context: 包含配置、项目信息等的上下文字典
        """
        self.context = context
        self.config = context.get("config", {})

    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 Agent 任务

        Args:
            input_data: 包含当前写作上下文、用户输入等信息

        Returns:
            处理结果，包含检索到的上下文、推荐内容等
        """
        pass

    def validate(self, output: Dict[str, Any]) -> bool:
        """
        验证输出格式（可选）

        Args:
            output: Agent 返回的结果

        Returns:
            是否通过验证
        """
        return True

    async def on_load(self, plugin_manager) -> None:
        """
        插件加载时调用（可选）

        Args:
            plugin_manager: 插件管理器实例
        """
        pass

    async def on_unload(self) -> None:
        """
        插件卸载时调用（可选），用于清理资源
        """
        pass


class BaseSkill(ABC):
    """Skill 抽象基类

    Skill 是技能命令，通过斜杠命令（如 /my-skill）调用。
    插件可通过继承此类并注册到 manifest.json 来添加自定义命令。
    """

    command: Optional[str] = None

    def __init__(self, context: Dict[str, Any]):
        """
        初始化 Skill

        Args:
            context: 包含 plugin_manager 等的上下文字典
        """
        self.context = context

    @abstractmethod
    async def execute(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        执行 Skill 命令

        Args:
            args: 命令参数列表
            **kwargs: 其他参数（如 --fast 标志）

        Returns:
            执行结果，包含消息、状态等
        """
        pass

    def get_help(self) -> str:
        """
        返回帮助信息

        Returns:
            帮助文本
        """
        return "没有提供帮助信息"

    async def on_load(self, plugin_manager) -> None:
        """
        插件加载时调用（可选）

        Args:
            plugin_manager: 插件管理器实例
        """
        pass

    async def on_unload(self) -> None:
        """
        插件卸载时调用（可选），用于清理资源
        """
        pass


class BaseChecker(ABC):
    """Checker 抽象基类

    Checker 是审查器，负责检查章节质量（一致性、连贯性、敏感词等）。
    插件可通过继承此类并注册到 manifest.json 来添加自定义审查器。
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化 Checker

        Args:
            config: 审查器配置
        """
        self.config = config or {}

    @abstractmethod
    async def check(self, chapter_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查章节质量

        Args:
            chapter_text: 章节正文
            context: 上下文（包含设定、前文等）

        Returns:
            检查结果字典，包含 passed/issues/score/suggestions
        """
        pass

    async def on_load(self, plugin_manager) -> None:
        """
        插件加载时调用（可选）

        Args:
            plugin_manager: 插件管理器实例
        """
        pass

    async def on_unload(self) -> None:
        """
        插件卸载时调用（可选），用于清理资源
        """
        pass


class BasePublisher(ABC):
    """Publisher 抽象基类

    Publisher 是发布平台，负责将章节上传到第三方平台（如番茄小说、七猫等）。
    插件可通过继承此类并注册到 manifest.json 来添加自定义发布平台。
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Publisher

        Args:
            config: 平台配置（包含认证信息等）
        """
        self.config = config
        self.authenticated = False

    @abstractmethod
    async def authenticate(self, credentials: Dict[str, str]) -> bool:
        """
        登录验证

        Args:
            credentials: 认证凭据（如用户名、密码、Token）

        Returns:
            是否认证成功
        """
        pass

    @abstractmethod
    async def get_books(self) -> List[Dict[str, Any]]:
        """
        获取书籍列表

        Returns:
            书籍列表，每项包含 id、title 等信息
        """
        pass

    @abstractmethod
    async def create_book(self, title: str, genre: str, synopsis: str) -> Dict[str, Any]:
        """
        创建新书

        Args:
            title: 书名
            genre: 题材
            synopsis: 简介

        Returns:
            创建的书籍信息
        """
        pass

    @abstractmethod
    async def upload_chapter(
        self, book_id: str, chapter: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        上传章节

        Args:
            book_id: 书籍 ID
            chapter: 章节信息，包含 title、content、order、is_draft

        Returns:
            上传结果
        """
        pass

    async def list_chapters(self, book_id: str) -> List[Dict[str, Any]]:
        """
        获取章节列表（可选实现）

        Args:
            book_id: 书籍 ID

        Returns:
            章节列表
        """
        return []

    async def logout(self) -> bool:
        """
        登出（可选实现）

        Returns:
            是否成功
        """
        self.authenticated = False
        return True

    async def on_load(self, plugin_manager) -> None:
        """
        插件加载时调用（可选）

        Args:
            plugin_manager: 插件管理器实例
        """
        pass

    async def on_unload(self) -> None:
        """
        插件卸载时调用（可选），用于清理资源
        """
        pass
