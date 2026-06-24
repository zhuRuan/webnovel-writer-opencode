from .base import BaseDAO
from datetime import datetime, timedelta
import json
import uuid


class StyleCollectorDAO(BaseDAO):
    # ── Chapters ──
    def insert_chapter(self, data: dict) -> int:
        word_count = len([c for c in data.get('content', '') if '\u4e00' <= c <= '\u9fff'])
        with self._conn() as conn:
            # Per-author cap: keep only newest 199 chapters before inserting new one
            author = data.get('author', '')
            count = conn.execute(
                "SELECT COUNT(*) FROM collected_chapters WHERE author = ?",
                (author,),
            ).fetchone()[0]
            if count >= 200:
                conn.execute(
                    "DELETE FROM collected_chapters WHERE id IN ("
                    "SELECT id FROM collected_chapters WHERE author = ? ORDER BY id ASC LIMIT ?"
                    ")",
                    (author, count - 199),
                )
            cursor = conn.execute(
                """INSERT INTO collected_chapters (author,work_title,chapter_num,chapter_title,content,source_url,word_count)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    data['author'], data['work_title'], data['chapter_num'],
                    data.get('chapter_title', ''), data['content'],
                    data.get('source_url', ''), word_count,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_chapters(self, author: str = None, work_title: str = None,
                     limit: int = 100, offset: int = 0) -> list[dict]:
        q = """SELECT id, author, work_title, chapter_num, chapter_title,
                      source_url, word_count, status, created_at
               FROM collected_chapters WHERE 1=1"""
        params = []
        if author:
            q += " AND author = ?"
            params.append(author)
        if work_title:
            q += " AND work_title = ?"
            params.append(work_title)
        q += " ORDER BY work_title, chapter_num LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return self._fetch(q, tuple(params))

    def get_chapter_content(self, chapter_id: int) -> str:
        rows = self._fetch(
            "SELECT content FROM collected_chapters WHERE id = ?", (chapter_id,)
        )
        return rows[0]["content"] if rows else ""

    def get_authors(self) -> list[str]:
        return [r['author'] for r in self._fetch(
            "SELECT DISTINCT author FROM collected_chapters ORDER BY author"
        )]

    def update_chapter_status(self, chapter_id: int, status: str):
        self._execute(
            "UPDATE collected_chapters SET status=? WHERE id=?",
            (status, chapter_id),
        )

    # ── Summaries ──
    def insert_summary(self, data: dict) -> int:
        return self._execute(
            """INSERT INTO style_summaries (author,work_title,summary_title,category,content,examples,keywords,chapter_range)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                data['author'], data.get('work_title', ''),
                data['summary_title'], data['category'],
                data['content'], json.dumps(data.get('examples', [])),
                json.dumps(data.get('keywords', [])),
                data.get('chapter_range', ''),
            ),
        )

    def get_summaries(self, author: str = None, category: str = None) -> list[dict]:
        q = "SELECT * FROM style_summaries WHERE 1=1"
        params = []
        if author:
            q += " AND author = ?"
            params.append(author)
        if category:
            q += " AND category = ?"
            params.append(category)
        return self._fetch(q + " ORDER BY author, category", tuple(params))

    def get_summary_categories(self) -> list[str]:
        return [r['category'] for r in self._fetch(
            "SELECT DISTINCT category FROM style_summaries"
        )]

    # ── Reports ──
    def create_report(self, author: str) -> str:
        task_id = f"collect-{uuid.uuid4().hex[:8]}"
        self._execute(
            """INSERT INTO collection_reports (author, task_id, status, start_time)
               VALUES (?,?,'searching',CURRENT_TIMESTAMP)""",
            (author, task_id),
        )
        return task_id

    def update_progress(self, task_id: str, status: str, step_msg: str,
                        current: int = 0, total: int = 0):
        self._execute(
            """UPDATE collection_reports SET status=?, progress=?, steps_json=(
               SELECT json_insert(steps_json, '$[#]', json_object('step',?, 'message',?)))
               WHERE task_id=?""",
            (
                status,
                json.dumps({'current': current, 'total': total, 'message': step_msg}),
                status, step_msg, task_id,
            ),
        )

    def complete_report(self, task_id: str, chapters: int, summaries: int):
        self._execute(
            """UPDATE collection_reports SET status='done', end_time=CURRENT_TIMESTAMP,
               chapters_collected=?, summaries_generated=? WHERE task_id=?""",
            (chapters, summaries, task_id),
        )

    def fail_report(self, task_id: str, error: str):
        self._execute(
            """UPDATE collection_reports SET status='failed', end_time=CURRENT_TIMESTAMP,
               error_message=? WHERE task_id=?""",
            (error, task_id),
        )

    def get_reports(self, author: str = None) -> list[dict]:
        q = "SELECT * FROM collection_reports"
        params = []
        if author:
            q += " WHERE author = ?"
            params.append(author)
        return self._fetch(q + " ORDER BY created_at DESC", tuple(params))

    def get_active_tasks(self) -> list[dict]:
        return self._fetch(
            "SELECT * FROM collection_reports WHERE status NOT IN ('done','failed','cancelled','stale')"
        )

    def cleanup_expired_summaries(self, ttl_days: int = 90) -> int:
        """Delete style_summaries rows older than *ttl_days* (default 90 days).
        Does not touch collected_chapters or director_style.
        """
        cutoff = (datetime.utcnow() - timedelta(days=ttl_days)).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM style_summaries WHERE created_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount
