#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KnowledgeDAO — entity knowledge queries with graceful degradation across
entities table + theater/actors/* + actor_skills table.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .base import BaseDAO


class KnowledgeDAO(BaseDAO):
    """Parameterized SQL + theater JSON access for entity knowledge."""

    # ── entity knowledge ────────────────────────────────────────────────

    def get_entity_knowledge(
        self, entity_id: str, project_root: str | Path
    ) -> Optional[dict]:
        """Return combined entity knowledge with graceful degradation.

        Returns None when the entity is not found in the entities table.
        """
        root = Path(project_root)

        # 1. Query entities table
        rows = self._fetch("SELECT * FROM entities WHERE id = ?", (entity_id,))
        entity_row = rows[0] if rows else None
        if not entity_row:
            return None

        # 2. Defaults from entities table
        name = entity_row.get("canonical_name", entity_id)
        source = "entity_only"
        core_desire = ""
        traits: list = []
        known_domains: dict[str, float] = {}
        skills: list[dict] = []

        # 2a. Extract traits / core_desire from current_json
        cj = entity_row.get("current_json", "{}")
        try:
            cj_data = json.loads(cj) if isinstance(cj, str) else cj
            if isinstance(cj_data, dict):
                raw_traits = cj_data.get("traits", [])
                traits = list(raw_traits) if isinstance(raw_traits, list) else ([raw_traits] if raw_traits else [])
                core_desire = cj_data.get("core_desire", "") or ""
        except (json.JSONDecodeError, TypeError):
            pass

        # 3. Try theater actor data (overrides defaults)
        actor_dir = root / "theater" / "actors" / entity_id
        if actor_dir.is_dir():
            source = "theater"

            # 3a. Read profile.json
            profile_path = actor_dir / "profile.json"
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                if isinstance(profile, dict):
                    name = profile.get("name", name)
                    core_desire = profile.get("core_desire", core_desire) or ""
                    p_traits = profile.get("traits", [])
                    if isinstance(p_traits, list) and p_traits:
                        traits = p_traits
            except (OSError, json.JSONDecodeError):
                pass

            # 3b. Read common_knowledge/actor_domains.json for known_domains
            try:
                from data_modules.theater.actor_manager import get_common_knowledge

                knowledge = get_common_knowledge(root, entity_id)
                kd = knowledge.get("known_domains", {})
                if isinstance(kd, dict):
                    known_domains = kd
            except (ModuleNotFoundError, Exception):
                pass

            # 3c. Query actor_skills table
            skills = self.get_actor_skills(entity_id)

        # 4. Safe type normalization
        return {
            "entity_id": entity_id,
            "name": name,
            "core_desire": core_desire if isinstance(core_desire, str) else "",
            "traits": traits if isinstance(traits, list) else [],
            "known_domains": known_domains if isinstance(known_domains, dict) else {},
            "skills": skills,
            "source": source,
        }

    # ── actor skills ────────────────────────────────────────────────────

    def get_actor_skills(self, actor_id: str) -> list[dict]:
        """Query actor_skills table; returns [] when table is missing."""
        try:
            rows = self._fetch(
                "SELECT skill_name, proficiency, label, note "
                "FROM actor_skills WHERE actor_id = ?",
                (actor_id,),
            )
        except Exception:
            return []

        result: list[dict] = []
        for r in rows:
            result.append({
                "name": r.get("skill_name", ""),
                "proficiency": r.get("proficiency", 0),
                "label": r.get("label", ""),
                "note": r.get("note", ""),
            })
        return result

    # ── theater actors list (fallback for empty entities table) ─────────

    def get_theater_actors_list(self, project_root: str | Path) -> list[dict]:
        """Scan theater/actors/ directory, read profile.json for basic info.

        Used as fallback when the entities table is empty.
        """
        root = Path(project_root)
        actors_dir = root / "theater" / "actors"
        if not actors_dir.is_dir():
            return []

        result: list[dict] = []
        for entry in sorted(actors_dir.iterdir()):
            if not entry.is_dir():
                continue
            actor_id = entry.name

            profile_path = entry / "profile.json"
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                profile = {}

            if not isinstance(profile, dict):
                profile = {}

            tier = profile.get("tier", "extra")
            entity_type = {
                "main": "主角",
                "supporting": "配角",
                "extra": "路人",
            }.get(tier, "角色")

            result.append({
                "actor_id": actor_id,
                "type": entity_type,
                "canonical_name": profile.get("name", actor_id),
                "tier": tier,
                "desc": profile.get("background", ""),
                "current_json": json.dumps({
                    "traits": profile.get("traits", []),
                    "role": profile.get("role", ""),
                    "core_desire": profile.get("core_desire", ""),
                }, ensure_ascii=False),
                "first_appearance": profile.get("intro_chapter", 0),
                "last_appearance": profile.get("last_active_chapter")
                                   or profile.get("intro_chapter", 0),
                "is_protagonist": 1 if profile.get("tier_rank") == 1 else 0,
                "is_archived": 0,
                "source": "theater",
            })

        return result
