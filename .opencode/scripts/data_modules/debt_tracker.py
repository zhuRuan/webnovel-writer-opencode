# -*- coding: utf-8 -*-
"""
债务追踪器

功能：
- 追踪网文中的"债务"（伏笔、承诺、断章钩子、逻辑坑位）
- 支持显式标签和语义识别
- 硬约束阻塞和软警告

债务类型：
- EXPLICIT_FORESADOW: [伏笔:xxx] 显式伏笔
- SEMANTIC_PROMISE: 语义承诺（发誓、约定等）
- CHAPTER_HOOK: 断章钩子
- LOGIC_PIT: 逻辑坑位（缺少道具等）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from logging import getLogger

logger = getLogger(__name__)


class DebtType(Enum):
    """债务类型"""
    EXPLICIT_FORESADOW = "explicit"    # [伏笔:xxx]
    SEMANTIC_PROMISE = "promise"       # 语义承诺
    CHAPTER_HOOK = "hook"              # 断章钩子
    LOGIC_PIT = "pit"                # 逻辑坑位


class DebtPriority(Enum):
    """债务优先级"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
    BLOCKING = 5


@dataclass
class Debt:
    """债务"""
    debt_id: str
    debt_type: DebtType
    content: str           # 债务内容
    created_chapter: int
    priority: DebtPriority = DebtPriority.MEDIUM
    repaid: bool = False
    repaid_chapter: Optional[int] = None
    related_chapters: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "debt_id": self.debt_id,
            "debt_type": self.debt_type.value,
            "content": self.content,
            "created_chapter": self.created_chapter,
            "priority": self.priority.value,
            "repaid": self.repaid,
            "repaid_chapter": self.repaid_chapter,
            "related_chapters": self.related_chapters,
        }


class DebtTracker:
    """债务追踪器"""
    
    DEBT_WARNING_THRESHOLD = 3
    
    EXPLICIT_TAG_PATTERN = re.compile(r"\[伏笔[：:](.+?)\]")
    REPAY_PATTERN = re.compile(r"\[回收[：:](.+?)\]")
    PROMISE_KEYWORDS = ["发誓", "约定", "承诺", "保证", "一定要", "必然会"]
    REPAY_KEYWORDS = ["归还", "兑现", "偿还", "还清", "终于", "取得", "获得"]

    def __init__(self):
        self._debts: Dict[str, Debt] = {}
        self._debt_counter = 0

    def create_debt(
        self,
        debt_type: DebtType,
        content: str,
        chapter: int,
        priority: DebtPriority = DebtPriority.MEDIUM
    ) -> Debt:
        """创建债务"""
        self._debt_counter += 1
        debt_id = f"DEBT_{self._debt_counter:04d}"
        
        debt = Debt(
            debt_id=debt_id,
            debt_type=debt_type,
            content=content,
            created_chapter=chapter,
            priority=priority,
        )
        
        self._debts[debt_id] = debt
        logger.info(f"[DebtTracker] 创建债务 {debt_id}: {content} (chapter={chapter}, priority={priority.name})")
        
        return debt

    def parse_explicit_debts(self, content: str, chapter: int) -> List[Debt]:
        """解析显式伏笔标签"""
        debts = []
        
        for match in self.EXPLICIT_TAG_PATTERN.finditer(content):
            foreshadow = match.group(1).strip()
            if foreshadow and not self._find_debt_by_content(foreshadow):
                debt = self.create_debt(
                    DebtType.EXPLICIT_FORESADOW,
                    foreshadow,
                    chapter,
                    DebtPriority.HIGH
                )
                debts.append(debt)
        
        return debts

    def detect_and_repay(self, content: str, chapter: int) -> List[Debt]:
        """检测偿还并标记债务"""
        repaid_debts = []
        
        for match in self.REPAY_PATTERN.finditer(content):
            repaid_content = match.group(1).strip()
            debt = self._find_debt_by_content(repaid_content)
            if debt and not debt.repaid:
                debt.repaid = True
                debt.repaid_chapter = chapter
                logger.info(f"[DebtTracker] 已偿还 {debt.debt_id}: {debt.content} (chapter={chapter})")
                repaid_debts.append(debt)
                logger.info(f"债务已偿还 {debt.debt_id}: {debt.content}")
        
        return repaid_debts

    def check_active_debts(self) -> List[Debt]:
        """获取所有未偿还债务"""
        return [d for d in self._debts.values() if not d.repaid]

    def get_high_priority_debts(self) -> List[Debt]:
        """获取高优先级债务（priority >= HIGH）"""
        return [
            d for d in self._debts.values()
            if not d.repaid and (d.priority.value if hasattr(d.priority, 'value') else d.priority) >= DebtPriority.HIGH.value
        ]

    def can_write_climax(self, chapter: int, is_climax: bool = False) -> tuple[bool, str]:
        """
        检查是否可以写章节
        
        Args:
            chapter: 章节号
            is_climax: 是否为高潮章节
        
        Returns:
            (can_write, reason)
        """
        active_debts = self.check_active_debts()
        high_priority_debts = self.get_high_priority_debts()
        
        logger.debug(f"[DebtTracker] can_write_climax chapter={chapter}, is_climax={is_climax}, active={len(active_debts)}, high_prio={len(high_priority_debts)}")
        
        if active_debts:
            logger.debug(f"[DebtTracker] 活跃债务: {[d.content for d in active_debts[:5]]}")
        
        if high_priority_debts:
            debt_list = ", ".join([d.content[:20] for d in high_priority_debts[:3]])
            logger.warning(f"[DebtTracker] HIGH PRIORITY BLOCK: {debt_list}")
            return False, f"存在未偿还高优先级债务: {debt_list}"
        
        if is_climax and len(active_debts) > self.DEBT_WARNING_THRESHOLD:
            logger.warning(f"[DebtTracker] CLIMAX THRESHOLD BLOCK: {len(active_debts)} debts > {self.DEBT_WARNING_THRESHOLD}")
            return False, f"高潮章节活跃债务过多: {len(active_debts)} 个（阈值 {self.DEBT_WARNING_THRESHOLD}）"
        
        if len(active_debts) > self.DEBT_WARNING_THRESHOLD:
            logger.info(f"[DebtTracker] WARNING: {len(active_debts)} debts (non-climax allowed)")
            return True, f"警告: 活跃债务数 {len(active_debts)}，建议偿还"
        
        logger.debug(f"[DebtTracker] can_write=True")
        return True, "可以写章节"

    def get_debt_summary(self) -> Dict:
        """获取债务摘要"""
        active = self.check_active_debts()
        high_prio = self.get_high_priority_debts()
        
        type_counts: Dict[str, int] = {}
        for debt in active:
            t = debt.debt_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        
        return {
            "total": len(self._debts),
            "active": len(active),
            "high_priority": len(high_prio),
            "by_type": type_counts,
            "can_climax": self.can_write_climax(0)[0],
        }

    def _find_debt_by_content(self, content: str) -> Optional[Debt]:
        """根据内容查找债务"""
        for debt in self._debts.values():
            if content in debt.content or debt.content in content:
                return debt
        return None

    def mark_repaid(self, debt_id: str, chapter: int) -> bool:
        """手动标记债务已偿还"""
        if debt_id in self._debts:
            self._debts[debt_id].repaid = True
            self._debts[debt_id].repaid_chapter = chapter
            return True
        return False