# -*- coding: utf-8 -*-
"""
CheckersManager 测试
"""

import pytest
from dataclasses import asdict

from ..checkers_manager import CheckersManager, CodeCheckerResult


class TestCodeCheckerRegistration:
    """Code Checker 注册测试"""

    def test_register_world_consistency_checker(self):
        """测试注册 WorldConsistencyChecker"""
        CheckersManager.register_world_consistency_checker()
        checkers = CheckersManager.get_code_checkers()
        assert "world-consistency" in checkers

    def test_run_code_checkers_returns_results(self):
        """测试运行 code checkers 返回结果"""
        CheckersManager.register_world_consistency_checker()
        
        test_content = "主角突破到金丹境界，与元婴强者战斗"
        results = CheckersManager.run_code_checkers(1, test_content, {})
        
        assert len(results) > 0
        assert all(isinstance(r, CodeCheckerResult) for r in results)
        
        result = results[0]
        assert result.checker_id == "world-consistency"
        assert isinstance(result.issues, list)
        assert isinstance(result.passed, bool)
        assert isinstance(result.blocked, bool)

    def test_block_on_critical(self):
        """测试 critical 问题阻塞"""
        def critical_checker(chapter, content, ctx):
            return [
                {"issue_id": "TEST_001", "severity": "critical", "message": "test"}
            ]
        
        CheckersManager._code_checkers = {}
        CheckersManager.register_code_checker(
            "test-critical",
            critical_checker,
            {"block_on_critical": True}
        )
        
        results = CheckersManager.run_code_checkers(1, "test", {})
        result = next(r for r in results if r.checker_id == "test-critical")
        assert result.blocked is True

    def test_no_block_without_critical(self):
        """测试无 critical 时不阻塞"""
        def low_severity_checker(chapter, content, ctx):
            return [
                {"issue_id": "TEST_001", "severity": "low", "message": "test"}
            ]
        
        CheckersManager._code_checkers = {}
        CheckersManager.register_code_checker(
            "test-low",
            low_severity_checker,
            {"block_on_critical": True}
        )
        
        results = CheckersManager.run_code_checkers(1, "test", {})
        result = next(r for r in results if r.checker_id == "test-low")
        assert result.blocked is False

    def test_custom_code_checker(self):
        """测试自定义 code checker"""
        def my_checker(chapter, content, ctx):
            if "error" in content:
                return [
                    {"issue_id": "MY_001", "severity": "high", "message": "发现错误"}
                ]
            return []
        
        CheckersManager._code_checkers = {}
        CheckersManager.register_code_checker(
            "my-checker",
            my_checker,
            {"block_on_critical": False}
        )
        
        results = CheckersManager.run_code_checkers(1, "this has error", {})
        result = next(r for r in results if r.checker_id == "my-checker")
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0]["issue_id"] == "MY_001"


class TestLayeredCheckers:
    """分层审查器测试"""

    def test_run_layered_checkers_blocked(self):
        """测试 code layer 阻塞时返回 blocked"""
        def critical_checker(chapter, content, ctx):
            return [
                {"issue_id": "TEST_001", "severity": "critical", "message": "test"}
            ]
        
        CheckersManager._code_checkers = {}
        CheckersManager.register_code_checker(
            "block-checker",
            critical_checker,
            {"block_on_critical": True}
        )
        
        result = CheckersManager.run_layered_checkers(1, "test", {})
        
        assert result["blocked"] is True
        assert result["layer"] == "code"
        assert result["code_results"]
        assert result["issues"]

    def test_run_layered_checkers_continue(self):
        """测试无阻塞时继续到 LLM layer"""
        def clean_checker(chapter, content, ctx):
            return []
        
        CheckersManager._code_checkers = {}
        CheckersManager.register_code_checker(
            "clean-checker",
            clean_checker,
            {"block_on_critical": True}
        )
        
        result = CheckersManager.run_layered_checkers(1, "test", {}, run_llm=False)
        
        assert result["blocked"] is False
        assert result["layer"] == "code"
        assert result["code_results"]