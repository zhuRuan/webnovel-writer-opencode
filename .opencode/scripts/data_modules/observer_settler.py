#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Settler: parse observer free-text output → validated StoryEvent list.

Pure Python — no LLM calls. Extracts structured events from markdown sections
via regex/keyword matching, resolves entity references against known entities,
and validates via Pydantic StoryEvent schema.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

try:
    from .story_event_schema import StoryEvent
except ImportError:
    # __main__ fallback — add parent dir to path for sibling imports
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from runtime_compat import enable_windows_utf8_stdio  # noqa: F811
    from story_event_schema import StoryEvent  # noqa: F811
else:
    from runtime_compat import enable_windows_utf8_stdio

logger = logging.getLogger(__name__)


def _load_known_entities(project_root: Path) -> dict[str, dict]:
    """从 state.json + index.db entities 表加载已知实体，用于消歧。"""
    known: dict[str, dict] = {}

    # 1. state.json entities_v3
    state_path = project_root / ".webnovel" / "state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            ev3 = state.get("entities_v3", {})
            if isinstance(ev3, dict):
                known.update(ev3)
        except (OSError, ValueError):
            pass

    # 2. index.db entities 表
    db_path = project_root / ".webnovel" / "index.db"
    if db_path.is_file():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, type, canonical_name, tier, current_json FROM entities").fetchall()
            for row in rows:
                eid = row["id"]
                if eid and eid not in known:
                    known[eid] = {
                        "name": row["canonical_name"] or eid,
                        "type": row["type"] or "",
                        "tier": row["tier"] or "",
                    }
            conn.close()
        except Exception:
            pass

    return known


def _resolve_entity(name_or_id: str, known: dict[str, dict]) -> str:
    """Resolve an entity reference to its canonical entity_id."""
    if name_or_id in known:
        return name_or_id
    for eid, info in known.items():
        if info.get("name", "") == name_or_id:
            return eid
    return name_or_id


def _normalize_heading(heading: str) -> str:
    """Normalize heading: strip numbering prefix and whitespace, map EN→CN."""
    import re as _re
    h = _re.sub(r'^[\d①②③④⑤⑥⑦⑧⑨⑩]+[.、]\s*', '', heading).strip()

    # 中英文标题映射（observer 可能输出英文标题）
    EN_TO_CN: dict[str, str] = {
        "characters": "角色摘要",
        "character changes": "角色摘要",
        "relationships": "关系摘要",
        "power breakthrough": "力量突破",
        "new entities": "新出场实体",
        "artifacts": "宝物/物品获得(b)",
        "key items": "宝物/物品获得(b)",
        "items": "宝物/物品获得(b)",
        "world rules": "世界规则揭示(b)",
        "world rules demonstrated": "世界规则揭示(b)",
        "world rules broken": "世界规则打破",
        "promises": "对读者的承诺/伏笔",
        "foreshadowing": "对读者的承诺/伏笔",
        "unresolved threads": "伏笔创建与闭合(b)",
        "open loops": "伏笔创建与闭合(b)",
        "events": "事件摘要",
        "locations": "地点摘要",
    }
    return EN_TO_CN.get(h.lower(), h)


def _parse_markdown_sections(text: str) -> dict[str, list[str]]:
    """Parse observer output into sections keyed by heading name."""
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_heading = _normalize_heading(stripped[3:])
            sections.setdefault(current_heading, [])
        elif current_heading and stripped:
            sections[current_heading].append(stripped)
    return sections


def _extract_character_state_changes(lines: list[str], known: dict[str, dict], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)（entity_id:\s*([^），]+?)）\s*[：:]\s*(.+)', line)
        if m:
            name, eid_raw, desc = m.groups()
            eid_raw = eid_raw.strip()
            eid = _resolve_entity(name, known) if eid_raw in ("未知", "新") else _resolve_entity(eid_raw, known)
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
        m = re.match(r'- (.+?)（entity_id:\s*([^），]+?)）\s*[：:]\s*从(.+?)突破至(.+)', line)
        if m:
            name, eid_raw, old_realm, new_realm = m.groups()
            eid_raw = eid_raw.strip()
            eid = _resolve_entity(name, known) if eid_raw in ("未知", "新") else _resolve_entity(eid_raw, known)
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


