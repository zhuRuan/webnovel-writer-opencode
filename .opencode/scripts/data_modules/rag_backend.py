#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG Backend 接口抽象

渐进式重构：
- Phase 1: 抽象后端接口 (Protocol)
- Phase 2: 适配器包装现有实现
- Phase 3: RAGAdapter 改为委托模式
"""

import asyncio
import math
from typing import Protocol, runtime_checkable
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class BackendSearchResult:
    """后端搜索结果"""
    chunk_id: str
    chapter: int
    scene_index: int
    content: str
    score: float
    source: str  # "vector" | "bm25" | "graph" | "hybrid"
    parent_chunk_id: Optional[str] = None
    chunk_type: Optional[str] = None
    source_file: Optional[str] = None


@dataclass
class BackendStats:
    """后端统计信息"""
    total_chunks: int = 0
    total_entities: int = 0
    total_edges: int = 0
    last_updated: str = ""


@runtime_checkable
class RAGBackend(Protocol):
    """RAG 后端协议"""

    backend_name: str

    async def search(
        self,
        query: str,
        top_k: int = 5,
        chunk_type: Optional[str] = None,
        chapter: Optional[int] = None,
    ) -> List[BackendSearchResult]:
        """搜索接口"""
        ...

    def add_chunks(self, chunks: List[Dict]) -> int:
        """添加上下文块"""
        ...

    def get_stats(self) -> BackendStats:
        """获取统计信息"""
        ...

    def is_available(self) -> bool:
        """检查后端是否可用"""
        ...


@runtime_checkable
class TemporalGraphBackend(Protocol):
    """时序图后端协议"""

    backend_name: str

    def add_edge(
        self,
        src: str,
        rel: str,
        tgt: str,
        chapter: int,
        weight: float = 1.0,
    ) -> None:
        """添加边"""
        ...

    def query_expand(
        self,
        entity: str,
        current_chapter: int,
        max_hops: int = 2,
        max_entities: int = 10,
    ) -> List[Dict]:
        """时序衰减查询扩展"""
        ...

    def get_neighbors(
        self,
        entity: str,
        rel_type: Optional[str] = None,
    ) -> List[Dict]:
        """获取邻居边"""
        ...

    def save_state(self, db_path: str) -> int:
        """保存到数据库"""
        ...

    def load_state(self, db_path: str) -> bool:
        """从数据库加载"""
        ...


class BackendFactory:
    """后端工厂"""

    _backends: Dict[str, type] = {}

    @classmethod
    def register(cls, backend_type: str, backend_class: type) -> None:
        """注册后端"""
        cls._backends[backend_type] = backend_class

    @classmethod
    def create(cls, backend_type: str, config=None) -> Optional[RAGBackend]:
        """创建后端实例"""
        backend_class = cls._backends.get(backend_type)
        if backend_class:
            return backend_class(config)
        return None

    @classmethod
    def list_backends(cls) -> List[str]:
        """列出已注册的后端"""
        return list(cls._backends.keys())


class VectorSearchBackend:
    """向量检索后端适配器（包装现有 RAGAdapter 实现）"""

    backend_name: str = "vector"

    def __init__(self, config=None, rag_adapter=None):
        self.config = config
        self._rag = rag_adapter

    async def search(
        self,
        query: str,
        top_k: int = 5,
        chunk_type: Optional[str] = None,
        chapter: Optional[int] = None,
    ) -> List[BackendSearchResult]:
        if not self._rag:
            return []
        results = await self._rag.vector_search(
            query, top_k=top_k, chunk_type=chunk_type, chapter=chapter, log_query=False
        )
        return [
            BackendSearchResult(
                chunk_id=r.chunk_id,
                chapter=r.chapter,
                scene_index=r.scene_index,
                content=r.content,
                score=r.score,
                source=r.source,
                parent_chunk_id=r.parent_chunk_id,
                chunk_type=r.chunk_type,
                source_file=r.source_file,
            )
            for r in results
        ]

    def add_chunks(self, chunks: List[Dict]) -> int:
        return 0

    def get_stats(self) -> BackendStats:
        return BackendStats()

    def is_available(self) -> bool:
        return self._rag is not None


class TemporalGraphBackendAdapter:
    """时序图后端适配器（包装现有 TemporalGraphIndex）"""

    backend_name: str = "temporal_graph"

    def __init__(self, config=None, temporal_graph=None):
        self.config = config
        self._graph = temporal_graph

    def add_edge(
        self,
        src: str,
        rel: str,
        tgt: str,
        chapter: int,
        weight: float = 1.0,
    ) -> None:
        if self._graph:
            self._graph.add_edge(src, rel, tgt, chapter, weight)

    def query_expand(
        self,
        entity: str,
        current_chapter: int,
        max_hops: int = 2,
        max_entities: int = 10,
    ) -> List[Dict]:
        if not self._graph:
            return []
        results = self._graph.query_expand(entity, current_chapter, max_hops, max_entities)
        return [
            {
                "entity": r.entity,
                "rel": r.rel,
                "score": r.score,
                "src": r.src,
                "hop": r.hop,
            }
            for r in results
        ]

    def get_neighbors(
        self,
        entity: str,
        rel_type: Optional[str] = None,
    ) -> List[Dict]:
        if not self._graph:
            return []
        edges = self._graph.get_neighbors(entity, rel_type)
        return [
            {
                "src": e.src,
                "rel": e.rel,
                "tgt": e.tgt,
                "weight": e.weight,
                "last_seen_chapter": e.last_seen_chapter,
            }
            for e in edges
        ]

    def save_state(self, db_path: str) -> int:
        if not self._graph:
            return 0
        return self._graph.save_to_db(db_path)

    def load_state(self, db_path: str) -> bool:
        if not self._graph:
            return False
        return self._graph.load_from_db(db_path)

    def is_available(self) -> bool:
        return self._graph is not None


BackendFactory.register("vector", VectorSearchBackend)
BackendFactory.register("temporal_graph", TemporalGraphBackendAdapter)