# inkOS 借鉴改进 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 三项增量改进——运行时产物落盘、Observer→Reflector 双段提取、真相文件 Markdown 投影

**Architecture:** 纯增量。不破坏现有 pipeline。三项独立可交付。#1 在 context_manager 返回前落盘，#2 新增 observer-agent + settler 脚本 + 拆分 SKILL.md Step 5.1，#3 新增独立渲染模块 + 在 commit/rebuild 末尾调用

**Tech Stack:** Python 3, Pydantic (StoryEvent), json, sqlite3

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `.opencode/scripts/data_modules/context_manager.py` | 修改 | #1：build_context 返回前落盘 runtime 产物 |
| `.opencode/agents/observer-agent.md` | 新建 | #2：observer agent——自由文本提取，无 schema 约束 |
| `.opencode/scripts/data_modules/observer_settler.py` | 新建 | #2：settler——解析 observer 输出 → Pydantic 校验 → extraction_result |
| `.opencode/scripts/data_modules/tests/test_observer_settler.py` | 新建 | #2：settler 单元测试 |
| `.opencode/skills/webnovel-write/SKILL.md` | 修改 | #2：Step 5.1 拆成 5.1a/5.1b/5.1c |
| `.opencode/scripts/data_modules/state_projection_renderer.py` | 新建 | #3：从 state.json + index.db 渲染 5 个 markdown 投影 |
| `.opencode/scripts/data_modules/tests/test_state_projection_renderer.py` | 新建 | #3：渲染器单元测试 |
| `.opencode/scripts/data_modules/chapter_commit_service.py` | 修改 | #3：apply_projections 末尾调用 render_all_projections |
| `.opencode/scripts/data_modules/ssot_enforcer.py` | 修改 | #3：rebuild_projections 末尾调用 render_all_projections |
| `.opencode/scripts/data_modules/webnovel.py` | 修改 | #3：新增 `state render` CLI 子命令 |

---

### Task 1: #1 运行时产物持久化

**Files:**
- Modify: `.opencode/scripts/data_modules/context_manager.py:104-120`

- [ ] **Step 1: 修改 build_context 方法——在 return 前落盘 runtime 产物**

`.opencode/scripts/data_modules/context_manager.py` 第 104-120 行，`build_context()` 方法。将原来的直接 `return` 改为先落盘再返回：

```python
def build_context(
    self,
    chapter: int,
    template: str | None = None,
    max_chars: Optional[int] = None,
) -> Dict[str, Any]:
    template = template or self.DEFAULT_TEMPLATE
    self._active_template = template
    if template not in self.TEMPLATE_WEIGHTS:
        template = self.DEFAULT_TEMPLATE
        self._active_template = template

    pack = self._build_pack(chapter)
    if getattr(self.config, "context_ranker_enabled", True):
        pack = self.context_ranker.rank_pack(pack, chapter)

    payload = self._assemble_json_payload(pack, template=template)

    # Persist runtime artifacts for post-hoc debugging
    try:
        from .story_contracts import write_json
        runtime_dir = self.config.project_root / ".webnovel" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)

        write_json(runtime_dir / f"chapter-{chapter:03d}.context.json", payload)

        trace = {
            "chapter": chapter,
            "template": template,
            "stage": self._resolve_context_stage(chapter),
            "weights_used": self._resolve_template_weights(template=template, chapter=chapter),
            "sections": {
                "included": [s for s in self.SECTION_ORDER if s in payload],
                "excluded": [s for s in self.SECTION_ORDER if s not in payload],
            },
            "ranker": {
                "enabled": getattr(self.config, "context_ranker_enabled", True),
            },
        }
        write_json(runtime_dir / f"chapter-{chapter:03d}.trace.json", trace)
    except Exception:
        pass  # runtime artifact persistence must not block context assembly

    return payload
```

- [ ] **Step 2: 运行 context 相关测试确认无回归**

```bash
cd e:/workspace/webnovel-writer
python -m pytest .opencode/scripts/data_modules/tests/test_context_override_hints.py -q -p no:cov -o "addopts="
```

预期：3 passed

- [ ] **Step 3: 手动验证——构造一个 context 调用，检查产物是否落盘**

```bash
python -c "
import sys; sys.path.insert(0, '.opencode/scripts')
from pathlib import Path
import tempfile, json
from data_modules.config import DataModulesConfig
from data_modules.context_manager import ContextManager

# Create minimal project
tmp = Path(tempfile.mkdtemp())
(tmp / '.webnovel').mkdir()
(tmp / '.webnovel' / 'state.json').write_text(json.dumps({'schema_version': '5.1', 'progress': {}}))
(tmp / 'MASTER_SETTING.json').write_text('{}')

cfg = DataModulesConfig(project_root=tmp)
mgr = ContextManager(cfg)
result = mgr.build_context(chapter=1)

# Check runtime artifacts
runtime = tmp / '.webnovel' / 'runtime'
assert runtime.is_dir(), 'runtime dir not created'
assert (runtime / 'chapter-001.context.json').is_file(), 'context.json missing'
assert (runtime / 'chapter-001.trace.json').is_file(), 'trace.json missing'
print('OK: both runtime artifacts persisted')
"
```

