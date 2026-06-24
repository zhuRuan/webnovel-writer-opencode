# DAO 数据访问层 — 模块设计

> 版本: 2.9 | 更新: 2026-06 | 父文档: [00-master-architecture.md](00-master-architecture.md)

## 概述

统一数据访问层，封装所有 SQLite 操作。上层 API 和 Agent 通过 DAO 调用数据，不直接写 SQL。v2.9 引入，替代此前散落在 `app.py`、`context_manager.py` 等模块中的零散 SQL。

## 架构

```
dao/__init__.py → get_dao(Class, db_path)  工厂 + 单例缓存
    │
    ├── base.py              → BaseDAO (_fetch / _execute / _exists)
    ├── entity_dao.py        → 实体 / 别名 / 状态变化
    ├── character_event_dao.py → 角色事件 CRUD + 逾期查询
    ├── knowledge_dao.py     → 角色知识 (theater + skills)
    ├── faction_dao.py       → 势力聚合查询
    ├── relationship_dao.py  → 关系 / 关系事件
    ├── memory_dao.py        → 角色记忆 CRUD + RAG + Wickelgren 衰减
    ├── state_dao.py         → 角色状态 (装备/健康度) + 事件溯源
    └── director_dao.py      → 导演文风 + 写作技法
```

## 设计原则

1. **单例复用**: 同 `db_path` 的 DAO 实例全局共享，`_instances` 字典缓存，减少连接开销
2. **参数化查询**: 所有 SQL 使用 `?` 占位符，防注入
3. **表不存在降级**: `_fetch` 内置 `"no such table"` → 返回空列表，兼容旧库
4. **向后兼容**: `state_dao.py` 兼容 `state_changes.field` 的旧格式（纯字段名）和新格式（`change_type.field_name`）

## 接口规范

### BaseDAO — 连接与安全查询

| 方法 | 签名 | 说明 |
|------|------|------|
| `_fetch` | `(query, params=()) -> list[dict]` | 安全查询，表不存在返回 `[]` |
| `_execute` | `(query, params=()) -> int` | 写操作，返回 `lastrowid` |
| `_exists` | `(table, where, params=()) -> bool` | 存在性检查 |

### EntityDAO

| 方法 | 说明 |
|------|------|
| `list_entities(entity_type, limit, offset)` | 实体列表（分页） |
| `get_entity(entity_id)` | 单个实体详情 |
| `create_entity(data)` | 创建实体 |
| `update_entity(entity_id, data)` | 更新实体 |
| `delete_entity(entity_id)` | 删除实体 |
| `list_aliases(entity_id)` | 实体别名列表 |
| `add_alias(entity_id, alias)` | 添加别名 |
| `get_state_changes(entity_id, limit)` | 状态变化历史 |

### CharacterEventDAO

| 方法 | 说明 |
|------|------|
| `list_events(entity_id, event_type, limit, offset)` | 角色事件列表 |
| `get_overdue_events(current_chapter)` | 逾期事件查询 |
| `create_event(data)` | 创建事件 |
| `update_event(event_id, data)` | 更新事件 |
| `delete_event(event_id)` | 删除事件 |

### KnowledgeDAO

| 方法 | 说明 |
|------|------|
| `list_knowledge(actor_id, domain)` | 角色知识列表 |
| `get_knowledge(knowledge_id)` | 知识详情 |
| `create_knowledge(data)` | 创建知识条目 |
| `update_knowledge(knowledge_id, data)` | 更新知识 |
| `delete_knowledge(knowledge_id)` | 删除知识 |

### FactionDAO

| 方法 | 说明 |
|------|------|
| `list_factions()` | 势力聚合（节点 + 边） |
| `get_faction(name)` | 单个势力详情 |
| `get_faction_members(name)` | 势力成员列表 |

### RelationshipDAO

| 方法 | 说明 |
|------|------|
| `list_relationships(entity_id, rel_type)` | 关系列表 |
| `get_relationship(source_id, target_id)` | 关系详情 |
| `create_relationship(data)` | 创建关系 |
| `update_relationship(source_id, target_id, data)` | 更新关系 |
| `delete_relationship(source_id, target_id)` | 删除关系 |
| `list_relationship_events(entity_id, limit)` | 关系事件历史 |

### MemoryDAO

| 方法 | 说明 |
|------|------|
| `list_memories(actor_id, memory_type, tag, limit, offset)` | 记忆列表（多条件筛选） |
| `get_memory(memory_id)` | 记忆详情（含标签） |
| `create_memory(data)` | 创建记忆 |
| `update_memory(memory_id, data)` | 更新记忆 |
| `delete_memory(memory_id)` | 删除记忆 |
| `add_tag(memory_id, tag)` | 添加标签 |
| `remove_tag(memory_id, tag)` | 移除标签 |
| `search_memories(actor_id, query, limit)` | 关键词搜索 |
| `apply_decay(actor_id, current_chapter)` | 应用 Wickelgren 衰减 |
| `get_top_memories(actor_id, limit, current_chapter)` | 获取 top-K 记忆（含衰减） |

### StateDAO

| 方法 | 说明 |
|------|------|
| `get_state(actor_id)` | 角色完整当前状态 |
| `get_memory_strength(actor_id)` | 查询记忆强度（默认 5） |
| `upsert_state(actor_id, data)` | 创建或更新状态 |
| `update_health(actor_id, health_data)` | 更新健康状态 |
| `update_equipment(actor_id, equipment_data)` | 更新装备 |
| `update_location(actor_id, location, chapter)` | 更新位置 |
| `record_change(entity_id, field, old_value, new_value, reason, chapter)` | 记录状态变化事件 |

### DirectorDAO

| 方法 | 说明 |
|------|------|
| `list_styles(category, is_active)` | 文风规则列表 |
| `get_style(style_id)` | 文风规则详情 |
| `create_style(data)` | 创建文风规则 |
| `update_style(style_id, data)` | 更新文风规则 |
| `delete_style(style_id)` | 删除文风规则 |
| `get_styles_prompt()` | 生成可注入 Agent 的文风提示 |
| `list_techniques(category, search, limit)` | 技法列表 |
| `get_techniques_grouped()` | 按 7 大主分类分组 |
| `track_technique(chapter, technique_name, category, context)` | 记录章节技法使用 |
| `import_from_csv(csv_path)` | 从 CSV 导入技法 |

## 使用示例

```python
from .opencode.scripts.data_modules.dao import get_dao
from .opencode.scripts.data_modules.dao.memory_dao import MemoryDAO

dao = get_dao(MemoryDAO, ".webnovel/index.db")
memories = dao.list_memories(actor_id="lin_zhan", memory_type="episodic", limit=10)
```

## 与旧代码的关系

- `app.py` 中 91 个 API 端点已全部迁移到 DAO 调用
- `context_manager.py` 的角色情报板构建通过 MemoryDAO + StateDAO + CharacterEventDAO
- `actor_manager.py` 的记忆检索通过 MemoryDAO
- 旧 `state_changes` 表保留，`StateDAO` 兼容新旧两种 `field` 格式
