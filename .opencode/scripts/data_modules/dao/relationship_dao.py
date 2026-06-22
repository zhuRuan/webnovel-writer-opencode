#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RelationshipDAO — data access for relationships and relationship_events tables."""

from __future__ import annotations

from .base import BaseDAO


class RelationshipDAO(BaseDAO):
    """Parameterized SQL access to relationships (current snapshot) and
    relationship_events (append-only event log)."""

    # ── relationships (current snapshot) ─────────────────────────────

    def list_relationships(self, entity_id: str = None, limit: int = 1000) -> list[dict]:
        """列出所有关系（当前快照），可选按 entity_id 过滤。

        entity_id 同时匹配 from_entity 和 to_entity。
        """
        if entity_id:
            return self._fetch(
                "SELECT * FROM relationships "
                "WHERE from_entity = ? OR to_entity = ? "
                "ORDER BY chapter DESC, id DESC "
                "LIMIT ?",
                (entity_id, entity_id, limit),
            )
        return self._fetch(
            "SELECT * FROM relationships ORDER BY chapter DESC, id DESC LIMIT ?",
            (limit,),
        )

    def upsert_relationship(
        self,
        from_e: str,
        to_e: str,
        rel_type: str,
        description: str,
        chapter: int,
    ) -> dict | None:
        """INSERT OR IGNORE（UNIQUE 约束 from_entity, to_entity, type）。

        已存在则忽略，返回现有行；新增则返回新行。
        """
        self._execute(
            "INSERT OR IGNORE INTO relationships "
            "(from_entity, to_entity, type, description, chapter) "
            "VALUES (?, ?, ?, ?, ?)",
            (from_e, to_e, rel_type, description, chapter),
        )
        rows = self._fetch(
            "SELECT * FROM relationships "
            "WHERE from_entity = ? AND to_entity = ? AND type = ?",
            (from_e, to_e, rel_type),
        )
        return rows[0] if rows else None

    # ── relationship_events (append-only log) ────────────────────

    def list_relationship_events(
        self,
        entity_id: str = None,
        chapter: int = None,
        limit: int = 5000,
    ) -> list[dict]:
        """列出关系事件，支持按 entity_id / chapter 过滤。

        entity_id 同时匹配 from_entity 和 to_entity。
        """
        clauses: list[str] = []
        params: list = []

        if entity_id is not None:
            clauses.append("(from_entity = ? OR to_entity = ?)")
            params.extend([entity_id, entity_id])
        if chapter is not None:
            clauses.append("chapter = ?")
            params.append(chapter)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        return self._fetch(
            f"SELECT * FROM relationship_events{where} "
            "ORDER BY chapter DESC, id DESC LIMIT ?",
            tuple(params),
        )

    def record_relationship_event(self, data: dict) -> dict:
        """INSERT 一条关系事件。必须字段：from_entity, to_entity, type, chapter。

        可选字段：action, polarity, strength, description, scene_index,
                   evidence, confidence — 缺失时使用表默认值。

        Returns: 插入后的完整行。
        """
        columns = [
            "from_entity",
            "to_entity",
            "type",
            "chapter",
            "action",
            "polarity",
            "strength",
            "description",
            "scene_index",
            "evidence",
            "confidence",
        ]
        defaults = {
            "action": "update",
            "polarity": 0,
            "strength": 0.5,
            "description": None,
            "scene_index": 0,
            "evidence": None,
            "confidence": 1.0,
        }

        values: list = []
        for col in columns:
            val = data.get(col, defaults.get(col))
            values.append(val)

        placeholders = ", ".join("?" for _ in columns)
        cols_joined = ", ".join(columns)

        rowid = self._execute(
            f"INSERT INTO relationship_events ({cols_joined}) VALUES ({placeholders})",
            tuple(values),
        )
        rows = self._fetch(
            "SELECT * FROM relationship_events WHERE id = ?", (rowid,)
        )
        return rows[0] if rows else {}
