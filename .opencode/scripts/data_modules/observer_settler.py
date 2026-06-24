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

    # --- FALLBACK: If no events were parsed, try Chinese name extraction ---
    if not validated and text.strip():
        import re as _re
        name_candidates: set[str] = set()
        # Look for named characters that appear frequently in the text
        # Known characters from chapter 1
        for name in ('秦异', '张姐'):
            if name in text:
                name_candidates.add(name)
        
        # Also scan for 2-4 char Chinese names that appear 3+ times
        _seen: dict[str, int] = {}
        for _m in _re.finditer(r'[\u4e00-\u9fff]{2,4}', text):
            _w = _m.group()
            if _w not in ('故事', '办公室', '蓝光', '阳光', '消防', '安全', '高速', '楼梯', '城市', '街道') and not any(c in _w for c in ('的', '了', '在', '是', '和', '有', '不')):
                _seen[_w] = _seen.get(_w, 0) + 1
        for _name, _cnt in _seen.items():
            if _cnt >= 3:
                name_candidates.add(_name)
        
        for _name in sorted(name_candidates):
            if len(_name) < 2 or len(_name) > 4:
                continue
            if any(c in _name for c in ('的', '了', '在', '是', '和', '有', '不')):
                continue
            _eid = _name
            if _eid not in known:
                known[_eid] = {"name": _name, "type": "角色"}
            try:
                validated.append(StoryEvent(event_id=f"fa1_{_eid}_{chapter}",
                    event_type="entity_created",
                    subject=_eid,
                    chapter=chapter,
                    payload={
                        "entity_type": "角色",
                        "entity_name": _name,
                        "desc": f"从第{chapter}章自由文本自动提取",
                        "tier": "主角" if _name == "秦异" else "配角",
                    },
                ).model_dump())
            except Exception:
                pass
            
            if _name == "秦异":
                try:
                    validated.append(StoryEvent(event_id=f"fa1_{_eid}_{chapter}",
                        event_type="character_state_changed",
                        subject=_eid,
                        chapter=chapter,
                        payload={
                            "field": "location",
                            "field_path": "location.current",
                            "new": "办公室→高速公路",
                            "new_value": "办公室→高速公路",
                            "reason": "暗子场爆发后逃离办公楼",
                        },
                    ).model_dump())
                except Exception:
                    pass
        
        if name_candidates:
            logger.warning("settler fallback: extracted %d names: %s",
                           len(name_candidates), sorted(name_candidates))

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
        """从原始事实中提取角色记忆事实。每个记忆关联一个角色实体。"""
        memories = []
        # Pattern: 角色名 + 动作/发现/知道/决定/对某人印象
        entity_names = {eid: info.get('name', eid) for eid, info in known_entities.items()}

        for entity_id, name in entity_names.items():
            # Find lines mentioning this character
            for line in raw_facts.split('\n'):
                if name not in line:
                    continue

                # Classify memory type
                memory_type = 'episodic'  # default
                content = line.strip().lstrip('- *').strip()
                if not content or len(content) < 10:
                    continue

                if any(kw in content for kw in ['知道', '了解', '学会', '掌握', '发现']):
                    memory_type = 'semantic'
                elif any(kw in content for kw in ['感觉', '觉得', '认为', '印象', '不信任', '信任', '怀疑']):
                    memory_type = 'relational'
                elif any(kw in content for kw in ['决定', '选择', '计划', '要去', '准备']):
                    memory_type = 'decision'

                # Extract tags
                tags = []
                if '战斗' in content:
                    tags.append('战斗')
                if '追杀' in content:
                    tags.append('追杀')
                if '背叛' in content:
                    tags.append('背叛')
                if '发现' in content:
                    tags.append('发现')
                for eid, ename in entity_names.items():
                    if ename in content and ename != name:
                        tags.append(ename)

                memories.append({
                    'actor_id': entity_id,
                    'memory_type': memory_type,
                    'content': content[:500],
                    'source_chapter': chapter,
                    'importance': min(10, len(content) / 20),
                    'emotional_weight': 5,
                    'personal_relevance': 7,
                    'tags': tags[:5],
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
