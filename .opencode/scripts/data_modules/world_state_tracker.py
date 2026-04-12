# -*- coding: utf-8 -*-
"""
世界观状态追踪器

功能：
- 追踪角色战力等级变化
- 追踪道具/法宝状态
- 追踪势力实力变化
- 记录时间线事件
- 追踪角色关系弧线

用于宏观一致性审查器检测战力崩坏、道具复用、时间线矛盾等。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from logging import getLogger

logger = getLogger(__name__)


@dataclass
class PowerLevel:
    """战力等级"""
    name: str           # 等级名称（如 "斗皇"）
    value: int          # 数值（用于比较）
    chapter: int        # 首次出现章节
    source: str         # 来源（修炼/奇遇/传承等）


@dataclass
class ItemStatus:
    """道具状态"""
    name: str
    status: str          # intact / damaged / destroyed / unknown
    durability: int = 100 # 耐久度 0-100
    last_seen_chapter: int = 0


@dataclass
class FactionPower:
    """势力实力"""
    name: str
    power_level: int     # 实力数值（1-10）
    change_history: List[Tuple[int, int]] = field(default_factory=list)  # (chapter, power_change)


@dataclass
class RelationshipArc:
    """关系弧线"""
    character_a: str
    character_b: str
    current_value: float  # -1.0 到 1.0 (敌对到亲密)
    events: List[Dict] = field(default_factory=list)


@dataclass
class TimelineEvent:
    """时间线事件"""
    chapter: int
    event_type: str      # power_up / item_destroy / relationship_change / etc.
    description: str
    affected_entities: List[str] = field(default_factory=list)


class WorldStateTracker:
    """世界观状态追踪器"""
    
    # 默认战力等级映射（可扩展）
    DEFAULT_POWER_LEVELS = {
        "筑基": 1, "金丹": 2, "元婴": 3, "化神": 4, "炼虚": 5,
        "合体": 6, "大乘": 7, "渡劫": 8,
        "斗者": 1, "斗师": 2, "大斗师": 3, "斗灵": 4, "斗王": 5,
        "斗皇": 6, "斗宗": 7, "斗尊": 8, "斗帝": 9,
    }
    
    def __init__(self, config=None):
        self.config = config
        self._power_levels: Dict[str, List[PowerLevel]] = {}  # character_id -> [PowerLevel(...)]
        self._item_status: Dict[str, ItemStatus] = {}          # item_name -> ItemStatus(...)
        self._faction_power: Dict[str, FactionPower] = {}      # faction_name -> FactionPower(...)
        self._timeline: List[TimelineEvent] = []
        self._relationship_arcs: Dict[Tuple[str, str], RelationshipArc] = {}
        
        if config:
            power_levels_cfg = getattr(config, "world_power_levels", None)
            if power_levels_cfg:
                self.DEFAULT_POWER_LEVELS = dict(power_levels_cfg)
            
            resolver = getattr(config, "resolve_world_preset", None)
            if resolver:
                preset = resolver()
                if preset.get("power_levels"):
                    self.DEFAULT_POWER_LEVELS = dict(preset["power_levels"])
    
    def load_from_state(self, state_data: Dict) -> None:
        """从 state.json 加载历史状态"""
        if not state_data:
            return
        
        characters = state_data.get("characters", {})
        for char_id, char_data in characters.items():
            power_name = char_data.get("power_level", "")
            if power_name:
                value = self._parse_power_value(power_name)
                self._power_levels[char_id] = [
                    PowerLevel(power_name, value, char_data.get("first_appearance", 1), "state_load")
                ]
        
        items = state_data.get("items", {})
        for item_name, item_data in items.items():
            self._item_status[item_name] = ItemStatus(
                name=item_name,
                status=item_data.get("status", "unknown"),
                durability=item_data.get("durability", 100),
                last_seen_chapter=item_data.get("last_seen_chapter", 0)
            )
        
        factions = state_data.get("factions", {})
        for faction_name, faction_data in factions.items():
            self._faction_power[faction_name] = FactionPower(
                name=faction_name,
                power_level=faction_data.get("power_level", 5),
                change_history=[]
            )
    
    def load_from_index(self, index_manager) -> None:
        """从 index.db 加载状态"""
        try:
            for entity in index_manager.get_core_entities():
                entity_type = entity.get("type", "")
                if entity_type == "角色":
                    current = entity.get("current", {})
                    power = current.get("power_level", "")
                    if power:
                        value = self._parse_power_value(power)
                        self._power_levels[entity["id"]] = [
                            PowerLevel(power, value, entity.get("first_appearance", 1), "index_load")
                        ]
                
                elif entity_type == "势力":
                    current = entity.get("current", {})
                    self._faction_power[entity["canonical_name"]] = FactionPower(
                        name=entity["canonical_name"],
                        power_level=current.get("power_level", 5),
                        change_history=[]
                    )
        except Exception as e:
            logger.warning("从 index 加载状态失败: %s", e)
    
    def record_chapter_events(self, chapter: int, events: List[Dict]) -> None:
        """记录本章产生的状态变化"""
        for event in events:
            event_type = event.get("type", "")
            
            if event_type == "power_up":
                self._handle_power_up(chapter, event)
            elif event_type == "item_destroy":
                self._handle_item_destroy(chapter, event)
            elif event_type == "item_damage":
                self._handle_item_damage(chapter, event)
            elif event_type == "faction_power_change":
                self._handle_faction_change(chapter, event)
            elif event_type == "relationship_change":
                self._handle_relationship_change(chapter, event)
            
            self._timeline.append(TimelineEvent(
                chapter=chapter,
                event_type=event_type,
                description=event.get("description", ""),
                affected_entities=event.get("affected", [])
            ))
    
    def get_current_power(self, character_id: str) -> Optional[int]:
        """获取角色当前战力值"""
        levels = self._power_levels.get(character_id, [])
        if levels:
            return levels[-1].value
        return None
    
    def get_power_history(self, character_id: str) -> List[PowerLevel]:
        """获取角色战力历史"""
        return self._power_levels.get(character_id, [])
    
    def get_item_status(self, item_name: str) -> str:
        """获取道具状态"""
        item = self._item_status.get(item_name)
        return item.status if item else "unknown"
    
    def get_power_gap(self, character_id: str, scene_power: int) -> int:
        """计算角色与场景战力的差距"""
        current_power = self.get_current_power(character_id)
        if current_power is None:
            return 0
        return scene_power - current_power
    
    def get_faction_power(self, faction_name: str) -> Optional[int]:
        """获取势力实力"""
        faction = self._faction_power.get(faction_name)
        return faction.power_level if faction else None
    
    def get_relationship(self, char_a: str, char_b: str) -> Optional[float]:
        """获取两角色关系值 (-1.0 ~ 1.0)"""
        key = (char_a, char_b)
        arc = self._relationship_arcs.get(key)
        return arc.current_value if arc else None
    
    def check_power_jump(self, character_id: str, new_power: int, threshold: int = 3) -> bool:
        """检测战力是否跨越阈值"""
        current_power = self.get_current_power(character_id)
        if current_power is None:
            return False
        return (new_power - current_power) > threshold
    
    def get_timeline_events(self, since_chapter: int = 0) -> List[TimelineEvent]:
        """获取时间线事件"""
        return [e for e in self._timeline if e.chapter >= since_chapter]
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "tracked_characters": len(self._power_levels),
            "tracked_items": len(self._item_status),
            "tracked_factions": len(self._faction_power),
            "tracked_relationships": len(self._relationship_arcs),
            "timeline_events": len(self._timeline),
        }
    
    # ==================== 私有方法 ====================
    
    def _parse_power_value(self, power_name: str) -> int:
        """解析战力名称为数值"""
        power_name = power_name.strip()
        
        if power_name in self.DEFAULT_POWER_LEVELS:
            return self.DEFAULT_POWER_LEVELS[power_name]
        
        match = re.search(r"(\d+)", power_name)
        if match:
            return int(match.group(1))
        
        return 5  # 默认中等
    
    def _handle_power_up(self, chapter: int, event: Dict):
        """处理战力提升事件"""
        char_id = event.get("character_id")
        new_power = event.get("power_level", "")
        value = self._parse_power_value(new_power)
        
        if char_id not in self._power_levels:
            self._power_levels[char_id] = []
        
        self._power_levels[char_id].append(PowerLevel(
            name=new_power,
            value=value,
            chapter=chapter,
            source=event.get("source", "unknown")
        ))
    
    def _handle_item_destroy(self, chapter: int, event: Dict):
        """处理道具销毁事件"""
        item_name = event.get("item_name")
        self._item_status[item_name] = ItemStatus(
            name=item_name,
            status="destroyed",
            durability=0,
            last_seen_chapter=chapter
        )
    
    def _handle_item_damage(self, chapter: int, event: Dict):
        """处理道具损坏事件"""
        item_name = event.get("item_name")
        durability = event.get("durability", 50)
        
        self._item_status[item_name] = ItemStatus(
            name=item_name,
            status="damaged" if durability > 0 else "destroyed",
            durability=durability,
            last_seen_chapter=chapter
        )
    
    def _handle_faction_change(self, chapter: int, event: Dict):
        """处理势力变化事件"""
        faction_name = event.get("faction_name")
        change = event.get("change", 0)
        
        if faction_name in self._faction_power:
            faction = self._faction_power[faction_name]
            faction.power_level = max(1, min(10, faction.power_level + change))
            faction.change_history.append((chapter, change))
        else:
            self._faction_power[faction_name] = FactionPower(
                name=faction_name,
                power_level=5 + change,
                change_history=[(chapter, change)]
            )
    
    def _handle_relationship_change(self, chapter: int, event: Dict):
        """处理关系变化事件"""
        char_a = event.get("character_a")
        char_b = event.get("character_b")
        change = event.get("change", 0.1)
        
        key = (char_a, char_b)
        if key in self._relationship_arcs:
            arc = self._relationship_arc[key]
            arc.current_value = max(-1.0, min(1.0, arc.current_value + change))
            arc.events.append({"chapter": chapter, "change": change})
        else:
            self._relationship_arcs[key] = RelationshipArc(
                character_a=char_a,
                character_b=char_b,
                current_value=change,
                events=[{"chapter": chapter, "change": change}]
            )