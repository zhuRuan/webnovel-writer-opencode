"""
测试 entities 路由的 10 个 GET 端点。

覆盖:
  GET /api/entities                  → list_entities
  GET /api/entities/{entity_id}      → get_entity
  GET /api/entities/{entity_id}/timeline → entity_timeline
  GET /api/entities/{entity_id}/knowledge → get_entity_knowledge
  GET /api/factions                  → list_factions
  GET /api/factions/{faction_id}     → get_faction
  GET /api/relationships             → list_relationships
  GET /api/relationship-events       → list_relationship_events
  GET /api/consistency/anomalies     → consistency_anomalies
  GET /api/state-changes             → list_state_changes
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.core.config import init_project_root
from dashboard.routers.entities import router


# ── 辅助 ─────────────────────────────────────────────────────────


def _make_app(project_root: Path) -> FastAPI:
    """用 entities 路由构建独立的 FastAPI 实例。"""
    init_project_root(project_root)
    app = FastAPI(title="test-entities-router")
    app.include_router(router)
    return app


def _create_test_db(project_root: Path) -> sqlite3.Connection:
    """创建带完整表结构的 index.db，返回连接。

    DAO 查询的列名与真实表结构一致（from_entity / to_entity）。
    """
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(webnovel_dir / "index.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=MEMORY")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL DEFAULT 'character',
            canonical_name TEXT,
            tier TEXT,
            desc TEXT,
            current_json TEXT,
            first_appearance INTEGER,
            last_appearance INTEGER,
            is_protagonist INTEGER DEFAULT 0,
            is_archived INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS state_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            field TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            chapter INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_entity TEXT NOT NULL,
            to_entity TEXT NOT NULL,
            type TEXT,
            description TEXT,
            strength REAL DEFAULT 1.0,
            chapter INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS relationship_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_entity TEXT NOT NULL,
            to_entity TEXT NOT NULL,
            event_type TEXT NOT NULL,
            description TEXT,
            chapter INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS appearances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            chapter INTEGER NOT NULL,
            scene TEXT
        );
    """)
    conn.commit()
    return conn


def _seed_entities(conn: sqlite3.Connection) -> None:
    """插入测试实体数据。"""
    conn.executemany(
        "INSERT INTO entities (id, type, canonical_name, tier, is_protagonist, is_archived) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("char_001", "character", "主角", "protagonist", 1, 0),
            ("char_002", "character", "配角", "supporting", 0, 0),
            ("char_003", "character", "已归档", "minor", 0, 1),
            ("faction_001", "势力", "测试宗派", "major", 0, 0),
            ("faction_002", "势力", "敌对势力", "major", 0, 0),
        ],
    )
    conn.commit()


def _seed_state_changes(conn: sqlite3.Connection) -> None:
    """插入状态变更数据（每个 entity_id+field 仅 1 个不同值，无冲突）。"""
    conn.executemany(
        "INSERT INTO state_changes (entity_id, field, old_value, new_value, chapter) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("char_001", "level", "1", "2", 5),
            ("char_001", "health", "100", "80", 5),
            ("char_002", "level", "1", "2", 8),
        ],
    )
    conn.commit()


def _seed_relationships(conn: sqlite3.Connection) -> None:
    """插入关系数据。"""
    conn.executemany(
        "INSERT INTO relationships (from_entity, to_entity, type, chapter) "
        "VALUES (?, ?, ?, ?)",
        [
            ("char_001", "char_002", "朋友", 1),
            ("char_001", "faction_001", "成员", 1),
        ],
    )
    conn.commit()


def _seed_relationship_events(conn: sqlite3.Connection) -> None:
    """插入关系事件数据。"""
    conn.executemany(
        "INSERT INTO relationship_events (from_entity, to_entity, event_type, description, chapter) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("char_001", "char_002", "相遇", "主角与配角相遇", 1),
            ("char_001", "faction_001", "加入", "主角加入宗派", 3),
        ],
    )
    conn.commit()


def _seed_appearances(conn: sqlite3.Connection) -> None:
    """插入出场数据。"""
    conn.executemany(
        "INSERT INTO appearances (entity_id, chapter) VALUES (?, ?)",
        [
            ("char_001", 1),
            ("char_001", 5),
            ("char_001", 10),
            ("char_002", 2),
        ],
    )
    conn.commit()


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def app(project_root) -> FastAPI:
    """返回配置好的 FastAPI 实例。"""
    return _make_app(project_root)


@pytest.fixture
def client(app) -> TestClient:
    """返回 TestClient。"""
    return TestClient(app)


@pytest.fixture
def seeded_db(project_root) -> sqlite3.Connection:
    """创建并填充测试数据库（无一致性冲突），返回连接。"""
    conn = _create_test_db(project_root)
    _seed_entities(conn)
    _seed_state_changes(conn)
    _seed_relationships(conn)
    _seed_relationship_events(conn)
    _seed_appearances(conn)
    return conn