预期：`OK: both runtime artifacts persisted`

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/context_manager.py
git commit -m "feat: context_ runtime 产物落盘（chapter-NNN.context.json + trace.json）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: #2 observer-agent 定义

**Files:**
- Create: `.opencode/agents/observer-agent.md`

- [ ] **Step 1: 创建 observer-agent.md**

```markdown
---
name: observer-agent
description: 从正文自由提取事实——宁可多提，不做 schema 约束
mode: subagent
tools:
  read: true
  write: true
  bash: true
---

# observer-agent

## 0. 环境

```bash
if [ -z "$SCRIPTS_DIR" ] || [ ! -d "$SCRIPTS_DIR" ]; then
  echo "❌ SCRIPTS_DIR 未正确设置"
  exit 1
fi
```

`{project_root}` 和 `{chapter}` 由调用方传入。

## 1. 身份

从章节正文中**过度提取**事实。你的输出是自由文本——不做 JSON schema 约束。宁可多提 10 条，不漏 1 条。不确定的实体可以写描述而不是精确 entity_id。后续有专门的校验步骤过滤。

## 2. 输入准备

在提取之前，先获取已知实体目录（用于正确引用已有实体）：

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "{project_root}" index get-core-entities
```

Read 正文文件（调用方传入章节文件路径）。

## 3. 输出格式

自由文本，按以下 9 个段落组织。**每个段落输出为 `## 段落名` 的 markdown 标题**：

### ## 角色状态变化
每行一条。格式：`- {角色名}（entity_id: {id}，如不确定写"未知"）：{变化描述}`
关注：修为突破、伤势变化、位置移动、情绪重大转变、新称号/身份获得、技能习得

### ## 新出场实体
每行一条。格式：`- {实体名}（类型：角色/势力/地点/物品，entity_id: {id}或"新"）：{简短描述}`

### ## 关系变化
每行一条。格式：`- {角色A} ↔ {角色B}：关系从{旧状态}变为{新状态}`

### ## 力量突破
每行一条。格式：`- {角色名}（entity_id: {id}）：从{旧境界}突破至{新境界}`
注意：必须涉及修为、境界、战力等级的明确变化

### ## 宝物/物品获得
每行一条。格式：`- {物品名}（entity_id: {id}或"新"）：被{持有者}获得/使用`

### ## 世界规则揭示
每行一条。格式：`- 新规则：{规则描述}`

### ## 世界规则打破
每行一条。格式：`- 被打破的规则：{规则描述}。打破方式：{描述}`

### ## 对读者的承诺/伏笔
每行一条。格式：`- [新埋设] {承诺/伏笔描述}` 或 `- [偿还] {已兑现的承诺描述}`

### ## 伏笔创建与闭合
每行一条。格式：`- [新伏笔] {内容}（紧迫度：0-100）` 或 `- [闭合] {内容}`

## 4. 提取规则

- **宁可多提**：不确定算不算的都写上
- **实体引用**：已知实体用 `entity_id: xxx`，不确定写"未知"或描述
- **不编造**：正文没写的不提
- **不省略**：同一章可以有多个同类事件
- **中文输出**：全部中文
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/agents/observer-agent.md
git commit -m "feat: 新增 observer-agent——自由文本事实提取，无 schema 约束

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: #2 settler 脚本

**Files:**
- Create: `.opencode/scripts/data_modules/observer_settler.py`
- Create: `.opencode/scripts/data_modules/tests/test_observer_settler.py`

- [ ] **Step 1: 创建 observer_settler.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Settler: parse observer free-text output → validated StoryEvent list.

Pure Python — no LLM calls. Extracts structured events from markdown sections
via regex/keyword matching, resolves entity references against known entities,
and validates via Pydantic StoryEvent schema.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from runtime_compat import enable_windows_utf8_stdio

from .story_event_schema import StoryEvent


