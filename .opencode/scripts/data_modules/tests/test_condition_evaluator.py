# -*- coding: utf-8 -*-
"""
ConditionEvaluator 测试
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_modules.condition_evaluator import (
    ConditionEvaluator,
    TriggerCondition,
    create_evaluator_from_chapter
)


class TestConditionEvaluator:
    """ConditionEvaluator 测试"""

    def test_basic_condition(self):
        """测试基本条件表达式"""
        evaluator = ConditionEvaluator({
            "chapter_number": 15,
            "chapter_type": "normal"
        })
        
        assert evaluator.eval_condition("chapter_number >= 10") is True
        assert evaluator.eval_condition("chapter_number < 10") is False

    def test_chapter_type_condition(self):
        """测试章节类型条件"""
        evaluator = ConditionEvaluator({
            "chapter_type": "transitional"
        })
        
        assert evaluator.eval_condition("chapter_type != 'transitional'") is False
        assert evaluator.eval_condition("chapter_type == 'transitional'") is True

    def test_keyword_matching(self):
        """测试关键词匹配"""
        evaluator = ConditionEvaluator({
            "content": "萧炎在迦南学院修炼，遭遇了强大的敌人，战斗一触即发！"
        })
        
        assert evaluator.check_keywords(["战斗", "敌人"], min_count=1) is True
        assert evaluator.check_keywords(["战斗", "敌人"], min_count=2) is True
        assert evaluator.check_keywords(["神秘宝藏"], min_count=1) is False

    def test_combined_conditions(self):
        """测试组合条件"""
        evaluator = ConditionEvaluator({
            "chapter_type": "normal",
            "content": "本章有悬念..."
        })
        
        conditions = [
            TriggerCondition(type="condition", expression="chapter_type != 'transitional'"),
            TriggerCondition(type="keyword", keywords=["悬念"], min_count=1)
        ]
        
        assert evaluator.evaluate(conditions) is True

    def test_and_logic(self):
        """测试 AND 逻辑（所有条件必须满足）"""
        evaluator = ConditionEvaluator({
            "chapter_number": 5,
            "content": "战斗开始"
        })
        
        conditions = [
            TriggerCondition(type="condition", expression="chapter_number >= 10"),
            TriggerCondition(type="keyword", keywords=["战斗"], min_count=1)
        ]
        
        assert evaluator.evaluate(conditions) is False

    def test_empty_conditions(self):
        """测试空条件列表"""
        evaluator = ConditionEvaluator({})
        assert evaluator.evaluate([]) is True

    def test_invalid_expression(self):
        """测试无效表达式"""
        evaluator = ConditionEvaluator({
            "chapter_number": 10
        })
        
        assert evaluator.eval_condition("undefined_var > 5") is False
        assert evaluator.eval_condition("10 + ") is False

    def test_create_evaluator_from_chapter(self):
        """测试从章节信息创建评估器"""
        evaluator = create_evaluator_from_chapter(
            chapter=20,
            chapter_type="climax",
            content="激烈的战斗"
        )
        
        assert evaluator.context["chapter_number"] == 20
        assert evaluator.context["chapter_type"] == "climax"
        assert "战斗" in evaluator.context["content"]

    def test_should_trigger_with_string(self):
        """测试兼容旧格式（字符串）"""
        evaluator = ConditionEvaluator({
            "chapter_number": 15
        })
        
        assert evaluator.should_trigger(["chapter_number >= 10"]) is True

    def test_should_trigger_with_dict(self):
        """测试新格式（字典）"""
        evaluator = ConditionEvaluator({
            "chapter_type": "normal",
            "content": "悬念揭晓"
        })
        
        triggers = [
            {"type": "condition", "expression": "chapter_type != 'transitional'"},
            {"type": "keyword", "keywords": ["悬念"], "min_count": 1}
        ]
        
        assert evaluator.should_trigger(triggers) is True

    def test_no_content(self):
        """测试无内容情况"""
        evaluator = ConditionEvaluator({
            "chapter_number": 15,
            "content": ""
        })
        
        assert evaluator.check_keywords(["某个词"], min_count=1) is False

    def test_boolean_context(self):
        """测试布尔上下文"""
        evaluator = ConditionEvaluator({
            "has_unresolved_hook": True,
            "has_pacing_risk": False
        })
        
        assert evaluator.eval_condition("has_unresolved_hook == True") is True
        assert evaluator.eval_condition("has_pacing_risk == True") is False

    def test_custom_context(self):
        """测试自定义上下文"""
        evaluator = ConditionEvaluator({
            "word_count": 3000,
            "is_key_chapter": True,
            "user_requested": False
        })
        
        assert evaluator.eval_condition("word_count >= 2000 and is_key_chapter") is True
        assert evaluator.eval_condition("user_requested == False") is True

    def test_trusted_names_only(self):
        """测试仅允许预定义变量"""
        import builtins
        evaluator = ConditionEvaluator({})
        
        result = evaluator.eval_condition("__import__('os')")
        assert result is False

    def test_complex_expression(self):
        """测试复杂表达式"""
        evaluator = ConditionEvaluator({
            "chapter_number": 25,
            "chapter_type": "climax"
        })
        
        expr = "(chapter_number >= 10 and chapter_number < 50) or chapter_type == 'climax'"
        assert evaluator.eval_condition(expr) is True
        
        expr = "chapter_number >= 100 and chapter_type == 'arc_end'"
        assert evaluator.eval_condition(expr) is False
