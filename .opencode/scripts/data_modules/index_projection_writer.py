#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .commit_artifacts import extraction_dict, extraction_list, extraction_text
from .config import DataModulesConfig
from .index_manager import ChapterMeta, EntityMeta, IndexManager, SceneMeta, StateChangeMeta

try:
    from chapter_paths import find_chapter_file
except ImportError:  # pragma: no cover
    from scripts.chapter_paths import find_chapter_file


def _proficiency_label(level: int) -> str:
    if level <= 2: return "入门"
    elif level <= 4: return "基础"
    elif level <= 6: return "熟练"
    elif level <= 8: return "精通"
    else: return "大师"


_DEFAULT_EXTRA_SKILLS = {
    "掠夺者": [("格斗", 4, "熟练"), ("警觉", 5, "熟练"), ("追踪", 4, "熟练"), ("野外生存", 3, "基础")],
    "军人": [("格斗", 6, "熟练"), ("枪械", 6, "熟练"), ("战术", 5, "熟练"), ("纪律", 7, "精通"), ("负重", 5, "熟练")],
    "商人": [("谈判", 5, "熟练"), ("估价", 6, "熟练"), ("警觉", 4, "熟练"), ("社交", 5, "熟练")],
    "村民": [("农耕", 5, "熟练"), ("手工", 4, "熟练"), ("警觉", 3, "基础"), ("社交", 4, "基础")],
    "医疗": [("急救", 6, "熟练"), ("药草", 5, "熟练"), ("诊断", 5, "熟练"), ("社交", 4, "基础")],
    "技术员": [("工程", 6, "熟练"), ("电子", 6, "熟练"), ("修理", 5, "熟练"), ("编程", 4, "基础")],
    "废土游民": [("野外生存", 6, "熟练"), ("警觉", 6, "熟练"), ("拾荒", 5, "熟练"), ("追踪", 4, "熟练")],
    "default": [("格斗", 3, "基础"), ("警觉", 4, "基础"), ("求生", 3, "基础")],
    "extra": [("格斗", 3, "基础"), ("警觉", 4, "基础")],
    "supporting": [("格斗", 5, "熟练"), ("枪械", 4, "基础"), ("警觉", 5, "熟练"), ("谈判", 4, "基础")],
}

