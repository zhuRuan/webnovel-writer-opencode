#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
敏感词检查器插件

演示插件：检查章节中是否包含敏感词
"""

from typing import Any, Dict, List

from data_modules.plugin_base import BaseChecker


class SensitiveWordChecker(BaseChecker):
    """敏感词审查器"""

    SENSITIVE_WORDS = {
        "政治相关": ["敏感词1", "敏感词2"],
        "暴力血腥": ["暴力词1", "血腥词2"],
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.custom_words = self.config.get("custom_words", [])

    async def check(self, chapter_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        issues: List[Dict[str, Any]] = []
        found_words: Dict[str, List[str]] = {}

        all_words = self.SENSITIVE_WORDS.copy()
        if self.custom_words:
            all_words["自定义"] = self.custom_words

        for category, words in all_words.items():
            for word in words:
                if word in chapter_text:
                    pos = chapter_text.find(word)
                    issues.append(
                        {
                            "type": "sensitive_word",
                            "word": word,
                            "category": category,
                            "position": pos,
                            "severity": "error",
                            "message": f"检测到敏感词: {word} (类别: {category})",
                        }
                    )
                    if category not in found_words:
                        found_words[category] = []
                    found_words[category].append(word)

        score = max(0, 100 - len(issues) * 10)
        suggestions = (
            ["请移除检测到的敏感词"] if issues else ["章节通过敏感词检查"]
        )

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "score": score,
            "suggestions": suggestions,
        }
