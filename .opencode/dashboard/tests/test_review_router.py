"""测试 routers/review.py —— 4 个迁移端点。"""

import json
import sqlite3
from pathlib import Path

import pytest

from dashboard.core.config import get_db_path, init_project_root


# ── helpers ───────────────────────────────────────────────────


def _ensure_review_metrics_table(project_root: Path) -> None:
    """创建 review_metrics 表并插入测试数据。"""
    db_path = project_root / ".webnovel" / "index.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS review_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            end_chapter INTEGER NOT NULL,
            overall_score REAL,
            dimension_scores TEXT,
            severity_counts TEXT,
            critical_issues TEXT
        )
    """)
    # 清空旧数据
    conn.execute("DELETE FROM review_metrics")
    conn.execute(
        "INSERT INTO review_metrics (end_chapter, overall_score, dimension_scores, severity_counts, critical_issues) VALUES (?, ?, ?, ?, ?)",
        (
            1,
            8.5,
            json.dumps({"pacing": 8, "character": 9, "dialogue": 7}),
            json.dumps({"critical": 1, "warning": 2}),
            json.dumps(["issue 1", "issue 2"]),
        ),
    )
    conn.execute(
        "INSERT INTO review_metrics (end_chapter, overall_score, dimension_scores, severity_counts, critical_issues) VALUES (?, ?, ?, ?, ?)",
        (
            2,
            9.0,
            json.dumps({"pacing": 9, "character": 8, "dialogue": 9}),
            json.dumps({"warning": 1}),
            json.dumps(["issue 3"]),
        ),
    )
    conn.commit()
    conn.close()


def _ensure_chapters_table(project_root: Path) -> None:
    """创建 chapters、chapter_reading_power 表并插入测试数据。"""
    db_path = project_root / ".webnovel" / "index.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chapters (
            chapter INTEGER PRIMARY KEY,
            title TEXT,
            location TEXT,
            word_count INTEGER,
            characters TEXT,
            summary TEXT
        );
        CREATE TABLE IF NOT EXISTS chapter_reading_power (
            chapter INTEGER PRIMARY KEY,
            hook_type TEXT,
            hook_strength TEXT,
            is_transition INTEGER DEFAULT 0,
            override_count INTEGER DEFAULT 0,
            debt_balance REAL DEFAULT 0.0
        );
    """)
    conn.execute("DELETE FROM chapters")
    conn.execute("DELETE FROM chapter_reading_power")
    conn.execute(
        "INSERT INTO chapters (chapter, title, location, word_count, characters, summary) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "测试章节1", "城市街道", 3000, json.dumps(["角色A", "角色B"]), "测试摘要1"),
    )
    conn.execute(
        "INSERT INTO chapters (chapter, title, location, word_count, characters, summary) VALUES (?, ?, ?, ?, ?, ?)",
        (2, "测试章节2", "学校", 2500, json.dumps(["角色A"]), "测试摘要2"),
    )
    conn.execute(
        "INSERT INTO chapter_reading_power (chapter, hook_type, hook_strength, is_transition, override_count, debt_balance) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "悬念", "strong", 0, 2, 1.5),
    )
    conn.execute(
        "INSERT INTO chapter_reading_power (chapter, hook_type, hook_strength, is_transition, override_count, debt_balance) VALUES (?, ?, ?, ?, ?, ?)",
        (2, "反转", "medium", 1, 0, 0.0),
    )
    conn.commit()
    conn.close()


def _ensure_state_with_strands(project_root: Path) -> None:
    """写入包含 strand_tracker 和 volumes_planned 的 state.json。"""
    state_path = project_root / ".webnovel" / "state.json"
    state_data = {
        "project_info": {"title": "test"},
        "strand_tracker": {
            "history": [
                {"chapter": 1, "strand": "主线"},
                {"chapter": 2, "strand": "支线A"},
            ]
        },
        "progress": {
            "volumes_planned": [
                {"volume": 1, "chapters_range": "1-50"},
                {"volume": 2, "chapters_range": "51-100"},
            ]
        },
    }
    state_path.write_text(json.dumps(state_data, ensure_ascii=False), encoding="utf-8")


# ── tests ─────────────────────────────────────────────────────


