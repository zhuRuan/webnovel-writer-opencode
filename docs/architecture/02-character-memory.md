# 角色记忆与状态系统 — 模块设计

> 版本: 2.9 | 更新: 2026-06 | 父文档: [00-master-architecture.md](00-master-architecture.md)

## 概述

为每个角色提供私有记忆库 + 状态追踪 + 计划系统。解决长篇连载中"角色动机漂移"和"记忆遗忘"问题。核心模块：`memory_dao.py` + `state_dao.py` + `character_event_dao.py`。

## 记忆模型

### 4 种记忆类型

| 类型 | 说明 | 示例 |
|------|------|------|
| 情景记忆 (episodic) | 5W 框架：Who/What/When/Where/Why | "第3章：林战在废墟小镇被铁牙的追捕队截住" |
| 语义记忆 (semantic) | 学到的知识/事实 | "T2级改造士兵核心弱点在脊柱接驳口" |
| 关系记忆 (relational) | 对特定人物的印象/态度 | "对铁牙：曾是兄弟、现在是敌人" |
| 决策记忆 (decision) | 做过的重要选择及原因 | "选择去深渊城而非回铁壁城" |

### 重要性评分

```
importance = emotional_weight × 0.4 + personal_relevance × 0.3 + novelty × 0.2 + consequence × 0.1
```

- emotional_weight (0-10): 事件的情绪强度
- personal_relevance (0-10): 与角色目标/关系的相关度
- novelty (0-10): 是否是全新信息
- consequence (0-10): 对后续剧情的影响程度

## 遗忘机制

### Wickelgren 衰减公式

```
retention = importance × e^(-λ × Δchapter / memory_strength)
```

- λ: 衰减系数（默认 0.1）
- Δchapter: 距记忆来源章节的章节数
- memory_strength: 每角色独立属性 (1-10)，存于 `character_state` 表

### 记忆力强度分级

| 强度 | 描述 | 衰减半衰期 |
|------|------|-----------|
| 9-10 | 过目不忘（天才/改造人） | 100 章 |
| 7-8 | 优秀（军人的洞察力） | 50 章 |
| 5-6 | 正常 | 20 章 |
| 3-4 | 较差（老人/受损） | 8 章 |
| 1-2 | 极差（失忆/醉酒） | 3 章 |

### 检索增强与竞争抑制

- 检索增强: 每次检索 `retention × 1.2`
- 遗忘过滤: `retention < 0.3` 的记忆不返回
- 竞争抑制: 超容量时低分记忆 retention 减半，高分记忆增强

## 数据库表

### character_memories — 记忆主表

```sql
CREATE TABLE character_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id TEXT NOT NULL,
    memory_type TEXT NOT NULL CHECK(memory_type IN ('episodic','semantic','relational','decision')),
    content TEXT NOT NULL,
    who TEXT, what TEXT, when_chapter INTEGER, where_place TEXT, why_reason TEXT,
    importance REAL DEFAULT 5.0,
    emotional_weight REAL DEFAULT 5.0,
    personal_relevance REAL DEFAULT 5.0,
    novelty REAL DEFAULT 5.0,
    consequence REAL DEFAULT 5.0,
    retention REAL DEFAULT 1.0,
    retrieval_count INTEGER DEFAULT 0,
    source_chapter INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### memory_tags — 多标签关联

```sql
CREATE TABLE memory_tags (
    memory_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag),
    FOREIGN KEY (memory_id) REFERENCES character_memories(id) ON DELETE CASCADE
)
```

### memory_embeddings — RAG 向量（预留）

```sql
CREATE TABLE memory_embeddings (
    memory_id INTEGER PRIMARY KEY,
    embedding BLOB NOT NULL,
    model TEXT DEFAULT 'default',
    FOREIGN KEY (memory_id) REFERENCES character_memories(id) ON DELETE CASCADE
)
```

### character_state — 角色状态快照

```sql
CREATE TABLE character_state (
    actor_id TEXT PRIMARY KEY,
    health TEXT DEFAULT '{}',       -- JSON: {hp, max_hp, injuries:[], status_effects:[]}
    equipment TEXT DEFAULT '[]',    -- JSON: [{name, slot, grade, effects}]
    inventory TEXT DEFAULT '[]',    -- JSON: [{name, quantity, description}]
    location TEXT DEFAULT '',
    memory_strength INTEGER DEFAULT 5,
    chapter INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### state_changes — 状态变化事件溯源

保留旧表，`StateDAO` 兼容新旧两种 `field` 格式：
- 新格式: `health.hp`, `equipment.weapon`, `location`
- 旧格式: `description`（纯字段名）

### character_events — 角色事件/计划

```sql
CREATE TABLE character_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    event_type TEXT NOT NULL,       -- appearance/state_change/relationship_change/milestone/death/plan
    event_data TEXT NOT NULL,       -- JSON: {goal, steps, deadline_chapter, status}
    chapter_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
)
```

## RAG 检索流程

```
actor-agent 准备演绎
    │
    ├── 1. 从 character_memories 查询角色记忆（按 retention DESC, importance DESC）
    ├── 2. 用当前场景上下文做语义搜索（memory_embeddings 向量相似度，预留）
    ├── 3. 混合排序: similarity × 0.5 + retention × 0.3 + importance × 0.2
    ├── 4. 取 top-K（K 与角色 memory_strength 相关）
    └── 5. 注入 actor-agent 的 prompt
```

当前阶段以关键词匹配为主，向量相似度为未来增强。

## 计划系统

### 计划来源

- 手动创建: 通过 Dashboard 或 API 创建 `character_events` (event_type='plan')
- 决策记忆推断: 角色做了选择 A → 计划下一步是执行 A
- 关系记忆推断: 角色对某人形成印象 → 计划下次见面时的态度

### 计划呈现

Dashboard 角色图鉴页 → 角色计划 Tab:
- 计划摘要卡片: 优先级 + 状态 + 目标章节 + 进度条
- 来源标注: 手动创建 | 从记忆推断 | 从角色事件
- 逾期预警: `deadline_chapter < current_chapter` 且 `status != 'completed'`

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/memories?actor_id=X&memory_type=Y&tag=Z` | 记忆列表 |
| GET | `/api/memories/{id}` | 记忆详情 |
| POST | `/api/memories` | 创建记忆 |
| PUT | `/api/memories/{id}` | 更新记忆 |
| DELETE | `/api/memories/{id}` | 删除记忆 |
| POST | `/api/memories/{id}/tags` | 添加标签 |
| DELETE | `/api/memories/{id}/tags/{tag}` | 移除标签 |
| GET | `/api/memories/search?actor_id=X&q=Y` | 关键词搜索 |
| GET | `/api/character-state/{actor_id}` | 角色状态 |
| PUT | `/api/character-state/{actor_id}` | 更新状态 |
| GET | `/api/character-events?entity_id=X&event_type=plan` | 角色计划列表 |
| GET | `/api/character-events/overdue?current_chapter=N` | 逾期计划 |
| POST | `/api/character-events` | 创建事件/计划 |
| PUT | `/api/character-events/{id}` | 更新事件/计划 |
| DELETE | `/api/character-events/{id}` | 删除事件/计划 |