# ── GET /api/entities ────────────────────────────────────────────


class TestListEntities:
    """GET /api/entities"""

    def test_basic(self, client, seeded_db):
        """列出所有实体，包含非归档实体。"""
        resp = client.get("/api/entities")
        assert resp.status_code == 200
        data = resp.json()
        # char_003 是 archived，默认不包括
        ids = {e["id"] for e in data}
        assert "char_001" in ids
        assert "char_002" in ids
        assert "char_003" not in ids

    def test_filter_by_type(self, client, seeded_db):
        """使用 entity_type 参数筛选。"""
        resp = client.get("/api/entities?type=character")
        assert resp.status_code == 200
        data = resp.json()
        assert all(e["type"] == "character" for e in data)
        ids = {e["id"] for e in data}
        assert "faction_001" not in ids

    def test_include_archived(self, client, seeded_db):
        """include_archived=true 返回已归档实体。"""
        resp = client.get("/api/entities?include_archived=true")
        assert resp.status_code == 200
        data = resp.json()
        ids = {e["id"] for e in data}
        assert "char_003" in ids


# ── GET /api/entities/{entity_id} ────────────────────────────────


class TestGetEntity:
    """GET /api/entities/{entity_id}"""

    def test_found(self, client, seeded_db):
        """返回已存在的实体。"""
        resp = client.get("/api/entities/char_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "char_001"
        assert data["canonical_name"] == "主角"
        assert data["is_protagonist"] == 1

    def test_not_found(self, client, seeded_db):
        """不存在的实体返回 404。"""
        resp = client.get("/api/entities/nonexistent")
        assert resp.status_code == 404
        assert "不存在" in resp.text


# ── GET /api/entities/{entity_id}/timeline ───────────────────────


class TestEntityTimeline:
    """GET /api/entities/{entity_id}/timeline"""

    def test_with_changes(self, client, seeded_db):
        """返回状态变更和出场时间线。"""
        resp = client.get("/api/entities/char_001/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert "changes" in data
        assert "appearances" in data
        assert len(data["changes"]) == 2  # char_001 有 2 条 state_changes
        assert len(data["appearances"]) == 3  # char_001 出场 3 次

    def test_no_data(self, client, seeded_db):
        """没有数据的实体返回空列表。"""
        resp = client.get("/api/entities/faction_001/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["changes"] == []
        assert data["appearances"] == []


# ── GET /api/entities/{entity_id}/knowledge ──────────────────────


class TestEntityKnowledge:
    """GET /api/entities/{entity_id}/knowledge"""

    def test_found(self, client, seeded_db):
        """返回实体知识数据。"""
        resp = client.get("/api/entities/char_001/knowledge")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "char_001"
        assert data["name"] == "主角"
        assert data["source"] == "entity_only"

    def test_not_found(self, client, seeded_db):
        """不存在的实体返回 404。"""
        resp = client.get("/api/entities/nonexistent/knowledge")
        assert resp.status_code == 404
        assert "不存在" in resp.text


# ── GET /api/factions ────────────────────────────────────────────


class TestListFactions:
    """GET /api/factions"""

    def test_basic(self, client, seeded_db):
        """列出所有势力。"""
        resp = client.get("/api/factions")
        assert resp.status_code == 200
        data = resp.json()
        assert "factions" in data
        names = {f["name"] for f in data["factions"]}
        assert "测试宗派" in names
        assert "敌对势力" in names

    def test_excludes_non_factions(self, client, seeded_db):
        """非势力实体不会出现在结果中。"""
        resp = client.get("/api/factions")
        data = resp.json()
        for f in data["factions"]:
            assert f["type"] == "势力"


# ── GET /api/factions/{faction_id} ───────────────────────────────


class TestGetFaction:
    """GET /api/factions/{faction_id}"""

    def test_found(self, client, seeded_db):
        """返回已存在的势力。"""
        resp = client.get("/api/factions/faction_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "faction_001"
        assert data["type"] == "势力"

    def test_not_found(self, client, seeded_db):
        """不存在的势力返回 404。"""
        resp = client.get("/api/factions/nonexistent")
        assert resp.status_code == 404
        assert "不存在" in resp.text

    def test_character_not_faction(self, client, seeded_db):
        """角色实体不是势力，返回 404。"""
        resp = client.get("/api/factions/char_001")
        assert resp.status_code == 404


# ── GET /api/relationships ───────────────────────────────────────


class TestListRelationships:
    """GET /api/relationships"""

    def test_basic(self, client, seeded_db):
        """列出所有关系。"""
        resp = client.get("/api/relationships")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    def test_filter_by_entity(self, client, seeded_db):
        """使用 entity 参数筛选关系。"""
        resp = client.get("/api/relationships?entity=char_001")
        assert resp.status_code == 200
        data = resp.json()
        for r in data:
            assert r["from_entity"] == "char_001" or r["to_entity"] == "char_001"


# ── GET /api/relationship-events ─────────────────────────────────


class TestListRelationshipEvents:
    """GET /api/relationship-events"""

    def test_basic(self, client, seeded_db):
        """列出所有关系事件。"""
        resp = client.get("/api/relationship-events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    def test_filter_by_entity(self, client, seeded_db):
        """使用 entity 参数筛选关系事件。"""
        resp = client.get("/api/relationship-events?entity=char_001")
        assert resp.status_code == 200
        data = resp.json()
        for e in data:
            assert e["from_entity"] == "char_001" or e["to_entity"] == "char_001"

    def test_filter_by_chapter_range(self, client, seeded_db):
        """使用 from_chapter/to_chapter 参数筛选。"""
        resp = client.get("/api/relationship-events?from_chapter=2&to_chapter=5")
        assert resp.status_code == 200
        data = resp.json()
        for e in data:
            assert int(e["chapter"]) >= 2
            assert int(e["chapter"]) <= 5

    def test_empty_with_no_match(self, client, seeded_db):
        """没有匹配的事件返回空列表。"""
        resp = client.get("/api/relationship-events?from_chapter=100")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []


# ── GET /api/consistency/anomalies ───────────────────────────────


class TestConsistencyAnomalies:
    """GET /api/consistency/anomalies"""

    def test_no_anomalies(self, client, seeded_db):
        """每个 entity+field 只有 1 个不同值时无异常。"""
        resp = client.get("/api/consistency/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert "anomalies" in data
        assert data["total"] == 0

    def test_detect_value_conflict(self, client, project_root, app):
        """state_changes 中有多值冲突时检测到 value_conflict。"""
        conn = _create_test_db(project_root)
        # char_001 的 level 字段存在多个不同值
        conn.execute(
            "INSERT INTO state_changes (entity_id, field, old_value, new_value, chapter) "
            "VALUES (?, ?, ?, ?, ?)",
            ("char_001", "level", "1", "X", 5),
        )
        conn.execute(
            "INSERT INTO state_changes (entity_id, field, old_value, new_value, chapter) "
            "VALUES (?, ?, ?, ?, ?)",
            ("char_001", "level", "X", "Y", 10),
        )
        conn.commit()
        conn.close()

        with TestClient(app) as client:
            resp = client.get("/api/consistency/anomalies")
        data = resp.json()
        assert data["total"] > 0
        anomaly_types = {a["type"] for a in data["anomalies"]}
        assert "value_conflict" in anomaly_types

    def test_chapter_filter_detects_no_change(self, client, project_root, app):
        """用 chapter 参数筛选时检测到 no_change。"""
        conn = _create_test_db(project_root)
        # 需要至少 2 行同一 entity+field，且 new_val == prev
        conn.execute(
            "INSERT INTO state_changes (entity_id, field, old_value, new_value, chapter) "
            "VALUES (?, ?, ?, ?, ?)",
            ("char_001", "level", "1", "X", 2),
        )
        conn.execute(
            "INSERT INTO state_changes (entity_id, field, old_value, new_value, chapter) "
            "VALUES (?, ?, ?, ?, ?)",
            ("char_001", "level", "X", "X", 4),  # no_change: X == X
        )
        conn.commit()
        conn.close()

        with TestClient(app) as client:
            resp = client.get("/api/consistency/anomalies?chapter=4")
        data = resp.json()
        assert data["total"] == 1  # no_change detected within chapter <= 4
        assert data["anomalies"][0]["type"] == "no_change"


# ── GET /api/state-changes ───────────────────────────────────────


class TestListStateChanges:
    """GET /api/state-changes"""

    def test_basic(self, client, seeded_db):
        """列出所有状态变更。"""
        resp = client.get("/api/state-changes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3

    def test_filter_by_entity(self, client, seeded_db):
        """使用 entity 参数筛选状态变更。"""
        resp = client.get("/api/state-changes?entity=char_001")
        assert resp.status_code == 200
        data = resp.json()
        for row in data:
            assert row["entity_id"] == "char_001"

    def test_respects_limit(self, client, seeded_db):
        """limit 参数生效。"""
        resp = client.get("/api/state-changes?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= 2


# ── 404 路由 ─────────────────────────────────────────────────────


class TestRouteNotFound:
    """不存在的路由。"""

    def test_unknown_entity_route(self, client, seeded_db):
        resp = client.get("/api/entities/char_001/unknown")
        assert resp.status_code == 404
