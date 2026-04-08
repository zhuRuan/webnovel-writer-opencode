#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
世界规则与角色状态检查工具（轻量级）

提供轻量级的规则和状态一致性检查，无需调用 LLM。
"""

import re
from typing import Dict, List, Any, Tuple

from .config import get_config


def check_world_rules(chapter_text: str, world_rules: Dict[str, Any]) -> List[Dict]:
    """
    检查章节文本是否违反世界规则。
    
    Args:
        chapter_text: 章节正文
        world_rules: 世界规则字典
        
    Returns:
        issues 列表
    """
    issues = []
    
    magic = world_rules.get("magic_system", {})
    daily_limit_str = magic.get("daily_limit", "")
    if daily_limit_str:
        limit_match = re.search(r"(\d+)", daily_limit_str)
        if limit_match:
            limit = int(limit_match.group(1))
            cast_keywords = ["施法", "使用魔法", "释放法术", "发动魔法", "凝聚灵气", "运转真元"]
            count = 0
            for kw in cast_keywords:
                count += len(re.findall(kw, chapter_text))
            if count > limit:
                issues.append({
                    "type": "RULE_VIOLATION",
                    "rule": "magic_system.daily_limit",
                    "severity": "high",
                    "detail": f"章节中出现{count}次施法动作，超过限制{limit}次",
                    "location": "全文统计"
                })
    
    currency = world_rules.get("currency", {})
    gold_to_copper = currency.get("gold_to_copper", 100)
    exchange_pattern = r"(\d+)\s*金币\s*[=:：]\s*(\d+)\s*铜币"
    matches = re.findall(exchange_pattern, chapter_text)
    for gold, copper in matches:
        expected = int(gold) * gold_to_copper
        if int(copper) != expected:
            issues.append({
                "type": "RULE_VIOLATION",
                "rule": "currency.gold_to_copper",
                "severity": "medium",
                "detail": f"文中写{gold}金币={copper}铜币，规则应为1:{gold_to_copper}（{expected}铜币）",
                "location": f"匹配到 '{gold}金币={copper}铜币'"
            })
    
    return issues


def check_character_states(chapter_text: str, char_states: Dict[str, Dict]) -> List[Dict]:
    """
    检查角色状态是否与已有状态矛盾。
    
    Args:
        chapter_text: 章节正文
        char_states: 角色动态状态字典 {entity_id: {location, health_status, inventory, ...}}
        
    Returns:
        issues 列表
    """
    issues = []
    
    for char_id, state in char_states.items():
        health = state.get("health_status", "")
        if "左臂" in health or "受伤" in health or "轻伤" in health or "重伤" in health:
            conflicting_actions = [
                ("双手持剑", "受伤时难以双手持剑"),
                ("双手举起", "受伤影响双臂动作"),
                ("全力挥动", "受伤影响发挥"),
            ]
            for action, reason in conflicting_actions:
                if action in chapter_text:
                    issues.append({
                        "type": "STATE_CONFLICT",
                        "character": char_id,
                        "severity": "medium",
                        "detail": f"角色健康状态为'{health}'，但文中出现'{action}'：{reason}",
                        "location": f"包含'{action}'的段落"
                    })
        
        location = state.get("location", "")
        if location and ("皇城" in location or "城内" in location):
            far_locations = ["沙漠", "雪原", "海洋", "森林", "山脉"]
            has_travel = any(kw in chapter_text for kw in ["前往", "来到", "传送", "赶赴", " journey"])
            for fl in far_locations:
                if fl in chapter_text and not has_travel:
                    issues.append({
                        "type": "STATE_CONFLICT",
                        "character": char_id,
                        "severity": "low",
                        "detail": f"角色位置为'{location}'，但文中突然出现'{fl}'，缺少转移描述",
                        "location": f"出现'{fl}'的段落"
                    })
                    break
        
        inventory = state.get("inventory", [])
        if inventory and isinstance(inventory, list):
            for item in inventory:
                if item and item in chapter_text:
                    continue
                if "用钥匙" in chapter_text or "开门" in chapter_text:
                    if "钥匙" not in str(inventory):
                        issues.append({
                            "type": "STATE_CONFLICT",
                            "character": char_id,
                            "severity": "high",
                            "detail": f"角色物品栏中没有钥匙，但文中出现用钥匙开门的动作",
                            "location": "包含'钥匙'的段落"
                        })
                        break
    
    return issues


def run_rule_check(chapter_text: str, state_manager) -> Tuple[List[Dict], List[Dict]]:
    """
    执行完整的规则检查，返回 (issues, warnings)
    
    Args:
        chapter_text: 章节正文
        state_manager: StateManager 实例
        
    Returns:
        (issues 列表, warnings 列表)
    """
    world_rules = {}
    try:
        world_rules = state_manager.get_world_rules()
    except Exception:
        pass
    
    char_states = {}
    try:
        for entity_id, entity in state_manager.get_entities_by_type("角色").items():
            ds = state_manager.get_character_dynamic_state(entity_id)
            if ds:
                char_states[entity_id] = ds
    except Exception:
        pass
    
    if not world_rules and not char_states:
        return [], []
    
    all_issues = []
    all_issues.extend(check_world_rules(chapter_text, world_rules))
    all_issues.extend(check_character_states(chapter_text, char_states))
    
    issues_list = [i for i in all_issues if i.get("severity") in ("high", "medium")]
    warnings_list = [i for i in all_issues if i.get("severity") == "low"]
    
    return issues_list, warnings_list


def check_chapter_rules(chapter_text: str, project_root: str) -> Dict[str, Any]:
    """
    便捷函数：直接传入项目路径执行检查
    
    Args:
        chapter_text: 章节正文
        project_root: 项目根目录
        
    Returns:
        检查结果字典
    """
    from .state_manager import StateManager
    
    config = get_config(project_root=project_root)
    sm = StateManager(config)
    
    issues, warnings = run_rule_check(chapter_text, sm)
    
    return {
        "overall_pass": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }
