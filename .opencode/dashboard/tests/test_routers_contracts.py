"""Test contracts router — commits, contracts summary, overrides, debts, debt-events."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.core.config import get_db_path, init_project_root

_opencode_dir = Path(__file__).resolve().parents[2]
if str(_opencode_dir) not in sys.path:
    sys.path.insert(0, str(_opencode_dir))


# ── helpers ───────────────────────────────────────────────────


def _create_table_overrides(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS override_contracts (
            id INTEGER PRIMARY KEY,
            chapter INTEGER,
            status TEXT,
            rule TEXT,
            created_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO override_contracts (chapter, status, rule) VALUES (1, 'active', 'test_rule')"
    )
    conn.commit()
    conn.close()


def _create_table_debts(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chase_debt (
            id INTEGER PRIMARY KEY,
            chapter INTEGER,
            status TEXT,
            description TEXT,
            updated_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO chase_debt (chapter, status, description, updated_at) VALUES (1, 'open', 'test debt', '2024-01-01')"
    )
    conn.commit()
    conn.close()


def _create_table_debt_events(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS debt_events (
            id INTEGER PRIMARY KEY,
            debt_id INTEGER,
            chapter INTEGER,
            event_type TEXT,
            description TEXT
        )
    """)
    conn.execute(
        "INSERT INTO debt_events (debt_id, chapter, event_type, description) VALUES (1, 1, 'created', 'test event')"
    )
    conn.commit()
    conn.close()


# ── GET /api/commits ─────────────────────────────────────────


class TestListCommits:
    """GET /api/commits"""

    def test_empty_when_no_commits_dir(self, project_root: Path) -> None:
        """没有 commits 目录时返回空列表。"""
        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/commits")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"items": [], "total": 0, "limit": 20}

    def test_returns_commits(self, project_root: Path) -> None:
        """有 commit 文件时正确解析并返回。"""
        story_system = project_root / ".story-system" / "commits"
        story_system.mkdir(parents=True, exist_ok=True)
        commit = {
            "meta": {"chapter": 3, "status": "committed"},
            "provenance": {"write_fact_role": "main"},
            "projection_status": {"state": "ok"},
            "contract_refs": {"contract": "ref"},
        }
        (story_system / "chapter_003.commit.json").write_text(
            json.dumps(commit, ensure_ascii=False), encoding="utf-8"
        )

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/commits?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["chapter"] == 3
        assert item["status"] == "committed"
        assert item["projection_status"] == {"state": "ok"}
        assert item["write_fact_role"] == "main"
        assert item["contract_refs"] == {"contract": "ref"}
        assert item["path"] == "chapter_003.commit.json"
        assert "updated_at" in item
        assert data["total"] == 1
        assert data["limit"] == 10

    def test_sorts_descending_by_chapter(self, project_root: Path) -> None:
        """commit 按 chapter 降序排列。"""
        story_system = project_root / ".story-system" / "commits"
        story_system.mkdir(parents=True, exist_ok=True)
        for ch in (1, 5, 3):
            payload = {"meta": {"chapter": ch, "status": "ok"}}
            (story_system / f"chapter_{ch:03d}.commit.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/commits?limit=10")
        chapters = [item["chapter"] for item in resp.json()["items"]]
        assert chapters == [5, 3, 1]

    def test_honors_limit(self, project_root: Path) -> None:
        """limit 参数生效。"""
        story_system = project_root / ".story-system" / "commits"
        story_system.mkdir(parents=True, exist_ok=True)
        for ch in range(1, 6):
            payload = {"meta": {"chapter": ch, "status": "ok"}}
            (story_system / f"chapter_{ch:03d}.commit.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/commits?limit=2")
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["limit"] == 2
        assert data["total"] == 5

    def test_skips_corrupted_files(self, project_root: Path) -> None:
        """损坏的 JSON 文件被跳过。"""
        story_system = project_root / ".story-system" / "commits"
        story_system.mkdir(parents=True, exist_ok=True)
        (story_system / "chapter_001.commit.json").write_text("not json", encoding="utf-8")
        payload = {"meta": {"chapter": 2, "status": "ok"}}
        (story_system / "chapter_002.commit.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/commits")
        assert len(resp.json()["items"]) == 1


# ── GET /api/contracts/summary ───────────────────────────────


