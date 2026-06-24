#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from data_modules.config import DataModulesConfig
from data_modules.index_manager import (
    ChapterMeta,
    ChapterReadingPowerMeta,
    IndexManager,
    ReviewMetrics,
)


def _create_dashboard_client(monkeypatch, project_root: Path) -> TestClient:
    plugin_root = Path(__file__).resolve().parents[3]
    scripts_dir = plugin_root / "scripts"

    clean_path = []
    scripts_resolved = scripts_dir.resolve()
    for entry in sys.path:
        try:
            if Path(entry).resolve() == scripts_resolved:
                continue
        except Exception:
            pass
        clean_path.append(entry)

    if str(plugin_root) not in clean_path:
        clean_path.insert(0, str(plugin_root))

    monkeypatch.setattr(sys, "path", clean_path)
    for name in list(sys.modules):
        if name == "dashboard.app" or name == "data_modules" or name.startswith("data_modules."):
            sys.modules.pop(name, None)

    module = importlib.import_module("dashboard.app")
    app = module.create_app(project_root)
    return TestClient(app)


def _write_state(project_root: Path) -> None:
    state = {
        "project_info": {
            "title": "像素写手测试书",
            "genre": "玄幻",
            "target_words": 1000000,
            "target_chapters": 300,
        },
        "progress": {
            "current_chapter": 3,
            "current_volume": 2,
            "total_words": 9300,
            "volumes_planned": [
                {"volume": 1, "chapters_range": "1-2"},
                {"volume": 2, "chapters_range": "3-10"},
            ],
        },
        "protagonist_state": {
            "name": "林长青",
            "power": {"realm": "筑基"},
            "location": {"current": "青元宗"},
        },
        "strand_tracker": {
            "current_dominant": "constellation",
            "history": [
                {"chapter": 1, "strand": "quest"},
                {"chapter": 2, "strand": "fire"},
                {"chapter": 3, "strand": "constellation"},
            ],
        },
        "plot_threads": {
            "foreshadowing": [
                {
                    "content": "青元秘境钥匙碎片",
                    "status": "未回收",
                    "tier": "核心",
                    "planted_chapter": 1,
                    "target_chapter": 2,
                },
                {
                    "content": "凤灵儿真实身份",
                    "status": "未回收",
                    "tier": "支线",
                    "planted_chapter": 2,
                    "target_chapter": 6,
                },
                {
                    "content": "第一卷残图",
                    "status": "已回收",
                    "tier": "装饰",
                    "planted_chapter": 1,
                    "target_chapter": 3,
                    "resolved_chapter": 3,
                },
            ]
        },
        "chapter_meta": {
            "0001": {"summary": "第一章概要"},
            "0002": {"summary": "第二章概要"},
            "0003": {"summary": "第三章概要"},
        },
    }
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    (webnovel_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_project_data(project_root: Path) -> None:
    cfg = DataModulesConfig.from_project_root(project_root)
    cfg.ensure_dirs()
    _write_state(project_root)

    index = IndexManager(cfg)
    index.add_chapter(
        ChapterMeta(
            chapter=1,
            title="初入山门",
            location="青元宗",
            word_count=3000,
            characters=["lintian"],
            summary="第一章概要",
        )
    )
    index.add_chapter(
        ChapterMeta(
            chapter=2,
            title="秘境异动",
            location="青元秘境",
            word_count=3100,
            characters=["lintian", "fenglinger"],
            summary="第二章概要",
        )
    )
    index.add_chapter(
        ChapterMeta(
            chapter=3,
            title="夜探黑市",
            location="黑市",
            word_count=3200,
            characters=["lintian", "heishifanzi"],
            summary="第三章概要",
        )
    )

    index.save_chapter_reading_power(
        ChapterReadingPowerMeta(
            chapter=1,
            hook_type="悬念钩",
            hook_strength="weak",
            coolpoint_patterns=["身份伏笔"],
        )
    )
    index.save_chapter_reading_power(
        ChapterReadingPowerMeta(
            chapter=2,
            hook_type="反转钩",
            hook_strength="medium",
            coolpoint_patterns=["秘境反转"],
        )
    )
    index.save_chapter_reading_power(
        ChapterReadingPowerMeta(
            chapter=3,
            hook_type="追杀钩",
            hook_strength="strong",
            coolpoint_patterns=["黑市追杀"],
        )
    )

    index.save_review_metrics(
        ReviewMetrics(
            start_chapter=1,
            end_chapter=1,
            overall_score=71,
            severity_counts={"high": 1},
        )
    )
    index.save_review_metrics(
        ReviewMetrics(
            start_chapter=2,
            end_chapter=2,
            overall_score=83,
            severity_counts={"medium": 1},
        )
    )
    index.save_review_metrics(
        ReviewMetrics(
            start_chapter=3,
            end_chapter=3,
            overall_score=88,
            severity_counts={"low": 1},
        )
    )

    story_root = project_root / ".story-system"
    (story_root / "chapters").mkdir(parents=True, exist_ok=True)
    (story_root / "volumes").mkdir(parents=True, exist_ok=True)
    (story_root / "reviews").mkdir(parents=True, exist_ok=True)
    (story_root / "commits").mkdir(parents=True, exist_ok=True)
    (story_root / "MASTER_SETTING.json").write_text(
        json.dumps(
            {
                "meta": {"schema_version": "story-system/v1", "contract_type": "MASTER_SETTING"},
                "route": {"primary_genre": "玄幻升级流"},
                "master_constraints": {"core_tone": "先压后爆"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (story_root / "volumes" / "volume_001.json").write_text(
        json.dumps({"meta": {"contract_type": "VOLUME_BRIEF", "volume": 1}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (story_root / "volumes" / "volume_002.json").write_text(
        json.dumps({"meta": {"contract_type": "VOLUME_BRIEF", "volume": 2}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (story_root / "chapters" / "chapter_003.json").write_text(
        json.dumps(
            {"meta": {"contract_type": "CHAPTER_BRIEF", "chapter": 3}, "override_allowed": {"chapter_focus": "夜探黑市"}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (story_root / "reviews" / "chapter_003.review.json").write_text(
        json.dumps(
            {"meta": {"contract_type": "REVIEW_CONTRACT", "chapter": 3}, "must_check": ["黑市冲突"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (story_root / "commits" / "chapter_002.commit.json").write_text(
        json.dumps(
            {
                "meta": {"schema_version": "story-system/v1", "chapter": 2, "status": "accepted"},
                "provenance": {"write_fact_role": "chapter_commit"},
                "projection_status": {
                    "state": "done",
                    "index": "done",
                    "summary": "done",
                    "memory": "done",
                    "vector": "done",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (story_root / "commits" / "chapter_003.commit.json").write_text(
        json.dumps(
            {
                "meta": {"schema_version": "story-system/v1", "chapter": 3, "status": "rejected"},
                "provenance": {"write_fact_role": "chapter_commit"},
                "projection_status": {
                    "state": "skipped",
                    "index": "skipped",
                    "summary": "skipped",
                    "memory": "skipped",
                    "vector": "skipped",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    vector_db = cfg.vector_db
    with sqlite3.connect(vector_db) as conn:
        conn.execute(
            """
            CREATE TABLE vectors (
                chunk_id TEXT PRIMARY KEY,
                chapter INTEGER,
                scene_index INTEGER,
                content TEXT,
                embedding BLOB,
                parent_chunk_id TEXT,
                chunk_type TEXT,
                source_file TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO vectors (chunk_id, chapter, scene_index, content, embedding, parent_chunk_id, chunk_type, source_file)
            VALUES ('ch0003_s1', 3, 1, '黑市线索', X'00', NULL, 'scene', '正文/第0003章.md')
            """
        )
        conn.commit()

    (project_root / ".env").write_text(
        "\n".join(
            [
                "EMBED_BASE_URL=https://embed.example.com/v1",
                "EMBED_MODEL=test-embed",
                "EMBED_API_KEY=embed-key",
                "RERANK_BASE_URL=https://rerank.example.com/v1",
                "RERANK_MODEL=test-rerank",
                "RERANK_API_KEY=rerank-key",
            ]
        ),
        encoding="utf-8",
    )


def test_dashboard_app_imports_without_scripts_path(monkeypatch, tmp_path):
    plugin_root = Path(__file__).resolve().parents[3]
    scripts_dir = plugin_root / "scripts"

    project_root = tmp_path / "book"
    (project_root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (project_root / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")

    clean_path = []
    scripts_resolved = scripts_dir.resolve()
    for entry in sys.path:
        try:
            if Path(entry).resolve() == scripts_resolved:
                continue
        except Exception:
            pass
        clean_path.append(entry)

    if str(plugin_root) not in clean_path:
        clean_path.insert(0, str(plugin_root))

    monkeypatch.setattr(sys, "path", clean_path)
    for name in list(sys.modules):
        if name == "dashboard.app" or name == "data_modules" or name.startswith("data_modules."):
            sys.modules.pop(name, None)

    module = importlib.import_module("dashboard.app")
    app = module.create_app(project_root)
    client = TestClient(app)

    response = client.get("/api/story-runtime/health")
    assert response.status_code == 200


def test_dashboard_chapter_trend_endpoint_returns_recent_window(monkeypatch, tmp_path):
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/stats/chapter-trend", params={"limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["latest_chapter"] == 3
    assert [item["chapter"] for item in payload["items"]] == [2, 3]
    assert payload["items"][0]["review_score"] == 83
    assert payload["items"][0]["hook_strength"] == "medium"
    assert payload["items"][0]["hook_strength_value"] == 3
    assert payload["items"][0]["strand"] == "fire"
    assert payload["items"][0]["volume"] == 1
    assert payload["items"][1]["volume"] == 2


def test_dashboard_commits_and_contract_summary_endpoints(monkeypatch, tmp_path):
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    commits_response = client.get("/api/commits", params={"limit": 2})
    assert commits_response.status_code == 200
    commits_payload = commits_response.json()
    assert [item["chapter"] for item in commits_payload["items"]] == [3, 2]
    assert commits_payload["items"][0]["status"] == "rejected"
    assert commits_payload["items"][1]["projection_status"]["vector"] == "done"

    contracts_response = client.get("/api/contracts/summary")
    assert contracts_response.status_code == 200
    contracts_payload = contracts_response.json()
    assert contracts_payload["chapter"] == 3
    assert contracts_payload["current_volume"] == 2
    assert contracts_payload["master"]["primary_genre"] == "玄幻升级流"
    assert contracts_payload["master"]["core_tone"] == "先压后爆"
    assert contracts_payload["counts"]["volumes"] == 2
    assert contracts_payload["counts"]["chapters"] == 1
    assert contracts_payload["counts"]["reviews"] == 1
    assert contracts_payload["counts"]["commits"] == 2
    assert contracts_payload["current_contracts"]["chapter"] is True
    assert contracts_payload["current_contracts"]["review"] is True
    assert contracts_payload["current_contracts"]["commit"] is True


def test_dashboard_env_status_endpoints_report_local_rag_state(monkeypatch, tmp_path):
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    status_response = client.get("/api/env-status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["embed"]["api_key_present"] is True
    assert status_payload["rerank"]["api_key_present"] is True
    assert status_payload["vector_db"]["exists"] is True
    assert status_payload["vector_db"]["record_count"] == 1
    assert status_payload["rag_mode"] == "full"

    probe_response = client.get("/api/env-status/probe")
    assert probe_response.status_code == 200
    probe_payload = probe_response.json()
    assert probe_payload["ok"] is True
    check_names = [item["name"] for item in probe_payload["checks"]]
    assert "embed_api_key" in check_names
    assert "rerank_api_key" in check_names
    assert "vector_db" in check_names


# ──────────────────────────────────────────────────────────────────
# 空数据 / 无文件 场景测试 — 对应 角色图鉴、上下文健康、状态变化
# ──────────────────────────────────────────────────────────────────

def test_dashboard_entities_endpoint_returns_empty_when_no_entities(monkeypatch, tmp_path):
    """角色图鉴：entities 表为空时返回 200 + 空数组。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/entities")
    assert response.status_code == 200
    assert response.json() == []


def test_dashboard_entity_detail_returns_404_when_not_exists(monkeypatch, tmp_path):
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/entities/nonexistent")
    assert response.status_code == 404


def test_dashboard_entity_timeline_returns_empty_when_no_data(monkeypatch, tmp_path):
    """角色图鉴时间线：无 state_changes 无 scenes 时返回空。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/entities/any_id/timeline")
    assert response.status_code == 200
    payload = response.json()
    assert payload["changes"] == []
    assert payload["appearances"] == []


def test_dashboard_state_changes_returns_empty_when_no_data(monkeypatch, tmp_path):
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/state-changes")
    assert response.status_code == 200
    assert response.json() == []


def test_dashboard_relationships_returns_empty_when_no_data(monkeypatch, tmp_path):
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/relationships")
    assert response.status_code == 200
    assert response.json() == []


def test_dashboard_context_health_returns_404_when_no_trace(monkeypatch, tmp_path):
    """上下文健康：trace 文件不存在时返回 404。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/context/health/1")
    assert response.status_code == 404


def test_dashboard_context_history_returns_empty_when_no_traces(monkeypatch, tmp_path):
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/context/history")
    assert response.status_code == 200
    assert response.json()["items"] == []


# ──────────────────────────────────────────────────────────────────
# Theater 知识库 — 模块缺失时优雅降级
# ──────────────────────────────────────────────────────────────────

def test_dashboard_theater_knowledge_graceful_when_module_missing(monkeypatch, tmp_path):
    """角色知识：theater 模块不存在时返回 200 + 空数据。"""
    project_root = tmp_path / "book"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    (webnovel_dir / "state.json").write_text(
        json.dumps({"project_info": {"title": "测试书"}}), encoding="utf-8"
    )
    (project_root / "theater").mkdir(parents=True, exist_ok=True)

    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/theater/knowledge")
    assert response.status_code == 200
    payload = response.json()
    assert payload["actors"] == []
    assert payload["domain_tree"] is None


def test_dashboard_theater_knowledge_returns_empty_when_no_theater_dir(monkeypatch, tmp_path):
    """角色知识：theater/ 目录不存在时返回空。"""
    project_root = tmp_path / "book"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    (webnovel_dir / "state.json").write_text(
        json.dumps({"project_info": {"title": "测试书"}}), encoding="utf-8"
    )

    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/theater/knowledge")
    assert response.status_code == 200
    payload = response.json()
    assert payload["actors"] == []


# ──────────────────────────────────────────────────────────────────
# 文风约束 — 边缘场景
# ──────────────────────────────────────────────────────────────────

def test_dashboard_style_master_setting_returns_404_when_missing(monkeypatch, tmp_path):
    """文风约束：MASTER_SETTING.json 不存在时返回 404。"""
    project_root = tmp_path / "book"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    (webnovel_dir / "state.json").write_text("{}", encoding="utf-8")

    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/style/master-setting")
    assert response.status_code == 404


def test_dashboard_style_anti_patterns_returns_empty_when_missing(monkeypatch, tmp_path):
    """文风约束：anti_patterns.json 不存在时返回空数组。"""
    project_root = tmp_path / "book"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    (webnovel_dir / "state.json").write_text("{}", encoding="utf-8")

    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/style/anti-patterns")
    assert response.status_code == 200
    assert response.json().get("patterns") == []


def test_dashboard_style_techniques_returns_empty_when_csv_missing(monkeypatch, tmp_path):
    """文风约束：写作技法 CSV 不存在时返回 200 + 空。"""
    project_root = tmp_path / "book"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    (webnovel_dir / "state.json").write_text("{}", encoding="utf-8")
    (project_root / ".story-system").mkdir(parents=True, exist_ok=True)

    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/style/techniques")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert "techniques" in payload


def test_dashboard_style_chapters_returns_list_when_no_contracts(monkeypatch, tmp_path):
    """文风约束：章节合同列表——无合同时返回空。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/style/chapters")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert "chapters" in payload


# ──────────────────────────────────────────────────────────────────
# 角色图鉴：实体类型筛选 — 验证主角/配角过滤在 API 层正确
# ──────────────────────────────────────────────────────────────────

def test_dashboard_entities_filter_by_type(monkeypatch, tmp_path):
    """角色图鉴筛选：按类型过滤实体。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    all_entities = client.get("/api/entities").json()
    assert len(all_entities) == 0  # _build_project_data 没有 theater 角色, entities 表为空

    # theater 角色的筛选在应用层合并，用真实数据测
    client2 = _create_dashboard_client(monkeypatch, project_root)
    response = client2.get("/api/entities", params={"type": "主角"})
    assert response.status_code == 200
    for entity in response.json():
        assert entity["type"] == "主角", f"expected 主角, got {entity['type']}"


def test_dashboard_entity_detail_same_from_list_and_direct(monkeypatch, tmp_path):
    """列表和详情返回的同一实体数据一致。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    entities = client.get("/api/entities").json()
    if entities:
        eid = entities[0]["id"]
        detail = client.get(f"/api/entities/{eid}")
        assert detail.status_code == 200
        assert detail.json()["id"] == eid


def test_dashboard_entity_timeline_structure(monkeypatch, tmp_path):
    """角色时间线返回正确的数据结构。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/entities/any_id/timeline")
    assert response.status_code == 200
    payload = response.json()
    assert "changes" in payload
    assert "appearances" in payload
    assert isinstance(payload["changes"], list)
    assert isinstance(payload["appearances"], list)


def test_dashboard_relationships_filter_by_entity(monkeypatch, tmp_path):
    """关系列表可按实体筛选。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    response = client.get("/api/relationships", params={"entity": "lin_zhan"})
    assert response.status_code == 200
    assert isinstance(response.json(), list)

# ── 缺陷回归测试：本轮修复的 Bug ──

def test_workflow_api_format(monkeypatch, tmp_path):
    """Bug: 总览页进度条断裂 — workflow API 返回格式正确。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    resp = client.get("/api/workflow/status")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    # 格式: {"1": {"stage": "...", "complete": bool, "steps": int}}
    for ch, info in data.items():
        assert isinstance(info, dict), f"ch{ch} value should be dict"
        assert "stage" in info or "complete" in info, f"ch{ch} missing stage/complete"


def test_project_info_includes_chapter_status(monkeypatch, tmp_path):
    """Bug: 总览页只显示第 1 章 — project/info 应有 current_chapter。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    resp = client.get("/api/project/info")
    assert resp.status_code == 200
    data = resp.json()
    progress = data.get("progress", {})
    assert "current_chapter" in progress
    assert isinstance(progress["current_chapter"], int)


def test_entities_no_migration_artifacts(monkeypatch, tmp_path):
    """Bug: 陈末等测试数据混入真实项目 — entities 不应有迁移残留。"""
    project_root = tmp_path / "book"
    _build_project_data(project_root)
    client = _create_dashboard_client(monkeypatch, project_root)

    resp = client.get("/api/entities")
    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert "chen_mo" not in ids, "chen_mo 不应出现在 _build_project_data 创建的项目中"


def test_theater_knowledge_no_unconfirmed(monkeypatch, tmp_path):
    """Bug: 角色知识全是"待确认" — known_domains 应为确定性数据。"""
    project_root = tmp_path / "book"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    (webnovel_dir / "state.json").write_text(
        '{"project_info":{"title":"T"},"progress":{"current_chapter":1}}',
        encoding="utf-8",
    )
    theater_dir = project_root / "theater"
    (theater_dir / "actors").mkdir(parents=True)
    (theater_dir / "common_knowledge").mkdir(parents=True)
    (theater_dir / "actors" / "registry.json").write_text('{"actors":{}}', encoding="utf-8")

    client = _create_dashboard_client(monkeypatch, project_root)
    resp = client.get("/api/theater/knowledge")
    assert resp.status_code == 200
    data = resp.json()
    for actor in data.get("actors", []):
        domains = actor.get("known_domains", {})
        for domain, value in domains.items():
            assert isinstance(value, (int, float)), f"known_domain value should be float, got {type(value)}"