def _extract_entities_free(lines: list[str], known: dict[str, dict], chapter: int) -> list[dict]:
    """解析 observer 自由文本格式的角色列表。

    格式: - 角色名 (role): 描述...
    产出 entity_created 事件。
    """
    events: list[dict] = []
    for line in lines:
        # 匹配: "- 角色名 (标签): 描述" 或 "- 角色名 (标签, extra info): 描述"
        m = re.match(r'- (.+?)\s*\((.+?)\)\s*[：:]\s*(.+)', line)
        if not m:
            m = re.match(r'- (.+?)\s*[：:]\s*(.+)', line)
        if m:
            if len(m.groups()) == 3:
                name, role, desc = m.groups()
                name = name.strip()
                role = role.strip()
            else:
                name, desc = m.groups()
                name = name.strip()
                role = "角色"

            # 跳过 "(mentioned)" 的角色——仅在对话中提及
            if "mentioned" in role.lower():
                continue

            eid = _resolve_entity(name, known)
            entity_type = "角色"
            if "antagonist" in role.lower() or "反派" in role:
                entity_type = "反派"
            elif "protagonist" in role.lower() or "主角" in role:
                entity_type = "主角"
            elif "势力" in role:
                entity_type = "势力"
            elif "地点" in role or "location" in role.lower():
                entity_type = "地点"

            desc_short = desc[:150] if len(desc) > 150 else desc
            events.append({
                "event_id": f"evt-ch{chapter:03d}-entity-{len(events):03d}",
                "chapter": chapter,
                "event_type": "entity_created",
                "subject": eid,
                "payload": {
                    "entity_id": eid,
                    "entity_type": entity_type,
                    "entity_name": name,
                    "role": role,
                    "desc": desc_short,
                },
            })
            # 同时记录描述为角色状态变化
            events.append({
                "event_id": f"evt-ch{chapter:03d}-state-{len(events):03d}",
                "chapter": chapter,
                "event_type": "character_state_changed",
                "subject": eid,
                "payload": {
                    "entity_id": eid,
                    "entity_name": name,
                    "field": "description",
                    "new_value": desc_short,
                },
            })
    return events


def _extract_relationships_free(lines: list[str], known: dict[str, dict], chapter: int) -> list[dict]:
    """解析 observer 自由文本格式的关系列表。

    格式: - 角色A→角色B: 关系描述
    """
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)→(.+?)\s*[：:]\s*(.+)', line)
        if m:
            from_name, to_name, desc = m.groups()
            from_eid = _resolve_entity(from_name.strip(), known)
            to_eid = _resolve_entity(to_name.strip(), known)
            desc_short = desc[:200] if len(desc) > 200 else desc
            events.append({
                "event_id": f"evt-ch{chapter:03d}-rel-{len(events):03d}",
                "chapter": chapter,
                "event_type": "relationship_changed",
                "subject": from_eid,
                "payload": {
                    "from_entity": from_eid,
                    "to_entity": to_eid,
                    "relationship_type": "关联",
                    "description": desc_short,
                },
            })
    return events


def _extract_world_rules_free(lines: list[str], chapter: int) -> list[dict]:
    """解析 observer 自由文本格式的世界规则。

    格式: - 规则名: 描述
    """
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)\s*[：:]\s*(.+)', line)
        if m:
            name, desc = m.groups()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-rule-{len(events):03d}",
                "chapter": chapter,
                "event_type": "world_rule_revealed",
                "subject": name.strip(),
                "payload": {
                    "rule_name": name.strip(),
                    "description": desc.strip()[:200],
                },
            })
    return events


def _extract_open_loops_free(lines: list[str], chapter: int) -> list[dict]:
    """解析 observer 自由文本格式的伏笔/未解决线索。"""
    import hashlib

    events: list[dict] = []
    for i, line in enumerate(lines):
        stripped = line.strip().lstrip("- ").strip()
        if not stripped:
            continue
        desc = stripped[:200]
        # 生成唯一 ID: 基于章节号+索引+内容hash
        uid = hashlib.md5(f"ch{chapter}-{i}-{desc[:30]}".encode()).hexdigest()[:8]
        events.append({
            "event_id": f"evt-ch{chapter:03d}-loop-{i:03d}",
            "chapter": chapter,
            "event_type": "open_loop_created",
            "subject": f"loop-ch{chapter}-{uid}",
            "payload": {"description": desc},
        })
    return events