def _load_known_entities(project_root: Path) -> dict[str, dict]:
    """Load known entities from state.json entities_v3 for disambiguation."""
    state_path = project_root / ".webnovel" / "state.json"
    if not state_path.is_file():
        return {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return state.get("entities_v3", {})
    except (OSError, ValueError):
        return {}


def _resolve_entity(name_or_id: str, known: dict[str, dict]) -> str:
    """Resolve an entity reference to its canonical entity_id.

    If the input is already a known entity_id, return it.
    If it matches a known entity's name, return that entity's id.
    Otherwise return the input as-is.
    """
    if name_or_id in known:
        return name_or_id
    for eid, info in known.items():
        if info.get("name", "") == name_or_id:
            return eid
    return name_or_id


def _parse_markdown_sections(text: str) -> dict[str, list[str]]:
    """Parse observer output into sections keyed by heading name."""
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_heading = stripped[3:].strip()
            sections.setdefault(current_heading, [])
        elif current_heading and stripped:
            sections[current_heading].append(stripped)
    return sections


def _extract_character_state_changes(lines: list[str], known: dict[str, dict], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)（entity_id:\s*(\S+?)）\s*：\s*(.+)', line)
        if m:
            name, eid_raw, desc = m.groups()
            eid = _resolve_entity(eid_raw if eid_raw != "未知" else name, known)
            events.append({
                "event_id": f"evt-ch{chapter:03d}-state-{len(events):03d}",
                "chapter": chapter,
                "event_type": "character_state_changed",
                "subject": eid,
                "payload": {
                    "entity_id": eid,
                    "entity_name": name,
                    "description": desc,
                },
            })
    return events


def _extract_relationships(lines: list[str], known: dict[str, dict], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)\s*↔\s*(.+?)\s*：关系从(.+?)变为(.+)', line)
        if m:
            a, b, old_rel, new_rel = m.groups()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-rel-{len(events):03d}",
                "chapter": chapter,
                "event_type": "relationship_changed",
                "subject": _resolve_entity(a.strip(), known),
                "payload": {
                    "from_entity": _resolve_entity(a.strip(), known),
                    "to_entity": _resolve_entity(b.strip(), known),
                    "relationship_type": new_rel.strip(),
                    "description": f"从{old_rel.strip()}变为{new_rel.strip()}",
                },
            })
    return events


def _extract_power_breakthroughs(lines: list[str], known: dict[str, dict], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)（entity_id:\s*(\S+?)）\s*：从(.+?)突破至(.+)', line)
        if m:
            name, eid_raw, old_realm, new_realm = m.groups()
            eid = _resolve_entity(eid_raw if eid_raw != "未知" else name, known)
            events.append({
                "event_id": f"evt-ch{chapter:03d}-power-{len(events):03d}",
                "chapter": chapter,
                "event_type": "power_breakthrough",
                "subject": eid,
                "payload": {
                    "entity_id": eid,
                    "entity_name": name.strip(),
                    "old_realm": old_realm.strip(),
                    "new_realm": new_realm.strip(),
                },
            })
    return events


def _extract_entity_creations(lines: list[str], known: dict[str, dict], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)（类型：(\S+?)，entity_id:\s*(\S+?)）\s*：\s*(.*)', line)
        if m:
            name, etype, eid_raw, desc = m.groups()
            eid = eid_raw if eid_raw != "新" else name.strip()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-entity-{len(events):03d}",
                "chapter": chapter,
                "event_type": "entity_created",
                "subject": eid,
                "payload": {
                    "entity_id": eid,
                    "entity_type": etype.strip(),
                    "entity_name": name.strip(),
                },
            })
    return events


def _extract_world_rule_revealed(lines: list[str], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- 新规则[：:]\s*(.+)', line)
        if m:
            desc = m.group(1).strip()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-wrreveal-{len(events):03d}",
                "chapter": chapter,
                "event_type": "world_rule_revealed",
                "subject": f"rule_ch{chapter}",
                "payload": {
                    "rule_id": f"rule_ch{chapter}_{len(events):03d}",
                    "description": desc,
                },
            })
    return events


def _extract_world_rule_broken(lines: list[str], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- 被打破的规则[：:]\s*(.+?)[。.]\s*打破方式[：:]\s*(.+)', line)
        if m:
            rule_desc, how = m.groups()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-wrbreak-{len(events):03d}",
                "chapter": chapter,
                "event_type": "world_rule_broken",
                "subject": f"rule_ch{chapter}",
                "payload": {
                    "description": rule_desc.strip(),
                    "reason": how.strip(),
                },
            })
    return events


def _extract_promises(lines: list[str], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m_new = re.match(r'- \[新埋设\]\s*(.+)', line)
        m_paid = re.match(r'- \[偿还\]\s*(.+)', line)
        if m_new:
            desc = m_new.group(1).strip()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-promise-{len(events):03d}",
                "chapter": chapter,
                "event_type": "promise_created",
                "subject": f"promise_ch{chapter}",
                "payload": {
                    "promise_id": f"promise_ch{chapter}_{len(events):03d}",
                    "description": desc,
                },
            })
        elif m_paid:
            desc = m_paid.group(1).strip()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-promise-{len(events):03d}",
                "chapter": chapter,
                "event_type": "promise_paid_off",
                "subject": f"promise_ch{chapter}",
                "payload": {
                    "description": desc,
                },
            })
    return events


