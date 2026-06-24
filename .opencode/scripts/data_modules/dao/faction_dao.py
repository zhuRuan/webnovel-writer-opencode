#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FactionDAO — faction queries with relationship aggregation statistics."""

from __future__ import annotations


from .base import BaseDAO


class FactionDAO(BaseDAO):
    """势力数据访问 — 从 entities 表查询势力，聚合关系统计。"""

    def list_factions(self, limit: int = 200, offset: int = 0) -> dict:
        """列出所有势力（type='势力', 未归档），带关系聚合统计。

        Args:
            limit: 最大返回势力数（默认 200）
            offset: 偏移量（默认 0）

        Returns:
            {"factions": [{id, canonical_name, tier, desc, member_count,
                           enemies, allies, first_appearance, last_appearance,
                           relationships: [...]}]}
        """
        factions = self._fetch(
            "SELECT * FROM entities "
            "WHERE type = '势力' AND is_archived = 0 "
            "ORDER BY tier ASC, canonical_name ASC "
            "LIMIT ? OFFSET ?",
            (limit, offset),
        )

        # 关系加载上限，避免单势力海量关系撑爆内存
        RELATIONSHIP_LIMIT = 500

        result: list[dict] = []
        for f in factions:
            fid = f["id"]

            # 聚合统计：成员数 = 关联到该势力的关系数
            member_count = self._count(
                "relationships", "to_entity = ?", (fid,)
            )

            # 敌对关系数
            enemies = self._count(
                "relationships",
                "to_entity = ? AND type LIKE ?",
                (fid, "%敌对%"),
            )

            # 合作/联盟关系数
            allies = self._count(
                "relationships",
                "to_entity = ? AND (type LIKE ? OR type LIKE ?)",
                (fid, "%合作%", "%联盟%"),
            )

            # 该势力的所有关系（限制上限）
            relationships = self._fetch(
                "SELECT * FROM relationships "
                "WHERE from_entity = ? OR to_entity = ? "
                "ORDER BY chapter DESC LIMIT ?",
                (fid, fid, RELATIONSHIP_LIMIT),
            )

            result.append({
                "id": fid,
                "canonical_name": f["canonical_name"],
                "tier": f["tier"],
                "desc": f.get("desc"),
                "member_count": member_count,
                "enemies": enemies,
                "allies": allies,
                "first_appearance": f.get("first_appearance"),
                "last_appearance": f.get("last_appearance"),
                "relationships": relationships,
            })

        return {"factions": result}

    def get_faction(self, faction_id: str) -> dict | None:
        """查询单个势力，带关系聚合统计。不是势力类型则返回 None。

        Returns: 同 list_factions 中单个元素的结构，不存在或非势力时返回 None。
        """
        rows = self._fetch(
            "SELECT * FROM entities "
            "WHERE id = ? AND type = '势力' AND is_archived = 0",
            (faction_id,),
        )
        if not rows:
            return None

        f = rows[0]
        fid = f["id"]

        member_count = self._count(
            "relationships", "to_entity = ?", (fid,)
        )
        enemies = self._count(
            "relationships",
            "to_entity = ? AND type LIKE ?",
            (fid, "%敌对%"),
        )
        allies = self._count(
            "relationships",
            "to_entity = ? AND (type LIKE ? OR type LIKE ?)",
            (fid, "%合作%", "%联盟%"),
        )
        relationships = self._fetch(
            "SELECT * FROM relationships "
            "WHERE from_entity = ? OR to_entity = ? "
            "ORDER BY chapter DESC",
            (fid, fid),
        )

        return {
            "id": fid,
            "canonical_name": f["canonical_name"],
            "tier": f["tier"],
            "desc": f.get("desc"),
            "member_count": member_count,
            "enemies": enemies,
            "allies": allies,
            "first_appearance": f.get("first_appearance"),
            "last_appearance": f.get("last_appearance"),
            "relationships": relationships,
        }

    # ── helpers ──────────────────────────────────────────────────

    def _count(self, table: str, where: str, params: tuple = ()) -> int:
        """返回 COUNT(*) 结果。表不存在时静默返回 0。"""
        with self._conn() as conn:
            try:
                row = conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM {table} WHERE {where}",
                    params,
                ).fetchone()
                return row[0] if row else 0
            except Exception:
                return 0
