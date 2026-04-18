#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 rag_backend.py

验证 RAG 后端抽象、工厂和适配器。
"""

import pytest
import sys
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestBackendSearchResult:
    def test_backend_search_result_dataclass(self):
        from data_modules.rag_backend import BackendSearchResult

        result = BackendSearchResult(
            chunk_id="ch0001",
            chapter=1,
            scene_index=0,
            content="test content",
            score=0.95,
            source="vector",
        )
        assert result.chunk_id == "ch0001"
        assert result.chapter == 1
        assert result.score == 0.95
        assert result.source == "vector"

    def test_backend_search_result_optional_fields(self):
        from data_modules.rag_backend import BackendSearchResult

        result = BackendSearchResult(
            chunk_id="ch0001",
            chapter=1,
            scene_index=0,
            content="test",
            score=0.5,
            source="bm25",
            parent_chunk_id="parent",
            chunk_type="scene",
        )
        assert result.parent_chunk_id == "parent"
        assert result.chunk_type == "scene"


class TestBackendStats:
    def test_backend_stats_defaults(self):
        from data_modules.rag_backend import BackendStats

        stats = BackendStats()
        assert stats.total_chunks == 0
        assert stats.total_entities == 0
        assert stats.total_edges == 0


class TestBackendFactory:
    def test_factory_register_and_list(self):
        from data_modules.rag_backend import BackendFactory, VectorSearchBackend

        original_count = len(BackendFactory.list_backends())
        BackendFactory.register("test_backend", VectorSearchBackend)
        assert "test_backend" in BackendFactory.list_backends()

    def test_factory_create(self):
        from data_modules.rag_backend import BackendFactory, VectorSearchBackend

        backend = BackendFactory.create("vector")
        assert backend is not None
        isinstance(backend, VectorSearchBackend)

    def test_factory_create_unknown_returns_none(self):
        from data_modules.rag_backend import BackendFactory

        backend = BackendFactory.create("nonexistent_backend")
        assert backend is None


class TestVectorSearchBackend:
    @pytest.mark.asyncio
    async def test_vector_backend_with_mock_rag(self):
        from data_modules.rag_backend import VectorSearchBackend, BackendSearchResult

        mock_rag = MagicMock()
        mock_rag.vector_search = AsyncMock(return_value=[])

        backend = VectorSearchBackend(config=None, rag_adapter=mock_rag)
        results = await backend.search("test query", top_k=5)

        assert isinstance(results, list)
        mock_rag.vector_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_backend_without_rag_returns_empty(self):
        from data_modules.rag_backend import VectorSearchBackend

        backend = VectorSearchBackend(config=None, rag_adapter=None)
        results = await backend.search("test", top_k=5)

        assert results == []

    def test_vector_backend_is_available(self):
        from data_modules.rag_backend import VectorSearchBackend

        mock_rag = MagicMock()
        backend = VectorSearchBackend(config=None, rag_adapter=mock_rag)
        assert backend.is_available() is True

        backend_none = VectorSearchBackend(config=None, rag_adapter=None)
        assert backend_none.is_available() is False

    def test_vector_backend_add_chunks_returns_zero(self):
        from data_modules.rag_backend import VectorSearchBackend

        backend = VectorSearchBackend()
        assert backend.add_chunks([{"content": "test"}]) == 0

    def test_vector_backend_get_stats(self):
        from data_modules.rag_backend import VectorSearchBackend, BackendStats

        backend = VectorSearchBackend()
        stats = backend.get_stats()
        assert isinstance(stats, BackendStats)


class TestTemporalGraphBackendAdapter:
    def test_temporal_graph_backend_with_mock(self):
        from data_modules.rag_backend import TemporalGraphBackendAdapter

        mock_graph = MagicMock()
        mock_graph.query_expand = MagicMock(return_value=[])

        backend = TemporalGraphBackendAdapter(config=None, temporal_graph=mock_graph)
        assert backend.is_available() is True

    def test_temporal_graph_backend_without_graph(self):
        from data_modules.rag_backend import TemporalGraphBackendAdapter

        backend = TemporalGraphBackendAdapter(config=None, temporal_graph=None)
        assert backend.is_available() is False

    def test_temporal_graph_add_edge(self):
        from data_modules.rag_backend import TemporalGraphBackendAdapter

        mock_graph = MagicMock()
        backend = TemporalGraphBackendAdapter(config=None, temporal_graph=mock_graph)
        backend.add_edge("A", "friend", "B", chapter=10)

        mock_graph.add_edge.assert_called_once_with("A", "friend", "B", 10, 1.0)

    def test_temporal_graph_query_expand(self):
        from data_modules.rag_backend import TemporalGraphBackendAdapter

        mock_graph = MagicMock()
        mock_result = MagicMock()
        mock_result.entity = "B"
        mock_result.rel = "friend"
        mock_result.score = 0.8
        mock_result.src = "A"
        mock_result.hop = 1
        mock_graph.query_expand = MagicMock(return_value=[mock_result])

        backend = TemporalGraphBackendAdapter(config=None, temporal_graph=mock_graph)
        results = backend.query_expand("A", current_chapter=10)

        assert len(results) == 1
        assert results[0]["entity"] == "B"

    def test_temporal_graph_get_neighbors(self):
        from data_modules.rag_backend import TemporalGraphBackendAdapter

        mock_edge = MagicMock()
        mock_edge.src = "A"
        mock_edge.rel = "friend"
        mock_edge.tgt = "B"
        mock_edge.weight = 1.0
        mock_edge.last_seen_chapter = 5

        mock_graph = MagicMock()
        mock_graph.get_neighbors = MagicMock(return_value=[mock_edge])

        backend = TemporalGraphBackendAdapter(config=None, temporal_graph=mock_graph)
        results = backend.get_neighbors("A")

        assert len(results) == 1
        assert results[0]["tgt"] == "B"

    def test_temporal_graph_save_state(self):
        from data_modules.rag_backend import TemporalGraphBackendAdapter

        mock_graph = MagicMock()
        mock_graph.save_to_db = MagicMock(return_value=10)

        backend = TemporalGraphBackendAdapter(config=None, temporal_graph=mock_graph)
        result = backend.save_state("test.db")

        assert result == 10

    def test_temporal_graph_load_state(self):
        from data_modules.rag_backend import TemporalGraphBackendAdapter

        mock_graph = MagicMock()
        mock_graph.load_from_db = MagicMock(return_value=True)

        backend = TemporalGraphBackendAdapter(config=None, temporal_graph=mock_graph)
        result = backend.load_state("test.db")

        assert result is True


class TestProtocolInterfaces:
    def test_rag_backend_is_protocol(self):
        from data_modules.rag_backend import RAGBackend
        from typing import Protocol

        assert issubclass(RAGBackend, Protocol)

    def test_temporal_graph_backend_is_protocol(self):
        from data_modules.rag_backend import TemporalGraphBackend
        from typing import Protocol

        assert issubclass(TemporalGraphBackend, Protocol)