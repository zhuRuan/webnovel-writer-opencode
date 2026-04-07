#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Foreshadowing API tests (v5.5)
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

from data_modules.state_manager import StateManager
from data_modules.config import DataModulesConfig


@pytest.fixture
def temp_project(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return cfg


def test_add_foreshadowing_auto_planted_chapter(temp_project):
    """测试添加伏笔时自动获取当前章节号作为 planted_chapter"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)

    manager.update_progress(15)
    assert manager.get_current_chapter() == 15

    record = manager.add_foreshadowing(content="神秘玉佩的秘密", tier="支线", target_offset=50)
    assert record["planted_chapter"] == 15
    assert record["target_chapter"] == 65
    assert record["status"] == "未回收"
    assert record["tier"] == "支线"
    assert record["last_mentioned_chapter"] == 15


def test_add_foreshadowing_different_tiers(temp_project):
    """测试不同 tier 的伏笔"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    manager.update_progress(10)

    core = manager.add_foreshadowing(content="核心伏笔", tier="核心", target_offset=100)
    assert core["tier"] == "核心"

    decor = manager.add_foreshadowing(content="装饰伏笔", tier="装饰", target_offset=30)
    assert decor["tier"] == "装饰"


def test_resolve_foreshadowing_status_change(temp_project):
    """测试解决伏笔后状态变更"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    manager.update_progress(20)

    manager.add_foreshadowing(content="待回收伏笔")
    result = manager.resolve_foreshadowing(content="待回收伏笔", chapter=25)

    assert result is True
    foreshadows = manager.get_foreshadowing(status="未回收")
    assert len(foreshadows) == 0

    resolved = manager.get_foreshadowing(status="已回收")
    assert len(resolved) == 1
    assert resolved[0]["resolved_chapter"] == 25
    assert resolved[0]["resolved_at"] is not None


def test_resolve_foreshadowing_default_chapter(temp_project):
    """测试解决伏笔时默认使用当前进度章节号"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    manager.update_progress(30)

    manager.add_foreshadowing(content="测试伏笔")
    manager.resolve_foreshadowing(content="测试伏笔")

    resolved = manager.get_foreshadowing(status="已回收")
    assert resolved[0]["resolved_chapter"] == 30


def test_resolve_nonexistent_foreshadowing(temp_project):
    """测试解决不存在的伏笔返回 False"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    result = manager.resolve_foreshadowing(content="不存在的伏笔")
    assert result is False


def test_update_last_mentioned_chapter(temp_project):
    """测试更新伏笔最后提及章节"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    manager.update_progress(5)

    manager.add_foreshadowing(content="长期伏笔")

    manager.update_foreshadowing_mention(content="长期伏笔", chapter=10)
    manager.update_foreshadowing_mention(content="长期伏笔", chapter=12)

    foreshadows = manager.get_foreshadowing()
    assert foreshadows[0]["last_mentioned_chapter"] == 12


def test_get_foreshadowing_filter_by_status(temp_project):
    """测试按状态过滤伏笔"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    manager.update_progress(1)

    manager.add_foreshadowing(content="伏笔A")
    manager.add_foreshadowing(content="伏笔B")
    manager.add_foreshadowing(content="伏笔C")
    manager.resolve_foreshadowing(content="伏笔B", chapter=2)

    all_fs = manager.get_foreshadowing()
    assert len(all_fs) == 3

    pending = manager.get_foreshadowing(status="未回收")
    assert len(pending) == 2

    resolved = manager.get_foreshadowing(status="已回收")
    assert len(resolved) == 1


def test_get_overdue_foreshadowing_threshold(temp_project):
    """测试超期检测逻辑"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    manager.update_progress(10)

    manager.add_foreshadowing(content="超期伏笔", tier="支线")

    manager.update_progress(25)
    manager.update_foreshadowing_mention(content="超期伏笔", chapter=10)

    overdue = manager.get_overdue_foreshadowing(current_chapter=25, threshold=10)
    assert len(overdue) == 1
    assert overdue[0]["content"] == "超期伏笔"
    assert overdue[0]["elapsed_chapters"] == 15


def test_get_overdue_foreshadowing_tier_weight(temp_project):
    """测试 tier 权重影响 urgency 计算"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    manager.update_progress(5)

    manager.add_foreshadowing(content="核心伏笔", tier="核心")
    manager.add_foreshadowing(content="支线伏笔", tier="支线")

    manager.update_progress(25)
    manager.update_foreshadowing_mention(content="核心伏笔", chapter=5)
    manager.update_foreshadowing_mention(content="支线伏笔", chapter=5)

    overdue = manager.get_overdue_foreshadowing(threshold=10)
    assert len(overdue) == 2

    core_urgency = next(f["urgency"] for f in overdue if f["content"] == "核心伏笔")
    sub_urgency = next(f["urgency"] for f in overdue if f["content"] == "支线伏笔")

    assert core_urgency > sub_urgency


def test_foreshadowing_persistence_save_and_load(temp_project):
    """测试伏笔持久化（save_state 后重新加载）"""
    manager1 = StateManager(temp_project, enable_sqlite_sync=False)
    manager1.update_progress(5)
    manager1.add_foreshadowing(content="持久化伏笔", tier="核心", target_offset=50)
    manager1.save_state()

    state_data = json.loads(temp_project.state_file.read_text(encoding="utf-8"))
    assert "plot_threads" in state_data
    assert len(state_data["plot_threads"]["foreshadowing"]) == 1

    manager2 = StateManager(temp_project, enable_sqlite_sync=False)
    foreshadows = manager2.get_foreshadowing()
    assert len(foreshadows) == 1
    assert foreshadows[0]["content"] == "持久化伏笔"
    assert foreshadows[0]["last_mentioned_chapter"] == 5


def test_foreshadowing_history_compat_missing_field(temp_project):
    """测试历史兼容：缺少 last_mentioned_chapter 时回退到 planted_chapter"""
    state = {
        "progress": {"current_chapter": 30},
        "plot_threads": {
            "foreshadowing": [
                {
                    "content": "旧伏笔",
                    "status": "未回收",
                    "tier": "支线",
                    "planted_chapter": 10,
                }
            ]
        }
    }
    temp_project.state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    manager = StateManager(temp_project, enable_sqlite_sync=False)
    foreshadows = manager.get_foreshadowing()

    assert len(foreshadows) == 1
    assert foreshadows[0]["last_mentioned_chapter"] == 10


def test_get_overdue_empty_list(temp_project):
    """测试无伏笔时返回空列表"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    manager.update_progress(10)

    overdue = manager.get_overdue_foreshadowing()
    assert overdue == []


def test_get_overdue_all_resolved(temp_project):
    """测试已回收伏笔不返回"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    manager.update_progress(20)

    manager.add_foreshadowing(content="已回收伏笔")
    manager.resolve_foreshadowing(content="已回收伏笔", chapter=15)

    overdue = manager.get_overdue_foreshadowing(threshold=5)
    assert len(overdue) == 0


def test_foreshadowing_urgency_sorting(temp_project):
    """测试超期伏笔按 urgency 降序排列"""
    manager = StateManager(temp_project, enable_sqlite_sync=False)
    manager.update_progress(5)

    manager.add_foreshadowing(content="早期核心", tier="核心")
    manager.add_foreshadowing(content="中期支线", tier="支线")

    manager.update_progress(30)
    manager.update_foreshadowing_mention(content="早期核心", chapter=5)
    manager.update_foreshadowing_mention(content="中期支线", chapter=5)
    manager.update_foreshadowing_mention(content="中期支线", chapter=15)

    overdue = manager.get_overdue_foreshadowing(threshold=10)
    assert overdue[0]["content"] == "早期核心"
    assert overdue[1]["content"] == "中期支线"