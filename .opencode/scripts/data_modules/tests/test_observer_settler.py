#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for observer_settler — validate extraction from observer output."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_modules.observer_settler import (
    settle,
    _parse_markdown_sections,
    _resolve_entity,
    _extract_character_state_changes,
    _extract_power_breakthroughs,
    _extract_open_loops,
    _extract_promises,
    _extract_entity_creations,
    _extract_world_rule_revealed,
    _extract_world_rule_broken,
    _extract_relationships,
)


SAMPLE_OBSERVER_OUTPUT = """## 角色状态变化
- 萧炎（entity_id: xiaoyan）：从斗灵九星突破至斗王
- 药老（entity_id: 未知）：灵魂力消耗过度，陷入沉睡

## 新出场实体
- 云岚宗执法队（类型：势力，entity_id: 新）：首次出场，奉宗主之命追捕萧炎

## 关系变化
- 萧炎 ↔ 云岚宗：关系从中立变为敌对

## 力量突破
- 萧炎（entity_id: xiaoyan）：从斗灵突破至斗王

## 宝物/物品获得

## 世界规则揭示
- 新规则：云岚宗禁地不可飞行

## 世界规则打破
- 被打破的规则：云岚宗禁地不可飞行。打破方式：萧炎使用骨翼强行飞越

## 对读者的承诺/伏笔
- [新埋设] 三年之约临近，萧炎必须尽快提升实力
- [偿还] 药老承诺的炼丹术传承

## 伏笔创建与闭合
- [新伏笔] 云岚宗宗主对萧炎产生兴趣（紧迫度：80）
- [闭合] 萧炎获取青莲地心火
"""


class TestParseMarkdownSections:
    def test_parses_all_headings(self):
        sections = _parse_markdown_sections(SAMPLE_OBSERVER_OUTPUT)
        assert "角色状态变化" in sections
        assert "力量突破" in sections
        assert "伏笔创建与闭合" in sections

    def test_extracts_lines_under_heading(self):
        sections = _parse_markdown_sections(SAMPLE_OBSERVER_OUTPUT)
        state_lines = sections.get("角色状态变化", [])
        assert any("萧炎" in l for l in state_lines)
        assert any("药老" in l for l in state_lines)


class TestEntityResolution:
    def test_resolves_known_entity(self):
        known = {"xiaoyan": {"name": "萧炎", "entity_type": "角色"}}
        assert _resolve_entity("xiaoyan", known) == "xiaoyan"

    def test_resolves_by_name(self):
        known = {"xiaoyan": {"name": "萧炎", "entity_type": "角色"}}
        assert _resolve_entity("萧炎", known) == "xiaoyan"

    def test_unknown_passthrough(self):
        assert _resolve_entity("陌生人", {}) == "陌生人"


class TestCharacterStateChanges:
    def test_extracts_state_change(self):
        lines = ["- 萧炎（entity_id: xiaoyan）：从斗灵九星突破至斗王"]
        events = _extract_character_state_changes(lines, {"xiaoyan": {"name": "萧炎"}}, 5)
        assert len(events) == 1
        assert events[0]["event_type"] == "character_state_changed"
        assert events[0]["subject"] == "xiaoyan"


class TestPowerBreakthroughs:
    def test_extracts_breakthrough(self):
        lines = ["- 萧炎（entity_id: xiaoyan）：从斗灵突破至斗王"]
        events = _extract_power_breakthroughs(lines, {"xiaoyan": {"name": "萧炎"}}, 5)
        assert len(events) == 1
        assert events[0]["event_type"] == "power_breakthrough"
        assert events[0]["payload"]["new_realm"] == "斗王"


class TestOpenLoops:
    def test_extracts_new_loop(self):
        lines = ["- [新伏笔] 云岚宗宗主追杀（紧迫度：80）"]
        events = _extract_open_loops(lines, 5)
        assert len(events) == 1
        assert events[0]["event_type"] == "open_loop_created"
        assert events[0]["payload"]["urgency"] == 80

    def test_extracts_closed_loop(self):
        lines = ["- [闭合] 萧炎获取青莲地心火"]
        events = _extract_open_loops(lines, 5)
        assert len(events) == 1
        assert events[0]["event_type"] == "open_loop_closed"


class TestPromises:
    def test_extracts_new_promise(self):
        lines = ["- [新埋设] 三年之约临近"]
        events = _extract_promises(lines, 5)
        assert len(events) == 1
        assert events[0]["event_type"] == "promise_created"

    def test_extracts_paid_promise(self):
        lines = ["- [偿还] 药老承诺的炼丹术传承"]
        events = _extract_promises(lines, 5)
        assert len(events) == 1
        assert events[0]["event_type"] == "promise_paid_off"


class TestEntityCreations:
    def test_extracts_new_entity(self):
        lines = ["- 云岚宗执法队（类型：势力，entity_id: yunlan_guards）：首次出场"]
        events = _extract_entity_creations(lines, {}, 5)
        assert len(events) == 1
        assert events[0]["event_type"] == "entity_created"


class TestWorldRules:
    def test_extracts_revealed_rule(self):
        lines = ["- 新规则：禁地不可飞行"]
        events = _extract_world_rule_revealed(lines, 5)
        assert len(events) == 1
        assert events[0]["event_type"] == "world_rule_revealed"

    def test_extracts_broken_rule(self):
        lines = ["- 被打破的规则：禁地不可飞行。打破方式：骨翼强闯"]
        events = _extract_world_rule_broken(lines, 5)
        assert len(events) == 1
        assert events[0]["event_type"] == "world_rule_broken"


class TestRelationships:
    def test_extracts_relationship_change(self):
        lines = ["- 萧炎 ↔ 云岚宗：关系从中立变为敌对"]
        events = _extract_relationships(lines, {}, 5)
        assert len(events) == 1
        assert events[0]["event_type"] == "relationship_changed"


class TestSettleIntegration:
    def test_settle_produces_extraction_result(self, tmp_path):
        raw = tmp_path / "raw_facts.txt"
        raw.write_text(SAMPLE_OBSERVER_OUTPUT, encoding="utf-8")

        project = tmp_path / "project"
        (project / ".webnovel").mkdir(parents=True)
        (project / ".webnovel" / "state.json").write_text(json.dumps({
            "entities_v3": {"xiaoyan": {"name": "萧炎", "entity_type": "角色"}}
        }))

        result = settle(raw, project, 5)
        assert "accepted_events" in result
        assert len(result["accepted_events"]) >= 5

    def test_empty_input_produces_empty_output(self, tmp_path):
        raw = tmp_path / "empty.txt"
        raw.write_text("", encoding="utf-8")

        project = tmp_path / "project"
        (project / ".webnovel").mkdir(parents=True)
        (project / ".webnovel" / "state.json").write_text("{}")

        result = settle(raw, project, 1)
        assert result["accepted_events"] == []
