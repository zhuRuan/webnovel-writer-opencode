#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作流钩子实现 - 敏感词修复

包含：
- SensitiveWordFixHook: 审查后自动修复敏感词
- AfterWriteLoggerHook: 数据回写后记录日志
"""

import logging
from typing import Any, Dict, List

try:
    from data_modules.plugin_base import BaseHook
except ImportError:
    from plugin_base import BaseHook

logger = logging.getLogger(__name__)


class SensitiveWordFixHook(BaseHook):
    """敏感词自动修复钩子

    在审查后或润色后自动修复敏感词。
    """

    async def trigger(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行敏感词修复

        Args:
            context: 上下文，包含 chapter_content

        Returns:
            修改后的上下文
        """
        chapter_content = context.get("chapter_content", "")
        if not chapter_content:
            logger.debug("上下文中没有 chapter_content，跳过敏感词修复")
            return context

        original_content = chapter_content

        sensitive_words = self.config.get("sensitive_words", [
            "敏感词1", "敏感词2", "违禁词"
        ])

        for word in sensitive_words:
            if word in chapter_content:
                replacement = "*" * len(word)
                chapter_content = chapter_content.replace(word, replacement)
                logger.info(f"修复敏感词: {word} -> {replacement}")

        if chapter_content != original_content:
            context["chapter_content"] = chapter_content
            context["hook_modified"] = True
            context["hook_name"] = "SensitiveWordFixHook"
            logger.info("敏感词修复完成")

        return context

    def get_hook_points(self) -> List[str]:
        """返回钩子触发点"""
        return ["after_review", "after_polish"]


class AfterWriteLoggerHook(BaseHook):
    """数据回写后日志钩子

    在数据回写完成后记录操作日志。
    """

    async def trigger(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        记录回写日志

        Args:
            context: 上下文信息

        Returns:
            上下文（不做修改）
        """
        chapter = context.get("chapter", "unknown")
        state_updated = context.get("state_updated", False)
        index_updated = context.get("index_updated", False)

        logger.info(
            f"数据回写完成 - 章节: {chapter}, "
            f"状态更新: {state_updated}, 索引更新: {index_updated}"
        )

        context["hook_logged"] = True
        context["hook_name"] = "AfterWriteLoggerHook"

        return context

    def get_hook_points(self) -> List[str]:
        """返回钩子触发点"""
        return ["after_data_write"]