# RAG 与配置说明

## RAG 检索架构

```
查询 → QueryRouter(auto) → vector / bm25 / hybrid / graph_hybrid
                     └→ RRF 融合 + Rerank → Top-K
```

默认模型：

- Embedding：`Qwen/Qwen3-Embedding-8B`
- Reranker：`jina-reranker-v3`

## 环境变量加载顺序

1. 进程环境变量（最高优先级）
2. 书项目根目录下的 `.env`
3. 用户级全局：`~/.claude/webnovel-writer/.env`

## `.env` 最小配置

```bash
EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EMBED_API_KEY=your_embed_api_key

RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=jina-reranker-v3
RERANK_API_KEY=your_rerank_api_key
```

说明：

- 未配置 Embedding Key 时，语义检索会回退到 BM25。
- 推荐每本书单独配置 `${PROJECT_ROOT}/.env`，避免多项目串配置。

## API 获取地址

| 服务 | 地址 |
|------|------|
| ModelScope (Embedding) | https://www.modelscope.cn |
| Jina AI (Reranker) | https://jina.ai |

## Python CLI 命令

```bash
# 索引重建
python .opencode/scripts/webnovel.py index process-chapter --chapter 1

# 状态报告
python .opencode/scripts/webnovel.py status --focus all

# RAG 统计
python .opencode/scripts/webnovel.py rag stats
```

## Graph-RAG 持久化

TemporalGraphIndex 支持 SQLite 持久化，避免每次启动时全量重建：

### 数据流

```
首次启动:
  _init_temporal_graph()
    → _load_relationships_to_graph() (全量重建)
    → save_to_db(index.db)

后续启动:
  _init_temporal_graph()
    → load_from_db(index.db) ✓ (毫秒级加载)
```

### 数据库表

| 表名 | 说明 |
|------|------|
| `graph_nodes` | 图节点（角色/地点/势力） |
| `graph_edges` | 图边（关系及权重） |

### 触发时机

- **触发位置**: `RAGAdapter.__init__() → _init_temporal_graph()`
- **自动保存**: 启动时全量重建后 + 5分钟延迟保存
- **验收标准**: 第二次启动时初始化耗时 < 100ms

### 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `graph_rag_enabled` | True | 启用 Graph-RAG |
| `graph_rag_expand_hops` | 2 | 最大跳数 |
| `graph_rag_max_expanded_entities` | 50 | 最大扩展实体数 |
