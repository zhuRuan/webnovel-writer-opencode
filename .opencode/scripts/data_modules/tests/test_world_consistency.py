# -*- coding: utf-8 -*-
"""
世界观一致性检查器测试
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_modules.world_state_tracker import WorldStateTracker, PowerLevel, ItemStatus, FactionPower
from data_modules.world_consistency_checker import WorldConsistencyChecker, ConsistencyIssue


class TestWorldStateTracker:
    """WorldStateTracker 测试"""

    def test_power_level_tracking(self):
        """测试战力等级追踪"""
        tracker = WorldStateTracker()
        
        tracker._power_levels["xiaoyan"] = [
            PowerLevel("斗师", 2, 1, "修炼"),
            PowerLevel("斗灵", 4, 5, "奇遇"),
        ]
        
        assert tracker.get_current_power("xiaoyan") == 4
        history = tracker.get_power_history("xiaoyan")
        assert len(history) == 2

    def test_power_jump_detection(self):
        """测试战力跨越检测"""
        tracker = WorldStateTracker()
        tracker._power_levels["xiaoyan"] = [
            PowerLevel("斗师", 2, 1, "修炼"),
        ]
        
        assert tracker.check_power_jump("xiaoyan", 6, threshold=3) is True
        assert tracker.check_power_jump("xiaoyan", 5, threshold=3) is False

    def test_item_status_tracking(self):
        """测试道具状态追踪"""
        tracker = WorldStateTracker()
        
        tracker._item_status["玄重尺"] = ItemStatus(
            name="玄重尺", status="intact", durability=100, last_seen_chapter=5
        )
        
        assert tracker.get_item_status("玄重尺") == "intact"
        
        tracker._item_status["玄重尺"] = ItemStatus(
            name="玄重尺", status="destroyed", durability=0, last_seen_chapter=10
        )
        
        assert tracker.get_item_status("玄重尺") == "destroyed"

    def test_relationship_arc_tracking(self):
        """测试关系弧线追踪"""
        tracker = WorldStateTracker()
        
        tracker._relationship_arcs[("萧炎", "云韵")] = type('obj', (object,), {
            'character_a': '萧炎',
            'character_b': '云韵',
            'current_value': 0.5,
            'events': [
                {'chapter': 3, 'change': 0.3},
                {'chapter': 5, 'change': 0.2},
            ]
        })()
        
        rel = tracker.get_relationship("萧炎", "云韵")
        assert rel == 0.5

    def test_faction_power_tracking(self):
        """测试势力实力追踪"""
        tracker = WorldStateTracker()
        
        tracker._faction_power["迦南学院"] = FactionPower(
            name="迦南学院", power_level=8,
            change_history=[(5, 1), (10, -1)]
        )
        
        power = tracker.get_faction_power("迦南学院")
        assert power == 8

    def test_power_value_parsing(self):
        """测试战力值解析"""
        tracker = WorldStateTracker()
        
        assert tracker._parse_power_value("斗皇") == 6
        assert tracker._parse_power_value("元婴") == 3
        assert tracker._parse_power_value("斗宗") == 7
        assert tracker._parse_power_value("未知等级") == 5

    def test_timeline_events(self):
        """测试时间线事件"""
        tracker = WorldStateTracker()
        
        tracker.record_chapter_events(5, [
            {"type": "power_up", "character_id": "xiaoyan", "power_level": "斗灵"},
            {"type": "item_destroy", "item_name": "玄重尺"},
        ])
        
        events = tracker.get_timeline_events(since_chapter=5)
        assert len(events) == 2

    def test_load_from_state(self):
        """测试从 state 加载"""
        tracker = WorldStateTracker()
        
        state_data = {
            "characters": {
                "xiaoyan": {"power_level": "斗皇", "first_appearance": 1}
            },
            "items": {
                "玄重尺": {"status": "intact", "durability": 100}
            }
        }
        
        tracker.load_from_state(state_data)
        
        assert tracker.get_current_power("xiaoyan") == 6
        assert tracker.get_item_status("玄重尺") == "intact"

    def test_get_stats(self):
        """测试统计信息"""
        tracker = WorldStateTracker()
        
        tracker._power_levels["a"] = []
        tracker._item_status["b"] = None
        tracker._faction_power["c"] = None
        tracker._relationship_arcs[("x", "y")] = None
        
        stats = tracker.get_stats()
        
        assert stats["tracked_characters"] == 1
        assert stats["tracked_items"] == 1
        assert stats["tracked_factions"] == 1
        assert stats["tracked_relationships"] == 1


class TestWorldConsistencyChecker:
    """WorldConsistencyChecker 测试"""

    def test_detect_destroyed_item_reuse(self):
        """检测已销毁道具复用"""
        tracker = WorldStateTracker()
        tracker._item_status["玄重尺"] = ItemStatus(
            name="玄重尺", status="destroyed", durability=0, last_seen_chapter=10
        )
        
        checker = WorldConsistencyChecker(world_tracker=tracker)
        
        issues = checker._check_item_consistency("萧炎挥舞着玄重尺杀向敌人", 15)
        
        assert len(issues) >= 1
        assert any(i.issue_id == "ITEM_001" for i in issues)

    def test_detect_power_regression(self):
        """检测战力倒退"""
        tracker = WorldStateTracker()
        tracker._power_levels["xiaoyan"] = [
            PowerLevel("斗灵", 4, 5, "修炼"),
            PowerLevel("斗师", 2, 10, "退化"),
        ]
        
        checker = WorldConsistencyChecker(world_tracker=tracker)
        
        issues = checker._check_power_consistency("萧炎境界跌落", 10)
        
        assert len(issues) >= 1
        assert any(i.issue_id == "POWER_002" for i in issues)

    def test_detect_relationship_jump(self):
        """检测关系突变"""
        tracker = WorldStateTracker()
        tracker._relationship_arcs[("A", "B")] = type('obj', (object,), {
            'character_a': 'A',
            'character_b': 'B',
            'current_value': 0.8,
            'events': [
                {'chapter': 5, 'change': 0.3},
                {'chapter': 10, 'change': 0.5},
            ]
        })()
        
        checker = WorldConsistencyChecker(world_tracker=tracker)
        
        issues = checker._check_relationship_arc("A和B大打出手", 10)
        
        assert len(issues) >= 1

    def test_check_chapter_integration(self):
        """测试章节检查集成"""
        tracker = WorldStateTracker()
        tracker._item_status["武器"] = ItemStatus(
            name="武器", status="destroyed", durability=0, last_seen_chapter=3
        )
        
        checker = WorldConsistencyChecker(world_tracker=tracker)
        
        content = "萧炎使用武器击败敌人"
        issues = checker.check_chapter(10, content)
        
        assert isinstance(issues, list)

    def test_power_extraction(self):
        """测试战力等级提取"""
        checker = WorldConsistencyChecker()
        
        results = checker._extract_power_levels("萧炎突破到斗皇境界")
        
        assert len(results) >= 1
        assert any(p[0] == "斗皇" for p in results)

    def test_faction_change_extraction(self):
        """测试势力变化提取"""
        checker = WorldConsistencyChecker()
        
        results = checker._extract_faction_changes("迦南学院实力大增")
        
        assert len(results) >= 1
        assert results[0][1] == "大幅提升"

    def test_timeline_check(self):
        """测试时间线检查"""
        checker = WorldConsistencyChecker()
        
        issues = checker._check_timeline_consistency("200年前萧炎出生", 10)
        
        assert len(issues) >= 1
        assert issues[0].issue_id == "TIMELINE_001"

    def test_summary(self):
        """测试摘要获取"""
        tracker = WorldStateTracker()
        checker = WorldConsistencyChecker(world_tracker=tracker)
        
        summary = checker.get_summary()
        
        assert "power_threshold" in summary
        assert summary["power_threshold"] == 3