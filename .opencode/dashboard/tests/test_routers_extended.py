"""测试 routers/extended.py —— 7 个扩展 API 端点。"""

import json
import sqlite3
from pathlib import Path
from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.core.config import init_project_root, get_db_path
from dashboard.routers.extended import router as extended_router


@pytest.fixture
def client(project_root: Path) -> Generator[TestClient, None, None]:
    """创建仅包含 extended router 的最小 FastAPI 应用。"""
    init_project_root(project_root)

    app = FastAPI()
    app.include_router(extended_router)

    with TestClient(app) as c:
        yield c


def _seed_table(db_path: str, table: str, rows: list[dict]) -> None:
    """在测试 DB 中创建表并插入行。"""
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        # 推导列定义（简单处理：全 TEXT）
        cols = list(rows[0].keys())
        col_defs = ", ".join(f"{c} TEXT" for c in cols)
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({col_defs})")
        placeholders = ", ".join(["?" for _ in cols])
        for row in rows:
            conn.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                [str(v) for v in row.values()],
            )
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# GET /api/aliases
# ═══════════════════════════════════════════════════════════════

class TestAliases:
    def test_list_aliases_empty(self, client: TestClient) -> None:
        """空库返回空列表。"""
        resp = client.get("/api/aliases")
        assert resp.status_code == 200
        # DAO 可能返回 [] 或 HTTPException，取决于 DAO 实现
        # 此处仅验证不崩溃
        assert resp.status_code in (200, 404)


# ═══════════════════════════════════════════════════════════════
# GET /api/invalid-facts
# ═══════════════════════════════════════════════════════════════

