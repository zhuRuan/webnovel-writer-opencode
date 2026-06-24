#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EntityDAO — data access for entities, aliases, and state_changes."""

from __future__ import annotations

import json
from typing import Optional

from .base import BaseDAO


class EntityDAO(BaseDAO):
    """Parameterized SQL access to entities / aliases / state_changes tables."""

    # ── entities ──────────────────────────────────────────────────────

    def list_entities(
        self,
        entity_type: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        clauses: list[str] = ["1=1"]
        params: list = []

        if entity_type:
            clauses.append("type = ?")
            params.append(entity_type)
        if not include_archived:
            clauses.append("is_archived = 0")

        where = " AND ".join(clauses)
        params.extend([limit, offset])
        return self._fetch(
            f"SELECT * FROM entities WHERE {where} ORDER BY last_appearance DESC "
            f"LIMIT ? OFFSET ?",
            tuple(params),
        )

    def get_entity(self, entity_id: str) -> dict | None:
        rows = self._fetch("SELECT * FROM entities WHERE id = ?", (entity_id,))
        return rows[0] if rows else None

    def upsert_entity(self, data: dict) -> dict:
        """INSERT OR REPLACE into entities with smart current_json merge.

        Returns the saved row (post-insert query).
        """
        entity_id = data.get("id")
        if not entity_id:
            raise ValueError("entity data must include 'id'")

        # smart-merge current_json when entity already exists
        existing = self.get_entity(entity_id)
        if existing and data.get("current_json") and existing.get("current_json"):
            try:
                old = (
                    json.loads(existing["current_json"])
                    if isinstance(existing["current_json"], str)
                    else existing["current_json"]
                )
                new = (
                    json.loads(data["current_json"])
                    if isinstance(data["current_json"], str)
                    else data["current_json"]
                )
                merged = {**old, **new}
                data = {**data, "current_json": json.dumps(merged, ensure_ascii=False)}
            except (json.JSONDecodeError, TypeError):
                pass  # fall through to plain INSERT OR REPLACE

        columns = [
            "id",
            "type",
            "canonical_name",
            "tier",
            "desc",
            "current_json",
            "first_appearance",
            "last_appearance",
            "is_protagonist",
            "is_archived",
        ]

        values: list = []
        for col in columns:
            val = data.get(col)
            if col in ("is_protagonist", "is_archived"):
                val = 1 if val else 0
            elif col in ("first_appearance", "last_appearance"):
                val = int(val) if val else 0
            elif col == "tier":
                val = val or "装饰"
            elif col == "current_json" and isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            values.append(val)

        placeholders = ", ".join("?" for _ in columns)
        cols_joined = ", ".join(columns)

        self._execute(
            f"INSERT OR REPLACE INTO entities ({cols_joined}) VALUES ({placeholders})",
            tuple(values),
        )
        return self.get_entity(entity_id)

    # ── timeline ──────────────────────────────────────────────────────

    def get_entity_timeline(self, entity_id: str) -> dict:
        """Return state_changes + appearances for an entity.

        appearances silently returns [] when the table is missing.
        """
        state_changes = self._fetch(
            "SELECT * FROM state_changes WHERE entity_id = ? ORDER BY chapter DESC",
            (entity_id,),
        )
        appearances = self._fetch(
            "SELECT * FROM appearances WHERE entity_id = ? ORDER BY chapter DESC",
            (entity_id,),
        )
        return {"state_changes": state_changes, "appearances": appearances}

    # ── aliases ───────────────────────────────────────────────────────

    def list_aliases(self, entity_id: Optional[str] = None) -> list[dict]:
        if entity_id:
            return self._fetch(
                "SELECT * FROM aliases WHERE entity_id = ?", (entity_id,)
            )
        return self._fetch("SELECT * FROM aliases")

    # ── state_changes ─────────────────────────────────────────────────

    def get_state_changes(
        self, entity_id: Optional[str] = None, limit: int = 50
    ) -> list[dict]:
        if entity_id:
            return self._fetch(
                "SELECT * FROM state_changes WHERE entity_id = ? "
                "ORDER BY chapter DESC LIMIT ?",
                (entity_id, limit),
            )
        return self._fetch(
            "SELECT * FROM state_changes ORDER BY chapter DESC LIMIT ?",
            (limit,),
        )

    # ── consistency ───────────────────────────────────────────────────

    def get_consistency_anomalies(
        self, entity_id: Optional[str] = None
    ) -> list[dict]:
        """Find entity/field pairs with contradictory state_changes.

        Returns entities whose state_changes contain multiple distinct values
        for the same field — a signal of possible inconsistency.
        """
        base = (
            "SELECT entity_id, field, "
            "COUNT(DISTINCT COALESCE(new_value, '')) AS val_count, "
            "GROUP_CONCAT(DISTINCT new_value) AS all_values, "
            "MIN(chapter) AS first_chapter, MAX(chapter) AS last_chapter "
            "FROM state_changes "
        )
        if entity_id:
            return self._fetch(
                f"{base} WHERE entity_id = ? "
                "GROUP BY entity_id, field "
                "HAVING COUNT(DISTINCT COALESCE(new_value, '')) > 1",
                (entity_id,),
            )
        return self._fetch(
            f"{base} GROUP BY entity_id, field "
            "HAVING COUNT(DISTINCT COALESCE(new_value, '')) > 1"
        )