class TestReviewAnalytics:
    """GET /api/review/analytics 端点测试。"""

    def test_empty_returns_empty_structure(self, test_app) -> None:
        """无数据时应返回空 items 和空 summary。"""
        resp = test_app.get("/api/review/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["summary"] == {}

    def test_returns_analytics_with_data(self, test_app, project_root: Path) -> None:
        """有审查数据时应返回维度趋势、严重度统计等。"""
        _ensure_review_metrics_table(project_root)
        init_project_root(project_root)

        resp = test_app.get("/api/review/analytics")
        assert resp.status_code == 200
        data = resp.json()

        assert "dimension_trends" in data
        assert "dimension_averages" in data
        assert "weakest_dimensions" in data
        assert "severity_totals" in data
        assert "critical_issues" in data
        assert data["total_reviews"] == 2

        # 验证维度趋势
        pacing_trend = data["dimension_trends"].get("pacing", [])
        assert len(pacing_trend) == 2

        # 验证严重度总计
        assert data["severity_totals"].get("critical") == 1
        assert data["severity_totals"].get("warning") == 3

        # 验证弱点维度
        assert len(data["weakest_dimensions"]) <= 3
        assert len(data["critical_issues"]) <= 20


class TestReviewReports:
    """GET /api/review-reports 端点测试。"""

    def test_no_reports_dir_returns_empty(self, test_app) -> None:
        """审查报告目录不存在时应返回空列表。"""
        resp = test_app.get("/api/review-reports")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reports"] == []

    def test_lists_existing_reports(self, test_app, project_root: Path) -> None:
        """有审查报告文件时应列出所有报告。"""
        reports_dir = project_root / "审查报告"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "第0001章审查报告.md").write_text("# 报告1", encoding="utf-8")
        (reports_dir / "第0002章审查报告.md").write_text("# 报告2", encoding="utf-8")
        # 创建一个非审查报告的文件，确认不会被收录
        (reports_dir / "other.md").write_text("other", encoding="utf-8")

        resp = test_app.get("/api/review-reports")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["reports"]) == 2

        chapters = {r["chapter"] for r in data["reports"]}
        assert chapters == {1, 2}

        for r in data["reports"]:
            assert "name" in r
            assert "path" in r
            assert r["name"].startswith("第")
            assert r["name"].endswith("审查报告.md")


class TestReviewReport:
    """GET /api/review-report 端点测试。"""

    def test_missing_report_returns_404(self, test_app) -> None:
        """不存在的审查报告应返回 404。"""
        resp = test_app.get("/api/review-report?chapter=999")
        assert resp.status_code == 404

    def test_returns_report_content(self, test_app, project_root: Path) -> None:
        """存在的审查报告应返回 Markdown 内容。"""
        reports_dir = project_root / "审查报告"
        reports_dir.mkdir(parents=True, exist_ok=True)
        content = "# 第一章审查\n\n质量良好。"
        (reports_dir / "第0001章审查报告.md").write_text(content, encoding="utf-8")

        resp = test_app.get("/api/review-report?chapter=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chapter"] == 1
        assert data["content"] == content

    def test_variable_width_chapter_match(self, test_app, project_root: Path) -> None:
        """可变宽度的章节号文件也应被匹配（如 "第1章审查报告.md"）。"""
        reports_dir = project_root / "审查报告"
        reports_dir.mkdir(parents=True, exist_ok=True)
        content = "# 可变宽度测试"
        (reports_dir / "第5章审查报告.md").write_text(content, encoding="utf-8")

        resp = test_app.get("/api/review-report?chapter=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chapter"] == 5
        assert data["content"] == content


class TestChapterTrend:
    """GET /api/stats/chapter-trend 端点测试。"""

    def test_empty_returns_empty_items(self, test_app) -> None:
        """无章节数据时应返回空 items 和 0 统计。"""
        resp = test_app.get("/api/stats/chapter-trend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["latest_chapter"] == 0

    def test_returns_trend_with_data(self, test_app, project_root: Path) -> None:
        """有章节数据时应返回趋势列表，含 hook_strength、review_score 等。"""
        _ensure_chapters_table(project_root)
        _ensure_review_metrics_table(project_root)
        _ensure_state_with_strands(project_root)
        init_project_root(project_root)

        resp = test_app.get("/api/stats/chapter-trend")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 2
        assert data["latest_chapter"] == 2
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert len(data["items"]) == 2

        # 验证第一章
        ch1 = data["items"][0]
        assert ch1["chapter"] == 1
        assert ch1["title"] == "测试章节1"
        assert ch1["word_count"] == 3000
        assert isinstance(ch1["characters"], list)
        assert ch1["hook_type"] == "悬念"
        assert ch1["hook_strength"] == "strong"
        assert ch1["hook_strength_value"] == 5
        assert ch1["is_transition"] is False
        assert ch1["override_count"] == 2
        assert ch1["debt_balance"] == 1.5
        assert ch1["strand"] == "主线"
        assert ch1["volume"] == 1

        # 验证第二章
        ch2 = data["items"][1]
        assert ch2["chapter"] == 2
        assert ch2["hook_strength"] == "medium"
        assert ch2["hook_strength_value"] == 3
        assert ch2["is_transition"] is True
        assert ch2["strand"] == "支线a"  # _build_strand_map 会 lower()

    def test_respects_limit_and_offset(self, test_app, project_root: Path) -> None:
        """limit 和 offset 参数应正确生效。"""
        _ensure_chapters_table(project_root)
        _ensure_review_metrics_table(project_root)
        init_project_root(project_root)

        resp = test_app.get("/api/stats/chapter-trend?limit=1&offset=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        # chapters ORDER BY chapter DESC: [2, 1]; OFFSET 1 skips ch2, LIMIT 1 returns ch1
        assert len(data["items"]) == 1
        assert data["items"][0]["chapter"] == 1