def _extract_open_loops(lines: list[str], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m_new = re.match(r'- \[新伏笔\]\s*(.+?)（紧迫度[：:]\s*(\d+)）', line)
        m_closed = re.match(r'- \[闭合\]\s*(.+)', line)
        if m_new:
            content, urgency = m_new.groups()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-loop-{len(events):03d}",
                "chapter": chapter,
                "event_type": "open_loop_created",
                "subject": f"loop_ch{chapter}",
                "payload": {
                    "content": content.strip(),
                    "urgency": int(urgency),
                },
            })
        elif m_closed:
            content = m_closed.group(1).strip()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-loop-{len(events):03d}",
                "chapter": chapter,
                "event_type": "open_loop_closed",
                "subject": f"loop_ch{chapter}",
                "payload": {
                    "content": content,
                },
            })
    return events


def settle(raw_facts_path: Path, project_root: Path, chapter: int) -> dict:
    """Parse observer output → validated StoryEvent list."""
    text = raw_facts_path.read_text(encoding="utf-8")
    sections = _parse_markdown_sections(text)
    known = _load_known_entities(project_root)

    extractors: list[tuple[str, callable]] = [
        ("角色状态变化", _extract_character_state_changes),
        ("关系变化", _extract_relationships),
        ("力量突破", _extract_power_breakthroughs),
        ("新出场实体", _extract_entity_creations),
        ("世界规则揭示", _extract_world_rule_revealed),
        ("世界规则打破", _extract_world_rule_broken),
        ("对读者的承诺/伏笔", _extract_promises),
        ("伏笔创建与闭合", _extract_open_loops),
    ]

    all_events: list[dict] = []
    for heading, extractor in extractors:
        lines = sections.get(heading, [])
        if heading in ("角色状态变化", "关系变化", "力量突破", "新出场实体"):
            all_events.extend(extractor(lines, known, chapter))
        else:
            all_events.extend(extractor(lines, chapter))

    validated: list[dict] = []
    for evt in all_events:
        try:
            validated.append(StoryEvent.model_validate(evt).model_dump())
        except Exception:
            pass

    return {
        "accepted_events": validated,
        "state_deltas": [],
        "entity_deltas": [],
        "entities_appeared": [],
        "scenes": [],
        "chapter_meta": {},
        "dominant_strand": "",
        "summary_text": "",
    }


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Settle observer raw facts into extraction_result.json")
    ap.add_argument("--raw-facts", required=True, help="Path to observer raw_facts.txt")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--output", required=True, help="Path to write extraction_result.json")
    args = ap.parse_args()

    result = settle(Path(args.raw_facts), Path(args.project_root), args.chapter)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"settler: {len(result['accepted_events'])} events written to {args.output}")


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
```

- [ ] **Step 2: 创建测试文件 test_observer_settler.py**

```python
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
```

- [ ] **Step 3: 运行测试验证 settler**

```bash
cd e:/workspace/webnovel-writer
python -m pytest .opencode/scripts/data_modules/tests/test_observer_settler.py -v -p no:cov -o "addopts="
```

预期：全部 PASS

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/observer_settler.py .opencode/scripts/data_modules/tests/test_observer_settler.py
git commit -m "feat: 新增 observer_settler——解析 observer 输出 → StoryEvent 校验

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: #2 SKILL.md Step 5.1 拆分

**Files:**
- Modify: `.opencode/skills/webnovel-write/SKILL.md` — Step 5.1 区域

- [ ] **Step 1: 读取当前 Step 5.1 的精确内容**

在 `.opencode/skills/webnovel-write/SKILL.md` 的 Step 5.1 区域，找到 data-agent 的 Agent 调用模板。将旧的单个 Agent 调用改为三步。

当前代码（约第 240-270 行区域）中 `Agent(subagent_type: "data-agent", ...)` 的部分。

- [ ] **Step 2: 替换为三步流程**

将 Step 5.1 从单个 Agent 调用改为：

```markdown
#### 5.1 事实提取与校验

##### 5.1a Observer：自由提取

必须使用 `Agent` 工具调用 `observer-agent`，产出自由文本 raw_facts.txt。

```text
Agent(
  subagent_type: "observer-agent",
  prompt: "project_root={PROJECT_ROOT}; chapter={chapter_num}; chapter_file={CHAPTER_FILE}。输出到 {PROJECT_ROOT}/.webnovel/runtime/chapter-{chapter_num:03d}.raw_facts.txt。"
)
```

