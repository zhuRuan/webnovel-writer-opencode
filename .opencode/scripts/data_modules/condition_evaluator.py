# -*- coding: utf-8 -*-
"""
条件评估器 - 用于解析和评估审查器触发条件

支持两种触发类型：
1. condition: Python 表达式求值
2. keyword: 关键词匹配

安全设计：
- eval 仅允许基本运算符和预定义变量
- 禁止 __builtins__ 和函数调用
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from logging import getLogger

logger = getLogger(__name__)


@dataclass
class TriggerCondition:
    """触发条件"""
    type: str  # "condition" | "keyword"
    expression: str = ""  # condition 类型使用
    keywords: List[str] = None  # keyword 类型使用
    min_count: int = 1  # keyword 类型使用
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


class ConditionEvaluator:
    """轻量级条件评估器"""
    
    _allowed_names: Dict[str, Any] = {
        "True": True,
        "False": False,
        "None": None,
    }
    
    def __init__(self, context: Dict[str, Any]):
        """
        Args:
            context: 章节上下文，包含用于条件判断的变量
                - chapter_type: 章节类型 (normal/climax/transitional/arc_end)
                - chapter_number: 章节号
                - has_unresolved_hook: 是否有未闭合钩子
                - content: 章节内容
                - user_requested: 用户是否显式要求
                - ... 其他自定义字段
        """
        self.context = context
        self._names_cache: Dict[str, Any] = {}
    
    def _get_allowed_names(self) -> Dict[str, Any]:
        """获取 eval 允许的变量名"""
        if self._names_cache:
            return self._names_cache
        
        names = dict(self._allowed_names)
        for key, value in self.context.items():
            if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                names[key] = value
        
        self._names_cache = names
        return names
    
    def eval_condition(self, expression: str) -> bool:
        """
        安全地求值 Python 表达式
        
        Args:
            expression: Python 表达式，如 "chapter_number >= 10"
        
        Returns:
            表达式求值结果（布尔值）
        """
        try:
            names = self._get_allowed_names()
            result = eval(expression, {"__builtins__": {}}, names)
            return bool(result)
        except SyntaxError as e:
            logger.warning("条件表达式语法错误: %s - %s", expression, e)
            return False
        except NameError as e:
            logger.warning("条件表达式变量未定义: %s - %s", expression, e)
            return False
        except Exception as e:
            logger.warning("条件表达式求值失败: %s - %s", expression, e)
            return False
    
    def check_keywords(self, keywords: List[str], min_count: int = 1) -> bool:
        """
        检查内容中是否包含指定关键词
        
        Args:
            keywords: 关键词列表
            min_count: 最少匹配数量
        
        Returns:
            是否满足条件
        """
        content = self.context.get("content", "")
        if not content:
            return False
        
        count = 0
        for kw in keywords:
            if kw in content:
                count += 1
                if count >= min_count:
                    return True
        
        return False
    
    def evaluate(self, conditions: List[TriggerCondition]) -> bool:
        """
        评估所有条件（全 AND 逻辑）
        
        Args:
            conditions: 触发条件列表
        
        Returns:
            所有条件是否满足
        """
        if not conditions:
            return True
        
        for cond in conditions:
            if cond.type == "condition":
                if not self.eval_condition(cond.expression):
                    return False
            elif cond.type == "keyword":
                if not self.check_keywords(cond.keywords, cond.min_count):
                    return False
            else:
                logger.warning("未知条件类型: %s", cond.type)
                return False
        
        return True
    
    def should_trigger(self, triggers: List[Dict]) -> bool:
        """
        判断是否应该触发（兼容旧格式）
        
        Args:
            triggers: 触发条件列表（可能是字符串或字典）
        
        Returns:
            是否应该触发
        """
        conditions = self._parse_triggers(triggers)
        return self.evaluate(conditions)
    
    def _parse_triggers(self, triggers: List[Dict]) -> List[TriggerCondition]:
        """解析触发条件列表"""
        conditions = []
        
        for trigger in triggers:
            if isinstance(trigger, str):
                conditions.append(TriggerCondition(
                    type="condition",
                    expression=trigger
                ))
            elif isinstance(trigger, dict):
                trigger_type = trigger.get("type", "condition")
                
                if trigger_type == "condition":
                    conditions.append(TriggerCondition(
                        type="condition",
                        expression=trigger.get("expression", "")
                    ))
                elif trigger_type == "keyword":
                    conditions.append(TriggerCondition(
                        type="keyword",
                        keywords=trigger.get("keywords", []),
                        min_count=trigger.get("min_count", 1)
                    ))
            else:
                logger.warning("未知触发条件格式: %s", type(trigger))
        
        return conditions


def create_evaluator_from_chapter(
    chapter: int,
    chapter_type: str = "normal",
    content: str = "",
    **kwargs
) -> ConditionEvaluator:
    """
    从章节信息创建评估器
    
    Args:
        chapter: 章节号
        chapter_type: 章节类型
        content: 章节内容
        **kwargs: 其他上下文变量
    
    Returns:
        ConditionEvaluator 实例
    """
    context = {
        "chapter_number": chapter,
        "chapter_type": chapter_type,
        "content": content,
        "has_unresolved_hook": False,
        "user_requested": False,
        **kwargs
    }
    return ConditionEvaluator(context)
