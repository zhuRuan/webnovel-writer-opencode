# -*- coding: utf-8 -*-
"""
TemporalGraphIndex - 时序感知图索引

三层子图架构：
1. Episode Subgraph: 章节事件（原始数据）
2. Semantic Subgraph: 实体+关系（时序）
3. Community Subgraph: 聚类摘要（世界观/阵营）

支持时序衰减的多跳关系查询。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from logging import getLogger

logger = getLogger(__name__)


@dataclass
class GraphEdge:
    """图边"""
    src: str
    rel: str
    tgt: str
    weight: float = 1.0
    last_seen_chapter: int = 0
    count: int = 1


@dataclass
class GraphNode:
    """图节点"""
    id: str
    type: str  # 角色/地点/势力/物品
    name: str
    tier: str = "装饰"
    first_appearance: int = 0
    last_appearance: int = 0


@dataclass
class QueryResult:
    """查询结果"""
    entity: str
    rel: str
    score: float
    src: str
    hop: int


class TemporalGraphIndex:
    """时序感知图索引"""
    
    def __init__(self, decay_base: float = 0.9):
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[Tuple[str, str, str], GraphEdge] = {}
        self._adjacency: Dict[str, List[Tuple[str, str, str]]] = {}  # node -> [(src, rel, tgt), ...]
        self._decay_base = decay_base
    
    def add_node(self, node: GraphNode) -> None:
        """添加或更新节点"""
        self._nodes[node.id] = node
    
    def add_edge(self, src: str, rel: str, tgt: str, chapter: int, weight: float = 1.0) -> None:
        """添加或更新边（时序感知）"""
        key = (src, rel, tgt)
        
        if key in self._edges:
            edge = self._edges[key]
            edge.weight *= 1.2  # 重复提及强化
            edge.last_seen_chapter = max(edge.last_seen_chapter, chapter)
            edge.count += 1
        else:
            edge = GraphEdge(
                src=src, rel=rel, tgt=tgt,
                weight=weight, last_seen_chapter=chapter
            )
            self._edges[key] = edge
            
            if src not in self._adjacency:
                self._adjacency[src] = []
            self._adjacency[src].append(key)
        
        logger.debug("Added edge: %s -[%s]-> %s (weight=%.2f, chapter=%d)",
                    src, rel, tgt, edge.weight, chapter)
    
    def query_expand(
        self,
        entity: str,
        current_chapter: int,
        max_hops: int = 2,
        max_entities: int = 10
    ) -> List[QueryResult]:
        """
        时序衰减查询扩展
        
        Args:
            entity: 起始实体
            current_chapter: 当前章节
            max_hops: 最大跳数
            max_entities: 最大返回实体数
        
        Returns:
            排序后的查询结果列表
        """
        visited: Set[str] = {entity}
        candidates: List[QueryResult] = []
        
        current_layer = [entity]
        
        for hop in range(1, max_hops + 1):
            next_layer = []
            
            for src in current_layer:
                if src not in self._adjacency:
                    continue
                    
                for (s, rel, tgt) in self._adjacency[src]:
                    if tgt in visited:
                        continue
                    
                    edge = self._edges[(s, rel, tgt)]
                    
                    decay = self._decay_base ** max(0, current_chapter - edge.last_seen_chapter)
                    score = edge.weight * decay
                    
                    candidates.append(QueryResult(
                        entity=tgt,
                        rel=rel,
                        score=score,
                        src=s,
                        hop=hop
                    ))
                    next_layer.append(tgt)
                    visited.add(tgt)
            
            current_layer = next_layer
            if not current_layer:
                break
        
        candidates.sort(key=lambda x: (x.score, -x.hop), reverse=True)
        return candidates[:max_entities]
    
    def get_node(self, entity_id: str) -> Optional[GraphNode]:
        """获取节点"""
        return self._nodes.get(entity_id)
    
    def get_neighbors(self, entity: str, rel_type: Optional[str] = None) -> List[GraphEdge]:
        """获取邻居边"""
        if entity not in self._adjacency:
            return []
        
        edges = []
        for (s, rel, tgt) in self._adjacency[entity]:
            if rel_type is None or rel == rel_type:
                edges.append(self._edges[(s, rel, tgt)])
        return edges
    
    def get_path(
        self,
        src: str,
        tgt: str,
        max_hops: int = 3
    ) -> List[List[Tuple[str, str]]]:
        """查找两点间的所有路径"""
        paths: List[List[Tuple[str, str]]] = []
        current_path: List[Tuple[str, str]] = []
        
        def dfs(node: str, visited: Set[str], depth: int):
            if depth > max_hops:
                return
            if node == tgt:
                paths.append(list(current_path))
                return
            
            if node not in self._adjacency:
                return
                
            for (s, rel, nxt) in self._adjacency[node]:
                if nxt in visited:
                    continue
                visited.add(nxt)
                current_path.append((rel, nxt))
                dfs(nxt, visited, depth + 1)
                current_path.pop()
                visited.remove(nxt)
        
        dfs(src, {src}, 0)
        return paths
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "adjacency_entries": sum(len(v) for v in self._adjacency.values())
        }
    
    def clear(self) -> None:
        """清空图"""
        self._nodes.clear()
        self._edges.clear()
        self._adjacency.clear()
    
    def from_dict(self, data: Dict) -> None:
        """从字典加载"""
        self._nodes = {
            k: GraphNode(**v) for k, v in data.get("nodes", {}).items()
        }
        self._edges = {
            tuple(k.split("|")): GraphEdge(**v) 
            for k, v in data.get("edges", {}).items()
        }
        self._adjacency.clear()
        for (src, rel, tgt), edge in self._edges.items():
            if src not in self._adjacency:
                self._adjacency[src] = []
            self._adjacency[src].append((src, rel, tgt))
    
    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            "nodes": {k: {
                "id": v.id, "type": v.type, "name": v.name,
                "tier": v.tier, "first_appearance": v.first_appearance,
                "last_appearance": v.last_appearance
            } for k, v in self._nodes.items()},
            "edges": {
                f"{k[0]}|{k[1]}|{k[2]}": {
                    "src": v.src, "rel": v.rel, "tgt": v.tgt,
                    "weight": v.weight, "last_seen_chapter": v.last_seen_chapter,
                    "count": v.count
                } for k, v in self._edges.items()
            }
        }

    def save_to_db(self, db_path: str) -> int:
        """
        持久化到 SQLite 数据库
        
        Args:
            db_path: index.db 路径
        
        Returns:
            保存的边数量
        """
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY,
                type TEXT,
                name TEXT,
                tier TEXT,
                first_appearance INTEGER,
                last_appearance INTEGER
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                src TEXT,
                rel TEXT,
                tgt TEXT,
                weight REAL,
                last_seen_chapter INTEGER,
                count INTEGER,
                PRIMARY KEY (src, rel, tgt)
            )
        """)
        
        cursor.execute("DELETE FROM graph_nodes")
        cursor.execute("DELETE FROM graph_edges")
        
        for node in self._nodes.values():
            cursor.execute(
                "INSERT INTO graph_nodes VALUES (?, ?, ?, ?, ?, ?)",
                (node.id, node.type, node.name, node.tier,
                 node.first_appearance, node.last_appearance)
            )
        
        for edge in self._edges.values():
            cursor.execute(
                "INSERT INTO graph_edges VALUES (?, ?, ?, ?, ?, ?)",
                (edge.src, edge.rel, edge.tgt, edge.weight,
                 edge.last_seen_chapter, edge.count)
            )
        
        conn.commit()
        edge_count = len(self._edges)
        conn.close()
        
        logger.info(f"Graph 持久化完成: {len(self._nodes)} 节点, {edge_count} 边")
        return edge_count

    def load_from_db(self, db_path: str) -> bool:
        """
        从 SQLite 数据库加载
        
        Args:
            db_path: index.db 路径
        
        Returns:
            是否成功加载
        """
        import sqlite3
        if not db_path:
            return False
        
        import os
        if not os.path.exists(db_path):
            logger.warning(f"Graph DB 不存在: {db_path}")
            return False
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='graph_edges'
            """)
            if not cursor.fetchone():
                conn.close()
                return False
            
            cursor.execute("SELECT * FROM graph_nodes")
            for row in cursor.fetchall():
                node = GraphNode(
                    id=row[0], type=row[1], name=row[2],
                    tier=row[3], first_appearance=row[4],
                    last_appearance=row[5]
                )
                self._nodes[node.id] = node
            
            cursor.execute("SELECT * FROM graph_edges")
            for row in cursor.fetchall():
                edge = GraphEdge(
                    src=row[0], rel=row[1], tgt=row[2],
                    weight=row[3], last_seen_chapter=row[4],
                    count=row[5]
                )
                key = (edge.src, edge.rel, edge.tgt)
                self._edges[key] = edge
                
                if edge.src not in self._adjacency:
                    self._adjacency[edge.src] = []
                self._adjacency[edge.src].append(key)
            
            conn.close()
            
            logger.info(f"Graph 加载完成: {len(self._nodes)} 节点, {len(self._edges)} 边")
            return True
            
        except Exception as e:
            logger.error(f"Graph 加载失败: {e}")
            return False

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)