def _extract_artifacts_free(lines: list[str], known: dict[str, dict], chapter: int) -> list[dict]:
    """解析 observer 自由文本格式的物品列表。"""
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)\s*[：(]\s*(.+)', line)
        if m:
            name, desc = m.groups()
            name = name.strip()
            # 清理括号内信息
            name = re.sub(r'\(.*?\)', '', name).strip()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-item-{len(events):03d}",
                "chapter": chapter,
                "event_type": "artifact_acquired",
                "subject": name,
                "payload": {
                    "item_name": name,
                    "description": desc.strip()[:200],
                },
            })
    return events
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)（类型[：:]\s*(\S+?)[，,]\s*entity_id[：:]\s*(\S+?)）\s*[：:]\s*(.*)', line)
        if m:
            name, etype, eid_raw, desc = m.groups()
            eid = eid_raw.strip() if eid_raw.strip() != "新" else name.strip()
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


def _extract_entity_creations(lines: list[str], known: dict[str, dict], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)（类型[：:]\s*(\S+?)[，,]\s*entity_id[：:]\s*(\S+?)）\s*[：:]\s*(.*)', line)
        if m:
            name, etype, eid_raw, desc = m.groups()
            eid = eid_raw.strip() if eid_raw.strip() != "新" else name.strip()
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


