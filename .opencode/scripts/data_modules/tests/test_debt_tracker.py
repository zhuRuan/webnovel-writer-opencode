# -*- coding: utf-8 -*-
"""
DebtTracker 测试
"""

import pytest

from ..debt_tracker import DebtTracker, DebtType, DebtPriority


class TestDebtTracker:
    """DebtTracker 测试"""

    def test_create_debt(self):
        """测试创建债务"""
        tracker = DebtTracker()
        debt = tracker.create_debt(
            DebtType.EXPLICIT_FORESADOW,
            "神秘玉佩",
            chapter=1,
            priority=DebtPriority.HIGH
        )
        
        assert debt.debt_id == "DEBT_0001"
        assert debt.content == "神秘玉佩"
        assert debt.created_chapter == 1
        assert debt.repaid is False

    def test_parse_explicit_debts(self):
        """测试解析显式伏笔"""
        tracker = DebtTracker()
        content = "主角意外发现[伏笔:神秘玉佩]的线索"
        debts = tracker.parse_explicit_debts(content, chapter=1)
        
        assert len(debts) == 1
        assert debts[0].content == "神秘玉佩"
        assert debts[0].debt_type == DebtType.EXPLICIT_FORESADOW

    def test_parse_multiple_debts(self):
        """测试解析多个伏笔"""
        tracker = DebtTracker()
        content = "发现[伏笔:玉佩]和[伏笔:地图]"
        debts = tracker.parse_explicit_debts(content, chapter=1)
        
        assert len(debts) == 2

    def test_repay_debt(self):
        """测试偿还债务"""
        tracker = DebtTracker()
        tracker.create_debt(DebtType.EXPLICIT_FORESADOW, "玉佩", chapter=1)
        
        repaid = tracker.detect_and_repay("[回收:玉佩]", chapter=5)
        
        assert len(repaid) == 1
        assert repaid[0].repaid is True
        assert repaid[0].repaid_chapter == 5

    def test_check_active_debts(self):
        """测试获取活跃债务"""
        tracker = DebtTracker()
        tracker.create_debt(DebtType.EXPLICIT_FORESADOW, "债1", chapter=1)
        tracker.create_debt(DebtType.EXPLICIT_FORESADOW, "债2", chapter=2)
        
        tracker.mark_repaid("DEBT_0001", 3)
        
        active = tracker.check_active_debts()
        assert len(active) == 1
        assert active[0].debt_id == "DEBT_0002"

    def test_high_priority_debts(self):
        """测试高优先级债务"""
        tracker = DebtTracker()
        tracker.create_debt(DebtType.EXPLICIT_FORESADOW, "高优先", chapter=1, priority=DebtPriority.HIGH)
        tracker.create_debt(DebtType.SEMANTIC_PROMISE, "普通", chapter=2, priority=DebtPriority.MEDIUM)
        
        high_prio = tracker.get_high_priority_debts()
        assert len(high_prio) == 1
        assert high_prio[0].content == "高优先"

    def test_can_write_climax_blocked_by_threshold(self):
        """测试债务过多阻止高潮"""
        tracker = DebtTracker()
        for i in range(5):
            tracker.create_debt(DebtType.EXPLICIT_FORESADOW, f"债{i}", chapter=i+1)
        
        can_write, reason = tracker.can_write_climax(10, is_climax=True)  #高潮章节才阻断
        assert can_write is False
        assert "活跃债务过多" in reason

    def test_can_write_climax_blocked_by_high_priority(self):
        """测试高优先级债务阻止高潮"""
        tracker = DebtTracker()
        tracker.create_debt(DebtType.EXPLICIT_FORESADOW, "重要伏笔", chapter=1, priority=DebtPriority.CRITICAL)
        
        can_write, reason = tracker.can_write_climax(10)
        assert can_write is False
        assert "高优先级债务" in reason

    def test_can_write_climax_allowed(self):
        """测试允许写高潮"""
        tracker = DebtTracker()
        can_write, reason = tracker.can_write_climax(10)
        assert can_write is True

    def test_get_debt_summary(self):
        """测试债务摘要"""
        tracker = DebtTracker()
        tracker.create_debt(DebtType.EXPLICIT_FORESADOW, "债1", chapter=1, priority=DebtPriority.HIGH)
        
        summary = tracker.get_debt_summary()
        
        assert summary["total"] == 1
        assert summary["active"] == 1
        assert summary["high_priority"] == 1
        assert summary["by_type"]["explicit"] == 1