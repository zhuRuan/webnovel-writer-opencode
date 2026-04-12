# -*- coding: utf-8 -*-
"""
世界观一致性检查器

功能：
- 检测战力崩坏（越级挑战、战力倒挂）
- 检测道具/法宝一致性（已销毁道具复用）
- 检测势力平衡（势力实力突变）
- 检测关系弧线（好感度突变）

用于防止长篇网文创作中的设定崩塌。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from logging import getLogger

from .world_state_tracker import WorldStateTracker

logger = getLogger(__name__)


@dataclass
class ConsistencyIssue:
    """一致性问题"""
    issue_id: str          # 如 "POWER_001"
    severity: str          # critical / high / medium / low / warning
    message: str            # 问题描述
    location: str          # 位置（章节/场景）
    suggestion: str = ""   # 修复建议


class WorldConsistencyChecker:
    """世界观一致性检查器"""
    
    # 默认配置参数（当 config 为 None 时使用）
    DEFAULT_POWER_JUMP_THRESHOLD = 3
    DEFAULT_ITEM_DESTROYED_SEVERITY = "high"
    DEFAULT_FACTION_CHANGE_THRESHOLD = 0.2
    DEFAULT_RELATIONSHIP_JUMP_THRESHOLD = 0.5
    
    # 默认战力等级关键词
    DEFAULT_POWER_KEYWORDS = [
        "筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫",
        "斗者", "斗师", "大斗师", "斗灵", "斗王", "斗皇", "斗宗", "斗尊", "斗帝",
    ]
    
    # 默认已销毁/已损坏关键词
    DEFAULT_ITEM_DESTROYED_KEYWORDS = [
        "碎裂", "报废", "毁灭", "消散", "化为灰烬", "彻底损毁",
        "失去光泽", "暗淡无光", "裂纹", "破碎",
    ]
    
    def __init__(self, config=None, world_tracker: WorldStateTracker = None):
        self.config = config
        self.world_tracker = world_tracker or WorldStateTracker(config)
        
        if config:
            self.POWER_JUMP_THRESHOLD = getattr(config, "power_jump_threshold", self.DEFAULT_POWER_JUMP_THRESHOLD)
            self.ITEM_DESTROYED_SEVERITY = "high"
            self.FACTION_CHANGE_THRESHOLD = getattr(config, "faction_change_threshold", self.DEFAULT_FACTION_CHANGE_THRESHOLD)
            self.RELATIONSHIP_JUMP_THRESHOLD = getattr(config, "relationship_jump_threshold", self.DEFAULT_RELATIONSHIP_JUMP_THRESHOLD)
            
            power_levels_cfg = getattr(config, "world_power_levels", None)
            if power_levels_cfg:
                self.world_tracker.DEFAULT_POWER_LEVELS = dict(power_levels_cfg)
            
            self.POWER_KEYWORDS = getattr(config, "world_power_keywords", self.DEFAULT_POWER_KEYWORDS)
            self.ITEM_DESTROYED_KEYWORDS = getattr(config, "world_item_destroy_keywords", self.DEFAULT_ITEM_DESTROYED_KEYWORDS)
            
            resolver = getattr(config, "resolve_world_preset", None)
            if resolver:
                preset = resolver()
                if preset.get("power_levels"):
                    self.world_tracker.DEFAULT_POWER_LEVELS = dict(preset["power_levels"])
                if preset.get("power_keywords"):
                    self.POWER_KEYWORDS = list(preset["power_keywords"])
        else:
            self.POWER_JUMP_THRESHOLD = self.DEFAULT_POWER_JUMP_THRESHOLD
            self.ITEM_DESTROYED_SEVERITY = self.DEFAULT_ITEM_DESTROYED_SEVERITY
            self.FACTION_CHANGE_THRESHOLD = self.DEFAULT_FACTION_CHANGE_THRESHOLD
            self.RELATIONSHIP_JUMP_THRESHOLD = self.DEFAULT_RELATIONSHIP_JUMP_THRESHOLD
            self.POWER_KEYWORDS = self.DEFAULT_POWER_KEYWORDS
            self.ITEM_DESTROYED_KEYWORDS = self.DEFAULT_ITEM_DESTROYED_KEYWORDS
    
    def check_chapter(self, chapter: int, content: str, chapter_context: Dict = None) -> List[ConsistencyIssue]:
        """
        检查章节内容的一致性问题
        
        Args:
            chapter: 章节号
            content: 章节内容
            chapter_context: 章节上下文（可选）
        
        Returns:
            问题列表
        """
        issues = []
        
        logger.info("开始检查第 %d 章世界观一致性", chapter)
        
        # 1. 战力崩坏检测
        power_issues = self._check_power_consistency(content, chapter)
        issues.extend(power_issues)
        
        # 2. 道具/法宝一致性检测
        item_issues = self._check_item_consistency(content, chapter)
        issues.extend(item_issues)
        
        # 3. 势力平衡检测
        faction_issues = self._check_faction_balance(content, chapter)
        issues.extend(faction_issues)
        
        # 4. 关系弧线一致性（轻量级）
        relationship_issues = self._check_relationship_arc(content, chapter)
        issues.extend(relationship_issues)
        
        # 5. 时间线矛盾检测
        timeline_issues = self._check_timeline_consistency(content, chapter)
        issues.extend(timeline_issues)
        
        logger.info("第 %d 章检查完成，发现 %d 个问题", chapter, len(issues))
        
        return issues
    
    def _check_power_consistency(self, content: str, chapter: int) -> List[ConsistencyIssue]:
        """检测战力一致性"""
        issues = []
        
        # 提取本章提到的战力等级
        current_powers = self._extract_power_levels(content)
        
        for power_name, context in current_powers:
            value = self.world_tracker.DEFAULT_POWER_LEVELS.get(power_name, 5)
            
            # 检测越级挑战
            if "越级" in context or "跨级" in context or "越阶" in context:
                for char_id, char_power in self.world_tracker._power_levels.items():
                    if char_power:
                        current_value = char_power[-1].value
                        if value - current_value > self.POWER_JUMP_THRESHOLD:
                            issues.append(ConsistencyIssue(
                                issue_id="POWER_001",
                                severity="high",
                                message=f"战力跨度过大: {power_name} vs 当前 {current_value}",
                                location=f"第{chapter}章",
                                suggestion=f"建议增加过度阶段或削弱敌方战力"
                            ))
        
        # 检测战力倒退
        for char_id, levels in self.world_tracker._power_levels.items():
            if len(levels) >= 2:
                last = levels[-1]
                previous = levels[-2]
                if last.value < previous.value:
                    issues.append(ConsistencyIssue(
                        issue_id="POWER_002",
                        severity="critical",
                        message=f"战力倒退: {char_id} 从 {previous.name} 降至 {last.name}",
                        location=f"第{chapter}章",
                        suggestion="检查是否需要解释战力暂时下降的原因（如封印、损耗）"
                    ))
        
        return issues
    
    def _check_item_consistency(self, content: str, chapter: int) -> List[ConsistencyIssue]:
        """检测道具一致性"""
        issues = []
        
        # 检测是否使用了已销毁的道具
        for item_name, status in self.world_tracker._item_status.items():
            if status.status == "destroyed":
                if item_name in content:
                    issues.append(ConsistencyIssue(
                        issue_id="ITEM_001",
                        severity=self.ITEM_DESTROYED_SEVERITY,
                        message=f"使用已销毁道具: [{item_name}]",
                        location=f"第{chapter}章",
                        suggestion=f"道具已在第{status.last_seen_chapter}章销毁，不可复用"
                    ))
            
            elif status.status == "damaged":
                if item_name in content and ("全力" in content or "催动" in content or "爆发" in content):
                    issues.append(ConsistencyIssue(
                        issue_id="ITEM_002",
                        severity="medium",
                        message=f"使用已损坏道具: [{item_name}] (耐久度: {status.durability}%)",
                        location=f"第{chapter}章",
                        suggestion="高强度使用可能彻底损坏道具"
                    ))
        
        # 检测新增的道具销毁/损坏提及
        for keyword in self.ITEM_DESTROYED_KEYWORDS:
            if keyword in content:
                match = re.search(rf"(.+?){keyword}", content)
                if match:
                    item_name = match.group(1).strip()
                    if item_name and item_name not in self.world_tracker._item_status:
                        self.world_tracker._item_status[item_name] = type('obj', (object,), {
                            'name': item_name,
                            'status': 'destroyed' if '彻底' in keyword else 'damaged',
                            'durability': 0,
                            'last_seen_chapter': chapter
                        })()
        
        return issues
    
    def _check_faction_balance(self, content: str, chapter: int) -> List[ConsistencyIssue]:
        """检测势力平衡"""
        issues = []
        
        # 提取本章提到的势力实力变化
        faction_changes = self._extract_faction_changes(content)
        
        for faction_name, change_type in faction_changes:
            current_power = self.world_tracker.get_faction_power(faction_name)
            
            if current_power is None:
                continue
            
            if change_type == "大幅提升":
                if current_power >= 8:
                    issues.append(ConsistencyIssue(
                        issue_id="FACTION_001",
                        severity="medium",
                        message=f"势力 [{faction_name}] 实力过强 (等级: {current_power})",
                        location=f"第{chapter}章",
                        suggestion="考虑引入克制势力或内部矛盾"
                    ))
            
            elif change_type == "覆灭":
                if current_power >= 7:
                    issues.append(ConsistencyIssue(
                        issue_id="FACTION_002",
                        severity="warning",
                        message=f"强势力 [{faction_name}] 突然覆灭",
                        location=f"第{chapter}章",
                        suggestion="确保有足够铺垫，避免突兀"
                    ))
        
        return issues
    
    def _check_relationship_arc(self, content: str, chapter: int) -> List[ConsistencyIssue]:
        """检测关系弧线一致性"""
        issues = []
        
        # 检测好感度突变
        for (char_a, char_b), arc in self.world_tracker._relationship_arcs.items():
            if len(arc.events) >= 2:
                last_event = arc.events[-1]
                prev_event = arc.events[-2]
                
                if last_event["chapter"] == chapter:
                    change = abs(last_event["change"] - prev_event["change"])
                    
                    if change > self.RELATIONSHIP_JUMP_THRESHOLD:
                        issues.append(ConsistencyIssue(
                            issue_id="RELATIONSHIP_001",
                            severity="warning",
                            message=f"关系突变: {char_a} 与 {char_b} 好感度变化 {change:.1f}",
                            location=f"第{chapter}章",
                            suggestion="增加过渡场景，避免 abrupt 转变"
                        ))
        
        # 提取本章新的关系变化
        conflict_keywords = ["大打出手", "反目", "决裂", "仇恨"]
        intimacy_keywords = ["亲密", "拥抱", "表白", "告白", "生死相许"]
        
        for keyword in conflict_keywords:
            if keyword in content:
                for (char_a, char_b) in self.world_tracker._relationship_arcs:
                    rel_value = self.world_tracker.get_relationship(char_a, char_b)
                    if rel_value and rel_value > 0.3:
                        issues.append(ConsistencyIssue(
                            issue_id="RELATIONSHIP_002",
                            severity="warning",
                            message=f"关系 abrupt: {char_a} 与 {char_b} 突现冲突（之前正向关系: {rel_value:.1f}）",
                            location=f"第{chapter}章",
                            suggestion="添加冲突渐近过程"
                        ))
        
        return issues
    
    def _check_timeline_consistency(self, content: str, chapter: int) -> List[ConsistencyIssue]:
        """检测时间线矛盾"""
        issues = []
        
        # 时间关键词
        time_patterns = [
            (r"(\d+)年前", "past"),
            (r"(\d+)年后", "future"),
            (r"第(\d+)章", "specific"),
            (r"上次", "relative"),
            (r"这次", "relative"),
        ]
        
        for pattern, time_type in time_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                # 简单验证：确保时间跨度合理
                if time_type == "past":
                    years = int(match.group(1))
                    if years > 100:
                        issues.append(ConsistencyIssue(
                            issue_id="TIMELINE_001",
                            severity="medium",
                            message=f"时间跨度异常: {years}年前",
                            location=f"第{chapter}章",
                            suggestion="检查是否与设定集冲突"
                        ))
        
        return issues
    
    def _extract_power_levels(self, content: str) -> List[tuple]:
        """提取内容中的战力等级"""
        results = []
        for keyword in self.POWER_KEYWORDS:
            if keyword in content:
                # 提取上下文
                idx = content.find(keyword)
                start = max(0, idx - 20)
                end = min(len(content), idx + 20)
                context = content[start:end]
                results.append((keyword, context))
        return results
    
    def _extract_faction_changes(self, content: str) -> List[tuple]:
        """提取势力变化"""
        results = []
        
        patterns = [
            (r"(.+)实力大增", "大幅提升"),
            (r"(.+)实力暴涨", "大幅提升"),
            (r"(.+)被覆灭", "覆灭"),
            (r"(.+)灭亡", "覆灭"),
            (r"(.+)崛起", "崛起"),
        ]
        
        for pattern, change_type in patterns:
            match = re.search(pattern, content)
            if match:
                results.append((match.group(1), change_type))
        
        return results
    
    def record_events(self, chapter: int, events: List[Dict]):
        """记录本章事件到追踪器"""
        self.world_tracker.record_chapter_events(chapter, events)
    
    def get_summary(self) -> Dict:
        """获取检查摘要"""
        return {
            "tracked_entities": self.world_tracker.get_stats(),
            "power_threshold": self.POWER_JUMP_THRESHOLD,
            "relationship_jump_threshold": self.RELATIONSHIP_JUMP_THRESHOLD,
        }