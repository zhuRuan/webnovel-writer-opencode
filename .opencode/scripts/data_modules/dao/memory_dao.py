import math
from .base import BaseDAO

VALID_MEMORY_TYPES = ('episodic', 'semantic', 'relational', 'decision')


class MemoryDAO(BaseDAO):

    # ── 查询 ──────────────────────────────────────────────

    def list_memories(self, actor_id=None, memory_type=None, tag=None,
                      limit=50, offset=0):
        where = ["1=1"]
        params = []
        joins = ""

        if actor_id is not None:
            where.append("cm.actor_id = ?")
            params.append(actor_id)
        if memory_type is not None:
            where.append("cm.memory_type = ?")
            params.append(memory_type)
        if tag is not None:
            joins = "JOIN memory_tags mt ON cm.id = mt.memory_id"
            where.append("mt.tag = ?")
            params.append(tag)

        where_clause = " AND ".join(where)
        count_rows = self._fetch(
            f"SELECT COUNT(*) as cnt FROM character_memories cm {joins} "
            f"WHERE {where_clause}",
            tuple(params),
        )
        total = count_rows[0]["cnt"] if count_rows else 0

        rows = self._fetch(
            f"SELECT cm.* FROM character_memories cm {joins} "
            f"WHERE {where_clause} "
            f"ORDER BY cm.retention DESC, cm.importance DESC, cm.created_at DESC "
            f"LIMIT ? OFFSET ?",
            tuple(params) + (limit, offset),
        )
        return {"memories": rows, "total": total}

    def get_memory(self, memory_id: int):
        rows = self._fetch(
            "SELECT * FROM character_memories WHERE id = ?", (memory_id,)
        )
        if not rows:
            return None
        memory = rows[0]
        tags = self._fetch(
            "SELECT tag FROM memory_tags WHERE memory_id = ?", (memory_id,)
        )
        memory["tags"] = [t["tag"] for t in tags]
        return memory

    # ── 增 ────────────────────────────────────────────────

    def create_memory(self, data: dict):
        if data.get("memory_type", "") not in VALID_MEMORY_TYPES:
            raise ValueError(
                f"Invalid memory_type '{data.get('memory_type')}', "
                f"must be one of {VALID_MEMORY_TYPES}"
            )

        emotional_weight = data.get("emotional_weight", 5.0)
        personal_relevance = data.get("personal_relevance", 5.0)
        novelty = data.get("novelty", 5.0)
        consequence = data.get("consequence", 5.0)
        importance = data.get("importance")
        if importance is None:
            importance = (
                emotional_weight * 0.4
                + personal_relevance * 0.3
                + novelty * 0.2
                + consequence * 0.1
            )

        rowid = self._execute(
            "INSERT INTO character_memories "
            "(actor_id, memory_type, content, who, what, when_chapter, "
            "where_place, why_reason, importance, emotional_weight, "
            "personal_relevance, novelty, consequence, retention, "
            "retrieval_count, source_chapter, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, 0, ?, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                data["actor_id"],
                data["memory_type"],
                data["content"],
                data.get("who"),
                data.get("what"),
                data.get("when_chapter"),
                data.get("where_place"),
                data.get("why_reason"),
                importance,
                emotional_weight,
                personal_relevance,
                novelty,
                consequence,
                data["source_chapter"],
            ),
        )

        tags = data.get("tags", [])
        if tags:
            for tag in tags:
                self._execute(
                    "INSERT OR IGNORE INTO memory_tags (memory_id, tag) "
                    "VALUES (?, ?)",
                    (rowid, str(tag)),
                )

        return self.get_memory(rowid)

    # ── 删 ────────────────────────────────────────────────

    def delete_memory(self, memory_id: int) -> bool:
        if not self._exists("character_memories", "id = ?", (memory_id,)):
            return False
        self._execute("DELETE FROM character_memories WHERE id = ?", (memory_id,))
        return True

    # ── RAG 检索 ──────────────────────────────────────────

    def rag_search(self, actor_id: str, query_text: str, k: int = 10):
        keywords = [w.strip() for w in query_text.split() if len(w.strip()) >= 2]
        if not keywords:
            return []

        like_conditions = " OR ".join(["cm.content LIKE ?" for _ in keywords])
        like_params = [f"%{kw}%" for kw in keywords]

        rows = self._fetch(
            f"SELECT cm.* FROM character_memories cm "
            f"WHERE cm.actor_id = ? AND cm.retention >= 0.3 "
            f"AND ({like_conditions}) "
            f"ORDER BY cm.retention DESC, cm.importance DESC "
            f"LIMIT ?",
            tuple([actor_id] + like_params + [k * 2]),
        )

        scored = []
        for r in rows:
            content = r["content"] or ""
            text_relevance = sum(
                1 for kw in keywords if kw.lower() in content.lower()
            ) / max(len(keywords), 1)
            retention = r["retention"] or 1.0
            importance = r["importance"] or 5.0
            score = text_relevance * 0.5 + retention * 0.3 + importance * 0.2
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_k = scored[:k]

        for _, r in top_k:
            mem_id = r["id"]
            self._execute(
                "UPDATE character_memories SET retrieval_count = retrieval_count + 1, "
                "retention = MIN(1.0, retention * 1.2), "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (mem_id,),
            )

        result = []
        for _, r in top_k:
            tags = self._fetch(
                "SELECT tag FROM memory_tags WHERE memory_id = ?", (r["id"],)
            )
            r["tags"] = [t["tag"] for t in tags]
            result.append(r)
        return result

    # ── 衰减 ──────────────────────────────────────────────

    def decay_memories(self, current_chapter: int):
        LAMBDA = 0.1
        updated = 0
        BATCH_SIZE = 500

        strength_rows = self._fetch(
            "SELECT actor_id, memory_strength FROM character_state "
            "WHERE memory_strength IS NOT NULL"
        )
        strength_map = {r["actor_id"]: r.get("memory_strength", 5) for r in strength_rows}

        offset = 0
        while True:
            rows = self._fetch(
                "SELECT id, actor_id, importance, retrieval_count, "
                "source_chapter, retention FROM character_memories "
                "LIMIT ? OFFSET ?",
                (BATCH_SIZE, offset),
            )
            if not rows:
                break

            for r in rows:
                mem_id = r["id"]
                actor_id = r["actor_id"]
                importance = r["importance"] or 5.0
                retrieval_count = r["retrieval_count"] or 0
                source_chapter = r["source_chapter"] or 0
                memory_strength = strength_map.get(actor_id, 5)

                chapters_passed = max(current_chapter - source_chapter, 0)
                decay_factor = math.exp(
                    -LAMBDA * chapters_passed / max(memory_strength, 1)
                )
                retention = importance * decay_factor

                for _ in range(retrieval_count):
                    retention = min(1.0, retention * 1.2)

                self._execute(
                    "UPDATE character_memories SET retention = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (retention, mem_id),
                )
                updated += 1

            offset += BATCH_SIZE

        forgotten_rows = self._fetch(
            "SELECT COUNT(*) as cnt FROM character_memories WHERE retention < 0.3"
        )
        forgotten = forgotten_rows[0]["cnt"] if forgotten_rows else 0

        return {"updated": updated, "forgotten": forgotten}

    # ── 标签 ──────────────────────────────────────────────

    def get_memory_tags(self, actor_id: str):
        rows = self._fetch(
            "SELECT DISTINCT mt.tag FROM memory_tags mt "
            "JOIN character_memories cm ON cm.id = mt.memory_id "
            "WHERE cm.actor_id = ? "
            "ORDER BY mt.tag",
            (actor_id,),
        )
        return [r["tag"] for r in rows]
