#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记忆子模块单元测试：store, compactor, schema。"""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

import pytest

from data_modules.memory.schema import MemoryItem, ScratchpadData, CATEGORY_TO_BUCKET, memory_item_key
from data_modules.memory.store import ScratchpadManager
from data_modules.memory.compactor import compact_scratchpad
from data_modules.config import DataModulesConfig


# ---------------------------------------------------------------------------
# ScratchpadManager (store.py)
# ---------------------------------------------------------------------------

class TestScratchpadManager:
    def test_init_creates_dirs(self, tmp_path):
        (tmp_path / ".webnovel").mkdir(parents=True)
        cfg = DataModulesConfig(project_root=tmp_path)
        store = ScratchpadManager(cfg)
        assert store.path.parent.exists()

    def test_upsert_item(self, tmp_path):
        (tmp_path / ".webnovel").mkdir(parents=True)
        cfg = DataModulesConfig(project_root=tmp_path)
        store = ScratchpadManager(cfg)
        item = MemoryItem(
            id="test_1", layer="semantic", category="story_fact",
            subject="hero", field="status", value="awakened",
        )
        result = store.upsert_item(item)
        assert result.get("added") == 1

    def test_upsert_duplicate(self, tmp_path):
        (tmp_path / ".webnovel").mkdir(parents=True)
        cfg = DataModulesConfig(project_root=tmp_path)
        store = ScratchpadManager(cfg)
        item = MemoryItem(
            id="test_2", layer="semantic", category="story_fact",
            subject="hero", field="status", value="awakened",
        )
        store.upsert_item(item)
        result = store.upsert_item(item)
        assert result.get("added") == 0

    def test_query_by_status(self, tmp_path):
        (tmp_path / ".webnovel").mkdir(parents=True)
        cfg = DataModulesConfig(project_root=tmp_path)
        store = ScratchpadManager(cfg)
        store.upsert_item(MemoryItem(
            id="q1", layer="semantic", category="story_fact",
            subject="hero", field="status", value="active",
            status="active",
        ))
        store.upsert_item(MemoryItem(
            id="q2", layer="semantic", category="story_fact",
            subject="villain", field="status", value="hidden",
            status="outdated",
        ))
        active = store.query(status="active")
        assert len(active) == 1
        assert active[0].id == "q1"

    def test_load_empty(self, tmp_path):
        (tmp_path / ".webnovel").mkdir(parents=True)
        cfg = DataModulesConfig(project_root=tmp_path)
        store = ScratchpadManager(cfg)
        data = store.load()
        assert isinstance(data, ScratchpadData)


# ---------------------------------------------------------------------------
# compact_scratchpad (compactor.py)
# ---------------------------------------------------------------------------

class TestCompactScratchpad:
    def test_compact_reduces_items(self):
        data = ScratchpadData(
            story_facts=[
                MemoryItem(id=f"i{i}", layer="semantic", category="story_fact",
                           subject="a", field="b", value=str(i),
                           updated_at="2026-01-01T00:00:00")
                for i in range(20)
            ],
        )
        result = compact_scratchpad(data, max_items=10)
        assert result.count_items() <= 10

    def test_compact_preserves_recent(self):
        data = ScratchpadData(
            story_facts=[
                MemoryItem(id=f"i{i}", layer="semantic", category="story_fact",
                           subject="a", field="b", value=str(i),
                           updated_at=f"2026-01-{i+1:02d}T00:00:00")
                for i in range(5)
            ],
        )
        result = compact_scratchpad(data, max_items=3)
        assert result.count_items() == 3


# ---------------------------------------------------------------------------
# MemoryItem + helpers (schema.py)
# ---------------------------------------------------------------------------

class TestMemoryItem:
    def test_normalized_cleans_fields(self):
        item = MemoryItem(
            id="  test  ", layer="invalid", category="unknown",
            subject="  hero  ", field="", value="",
        )
        n = item.normalized()
        assert n.layer == "semantic"
        assert n.category == "story_fact"
        assert n.id == "  test  "

    def test_memory_item_key(self):
        item = MemoryItem(
            id="k1", layer="semantic", category="character_state",
            subject="hero", field="level", value="10",
        )
        key = memory_item_key(item)
        assert "hero" in key
        assert "level" in key

    def test_category_bucket_mapping(self):
        assert "character_state" in CATEGORY_TO_BUCKET
        assert CATEGORY_TO_BUCKET["character_state"] == "character_state"


# ---------------------------------------------------------------------------
# MemoryWriter (writer.py)
# ---------------------------------------------------------------------------

class TestMemoryWriter:
    def test_update_from_chapter_result(self, tmp_path):
        (tmp_path / ".webnovel").mkdir(parents=True)
        cfg = DataModulesConfig(project_root=tmp_path)
        from data_modules.memory.writer import MemoryWriter
        writer = MemoryWriter(cfg)
        chapter_result = {
            "state_changes": [
                {"entity_id": "hero", "field": "realm", "old": "筑基", "new": "金丹"},
            ],
            "entities_new": [],
            "relationships_new": [],
            "chapter_meta": {},
            "memory_facts": {},
        }
        stats = writer.update_from_chapter_result(chapter=1, result=chapter_result)
        assert stats["chapter"] == 1
        assert stats["items_added"] >= 1
        assert stats["items_updated"] == 0

    def test_update_with_empty_result(self, tmp_path):
        (tmp_path / ".webnovel").mkdir(parents=True)
        cfg = DataModulesConfig(project_root=tmp_path)
        from data_modules.memory.writer import MemoryWriter
        writer = MemoryWriter(cfg)
        stats = writer.update_from_chapter_result(chapter=5, result={})
        assert stats["items_added"] == 0
        assert stats["items_updated"] == 0
        assert stats["warnings"] == []


# ---------------------------------------------------------------------------
# MemoryOrchestrator (orchestrator.py)
# ---------------------------------------------------------------------------

class TestMemoryOrchestrator:
    def test_init(self, tmp_path):
        (tmp_path / ".webnovel").mkdir(parents=True)
        cfg = DataModulesConfig(project_root=tmp_path)
        from data_modules.memory.orchestrator import MemoryOrchestrator
        orch = MemoryOrchestrator(cfg)
        assert orch.config is cfg
        assert orch.store is not None