class IndexProjectionWriter:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def _inject_default_skills(self, actor_id: str, entity_type: str | None = None) -> None:
        """为角色注入默认技能。根据 entity_type 匹配不同技能组。"""
        skills = _DEFAULT_EXTRA_SKILLS.get(entity_type or 'default', _DEFAULT_EXTRA_SKILLS['default'])
        try:
            db_path = self.project_root / ".webnovel" / "index.db"
            if not db_path.is_file():
                return
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            for skill_name, proficiency, label in skills:
                conn.execute(
                    "INSERT OR IGNORE INTO actor_skills (actor_id, skill_name, proficiency, label) VALUES (?,?,?,?)",
                    (actor_id, skill_name, proficiency, label),
                )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _sync_theater_actor(self, actor_id: str, name: str, entity_type: str, chapter: int) -> None:
        actor_dir = self.project_root / "theater" / "actors" / actor_id
        if actor_dir.is_dir():
            return
        try:
            from datetime import datetime, timezone
            actor_dir.mkdir(parents=True, exist_ok=True)
            (actor_dir / "chapter_memories").mkdir(exist_ok=True)
            tier_role = {"主角": "main", "配角": "supporting", "反派": "supporting"}.get(entity_type, "extra")
            profile = {"actor_id": actor_id, "name": name, "tier": tier_role, "intro_chapter": chapter, "traits": [], "background": "", "role": entity_type}
            if entity_type == "主角":
                profile["tier_rank"] = 1
            (actor_dir / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            for f, d in [("habits.json", {"habits": []}), ("secrets.json", {}), ("relationships.json", {}), ("current_state.json", {"actor_id": actor_id})]:
                (actor_dir / f).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            self._inject_default_skills(actor_id, entity_type)
            registry_path = self.project_root / "theater" / "actors" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.is_file() else {}
            registry.setdefault("actors", {})[actor_id] = {"name": name, "tier": tier_role, "intro_chapter": chapter, "created_at": datetime.now(timezone.utc).isoformat()}
            registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def apply(self, commit_payload: dict) -> dict:
        if commit_payload["meta"]["status"] != "accepted":
            return {"applied": False, "writer": "index", "reason": "commit_rejected"}

        manager = IndexManager(DataModulesConfig.from_project_root(self.project_root))
        applied_count = 0
        chapter_applied = self._upsert_chapter(manager, commit_payload)
        if chapter_applied:
            applied_count += 1

        scenes_count = self._apply_scenes(manager, commit_payload)
        applied_count += scenes_count

        appearances_count = self._apply_appearances(manager, commit_payload)
        applied_count += appearances_count

        state_changes_count = self._apply_state_changes(manager, commit_payload)
        applied_count += state_changes_count

        entity_delta_count = 0
        for delta in self._collect_entity_deltas(commit_payload):
            result = manager.apply_entity_delta(delta)
            if result:
                entity_delta_count += 1
                applied_count += 1
        return {
            "applied": applied_count > 0,
            "writer": "index",
            "applied_count": applied_count,
            "chapters": 1 if chapter_applied else 0,
            "scenes": scenes_count,
            "appearances": appearances_count,
            "state_changes": state_changes_count,
            "entity_deltas": entity_delta_count,
        }

    def _upsert_chapter(self, manager: IndexManager, commit_payload: dict) -> bool:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        if chapter <= 0:
            return False

        meta = extraction_dict(commit_payload, "chapter_meta")
        summary_text = extraction_text(commit_payload, "summary_text")

        title = str(
            meta.get("title")
            or commit_payload.get("chapter_title")
            or self._title_from_chapter_file(chapter)
            or ""
        ).strip()
        location = str(meta.get("location") or commit_payload.get("location") or "").strip()
        summary = str(summary_text or meta.get("summary") or "").strip()
        word_count = self._safe_int(meta.get("word_count") or commit_payload.get("word_count"))
        if word_count <= 0:
            word_count = self._chapter_word_count(chapter)

        characters = meta.get("characters") or self._collect_character_ids(commit_payload)
        if not isinstance(characters, list):
            characters = []

        manager.add_chapter(
            ChapterMeta(
                chapter=chapter,
                title=title,
                location=location,
                word_count=word_count,
                characters=[str(c) for c in characters if str(c).strip()],
                summary=summary,
            )
        )
        return True

    def _apply_scenes(self, manager: IndexManager, commit_payload: dict) -> int:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        scenes = extraction_list(commit_payload, "scenes")
        if chapter <= 0 or not isinstance(scenes, list) or not scenes:
            return 0

        scene_metas: list[SceneMeta] = []
        for idx, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            scene_index = self._safe_int(scene.get("scene_index") or scene.get("index") or idx)
            characters = scene.get("characters") or scene.get("character_ids") or []
            if not isinstance(characters, list):
                characters = []
            scene_metas.append(
                SceneMeta(
                    chapter=chapter,
                    scene_index=scene_index,
                    start_line=self._safe_int(scene.get("start_line")),
                    end_line=self._safe_int(scene.get("end_line")),
                    location=str(scene.get("location") or "").strip(),
                    summary=str(scene.get("summary") or scene.get("content") or "").strip(),
                    characters=[str(c) for c in characters if str(c).strip()],
                )
            )
        if not scene_metas:
            return 0
        manager.add_scenes(chapter, scene_metas)
        return len(scene_metas)

    def _apply_appearances(self, manager: IndexManager, commit_payload: dict) -> int:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        entities = extraction_list(commit_payload, "entities_appeared")
        if chapter <= 0 or not isinstance(entities, list):
            return 0

        applied = 0
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            entity_id = str(entity.get("id") or entity.get("entity_id") or "").strip()
            if not entity_id or entity_id == "NEW":
                continue

            entity_type = str(entity.get("entity_type") or entity.get("type") or "角色").strip()
            entity_name = str(entity.get("entity_name") or entity.get("name") or entity_id).strip()
            manager.upsert_entity(EntityMeta(id=entity_id, type=entity_type, canonical_name=entity_name, first_appearance=chapter, last_appearance=chapter, desc=str(entity.get("desc") or "")[:500]), update_metadata=False)
            self._sync_theater_actor(entity_id, entity_name, entity_type, chapter)

            mentions = entity.get("mentions") or []
            if isinstance(mentions, str):
                mentions = [mentions]
            if not isinstance(mentions, list):
                mentions = []
            manager.record_appearance(
                entity_id=entity_id,
                chapter=chapter,
                mentions=[str(m) for m in mentions if str(m).strip()],
                confidence=self._safe_float(entity.get("confidence"), 1.0),
            )
            applied += 1
        return applied

    def _apply_state_changes(self, manager: IndexManager, commit_payload: dict) -> int:
        applied = 0
        for change in self._collect_state_changes(commit_payload):
            entity_id = str(change.get("entity_id") or "").strip()
            field = str(change.get("field") or "").strip()
            chapter = self._safe_int(change.get("chapter") or commit_payload.get("meta", {}).get("chapter"))
            if not entity_id or not field or chapter <= 0:
                continue
            old_value = self._stringify(change.get("old"))
            new_value = self._stringify(change.get("new"))
            reason = str(change.get("reason") or "").strip()
            if self._state_change_exists(manager, entity_id, field, old_value, new_value, reason, chapter):
                continue
            manager.record_state_change(
                StateChangeMeta(
                    entity_id=entity_id,
                    field=field,
                    old_value=old_value,
                    new_value=new_value,
                    reason=reason,
                    chapter=chapter,
                )
            )
            applied += 1
        return applied

    def _collect_state_changes(self, commit_payload: dict) -> list[dict]:
        deltas = [
            self._normalize_state_delta(delta)
            for delta in extraction_list(commit_payload, "state_deltas")
            if isinstance(delta, dict)
        ]
        seen = {
            (
                str(delta.get("entity_id") or "").strip(),
                str(delta.get("field") or "").strip(),
                self._safe_int(delta.get("chapter") or commit_payload.get("meta", {}).get("chapter")),
            )
            for delta in deltas
        }

        for event in extraction_list(commit_payload, "accepted_events"):
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "").strip()
            payload = dict(event.get("payload") or {})
            if event_type == "power_breakthrough":
                field = str(payload.get("field") or payload.get("field_path") or "realm").strip()
            elif event_type == "character_state_changed":
                field = str(payload.get("field") or payload.get("field_path") or "").strip()
            else:
                continue
            entity_id = str(payload.get("entity_id") or event.get("subject") or "").strip()
            chapter = self._safe_int(event.get("chapter") or commit_payload.get("meta", {}).get("chapter"))
            key = (entity_id, field, chapter)
            if not entity_id or not field or key in seen:
                continue
            seen.add(key)
            deltas.append(
                {
                    "entity_id": entity_id,
                    "field": field,
                    "old": (
                        payload.get("old")
                        if "old" in payload
                        else payload.get("from")
                        if "from" in payload
                        else payload.get("old_value")
                        if "old_value" in payload
                        else payload.get("previous_state")
                    ),
                    "new": (
                        payload.get("new")
                        if "new" in payload
                        else payload.get("to")
                        if "to" in payload
                        else payload.get("new_value")
                        if "new_value" in payload
                        else payload.get("new_state")
                    ),
                    "reason": event_type,
                    "chapter": chapter,
                }
            )
        return deltas

    def _normalize_state_delta(self, delta: dict) -> dict:
        result = dict(delta)
        if "field" not in result and "field_path" in result:
            result["field"] = result["field_path"]
        if "new" not in result and "new_value" in result:
            result["new"] = result["new_value"]
        if "old" not in result and "old_value" in result:
            result["old"] = result["old_value"]
        return result

    def _state_change_exists(
        self,
        manager: IndexManager,
        entity_id: str,
        field: str,
        old_value: str,
        new_value: str,
        reason: str,
        chapter: int,
    ) -> bool:
        with manager._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1 FROM state_changes
                WHERE entity_id = ?
                  AND field = ?
                  AND chapter = ?
                  AND COALESCE(old_value, '') = ?
                  AND COALESCE(new_value, '') = ?
                  AND COALESCE(reason, '') = ?
                LIMIT 1
                """,
                (entity_id, field, chapter, old_value, new_value, reason),
            )
            return cursor.fetchone() is not None

    def _collect_character_ids(self, commit_payload: dict) -> list[str]:
        ids: list[str] = []
        for entity in extraction_list(commit_payload, "entities_appeared"):
            if not isinstance(entity, dict):
                continue
            entity_id = str(entity.get("id") or entity.get("entity_id") or "").strip()
            if entity_id and entity_id != "NEW":
                ids.append(entity_id)
        for delta in extraction_list(commit_payload, "entity_deltas"):
            if not isinstance(delta, dict):
                continue
            entity_id = str(delta.get("entity_id") or delta.get("id") or "").strip()
            entity_type = str(delta.get("type") or delta.get("entity_type") or "").strip()
            if entity_id and (not entity_type or entity_type == "角色"):
                ids.append(entity_id)
        return list(dict.fromkeys(ids))

    def _title_from_chapter_file(self, chapter: int) -> str:
        path = find_chapter_file(self.project_root, chapter)
        if path is None:
            return ""
        stem = path.stem
        match = re.match(r"第0*\d+章[-_ ]+(.+)$", stem)
        return match.group(1).strip() if match else ""

    def _chapter_word_count(self, chapter: int) -> int:
        path = find_chapter_file(self.project_root, chapter)
        if path is None:
            return 0
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return 0
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"^#+ .*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"---", "", text)
        return len(text.strip())

    def _stringify(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)

    def _safe_int(self, value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _safe_float(self, value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _collect_entity_deltas(self, commit_payload: dict) -> list[dict]:
        deltas = [dict(delta) for delta in extraction_list(commit_payload, "entity_deltas") if isinstance(delta, dict)]
        for event in extraction_list(commit_payload, "accepted_events"):
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "").strip()
            payload = dict(event.get("payload") or {})
            chapter = int(event.get("chapter") or commit_payload.get("meta", {}).get("chapter") or 0)
            if event_type == "relationship_changed":
                from_entity = str(payload.get("from_entity") or event.get("subject") or "").strip()
                to_entity = str(payload.get("to_entity") or payload.get("to") or "").strip()
                rel_type = str(
                    payload.get("relationship_type")
                    or payload.get("relation_type")
                    or payload.get("type")
                    or ""
                ).strip()
                if from_entity and to_entity and rel_type:
                    deltas.append(
                        {
                            "from_entity": from_entity,
                            "to_entity": to_entity,
                            "relationship_type": rel_type,
                            "description": str(payload.get("description") or "").strip(),
                            "chapter": chapter,
                        }
                    )
            elif event_type == "artifact_obtained":
                entity_id = str(
                    payload.get("artifact_id")
                    or payload.get("entity_id")
                    or payload.get("id")
                    or event.get("subject")
                    or ""
                ).strip()
                if not entity_id:
                    continue
                current = {}
                owner = str(payload.get("owner") or payload.get("holder") or "").strip()
                location = str(payload.get("location") or "").strip()
                if owner:
                    current["holder"] = owner
                if location:
                    current["location"] = location
                deltas.append(
                    {
                        "entity_id": entity_id,
                        "canonical_name": str(payload.get("name") or event.get("subject") or entity_id).strip(),
                        "type": str(payload.get("type") or "物品").strip() or "物品",
                        "current": current,
                        "desc": str(payload.get("description") or "").strip(),
                        "chapter": chapter,
                    }
                )
        return deltas