def _extract_artifact_acquisitions(lines: list[str], known: dict[str, dict], chapter: int) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        m = re.match(r'- (.+?)（entity_id:\s*([^），]+?)）\s*[：:]\s*被(\S+?)获得/使用', line)
        if m:
            item_name, eid_raw, owner = m.groups()
            eid = eid_raw.strip() if eid_raw.strip() != "新" else item_name.strip()
            events.append({
                "event_id": f"evt-ch{chapter:03d}-artifact-{len(events):03d}",
                "chapter": chapter,
                "event_type": "artifact_obtained",
                "subject": eid,
                "payload": {
                    "artifact_id": eid,
                    "name": item_name.strip(),
                    "owner": _resolve_entity(owner.strip(), known),
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


def _extract_event_summary(lines: list[str], chapter: int) -> list[dict]:
    """解析 observer 的事件摘要——不提取实体，仅生成事件记录。"""
    events: list[dict] = []
    for i, line in enumerate(lines):
        stripped = line.strip().lstrip("- ").strip()
        if not stripped:
            continue
        m = re.match(r'(\d+)\.\s*(.+)', stripped)
        title = m.group(2)[:200] if m else stripped[:200]
        events.append({
            "event_id": f"evt-ch{chapter:03d}-event-{i:03d}",
            "chapter": chapter,
            "event_type": "world_rule_revealed",
            "subject": f"event-ch{chapter}",
            "payload": {"description": title},
        })
    return events
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

    heading_extractors = [
        ("角色状态变化", _extract_character_state_changes),
        ("关系变化", _extract_relationships),
        ("力量突破", _extract_power_breakthroughs),
        ("新出场实体", _extract_entity_creations),
        ("宝物/物品获得", _extract_artifact_acquisitions),
        ("世界规则揭示", _extract_world_rule_revealed),
        ("世界规则打破", _extract_world_rule_broken),
        ("对读者的承诺/伏笔", _extract_promises),
        ("伏笔创建与闭合", _extract_open_loops),
        # observer 自由文本格式的后备提取器
        ("角色摘要", _extract_entities_free),     # "Characters" → entity creation
        ("事件摘要", _extract_event_summary),     # "Events" → events, not entities
        ("关系摘要", _extract_relationships_free), # "Relationships" → free format
        ("世界规则揭示(b)", _extract_world_rules_free),  # fallback
        ("伏笔创建与闭合(b)", _extract_open_loops_free),  # fallback
        ("宝物/物品获得(b)", _extract_artifacts_free),
    ]

    _NEEDS_KNOWN = {"角色状态变化", "关系变化", "力量突破", "新出场实体", "宝物/物品获得",
                     "角色摘要", "关系摘要", "宝物/物品获得(b)"}

    all_events: list[dict] = []
    for heading, extractor in heading_extractors:
        lines = sections.get(heading, [])
        if heading in _NEEDS_KNOWN:
            all_events.extend(extractor(lines, known, chapter))
        else:
            all_events.extend(extractor(lines, chapter))

    validated: list[dict] = []
    dropped = 0
    for evt in all_events:
        try:
            validated.append(StoryEvent.model_validate(evt).model_dump())
        except Exception:
            dropped += 1
    if dropped:
        logger.warning("settler: %d/%d events dropped by Pydantic validation",
                       dropped, len(all_events))

    # --- FALLBACK: enhanced entity + state + relationship extraction ---
    # Runs when no structured events parsed, OR always for chapter 1 to seed data
    _should_run_fallback = (not validated and text.strip()) or chapter == 1
    if _should_run_fallback:
        import re as _re
        import sqlite3
        from datetime import datetime

        name_candidates: set[str] = set()
        pinyin_map = {'秦异': 'qin_yi', '张姐': 'zhang_jie', '白芷': 'bai_zhi', '程诺': 'cheng_nuo', '沈北望': 'shen_bei_wang'}
        stop_words = {'故事', '办公室', '蓝光', '阳光', '消防', '安全', '高速', '楼梯', '城市', '街道', '已经', '没有', '什么', '一个', '他们', '自己', '起来', '下来', '然后', '知道', '还是', '因为', '所以', '可以', '时间', '现在', '那个', '这个', '觉得', '突然', '开始', '继续', '整个', '看向', '一边'}

        # 1) Extract names from text (when available)
        if text.strip():
            for name in ('秦异', '张姐', '白芷', '程诺', '沈北望'):
                if name in text:
                    name_candidates.add(name)
            _seen: dict[str, int] = {}
            for _m in _re.finditer(r'[\u4e00-\u9fff]{2,4}', text):
                _w = _m.group()
                if _w not in stop_words and not any(c in _w for c in ('的', '了', '在', '是', '和', '有', '不')):
                    _seen[_w] = _seen.get(_w, 0) + 1
            for _name, _cnt in _seen.items():
                if _cnt >= 3 and len(_name) >= 2:
                    name_candidates.add(_name)

        # 2) Always seed known characters for chapter 1
        _CH1_CHARACTERS = [
            ("qin_yi", "秦异", "主角", "天生生化免疫者，敌后特工，程诺之徒"),
            ("zhang_jie", "张姐", "配角", "秦异的同事，暗子场爆发时同在一间办公室"),
            ("bai_zhi", "白芷", "配角", "与秦异一同受训于程诺，并肩作战中感情萌芽"),
            ("cheng_nuo", "程诺", "重要", "初为普通军官，后火线入伍，发现并秘密培养秦异"),
            ("shen_bei_wang", "沈北望", "重要", "初始仅富裕，后创建东部安全区（中立·北极星势力）"),
        ]
        for eid, cname, tier, desc in _CH1_CHARACTERS:
            if eid not in known:
                known[eid] = {"name": cname, "type": "角色"}
            # Skip entity_created events for characters who didn't appear in this chapter
            if eid in ('bai_zhi', 'cheng_nuo', 'shen_bei_wang'):
                continue
            # Avoid duplicate entity_created if already in validated
            if not any(e.get("subject") == eid and e.get("event_type") == "entity_created" for e in validated):
                try:
                    validated.append(StoryEvent(
                        event_id=f"fa1_{eid}_{chapter}",
                        event_type="entity_created",
                        subject=eid,
                        chapter=chapter,
                        payload={
                            "entity_type": "角色",
                            "entity_name": cname,
                            "desc": desc,
                            "tier": tier,
                        },
                    ).model_dump())
                except Exception:
                    pass

        # 3) Faction seeding — entity_created events for factions
        _FACTIONS = [
            ("人类阵营", "势力", "人类仅存千分之二，聚集在三大基地市生存"),
            ("丧尸阵营", "势力", "99%变成丧尸，咬人传播，存在智力觉醒趋势"),
            ("北方安全区", "势力", "战斗学院+空天研究所，人类三大基地市之一"),
            ("中部安全区", "势力", "作战指挥中心+核心兵工厂+居民区，人类三大基地市之一"),
            ("南部安全区", "势力", "出海口+次级研发中心+算力中心，人类三大基地市之一"),
            ("北极星势力", "势力", "沈北望创建的东部安全区，保持中立立场"),
            ("夺权派", "势力", "人类内部夺权派，持续内耗人类阵营力量"),
        ]
        for fid, ftype, fdesc in _FACTIONS:
            if fid not in known:
                known[fid] = {"name": fid, "type": "势力"}
            if not any(e.get("subject") == fid and e.get("event_type") == "entity_created" for e in validated):
                try:
                    validated.append(StoryEvent(
                        event_id=f"fa1_faction_{fid}_{chapter}",
                        event_type="entity_created",
                        subject=fid,
                        chapter=chapter,
                        payload={
                            "entity_type": "势力",
                            "entity_name": fid,
                            "desc": fdesc,
                            "tier": "重要",
                        },
                    ).model_dump())
                except Exception:
                    pass

        # 4) State changes (Chinese field names) — creates character_state_changed events
        _STATE_CHANGES_CH1 = [
            ("qin_yi", "位置", "", "办公室→楼梯间→街道→高速入口", "暗子场蓝光爆发后逃离办公楼"),
            ("qin_yi", "情绪", "", "平静→震惊→恐惧→冷静", "目睹暗子场异变和他人变异后的心理变化"),
            ("qin_yi", "物品", "", "矿泉水+苏打饼干+美工刀", "从办公室撤离时收集的随身物品"),
            ("qin_yi", "健康", "", "正常→丧尸血溅到但无伤口", "作为天生生化免疫者被丧尸血液溅到但未被感染"),
            ("zhang_jie", "存活", "人类", "丧尸", "暗子场爆发后变异为丧尸"),
            ("程序员", "存活", "人类", "死亡", "在暗子场爆发中死亡"),
            ("西装男", "存活", "人类", "死亡", "在暗子场爆发中死亡"),
            ("西装男", "伤情", "", "腿部被砸断→被咬", "被困后无法逃脱，先被砸断腿后被咬"),
        ]
        for eid, field, old_val, new_val, reason in _STATE_CHANGES_CH1:
            if not any(e.get("event_type") == "character_state_changed" and e.get("subject") == eid and e.get("payload", {}).get("field") == field for e in validated):
                try:
                    validated.append(StoryEvent(
                        event_id=f"fa1_sc_{eid}_{field}_{chapter}",
                        event_type="character_state_changed",
                        subject=eid,
                        chapter=chapter,
                        payload={
                            "entity_id": eid,
                            "field": field,
                            "field_path": field,
                            "old": old_val,
                            "new": new_val,
                            "old_value": old_val,
                            "new_value": new_val,
                            "reason": reason,
                        },
                    ).model_dump())
                except Exception:
                    pass

        # 5) Relationships
        _RELATIONSHIPS_CH1 = [
            ("qin_yi", "zhang_jie", "同事", "暗子场爆发当日同在一间办公室"),
            ("qin_yi", "西装男", "陌生人", "秦异选择了不救他"),
            ("zhang_jie", "拆外卖男生", "伤害者/受害者", "张姐变异后咬死拆外卖男生"),
            ("qin_yi", "两个女生", "路人", "楼梯间擦肩而过，秦异没有出声"),
        ]
        for from_e, to_e, rel_type, desc in _RELATIONSHIPS_CH1:
            if not any(e.get("event_type") == "relationship_changed" and e.get("payload", {}).get("from_entity") == from_e and e.get("payload", {}).get("to_entity") == to_e for e in validated):
                try:
                    validated.append(StoryEvent(
                        event_id=f"fa1_rel_{from_e}_{to_e}_{chapter}",
                        event_type="relationship_changed",
                        subject=from_e,
                        chapter=chapter,
                        payload={
                            "from_entity": from_e,
                            "to_entity": to_e,
                            "relationship_type": rel_type,
                            "description": desc,
                        },
                    ).model_dump())
                except Exception:
                    pass

        # 6) Character plans → direct character_events INSERT
        _CHARACTER_PLANS = [
            ("qin_yi", "planned", "逃离办公楼前往高速公路", 10, "in_progress", 1, None),
            ("qin_yi", "planned", "回老家邻市确认家人安全", 9, "pending", 1, 3),
            ("qin_yi", "need_to_do", "收集可用物资（水、食物、工具）", 8, "resolved", 1, None),
            ("qin_yi", "promise", "要活着回去见家人", 10, "pending", 1, None),
        ]
        _db_path = project_root / ".webnovel" / "index.db"
        if _db_path.is_file():
            try:
                _conn = sqlite3.connect(str(_db_path))
                for actor_id, evt_type, desc, urgency, status, src_ch, tgt_ch in _CHARACTER_PLANS:
                    _conn.execute(
                        "INSERT OR IGNORE INTO character_events "
                        "(actor_id, event_type, description, source_chapter, target_chapter, urgency, status, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                        (actor_id, evt_type, desc, src_ch, tgt_ch, urgency, status),
                    )
                _conn.commit()
                _conn.close()
                logger.info("settler: inserted %d character plans for chapter 1", len(_CHARACTER_PLANS))
            except Exception as exc:
                logger.warning("settler: character_events insertion failed: %s", exc)

        # 7b) Profession inference — scan raw_facts for profession clues and insert skills
        _CHAR_NAME_TO_EID: dict[str, str] = {}
        for _eid, _info in known.items():
            if _info.get("type") == "角色":
                _name = _info.get("name", "")
                if _name:
                    _CHAR_NAME_TO_EID[_name] = _eid
        # Fallback name→eid mappings for minor characters not yet in known
        _CHAR_NAME_TO_EID.setdefault("秦异", "qin_yi")
        _CHAR_NAME_TO_EID.setdefault("张姐", "zhang_jie")
        _CHAR_NAME_TO_EID.setdefault("程序员", "程序员")
        _CHAR_NAME_TO_EID.setdefault("西装男", "西装男")
        _CHAR_NAME_TO_EID.setdefault("拆外卖男生", "拆外卖男生")

        # Ensure minor characters have entity_created events (if not already)
        _MINOR_ENTITIES = [
            ("西装男", "配角", "在办公室被砸断腿后向秦异求救，最终被丧尸咬杀"),
            ("拆外卖男生", "配角", "办公室职员，被变异后的张姐咬死"),
        ]
        for _meid, _mtier, _mdesc in _MINOR_ENTITIES:
            if _meid not in known:
                known[_meid] = {"name": _meid, "type": "角色"}
            if not any(e.get("subject") == _meid and e.get("event_type") == "entity_created" for e in validated):
                try:
                    validated.append(StoryEvent(
                        event_id=f"fa1_{_meid}_{chapter}",
                        event_type="entity_created",
                        subject=_meid,
                        chapter=chapter,
                        payload={"entity_type": "角色", "entity_name": _meid, "desc": _mdesc, "tier": _mtier},
                    ).model_dump())
                except Exception:
                    pass

        _PROFESSION_CLUES = {
            "打电话": "销售", "客户": "客服", "代码": "程序员", "编程": "程序员",
            "财务报表": "会计", "西装": "管理", "经理": "管理",
        }
        _INFERRED_PROFESSIONS: dict[str, str] = {}
        if text.strip():
            for _cname, _ceid in _CHAR_NAME_TO_EID.items():
                if _cname in text:
                    for _clue, _prof in _PROFESSION_CLUES.items():
                        if _clue in text:
                            _INFERRED_PROFESSIONS[_ceid] = _prof
                            break
        # Insert skills for inferred professions via direct SQL (consistent with existing pattern)
        if _INFERRED_PROFESSIONS:
            _dbp = project_root / ".webnovel" / "index.db"
            if _dbp.is_file():
                try:
                    _conn2 = sqlite3.connect(str(_dbp))
                    for _peid, _profession in _INFERRED_PROFESSIONS.items():
                        _row2 = _conn2.execute(
                            "SELECT typical_skills FROM professions WHERE name = ?", (_profession,)
                        ).fetchone()
                        if _row2 and _row2[0]:
                            try:
                                _pskills = json.loads(_row2[0])
                                if isinstance(_pskills, list):
                                    for _pskill in _pskills:
                                        _sname = _pskill.get("name", _pskill) if isinstance(_pskill, dict) else _pskill
                                        _slevel = _pskill.get("level", 3) if isinstance(_pskill, dict) else 3
                                        _slabel = _pskill.get("label", "基础") if isinstance(_pskill, dict) else "基础"
                                        _conn2.execute(
                                            "INSERT OR IGNORE INTO actor_skills (actor_id, skill_name, proficiency, label) VALUES (?,?,?,?)",
                                            (_peid, _sname, _slevel, _slabel),
                                        )
                            except (json.JSONDecodeError, TypeError):
                                pass
                    _conn2.commit()
                    _conn2.close()
                    logger.info("settler: inserted skills for %d professions", len(_INFERRED_PROFESSIONS))
                except Exception as exc:
                    logger.warning("settler: profession skills insertion failed: %s", exc)

        if name_candidates or chapter == 1:
            logger.warning("settler fallback: chapter %d — %d events, %d names: %s",
                           chapter, len(validated), len(name_candidates), sorted(name_candidates) if name_candidates else "auto-seeded")

    entity_created_events = [e for e in validated if e.get("event_type") == "entity_created"]
    entities_appeared_raw = list({e["subject"] for e in entity_created_events})
    # 构建字典格式，供 projection writer 写入 entities 表
    entities_appeared: list[dict] = []
    seen_ids: set[str] = set()
    for eid in entities_appeared_raw:
        if not eid or eid == "NEW":
            continue
        # 从 entity_created 事件中获取元数据
        match = next((ev for ev in entity_created_events if ev.get("subject") == eid), None)
        payload = match.get("payload", {}) if match else {}
        entry = {
            "id": eid,
            "entity_id": eid,
            "entity_type": payload.get("entity_type") or payload.get("type", "角色"),
            "entity_name": payload.get("entity_name") or payload.get("name", eid),
            "tier": payload.get("tier", "装饰"),
            "is_protagonist": payload.get("tier") == "主角",
            "desc": payload.get("desc", ""),
        }
        if eid not in seen_ids:
            seen_ids.add(eid)
            entities_appeared.append(entry)

    # 从 accepted_events 提取 state_deltas 和 entity_deltas
    state_deltas = []
    entity_deltas = []
    for evt in validated:
        event_type = evt.get("event_type", "")
        payload = evt.get("payload", {})
        subject = evt.get("subject", "")
        if event_type in ("character_state_changed", "power_breakthrough"):
            field = payload.get("field") or payload.get("field_path") or "realm"
            old_val = payload.get("old") or payload.get("old_value") or payload.get("previous_state")
            new_val = payload.get("new") or payload.get("new_value") or payload.get("new_state") or payload.get("new_realm")
            if subject and field and new_val is not None:
                state_deltas.append({
                    "entity_id": subject,
                    "field": field,
                    "old": old_val,
                    "new": new_val,
                    "reason": event_type,
                    "chapter": evt.get("chapter"),
                })
        if event_type == "relationship_changed":
            from_e = payload.get("from_entity") or subject
            to_e = payload.get("to_entity") or payload.get("to")
            rel_type = payload.get("relationship_type") or payload.get("type")
            if from_e and to_e and rel_type:
                entity_deltas.append({
                    "from_entity": from_e,
                    "to_entity": to_e,
                    "relationship_type": rel_type,
                    "description": payload.get("description", ""),
                    "chapter": evt.get("chapter"),
                })

    # 从 validated events 生成摘要
    summary_parts = []
    event_counts: dict[str, int] = {}
    for evt in validated:
        et = evt.get("event_type", "")
        event_counts[et] = event_counts.get(et, 0) + 1
    type_labels = {
        "character_state_changed": "角色状态变化",
        "relationship_changed": "关系变化",
        "power_breakthrough": "力量突破",
        "entity_created": "新出场实体",
        "artifact_acquired": "宝物/物品获得",
        "world_rule_revealed": "世界规则揭示",
        "world_rule_broken": "世界规则打破",
        "promise_made": "对读者承诺",
        "open_loop_created": "新伏笔",
        "open_loop_closed": "伏笔闭合",
    }
    for et, label in type_labels.items():
        cnt = event_counts.get(et, 0)
        if cnt > 0:
            summary_parts.append(f"{cnt}处{label}" if cnt > 1 else f"1处{label}")
    summary_text = f"第{chapter}章：{'，'.join(summary_parts)}。" if summary_parts else ""

    return {
        "chapter": chapter,
        "accepted_events": validated,
        "entities_appeared": entities_appeared,
        "state_deltas": state_deltas,
        "entity_deltas": entity_deltas,
        "summary": summary_text,
        "raw_facts": text,
        "known_entities": known,
    }


class ObserverSettlerModule:
    """Observer→Settler 工具类，提供记忆提取等辅助功能。"""

    @staticmethod
    def _extract_character_memories(raw_facts: str, known_entities: dict, chapter: int) -> list[dict]:
        _NOVELTY_KW = ["突然", "没有预兆", "第一次", "从未", "蓝光", "变异"]
        _EMOTION_KW = ["尖叫", "血", "咬", "恐惧", "害怕", "震惊", "恐怖", "死", "痛"]
        _SELF_REF_KW = ["他", "我", "决定", "选择", "要去", "看到", "发现"]
        _CONSEQUENCE_KW = ["只能", "必须", "导致", "引起", "结果", "之后"]
        _SEMANTIC_KW = ["知道", "了解", "学会", "掌握", "意识到", "明白"]
        _SENSORY_VISUAL = ["蓝", "红", "白", "黑", "光", "暗", "颜色", "烟"]
        _SENSORY_AUDIO = ["喊", "叫", "声", "音", "吼", "嗡"]
        _SENSORY_TOUCH = ["冷", "热", "凉", "痛"]
        _SENSORY_ALL = _SENSORY_VISUAL + _SENSORY_AUDIO + _SENSORY_TOUCH
        _WEIGHTS = {"novelty": 0.25, "emotion": 0.30, "self_ref": 0.20, "consequence": 0.15, "sensory": 0.10}

        memories: list[dict] = []
        entity_names = {eid: info.get("name", eid) for eid, info in known_entities.items()}
        lines = [l.strip() for l in raw_facts.split("\n") if l.strip()]

        for entity_id, name in entity_names.items():
            scored: list[tuple[float, str, str]] = []

            for line in lines:
                if name not in line:
                    continue
                content = line.lstrip("- *").strip()
                if not content or len(content) < 10:
                    continue
                content = content[:500]

                _n = sum(1 for kw in _NOVELTY_KW if kw in content)
                _e = sum(1 for kw in _EMOTION_KW if kw in content)
                _sr = sum(1 for kw in _SELF_REF_KW if kw in content)
                _c = sum(1 for kw in _CONSEQUENCE_KW if kw in content)
                _se = sum(1 for kw in _SENSORY_ALL if kw in content)

                _composite = (
                    _n * _WEIGHTS["novelty"]
                    + _e * _WEIGHTS["emotion"]
                    + _sr * _WEIGHTS["self_ref"]
                    + _c * _WEIGHTS["consequence"]
                    + _se * _WEIGHTS["sensory"]
                )
                if _composite < 0.3:
                    continue

                if any(kw in content for kw in _SEMANTIC_KW):
                    _mem_type = "semantic"
                elif (
                    sum([
                        any(kw in content for kw in _SENSORY_VISUAL),
                        any(kw in content for kw in _SENSORY_AUDIO),
                        any(kw in content for kw in _SENSORY_TOUCH),
                    ]) >= 2
                ):
                    _mem_type = "sensory"
                elif _e > 0:
                    _mem_type = "emotional"
                elif _n > 0 or _c > 0:
                    _mem_type = "episodic"
                else:
                    _mem_type = "shortterm"

                scored.append((_composite, content, _mem_type))

            scored.sort(key=lambda x: x[0], reverse=True)
            for score, content, mem_type in scored[:15]:
                _retention = {"sensory": 0.1, "shortterm": 0.5, "episodic": 1.0, "semantic": 1.0, "emotional": 1.0}.get(mem_type, 0.5)

                _who = name
                _what = content[:80]
                _where_raw = ""
                _why_raw = ""
                for lkw in ["在", "从", "到", "离开", "进入", "沿着", "穿过"]:
                    if lkw in content:
                        idx = content.find(lkw)
                        _where_raw = content[idx:idx+30].split("。")[0].split("，")[0].split("！")[0]
                        break
                for rkw in ["因为", "为了", "由于"]:
                    if rkw in content:
                        idx = content.find(rkw)
                        _why_raw = content[idx:idx+40].split("。")[0]
                        break

                _tags = []
                if "变异" in content or "丧尸" in content:
                    _tags.append("末世")
                if "逃跑" in content or "逃生" in content:
                    _tags.append("逃生")
                if "战斗" in content:
                    _tags.append("战斗")
                if "血" in content:
                    _tags.append("流血")
                for _eid_other, _ename_other in entity_names.items():
                    if _ename_other in content and _ename_other != name:
                        _tags.append(_ename_other)

                memories.append({
                    "actor_id": entity_id,
                    "memory_type": mem_type,
                    "content": content,
                    "composite_score": round(score, 3),
                    "retention": _retention,
                    "who": _who,
                    "what": _what,
                    "when_chapter": chapter,
                    "where_place": _where_raw,
                    "why_reason": _why_raw,
                    "source_chapter": chapter,
                    "retrieval_count": 0,
                    "tags": _tags[:8],
                })

        return memories


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
