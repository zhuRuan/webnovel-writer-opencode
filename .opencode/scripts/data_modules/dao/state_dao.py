#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StateDAO — 角色状态管理，操作 character_state 和 state_changes 表。"""

from __future__ import annotations

import json
from typing import Optional

from .base import BaseDAO

# 合法的 change_type 值（用于 state_changes.field 复合前缀）
VALID_CHANGE_TYPES = ("health", "equipment", "inventory", "location", "description", "trait")


class StateDAO(BaseDAO):
    """角色状态数据访问 — character_state + state_changes 增删改查。

    character_state 表（当前状态快照）:
        actor_id, health(JSON), equipment(JSON), inventory(JSON), location, chapter, updated_at

    state_changes 表（事件溯源）:
        列: id, entity_id, field, old_value, new_value, reason, chapter, created_at
        field 列编码: 新行使用 "{change_type}.{field_name}" 格式 (如 "health.hp"),
                     旧行使用纯字段名 (如 "description") — 兼容两种格式。
    """

    # ── character_state 查询 ───────────────────────────────────────────

    def get_state(self, actor_id: str) -> dict | None:
        """获取角色的完整当前状态。

        Returns:
            解析后的 dict（JSON 字段已反序列化），无记录返回 None。
        """
        rows = self._fetch(
            "SELECT * FROM character_state WHERE actor_id = ?",
            (actor_id,),
        )
        if not rows:
            return None
        return self._parse_state_row(rows[0])

    def get_memory_strength(self, actor_id: str) -> int:
        """查询角色的记忆强度，无记录时返回默认值 5。"""
        state = self.get_state(actor_id)
        if state:
            val = state.get("memory_strength")
            if val is not None:
                return val
        return 5

    def upsert_state(self, actor_id: str, data: dict) -> dict:
        """创建或更新角色状态，智能合并 JSON 字段。

        data 可包含:
            health (dict)  — dict.update 合并
            equipment (list) — extend 追加
            inventory (list) — extend 追加
            location (str) — 覆盖
            chapter (int)  — 覆盖

        Returns:
            更新后的完整状态（与 get_state 格式相同）。
        """
        existing = self.get_state(actor_id)

        if existing:
            # 合并 JSON 字段
            merged = self._merge_state_json(existing, data)
        else:
            # 新记录
            merged = self._default_state(data)

        merged["actor_id"] = actor_id

        self._execute(
            "INSERT OR REPLACE INTO character_state "
            "(actor_id, health, equipment, inventory, location, memory_strength, chapter, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (
                actor_id,
                json.dumps(merged["health"], ensure_ascii=False),
                json.dumps(merged["equipment"], ensure_ascii=False),
                json.dumps(merged["inventory"], ensure_ascii=False),
                merged.get("location", ""),
                merged.get("memory_strength", 5),
                merged.get("chapter", 0),
            ),
        )

        return self.get_state(actor_id) or merged

    # ── state_changes 追溯 ─────────────────────────────────────────────

    def get_state_history(
        self,
        actor_id: str,
        change_type: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """查询角色的状态变化历史。

        Args:
            actor_id: 角色实体 ID
            change_type: 可选过滤（health/equipment/inventory/location/description/trait）
            limit: 最大返回数

        Returns:
            变化记录列表，每项包含: id, entity_id, field, old_value, new_value,
            reason, chapter, created_at, change_type（解析自 field 前缀）, sub_field
        """
        if change_type:
            # 新行: field = "health.hp"
            # 旧行: field = "description" (纯字段名)
            # 两者都匹配: LIKE 'health.%' OR field = 'health'
            rows = self._fetch(
                "SELECT * FROM state_changes "
                "WHERE entity_id = ? AND (field LIKE ? ESCAPE '\\' OR field = ?) "
                "ORDER BY chapter DESC, id DESC LIMIT ?",
                (actor_id, f"{change_type}.%", change_type, limit),
            )
        else:
            rows = self._fetch(
                "SELECT * FROM state_changes "
                "WHERE entity_id = ? "
                "ORDER BY chapter DESC, id DESC LIMIT ?",
                (actor_id, limit),
            )

        return [self._parse_state_change_row(r) for r in rows]

    def record_state_change(
        self,
        actor_id: str,
        change_type: str,
        field: str,
        old_value: str,
        new_value: str,
        chapter: int,
        reason: str = "",
    ) -> bool:
        """记录一次状态变化事件。

        Args:
            actor_id: 角色实体 ID
            change_type: health/equipment/inventory/location/description/trait
            field: 字段名（如 "hp", "sword", "current"）
            old_value: 旧值
            new_value: 新值
            chapter: 发生章节
            reason: 变化原因

        Returns:
            True 如果插入成功。
        """
        # 用复合字段名编码 change_type → "health.hp", "equipment.sword"
        composite_field = f"{change_type}.{field}"

        rowid = self._execute(
            "INSERT INTO state_changes "
            "(entity_id, field, old_value, new_value, reason, chapter) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (actor_id, composite_field, old_value, new_value, reason, chapter),
        )
        return rowid > 0

    # ── 综合视图 ───────────────────────────────────────────────────────

    def get_character_stats(self, actor_id: str) -> dict:
        """获取角色状态的综合视图。

        Returns:
            {
                "actor_id": str,
                "health": {hp, max_hp, injuries, status_effects},
                "equipment": [{name, slot, grade, effects}],
                "inventory": [{name, quantity, description}],
                "location": str,
                "last_updated_chapter": int
            }
            无状态记录时返回带默认值的 schema。
        """
        state = self.get_state(actor_id)
        if state is not None:
            return {
                "actor_id": actor_id,
                "health": state.get("health", {}),
                "equipment": state.get("equipment", []),
                "inventory": state.get("inventory", []),
                "location": state.get("location", ""),
                "last_updated_chapter": state.get("chapter", 0),
            }

        return {
            "actor_id": actor_id,
            "health": {
                "hp": 100,
                "max_hp": 100,
                "injuries": [],
                "status_effects": [],
            },
            "equipment": [],
            "inventory": [],
            "location": "",
            "last_updated_chapter": 0,
        }

    # ── 内部辅助 ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_state_row(row: dict) -> dict:
        """反序列化 character_state 行的 JSON 字段。"""
        result = dict(row)
        for field_name in ("health", "equipment", "inventory"):
            raw = result.get(field_name)
            if isinstance(raw, str):
                try:
                    result[field_name] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    result[field_name] = {} if field_name == "health" else []
        # 兼容旧行：memory_strength 为 NULL 时回退到默认值 5
        if result.get("memory_strength") is None:
            result["memory_strength"] = 5
        return result

    @staticmethod
    def _parse_state_change_row(row: dict) -> dict:
        """解析 state_changes 行，从复合 field 名拆出 change_type 和 sub_field。

        新行格式: field = "health.hp" → change_type="health", sub_field="hp"
        旧行格式: field = "description" → change_type="description", sub_field="description"
        """
        result = dict(row)
        raw_field = str(result.get("field", "") or "")
        if "." in raw_field:
            # 新格式: "health.hp"
            parts = raw_field.split(".", 1)
            result["change_type"] = parts[0]
            result["sub_field"] = parts[1]
        else:
            # 旧格式: "description"
            result["change_type"] = raw_field
            result["sub_field"] = raw_field
        return result

    @staticmethod
    def _default_state(data: dict) -> dict:
        """从输入 data 构建默认状态字典（用于新记录）。"""
        return {
            "health": data.get("health", {"hp": 100, "max_hp": 100, "injuries": [], "status_effects": []}),
            "equipment": data.get("equipment", []) if isinstance(data.get("equipment"), list) else [],
            "inventory": data.get("inventory", []) if isinstance(data.get("inventory"), list) else [],
            "location": data.get("location", ""),
            "memory_strength": data.get("memory_strength", 5),
            "chapter": data.get("chapter", 0),
        }

    @staticmethod
    def _merge_state_json(existing: dict, incoming: dict) -> dict:
        """智能合并新旧状态: health dict.update, equipment/inventory extend, location/chapter 覆盖。"""
        merged = dict(existing)

        # health: dict.update（浅层合并）
        if "health" in incoming:
            incoming_health = incoming["health"]
            if isinstance(incoming_health, dict):
                merged_health = dict(merged.get("health", {}))
                merged_health.update(incoming_health)
                merged["health"] = merged_health

        # equipment: extend 列表
        if "equipment" in incoming:
            incoming_eq = incoming["equipment"]
            if isinstance(incoming_eq, list):
                existing_eq = merged.get("equipment", [])
                if not isinstance(existing_eq, list):
                    existing_eq = []
                merged["equipment"] = existing_eq + incoming_eq

        # inventory: extend 列表
        if "inventory" in incoming:
            incoming_inv = incoming["inventory"]
            if isinstance(incoming_inv, list):
                existing_inv = merged.get("inventory", [])
                if not isinstance(existing_inv, list):
                    existing_inv = []
                merged["inventory"] = existing_inv + incoming_inv

        # location、chapter、memory_strength: 直接覆盖
        if "location" in incoming:
            merged["location"] = incoming["location"]
        if "chapter" in incoming:
            merged["chapter"] = incoming["chapter"]
        if "memory_strength" in incoming:
            merged["memory_strength"] = incoming["memory_strength"]

        return merged
