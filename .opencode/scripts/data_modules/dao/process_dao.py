from .base import BaseDAO


class ProcessDAO(BaseDAO):
    def log_agent_execution(self, data: dict):
        self._execute(
            """INSERT INTO agent_execution_log
               (chapter, agent_name, step, input_summary, output_summary, duration_ms, token_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data['chapter'],
                data['agent_name'],
                data['step'],
                data.get('input_summary', ''),
                data.get('output_summary', ''),
                data.get('duration_ms', 0),
                data.get('token_count', 0),
            ),
        )

    def get_chapter_trace(self, chapter: int) -> list[dict]:
        return self._fetch(
            "SELECT * FROM agent_execution_log WHERE chapter = ? ORDER BY id",
            (chapter,),
        )

    def record_debate(self, data: dict):
        self._execute(
            """INSERT INTO debate_records
               (chapter, actor_id, issue_category, actor_argument, director_ruling, ruling_reason, impact_on_script)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data['chapter'],
                data['actor_id'],
                data['issue_category'],
                data['actor_argument'],
                data['director_ruling'],
                data.get('ruling_reason', ''),
                data.get('impact_on_script', 0),
            ),
        )

    def get_chapter_debates(self, chapter: int) -> list[dict]:
        return self._fetch("SELECT * FROM debate_records WHERE chapter = ?", (chapter,))

    def get_global_stats(self) -> dict:
        """全局过程统计"""
        def safe_count(query, params=()):
            rows = self._fetch(query, params)
            return rows[0]['c'] if rows else 0
        
        total_chapters = safe_count("SELECT COUNT(DISTINCT chapter) as c FROM agent_execution_log")
        total_debates = safe_count("SELECT COUNT(*) as c FROM debate_records")
        avg_iter_rows = self._fetch("SELECT AVG(iteration) as a FROM writing_iterations")
        avg_iterations = avg_iter_rows[0]['a'] if avg_iter_rows and avg_iter_rows[0]['a'] else 0
        top = self._fetch("SELECT actor_id, COUNT(*) as c FROM debate_records GROUP BY actor_id ORDER BY c DESC LIMIT 1")
        
        return {
            'total_chapters_with_logs': total_chapters,
            'total_debates': total_debates,
            'avg_iterations_per_chapter': round(avg_iterations, 1) if avg_iterations else 0,
            'most_active_actor': top[0]['actor_id'] if top else None
        }

    def get_actor_behavior(self, actor_id: str) -> dict:
        debates = self._fetch(
            """SELECT issue_category, COUNT(*) as c,
               SUM(CASE WHEN director_ruling='采纳' THEN 1 ELSE 0 END) as accepted
               FROM debate_records WHERE actor_id = ? GROUP BY issue_category""",
            (actor_id,),
        )
        return {'actor_id': actor_id, 'debate_categories': [dict(r) for r in debates]}