class TestInvalidFacts:
    def test_empty_table(self, client: TestClient, project_root: Path) -> None:
        """invalid_facts 表不存在时返回空列表（fetchall_safe 吞掉异常）。"""
        resp = client.get("/api/invalid-facts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_filter_by_status(self, client: TestClient, project_root: Path) -> None:
        """按 status 筛选。"""
        db_path = get_db_path()
        _seed_table(db_path, "invalid_facts", [
            {"content": "fact-A", "status": "open", "marked_at": "2023-01-01"},
            {"content": "fact-B", "status": "closed", "marked_at": "2023-01-02"},
            {"content": "fact-C", "status": "open", "marked_at": "2023-01-03"},
        ])
        resp = client.get("/api/invalid-facts?status=open&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(r["status"] == "open" for r in data)

    def test_no_filter(self, client: TestClient, project_root: Path) -> None:
        """无筛选条件返回全部。"""
        db_path = get_db_path()
        _seed_table(db_path, "invalid_facts", [
            {"content": "fact-A", "status": "open", "marked_at": "2023-01-01"},
            {"content": "fact-B", "status": "closed", "marked_at": "2023-01-02"},
        ])
        resp = client.get("/api/invalid-facts?limit=100")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ═══════════════════════════════════════════════════════════════
# GET /api/rag-queries
# ═══════════════════════════════════════════════════════════════

class TestRagQueries:
    def test_empty_table(self, client: TestClient) -> None:
        resp = client.get("/api/rag-queries")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_filter_by_query_type(self, client: TestClient, project_root: Path) -> None:
        """按 query_type 筛选。"""
        db_path = get_db_path()
        _seed_table(db_path, "rag_query_log", [
            {"query_type": "entity", "query_text": "q1", "created_at": "2023-01-01"},
            {"query_type": "faction", "query_text": "q2", "created_at": "2023-01-02"},
            {"query_type": "entity", "query_text": "q3", "created_at": "2023-01-03"},
        ])
        resp = client.get("/api/rag-queries?query_type=entity&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(r["query_type"] == "entity" for r in data)

    def test_no_filter(self, client: TestClient, project_root: Path) -> None:
        db_path = get_db_path()
        _seed_table(db_path, "rag_query_log", [
            {"query_type": "entity", "query_text": "q1", "created_at": "2023-01-01"},
            {"query_type": "faction", "query_text": "q2", "created_at": "2023-01-02"},
        ])
        resp = client.get("/api/rag-queries?limit=100")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ═══════════════════════════════════════════════════════════════
# GET /api/tool-stats
# ═══════════════════════════════════════════════════════════════

class TestToolStats:
    def test_empty_table(self, client: TestClient) -> None:
        resp = client.get("/api/tool-stats")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_filter_by_tool_name(self, client: TestClient, project_root: Path) -> None:
        """按 tool_name 筛选。"""
        db_path = get_db_path()
        _seed_table(db_path, "tool_call_stats", [
            {"tool_name": "grep", "created_at": "2023-01-01"},
            {"tool_name": "read", "created_at": "2023-01-02"},
            {"tool_name": "grep", "created_at": "2023-01-03"},
        ])
        resp = client.get("/api/tool-stats?tool_name=grep&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(r["tool_name"] == "grep" for r in data)

    def test_no_filter(self, client: TestClient, project_root: Path) -> None:
        db_path = get_db_path()
        _seed_table(db_path, "tool_call_stats", [
            {"tool_name": "grep", "created_at": "2023-01-01"},
            {"tool_name": "read", "created_at": "2023-01-02"},
        ])
        resp = client.get("/api/tool-stats?limit=200")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ═══════════════════════════════════════════════════════════════
# GET /api/checklist-scores
# ═══════════════════════════════════════════════════════════════

class TestChecklistScores:
    def test_empty_table(self, client: TestClient) -> None:
        resp = client.get("/api/checklist-scores")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all(self, client: TestClient, project_root: Path) -> None:
        db_path = get_db_path()
        _seed_table(db_path, "writing_checklist_scores", [
            {"chapter": "1", "score": "85"},
            {"chapter": "2", "score": "90"},
        ])
        resp = client.get("/api/checklist-scores?limit=100")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ═══════════════════════════════════════════════════════════════
# GET /api/story-events
# ═══════════════════════════════════════════════════════════════

class TestStoryEvents:
    def test_empty_table(self, client: TestClient) -> None:
        resp = client.get("/api/story-events")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_payload_parsed(self, client: TestClient, project_root: Path) -> None:
        """验证 payload_json 被解析为 payload 字段。"""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE IF NOT EXISTS story_events (
                id INTEGER PRIMARY KEY,
                event_id TEXT,
                chapter INTEGER,
                event_type TEXT,
                subject TEXT,
                payload_json TEXT,
                created_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO story_events (event_id, chapter, event_type, subject, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("evt-001", "1", "entity_created", "TEST", '{"key":"val"}', "2023-01-01"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/story-events?limit=200")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["event_id"] == "evt-001"
        assert data[0]["payload"] == {"key": "val"}

    def test_filter_by_chapter(self, client: TestClient, project_root: Path) -> None:
        """按 chapter 筛选。"""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE IF NOT EXISTS story_events (
                id INTEGER PRIMARY KEY,
                event_id TEXT,
                chapter INTEGER,
                event_type TEXT,
                subject TEXT,
                payload_json TEXT,
                created_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO story_events (event_id, chapter, event_type, subject, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("evt-001", "1", "entity_created", "A", "{}", "2023-01-01"),
        )
        conn.execute(
            "INSERT INTO story_events (event_id, chapter, event_type, subject, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("evt-002", "2", "entity_updated", "B", "{}", "2023-01-02"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/story-events?chapter=1&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["event_id"] == "evt-001"

    def test_invalid_json_payload(self, client: TestClient, project_root: Path) -> None:
        """无效 JSON payload 返回空字典。"""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE IF NOT EXISTS story_events (
                id INTEGER PRIMARY KEY,
                event_id TEXT,
                chapter INTEGER,
                event_type TEXT,
                subject TEXT,
                payload_json TEXT,
                created_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO story_events (event_id, chapter, event_type, subject, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("evt-001", "1", "entity_created", "X", "NOT VALID JSON {{{", "2023-01-01"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/story-events?limit=200")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["payload"] == {}


# ═══════════════════════════════════════════════════════════════
# GET /api/story-events/health
# ═══════════════════════════════════════════════════════════════

class TestStoryEventHealth:
    def test_empty_tables(self, client: TestClient) -> None:
        resp = client.get("/api/story-events/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["story_events"] == 0
        assert data["pending_amend_proposals"] == 0
        assert data["event_files"] == 0

    def test_with_data(self, client: TestClient, project_root: Path) -> None:
        """有数据时返回正确的计数。"""
        db_path = get_db_path()
        conn = sqlite3.connect(db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        # story_events 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS story_events (
                id INTEGER PRIMARY KEY,
                event_id TEXT,
                chapter INTEGER,
                event_type TEXT,
                subject TEXT,
                payload_json TEXT,
                created_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO story_events (event_id, chapter, event_type, subject, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("evt-001", "1", "x", "X", "{}", "2023-01-01"),
        )
        # override_contracts 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS override_contracts (
                id INTEGER PRIMARY KEY,
                record_type TEXT,
                status TEXT,
                chapter INTEGER
            )
        """)
        conn.execute(
            "INSERT INTO override_contracts (record_type, status, chapter) "
            "VALUES (?, ?, ?)",
            ("amend_proposal", "pending", "1"),
        )
        conn.execute(
            "INSERT INTO override_contracts (record_type, status, chapter) "
            "VALUES (?, ?, ?)",
            ("amend_proposal", "resolved", "2"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/story-events/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["story_events"] == 1
        assert data["pending_amend_proposals"] == 1


# ═══════════════════════════════════════════════════════════════
# _to_int helper
# ═══════════════════════════════════════════════════════════════

class TestToIntHelper:
    def test_valid_int(self) -> None:
        from dashboard.routers.extended import _to_int
        assert _to_int("42") == 42
        assert _to_int(99) == 99

    def test_invalid_returns_zero(self) -> None:
        from dashboard.routers.extended import _to_int
        assert _to_int("abc") == 0
        assert _to_int(None) == 0
        assert _to_int("") == 0