产物：`{PROJECT_ROOT}/.webnovel/runtime/chapter-{chapter_num:03d}.raw_facts.txt`

##### 5.1b Settler：Schema 校验落盘

```bash
python -X utf8 "${SCRIPTS_DIR}/data_modules/observer_settler.py" \
  --raw-facts "${PROJECT_ROOT}/.webnovel/runtime/chapter-{chapter_num:03d}.raw_facts.txt" \
  --project-root "${PROJECT_ROOT}" \
  --chapter {chapter_num} \
  --output "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```

产物：`{PROJECT_ROOT}/.webnovel/tmp/extraction_result.json`

##### 5.1c Data Agent：契约校验与消歧

必须使用 `Agent` 工具调用 `data-agent`。data-agent 不再提取事实——仅做大纲履约对比和实体消歧。

```text
Agent(
  subagent_type: "data-agent",
  prompt: "project_root={PROJECT_ROOT}; chapter={chapter_num}。extraction_result 已由 settler 生成在 {PROJECT_ROOT}/.webnovel/tmp/extraction_result.json。只产出 fulfillment_result.json 和 disambiguation_result.json。不重新提取事实。"
)
```

产物：`fulfillment_result.json` + `disambiguation_result.json`
```

- [ ] **Step 3: 更新 Step 5.2 的 chapter-commit 命令**

确保 `--extraction-result` 指向 settler 的输出路径（`${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json`），而非 data-agent 的。当前已指向该路径，无需修改——仅确认。

- [ ] **Step 4: Commit**

```bash
git add .opencode/skills/webnovel-write/SKILL.md
git commit -m "feat: webnovel-write Step 5.1 拆成 Observer→Settler→Data Agent 三段

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: #3 Markdown 投影渲染器

**Files:**
- Create: `.opencode/scripts/data_modules/state_projection_renderer.py`
- Create: `.opencode/scripts/data_modules/tests/test_state_projection_renderer.py`

- [ ] **Step 1: 创建 state_projection_renderer.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render human-readable markdown projections from state.json + index.db.

Pure Python — no LLM calls. Each renderer produces one markdown file.
Triggered after chapter-commit, ssot rebuild, or manually via CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

HEADER = "> 此文件由系统自动生成，请勿手动编辑。数据源: state.json + index.db\n\n"


def _render_world_state(state: dict, project_root: Path) -> str:
    """世界观状态：实体状态 + 主角信息 + 世界规则。"""
    lines = [HEADER, "# 世界观状态\n"]
    ps = state.get("protagonist_state") or {}
    if ps:
        lines.append("## 主角状态\n")
        for k, v in ps.items():
            if k != "location":
                lines.append(f"- **{k}**: {v}")
        loc = ps.get("location", {})
        if isinstance(loc, dict) and loc:
            lines.append(f"- **位置**: {loc.get('current', '未知')}")
        lines.append("")

    entities = state.get("entities_v3") or {}
    if entities:
        lines.append("## 实体状态\n")
        for eid, info in sorted(entities.items()):
            cs = info.get("current_state") or {}
            state_str = ", ".join(f"{k}={v}" for k, v in cs.items()) if cs else "无特殊状态"
            lines.append(f"- **{info.get('name', eid)}** ({info.get('entity_type', '未知')}): {state_str}")
        lines.append("")

    rules = state.get("world_rules") or []
    if rules:
        lines.append("## 世界规则\n")
        for r in rules:
            status_icon = "🟢" if r.get("status") == "active" else "🔴"
            lines.append(f"- {status_icon} {r.get('description', '')}")
            if r.get("status") == "broken":
                lines.append(f"  - 打破于第{r.get('broken_chapter', '?')}章: {r.get('broken_reason', '')}")
        lines.append("")

    if not entities and not rules and not ps:
        lines.append("（暂无数据）\n")

    return "\n".join(lines)


def _render_foreshadowing_panel(state: dict, project_root: Path) -> str:
    """伏笔面板：活跃伏笔 + 已闭合伏笔。"""
    lines = [HEADER, "# 伏笔面板\n"]
    fs = state.get("foreshadowing") or []
    active = [f for f in fs if f.get("status") == "active"]
    closed = [f for f in fs if f.get("status") == "closed"]

    lines.append(f"## 活跃伏笔（{len(active)}）\n")
    for f in active:
        urgency = f.get("urgency", 50)
        bar = "█" * min(10, max(1, urgency // 10)) + "░" * (10 - min(10, max(1, urgency // 10)))
        lines.append(f"- **第{f.get('planted_chapter', '?')}章**: {f.get('content', '')}")
        lines.append(f"  - 紧迫度: [{bar}] {urgency}%")
    if not active:
        lines.append("（暂无活跃伏笔）\n")

    lines.append(f"\n## 已闭合伏笔（{len(closed)}）\n")
    for f in closed[-10:]:
        lines.append(f"- ~~第{f.get('planted_chapter', '?')}章: {f.get('content', '')}~~ → 第{f.get('closed_chapter', '?')}章闭合")
    if not closed:
        lines.append("（暂无已闭合伏笔）\n")

    return "\n".join(lines)


def _render_character_matrix(state: dict, project_root: Path) -> str:
    """角色关系矩阵。"""
    lines = [HEADER, "# 角色关系矩阵\n"]
    rels = state.get("relationships") or []
    entities = state.get("entities_v3") or {}

    if not rels:
        lines.append("（暂无关系数据）\n")
        return "\n".join(lines)

    # Entity name lookup
    def name_for(eid):
        return entities.get(eid, {}).get("name", eid)

    lines.append("| 角色A | 关系 | 角色B | 最后出现章 |")
    lines.append("|-------|------|-------|-----------|")
    for r in rels:
        lines.append(f"| {name_for(r.get('from', ''))} | {r.get('type', '')} | {name_for(r.get('to', ''))} | 第{r.get('last_seen_chapter', '?')}章 |")

    return "\n".join(lines)


def _render_power_system(state: dict, project_root: Path) -> str:
    """力量体系：角色境界 + 世界规则中的力量相关规则。"""
    lines = [HEADER, "# 力量体系\n"]

    entities = state.get("entities_v3") or {}
    power_entities = []
    for eid, info in entities.items():
        cs = info.get("current_state") or {}
        realm = cs.get("realm")
        if realm:
            power_entities.append((info.get("name", eid), realm, info.get("entity_type", "")))

    if power_entities:
        lines.append("## 角色境界\n")
        for name, realm, etype in sorted(power_entities):
            lines.append(f"- **{name}** ({etype}): {realm}")
    else:
        lines.append("（暂无境界数据）\n")

    rules = state.get("world_rules") or []
    power_rules = [r for r in rules if any(kw in r.get("description", "") for kw in ("境界", "力量", "修炼", "突破", "禁制"))]
    if power_rules:
        lines.append("\n## 力量相关规则\n")
        for r in power_rules:
            status_icon = "🟢" if r.get("status") == "active" else "🔴"
            lines.append(f"- {status_icon} {r.get('description', '')}")

    return "\n".join(lines)


def _render_chapter_index(state: dict, project_root: Path) -> str:
    """章节摘要索引：从 summaries 目录汇总。"""
    lines = [HEADER, "# 章节摘要\n"]
    summaries_dir = project_root / ".webnovel" / "summaries"

    progress = state.get("progress") or {}
    ch_status = progress.get("chapter_status") or {}

    if not ch_status:
        lines.append("（暂无章节记录）\n")
        return "\n".join(lines)

    lines.append("| 章节 | 状态 |")
    lines.append("|------|------|")
    for ch in sorted(ch_status.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        status = ch_status[ch].get("status", "unknown")
        icon = "✅" if status == "committed" else "📝" if status == "drafting" else "❓"
        lines.append(f"| 第{ch}章 | {icon} {status} |")

    lines.append(f"\n共 {len(ch_status)} 章。")
    if summaries_dir.is_dir():
        count = len(list(summaries_dir.glob("ch*.md")))
        lines.append(f" 其中 {count} 章有摘要文件。\n")

    return "\n".join(lines)


def render_all_projections(project_root: Path) -> dict[str, Path]:
    """从结构化数据渲染所有 markdown 投影。"""
    state_path = project_root / ".webnovel" / "state.json"
    if not state_path.is_file():
        return {}

    state = json.loads(state_path.read_text(encoding="utf-8"))

    renderers: dict[str, callable] = {
        "世界观状态.md": _render_world_state,
        "伏笔面板.md": _render_foreshadowing_panel,
        "角色关系矩阵.md": _render_character_matrix,
        "力量体系.md": _render_power_system,
        "章节摘要.md": _render_chapter_index,
    }

    output_dir = project_root / "story"
    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Path] = {}
    for filename, renderer in renderers.items():
        path = output_dir / filename
        path.write_text(renderer(state, project_root), encoding="utf-8")
        results[filename] = path

    return results


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Render markdown projections from state.json")
    ap.add_argument("--project-root", required=True)
    args = ap.parse_args()
    results = render_all_projections(Path(args.project_root))
    for name, path in results.items():
        print(f"  {name} → {path}")
    print(f"Rendered {len(results)} projection files.")


if __name__ == "__main__":
    import sys
    from runtime_compat import enable_windows_utf8_stdio
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
```

- [ ] **Step 2: 创建测试文件 test_state_projection_renderer.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for state_projection_renderer."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_modules.state_projection_renderer import (
    _render_world_state,
    _render_foreshadowing_panel,
    _render_character_matrix,
    _render_power_system,
    _render_chapter_index,
    render_all_projections,
)

MINIMAL_STATE = {
    "schema_version": "5.1",
    "progress": {"chapter_status": {"1": {"status": "committed"}}},
    "entities_v3": {
        "xiaoyan": {
            "name": "萧炎",
            "entity_type": "角色",
            "current_state": {"realm": "斗王", "emotion": "愤怒"},
        }
    },
    "foreshadowing": [
        {"content": "三年之约", "planted_chapter": 1, "urgency": 90, "status": "active"},
        {"content": "获取青莲地心火", "planted_chapter": 3, "urgency": 60, "status": "closed", "closed_chapter": 5},
    ],
    "relationships": [
        {"from": "xiaoyan", "to": "yunlanzong", "type": "敌对", "last_seen_chapter": 5},
    ],
    "protagonist_state": {"entity_id": "xiaoyan", "realm": "斗王", "location": {"current": "云岚宗"}},
    "world_rules": [
        {"rule_id": "rule_1", "description": "云岚宗禁地不可飞行", "status": "active", "revealed_chapter": 5},
        {"rule_id": "rule_2", "description": "斗王境界可短暂滞空", "status": "active", "revealed_chapter": 6},
    ],
    "reader_promises": [],
    "artifacts": [],
    "override_rules": [],
}


class TestWorldState:
    def test_renders_protagonist(self):
        result = _render_world_state(MINIMAL_STATE, Path("."))
        assert "萧炎" in result
        assert "斗王" in result

    def test_renders_world_rules(self):
        result = _render_world_state(MINIMAL_STATE, Path("."))
        assert "禁地不可飞行" in result

    def test_empty_state_no_crash(self):
        result = _render_world_state({}, Path("."))
        assert "暂无数据" in result


class TestForeshadowingPanel:
    def test_renders_active_and_closed(self):
        result = _render_foreshadowing_panel(MINIMAL_STATE, Path("."))
        assert "三年之约" in result
        assert "青莲地心火" in result
        assert "活跃伏笔" in result
        assert "已闭合伏笔" in result

    def test_empty_foreshadowing_no_crash(self):
        result = _render_foreshadowing_panel({}, Path("."))
        assert "暂无活跃伏笔" in result


class TestCharacterMatrix:
    def test_renders_relationship_table(self):
        result = _render_character_matrix(MINIMAL_STATE, Path("."))
        assert "萧炎" in result
        assert "敌对" in result

    def test_empty_relationships_no_crash(self):
        result = _render_character_matrix({}, Path("."))
        assert "暂无关系数据" in result


class TestPowerSystem:
    def test_renders_realms(self):
        result = _render_power_system(MINIMAL_STATE, Path("."))
        assert "斗王" in result

    def test_empty_no_crash(self):
        result = _render_power_system({}, Path("."))
        assert "暂无境界数据" in result


class TestChapterIndex:
    def test_renders_chapter_table(self):
        result = _render_chapter_index(MINIMAL_STATE, Path("."))
        assert "第1章" in result
        assert "committed" in result

    def test_empty_no_crash(self):
        result = _render_chapter_index({}, Path("."))
        assert "暂无章节记录" in result


class TestRenderAll:
    def test_renders_all_files(self, tmp_path):
        webnovel = tmp_path / ".webnovel"
        webnovel.mkdir()
        (webnovel / "state.json").write_text(json.dumps(MINIMAL_STATE), encoding="utf-8")
        results = render_all_projections(tmp_path)
        assert len(results) == 5
        for path in results.values():
            assert path.is_file()
            content = path.read_text(encoding="utf-8")
            assert "请勿手动编辑" in content

    def test_missing_state_json(self, tmp_path):
        results = render_all_projections(tmp_path)
        assert results == {}
```

- [ ] **Step 3: 运行测试**

```bash
cd e:/workspace/webnovel-writer
python -m pytest .opencode/scripts/data_modules/tests/test_state_projection_renderer.py -v -p no:cov -o "addopts="
```

预期：全部 PASS

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/state_projection_renderer.py .opencode/scripts/data_modules/tests/test_state_projection_renderer.py
git commit -m "feat: 新增 state_projection_renderer——从 state.json 渲染 5 个 markdown 投影

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: #3 集成到 chapter-commit 和 ssot rebuild

**Files:**
- Modify: `.opencode/scripts/data_modules/chapter_commit_service.py` — apply_projections 末尾
- Modify: `.opencode/scripts/data_modules/ssot_enforcer.py` — rebuild_projections 末尾

- [ ] **Step 1: 在 apply_projections 末尾调用 render_all_projections**

`.opencode/scripts/data_modules/chapter_commit_service.py`，`apply_projections()` 方法，在 `self._sync_foreshadowing(payload)` 之后、`return payload` 之前：

```python
        self._sync_foreshadowing(payload)

        # Render markdown projections
        try:
            from .state_projection_renderer import render_all_projections
            render_all_projections(self.project_root)
        except Exception as exc:
            logger.warning("Markdown projection render failed: %s", exc)

        return payload
```

- [ ] **Step 2: 在 rebuild_projections 末尾调用 render_all_projections**

`.opencode/scripts/data_modules/ssot_enforcer.py`，`rebuild_projections()` 方法，在 `return summary` 之前：

```python
    # Render markdown projections after rebuild
    try:
        from .state_projection_renderer import render_all_projections
        render_all_projections(project_root)
    except Exception:
        pass

    return summary
```

- [ ] **Step 3: 运行相关测试确认无回归**

```bash
cd e:/workspace/webnovel-writer
python -m pytest .opencode/scripts/data_modules/tests/test_ssot_smoke.py .opencode/scripts/data_modules/tests/test_context_override_hints.py -q -p no:cov -o "addopts="
```

预期：全部 PASS

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/chapter_commit_service.py .opencode/scripts/data_modules/ssot_enforcer.py
git commit -m "feat: chapter-commit 和 ssot rebuild 后自动渲染 markdown 投影

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: #3 CLI 子命令 `webnovel state render`

**Files:**
- Modify: `.opencode/scripts/data_modules/webnovel.py` — 新增 `state render` subparser

- [ ] **Step 1: 在 webnovel.py 的 state 子命令组下添加 render**

`.opencode/scripts/data_modules/webnovel.py`，找到 `p_state = sub.add_parser("state", ...)` 区域（约第 405 行），添加 render 子命令：

```python
p_state_render = state_sub.add_parser("render", help="渲染 markdown 投影文件（世界观状态/伏笔面板/关系矩阵等）")
p_state_render.set_defaults(func=_run_data_module_func("state_projection_renderer"))
```

等价的 dispatch 方式——直接注册：

```python
p_state_render.add_argument("--project-root", type=str, default=None,
                            help="项目根目录（默认自动探测）")
```

由于 webnovel.py 已经支持 `_run_data_module("state_projection_renderer", args)` 的转发模式，检查现有 state 子命令的 dispatch 方式：

```python
# 现有 state 子命令:
p_state_sub = state_sub.add_parser("query", ...)
# 或直接在 cmd_state 中路由到子模块
```

具体实现：在 `state` 命令下新增 `render` 子命令，直接调用 `render_all_projections`：

```python
# 在 state 的 help 下添加 render 子命令
p_state_render = state_sub.add_parser("render", help="渲染 markdown 投影")
p_state_render.set_defaults(func=lambda args: _render_projections_cli(args))

# 在文件顶部或 state dispatch 区域添加
def _render_projections_cli(args):
    from .state_projection_renderer import render_all_projections
    project_root = Path(args.project_root).expanduser().resolve() if getattr(args, 'project_root', None) else None
    if not project_root:
        project_root = resolve_project_root(Path.cwd())
    results = render_all_projections(project_root)
    for name, path in results.items():
        print(f"  {name} → {path}")
    print(f"Rendered {len(results)} projection files.")
    return 0
```

- [ ] **Step 2: 手动测试 CLI 命令**

```bash
python -X utf8 .opencode/scripts/webnovel.py --project-root "<test_project>" state render
```

预期输出：5 个文件路径

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/data_modules/webnovel.py
git commit -m "feat: 新增 webnovel state render CLI 命令

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: 最终验证

- [ ] **Step 1: 运行完整测试套件**

```bash
cd e:/workspace/webnovel-writer
python -m pytest .opencode/scripts/data_modules/tests/ -q -p no:cov -o "addopts=" --ignore=.opencode/scripts/data_modules/tests/test_publisher.py --ignore=.opencode/scripts/data_modules/tests/test_rag_adapter.py 2>&1 | tail -5
```

预期：与修复前相同的通过率（586 passed），无新增失败

- [ ] **Step 2: 运行新测试确认通过**

```bash
python -m pytest .opencode/scripts/data_modules/tests/test_observer_settler.py .opencode/scripts/data_modules/tests/test_state_projection_renderer.py -v -p no:cov -o "addopts="
```

预期：全部 PASS

- [ ] **Step 3: Commit**

```bash
git add -A  # 如有任何遗漏
git commit -m "chore: 最终测试验证——三项 inkOS 改进全部通过

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```
