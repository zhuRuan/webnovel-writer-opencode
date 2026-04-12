# -*- coding: utf-8 -*-
"""
TemporalGraphIndex 测试
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_modules.temporal_graph import TemporalGraphIndex, GraphNode, GraphEdge, QueryResult


class TestTemporalGraphIndex:
    """TemporalGraphIndex 测试"""

    def test_add_node(self):
        """测试添加节点"""
        graph = TemporalGraphIndex()
        node = GraphNode(id="xiaoyan", type="角色", name="萧炎", tier="核心")
        graph.add_node(node)
        
        retrieved = graph.get_node("xiaoyan")
        assert retrieved is not None
        assert retrieved.name == "萧炎"

    def test_add_edge(self):
        """测试添加边"""
        graph = TemporalGraphIndex()
        graph.add_edge("xiaoyan", "师徒", "yaolao", chapter=1)
        
        neighbors = graph.get_neighbors("xiaoyan")
        assert len(neighbors) == 1
        assert neighbors[0].rel == "师徒"
        assert neighbors[0].tgt == "yaolao"

    def test_edge_strengthening(self):
        """测试边强化（重复提及）"""
        graph = TemporalGraphIndex()
        graph.add_edge("xiaoyan", "师徒", "yaolao", chapter=1)
        graph.add_edge("xiaoyan", "师徒", "yaolao", chapter=5)
        
        neighbors = graph.get_neighbors("xiaoyan")
        assert len(neighbors) == 1
        assert neighbors[0].count == 2
        assert neighbors[0].last_seen_chapter == 5

    def test_query_expand_single_hop(self):
        """测试单跳查询"""
        graph = TemporalGraphIndex()
        graph.add_node(GraphNode(id="xiaoyan", type="角色", name="萧炎"))
        graph.add_node(GraphNode(id="yaolao", type="角色", name="药老"))
        graph.add_edge("xiaoyan", "师徒", "yaolao", chapter=1)
        
        results = graph.query_expand("xiaoyan", current_chapter=10, max_hops=1, max_entities=10)
        
        assert len(results) == 1
        assert results[0].entity == "yaolao"
        assert results[0].rel == "师徒"

    def test_query_expand_multi_hop(self):
        """测试多跳查询"""
        graph = TemporalGraphIndex()
        graph.add_node(GraphNode(id="xiaoyan", type="角色", name="萧炎"))
        graph.add_node(GraphNode(id="yaolao", type="角色", name="药老"))
        graph.add_node(GraphNode(id="enemy", type="角色", name="敌人"))
        
        graph.add_edge("xiaoyan", "师徒", "yaolao", chapter=1)
        graph.add_edge("yaolao", "宿敌", "enemy", chapter=5)
        
        results = graph.query_expand("xiaoyan", current_chapter=10, max_hops=2, max_entities=10)
        
        assert len(results) == 2
        entity_ids = [r.entity for r in results]
        assert "yaolao" in entity_ids
        assert "enemy" in entity_ids

    def test_query_expand_recency_decay(self):
        """测试时序衰减"""
        graph = TemporalGraphIndex()
        graph.add_edge("xiaoyan", "师徒", "yaolao", chapter=1, weight=1.0)
        graph.add_edge("xiaoyan", "仇敌", "enemy", chapter=9, weight=1.0)
        
        results = graph.query_expand("xiaoyan", current_chapter=10, max_hops=1, max_entities=10)
        
        assert len(results) == 2
        yaolao_result = next(r for r in results if r.entity == "yaolao")
        enemy_result = next(r for r in results if r.entity == "enemy")
        
        assert yaolao_result.score < enemy_result.score

    def test_query_expand_max_entities(self):
        """测试实体数量限制"""
        graph = TemporalGraphIndex()
        for i in range(20):
            graph.add_edge("xiaoyan", "相关", f"entity{i}", chapter=1)
        
        results = graph.query_expand("xiaoyan", current_chapter=10, max_hops=1, max_entities=5)
        
        assert len(results) == 5

    def test_get_path(self):
        """测试路径查找"""
        graph = TemporalGraphIndex()
        graph.add_edge("A", "->", "B", chapter=1)
        graph.add_edge("B", "->", "C", chapter=2)
        graph.add_edge("A", "->", "D", chapter=3)
        graph.add_edge("D", "->", "C", chapter=4)
        
        paths = graph.get_path("A", "C", max_hops=3)
        
        assert len(paths) >= 1

    def test_get_stats(self):
        """测试统计信息"""
        graph = TemporalGraphIndex()
        graph.add_node(GraphNode(id="n1", type="角色", name="节点1"))
        graph.add_node(GraphNode(id="n2", type="角色", name="节点2"))
        graph.add_edge("n1", "->", "n2", chapter=1)
        
        stats = graph.get_stats()
        
        assert stats["nodes"] == 2
        assert stats["edges"] == 1

    def test_clear(self):
        """测试清空图"""
        graph = TemporalGraphIndex()
        graph.add_edge("A", "->", "B", chapter=1)
        graph.clear()
        
        assert graph.get_stats()["nodes"] == 0
        assert graph.get_stats()["edges"] == 0

    def test_serialization(self):
        """测试序列化"""
        graph = TemporalGraphIndex()
        graph.add_node(GraphNode(id="n1", type="角色", name="节点1", first_appearance=1))
        graph.add_edge("n1", "->", "n2", chapter=5)
        
        data = graph.to_dict()
        assert "nodes" in data
        assert "edges" in data
        
        graph2 = TemporalGraphIndex()
        graph2.from_dict(data)
        
        assert graph2.get_stats()["nodes"] == 1
        assert graph2.get_stats()["edges"] == 1

    def test_save_load_db(self, tmp_path):
        """测试数据库持久化"""
        import sqlite3
        
        db_path = str(tmp_path / "test_graph.db")
        
        graph = TemporalGraphIndex()
        node = GraphNode(id="角色1", type="角色", name="萧炎")
        graph.add_node(node)
        graph.add_edge("角色1", "结识", "角色2", chapter=5)
        
        edge_count = graph.save_to_db(db_path)
        assert edge_count == 1
        assert graph.node_count == 1
        assert graph.edge_count == 1
        
        graph2 = TemporalGraphIndex()
        loaded = graph2.load_from_db(db_path)
        assert loaded is True
        assert graph2.node_count == 1
        assert graph2.edge_count == 1
        
        node_retrieved = graph2.get_node("角色1")
        assert node_retrieved.name == "萧炎"
