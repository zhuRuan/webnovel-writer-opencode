from .base import BaseDAO

VALID_EVENT_TYPES = ('need_to_do', 'want_to_do', 'planned', 'promise', 'prerequisite')
ALLOWED_UPDATE_FIELDS = {'status', 'urgency', 'description', 'target_chapter'}


class CharacterEventDAO(BaseDAO):
    """角色事件 DAO — character_events 表（事件驱动替代 chase_debt）"""

    # ── 查询 ──────────────────────────────────────────────

    def list_events(self, actor_id=None, status=None, overdue=False,
                    current_chapter=0, threshold=10):
        """列出事件，支持按角色/状态/逾期过滤。

        Returns: {"events": [...], "total": N}
        """
        where = ["1=1"]
        params = []

        if actor_id is not None:
            where.append("actor_id = ?")
            params.append(actor_id)
        if status is not None:
            where.append("status = ?")
            params.append(status)
        if overdue:
            where.append("status IN ('pending','in_progress')")
            where.append("target_chapter IS NOT NULL")
            where.append("(target_chapter + ?) < ?")
            params.append(threshold)
            params.append(current_chapter)

        where_clause = " AND ".join(where)
        rows = self._fetch(
            f"SELECT * FROM character_events WHERE {where_clause} "
            "ORDER BY urgency DESC, created_at DESC",
            tuple(params),
        )
        return {"events": rows, "total": len(rows)}

    def get_overdue_events(self, current_chapter: int, threshold: int = 10) -> list[dict]:
        """查询逾期事件：pending/in_progress 且 target_chapter + threshold < current_chapter。"""
        return self._fetch(
            "SELECT * FROM character_events "
            "WHERE status IN ('pending','in_progress') "
            "AND target_chapter IS NOT NULL "
            "AND (target_chapter + ?) < ? "
            "ORDER BY urgency DESC, created_at DESC",
            (threshold, current_chapter),
        )

    # ── 增 ────────────────────────────────────────────────

    def create_event(self, data: dict) -> dict:
        """创建事件，自动设置 status='pending', created_at=CURRENT_TIMESTAMP。

        必须字段：actor_id, event_type, description, source_chapter
        Raises: ValueError 如果 event_type 不合法。
        """
        event_type = data.get("event_type", "")
        if event_type not in VALID_EVENT_TYPES:
            raise ValueError(
                f"Invalid event_type '{event_type}', must be one of {VALID_EVENT_TYPES}"
            )

        rowid = self._execute(
            "INSERT INTO character_events "
            "(actor_id, event_type, description, source_chapter, target_chapter, "
            "prerequisites, trigger_condition, urgency, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                data["actor_id"],
                event_type,
                data["description"],
                data["source_chapter"],
                data.get("target_chapter"),
                data.get("prerequisites", "[]"),
                data.get("trigger_condition", ""),
                data.get("urgency", 5),
            ),
        )
        rows = self._fetch(
            "SELECT * FROM character_events WHERE id = ?", (rowid,)
        )
        return rows[0] if rows else {}

    # ── 改 ────────────────────────────────────────────────

    def update_event(self, event_id: int, data: dict) -> dict | None:
        """更新事件，仅允许修改 status, urgency, description, target_chapter。

        Returns: 更新后的行，不存在返回 None。
        """
        # 过滤出允许的字段
        updates = {k: v for k, v in data.items() if k in ALLOWED_UPDATE_FIELDS}
        if not updates:
            return None

        if not self._exists("character_events", "id = ?", (event_id,)):
            return None

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        set_clause += ", updated_at = CURRENT_TIMESTAMP"
        values = list(updates.values()) + [event_id]

        self._execute(
            f"UPDATE character_events SET {set_clause} WHERE id = ?",
            tuple(values),
        )
        rows = self._fetch(
            "SELECT * FROM character_events WHERE id = ?", (event_id,)
        )
        return rows[0] if rows else None

    # ── 删 ────────────────────────────────────────────────

    def delete_event(self, event_id: int) -> bool:
        """删除事件，返回 True（已删除）或 False（不存在）。"""
        if not self._exists("character_events", "id = ?", (event_id,)):
            return False
        self._execute("DELETE FROM character_events WHERE id = ?", (event_id,))
        return True

    # ── 解决 ──────────────────────────────────────────────

    def resolve_event(self, event_id: int, chapter=None) -> dict | None:
        """标记事件为 resolved，可选记录 resolved_chapter。

        Returns: 更新后的行，不存在返回 None。
        """
        if not self._exists("character_events", "id = ?", (event_id,)):
            return None

        if chapter is not None:
            self._execute(
                "UPDATE character_events SET status = 'resolved', "
                "resolved_chapter = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (chapter, event_id),
            )
        else:
            self._execute(
                "UPDATE character_events SET status = 'resolved', "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (event_id,),
            )
        rows = self._fetch(
            "SELECT * FROM character_events WHERE id = ?", (event_id,)
        )
        return rows[0] if rows else None