class TestContractsSummary:
    """GET /api/contracts/summary"""

    def test_returns_defaults_when_no_state(self, project_root: Path) -> None:
        """没有 story-system 时返回默认值。"""
        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/contracts/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "chapter" in data
        assert "current_volume" in data
        assert "master" in data
        assert "counts" in data
        assert "current_contracts" in data
        # 默认值校验
        assert isinstance(data["chapter"], int)
        assert isinstance(data["current_volume"], int)
        assert data["master"]["exists"] is False

    def test_with_story_system_dirs(self, project_root: Path) -> None:
        """.story-system 目录存在时 counts 返回非零值。"""
        for sub in ("volumes", "chapters", "reviews", "commits"):
            (project_root / ".story-system" / sub).mkdir(parents=True, exist_ok=True)

        # 创建两个 volume 文件
        (project_root / ".story-system" / "volumes" / "volume_001.json").write_text(
            "{}", encoding="utf-8"
        )
        (project_root / ".story-system" / "volumes" / "volume_002.json").write_text(
            "{}", encoding="utf-8"
        )
        # 创建当前 volume 的合约文件
        (project_root / ".story-system" / "volumes" / "volume_001.contract.json").write_text(
            "{}", encoding="utf-8"
        )

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/contracts/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["counts"]["volumes"] >= 1

    def test_honors_state_current_chapter(self, project_root: Path) -> None:
        """state.json 中的 current_chapter 影响结果。"""
        webnovel_dir = project_root / ".webnovel"
        webnovel_dir.mkdir(parents=True, exist_ok=True)
        (webnovel_dir / "state.json").write_text(
            json.dumps({"progress": {"current_chapter": 42, "current_volume": 3}},
                       ensure_ascii=False),
            encoding="utf-8",
        )

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/contracts/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chapter"] == 42
        assert data["current_volume"] == 3


# ── GET /api/overrides ───────────────────────────────────────


class TestListOverrides:
    """GET /api/overrides"""

    def test_empty_table(self, project_root: Path) -> None:
        """表不存在时返回空列表。"""
        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/overrides")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_with_data(self, project_root: Path) -> None:
        """有数据时返回正确。"""
        init_project_root(project_root)
        _create_table_overrides(get_db_path())

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/overrides")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["status"] == "active"

    def test_filters_by_status(self, project_root: Path) -> None:
        """status 参数过滤有效。"""
        init_project_root(project_root)
        db_path = get_db_path()
        _create_table_overrides(db_path)

        # 添加另一条不同状态的数据
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO override_contracts (chapter, status, rule) VALUES (2, 'inactive', 'old_rule')"
        )
        conn.commit()
        conn.close()

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/overrides?status=active")
        assert resp.status_code == 200
        data = resp.json()
        assert all(item["status"] == "active" for item in data)

    def test_honors_limit(self, project_root: Path) -> None:
        """limit 参数生效。"""
        init_project_root(project_root)
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS override_contracts (
                id INTEGER PRIMARY KEY, chapter INTEGER, status TEXT
            )
        """)
        for ch in range(1, 6):
            conn.execute(
                "INSERT INTO override_contracts (chapter, status) VALUES (?, 'active')",
                (ch,),
            )
        conn.commit()
        conn.close()

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/overrides?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ── GET /api/debts ───────────────────────────────────────────


class TestListDebts:
    """GET /api/debts"""

    def test_empty_table(self, project_root: Path) -> None:
        """表不存在时返回空列表。"""
        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/debts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_with_data(self, project_root: Path) -> None:
        """有数据时返回正确。"""
        init_project_root(project_root)
        _create_table_debts(get_db_path())

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/debts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["status"] == "open"

    def test_filters_by_status(self, project_root: Path) -> None:
        """status 参数过滤有效。"""
        init_project_root(project_root)
        db_path = get_db_path()
        _create_table_debts(db_path)

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO chase_debt (chapter, status, description, updated_at) VALUES (2, 'closed', 'done', '2024-01-02')"
        )
        conn.commit()
        conn.close()

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/debts?status=open")
        assert resp.status_code == 200
        data = resp.json()
        assert all(item["status"] == "open" for item in data)


# ── GET /api/debt-events ─────────────────────────────────────


class TestListDebtEvents:
    """GET /api/debt-events"""

    def test_empty_table(self, project_root: Path) -> None:
        """表不存在时返回空列表。"""
        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/debt-events")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_with_data(self, project_root: Path) -> None:
        """有数据时返回正确。"""
        init_project_root(project_root)
        _create_table_debt_events(get_db_path())

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/debt-events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_filters_by_debt_id(self, project_root: Path) -> None:
        """debt_id 参数过滤有效。"""
        init_project_root(project_root)
        db_path = get_db_path()
        _create_table_debt_events(db_path)

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO debt_events (debt_id, chapter, event_type, description) VALUES (2, 2, 'resolved', 'done')"
        )
        conn.commit()
        conn.close()

        app = create_app(project_root)
        with TestClient(app) as client:
            resp = client.get("/api/debt-events?debt_id=1")
        assert resp.status_code == 200
        data = resp.json()
        assert all(item["debt_id"] == 1 for item in data)
