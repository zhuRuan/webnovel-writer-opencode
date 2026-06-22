import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Optional

class BaseDAO:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _fetch(self, query: str, params: tuple = ()) -> list[dict]:
        with self._conn() as conn:
            try:
                rows = conn.execute(query, params).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc).lower():
                    return []
                raise

    def _execute(self, query: str, params: tuple = ()) -> int:
        with self._conn() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.lastrowid

    def _exists(self, table: str, where: str, params: tuple = ()) -> bool:
        with self._conn() as conn:
            row = conn.execute(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", params).fetchone()
            return row is not None
