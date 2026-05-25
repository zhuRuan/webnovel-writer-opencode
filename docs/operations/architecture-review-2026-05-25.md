# 项目分层架构审查报告 & 修复计划

> 审查日期：2026-05-25
> 审查范围：6 层架构 × 62 数据模块 × 12 skill × 5 agent
> 方法：代码静态分析 + CodeGraph AST 索引 + 文档交叉验证

---

## P0: 双重事件系统冲突 (EventLogStore vs SSOT Enforcer)

### 现状

项目存在两套完全独立的事件系统，写入同一目录 `.story-system/events/`：

| 维度 | EventLogStore (Phase 3-4) | SSOT Enforcer (Phase 5 新增) |
|------|--------------------------|---------------------------|
| 文件命名 | `chapter_003.events.json` | `000001.event.json` |
| 文件格式 | JSON 数组 (多事件) | JSON 对象 (单事件) |
| Schema 验证 | Pydantic `StoryEvent` (10 种类型) | 自由 dict (无验证) |
| 触发位置 | `chapter_commit_service.py:132` | `chapter_commit.py:60` |
| 数据内容 | **故事内容**：角色状态变化、关系变化、突破、宝物、伏笔 | **运维元数据**：章节提交状态、override 规则变更 |
| SQLite 镜像 | 有 (`story_events` 表) | 无 |

### 核心断裂

SSOT enforcer 的架构承诺（文件头部注释）：

> `.story-system/events/*.event.json ← append-only TRUTH (event log)`
> `state.json / index.db ← materialized VIEW (projection, rebuildable)`
> `Projection can be rebuilt from event log at any time`

**实际情况：**

1. `publish_event()` 每章只被调用 1 次，仅记录 `chapter_status_changed` — 不包含 Data Agent 提取的任何故事内容事件
2. `rebuild_state_json()` 只处理 4 种事件类型：chapter_status_changed, entity_created, open_loop_created, open_loop_closed
3. **10 种故事内容事件（character_state_changed, relationship_changed, world_rule_revealed/broken, power_breakthrough, artifact_obtained, promise_created/paid_off）全部走 EventLogStore，完全不经过 SSOT event log**
4. `ssot rebuild` 只能重建章节号列表和 entity stub，不能重建任何实际故事状态
5. `ssot rebuild` 完全不覆盖 `index.db` — 而 index.db 是实体关系的核心存储
6. `read_events()` 遍历 `*.event.json` 时遇到 `chapter_*.events.json` 文件解析失败，静默跳过

### 数据流对比

```
实际（当前）：
  Data Agent 提取事实
    ├── accepted_events ──→ EventLogStore ──→ chapter_NNN.events.json + SQLite  ← 故事内容
    ├── state_deltas ──→ StateProjectionWriter ──→ state.json
    ├── entity_deltas ──→ IndexProjectionWriter ──→ index.db
    └── ...
  
  chapter_commit CLI（事后追加）
    └── publish_event("chapter_status_changed") ──→ NNNNNN.event.json  ← 仅有元数据

应有（架构承诺）：
  Data Agent 提取事实
    └── accepted_events ──→ publish_event() × N ──→ NNNNNN.event.json  ← 所有事件
                                  │
                                  └──→ 5 个 projection writers（作为投影层）
```

### 修复方案

**目标：** 合并为统一事件日志，`publish_event()` 成为唯一写入口，`EventLogStore` 降级为 SQLite 镜像层。

**Step 1 — 统一事件格式（ssot_enforcer.py）**

```python
# 扩展 publish_event，接受完整的 story event schema
# 统一文件格式为按章组织的数组（兼容 EventLogStore 现有格式）
# 写 JSON 文件 + SQLite 镜像（迁移 EventLogStore._write_sqlite_mirror 逻辑）
```

**Step 2 — apply_projections 中调用 publish_event（chapter_commit_service.py:127）**

```python
# 在 apply_projections 开头，对每个 accepted_event 调用 publish_event
# 替换 EventLogStore.write_events() 调用
for event in payload.get("accepted_events", []):
    publish_event(self.project_root, event["event_type"],
                  event.get("payload", {}), chapter=chapter)
```

**Step 3 — 扩展 rebuild_state_json 支持全部 14 种事件类型**

```
当前支持：chapter_status_changed, entity_created, open_loop_created, open_loop_closed
需新增：character_state_changed → protagonist_state / entity_state
        relationship_changed → entities_v3 关系字段
        power_breakthrough → entity_state.realm
        artifact_obtained → entity_state.items
        world_rule_revealed → world_rules
        world_rule_broken → world_rules + override_ledger
        promise_created → reader_promises
        promise_paid_off → reader_promises
```

**Step 4 — 新增 rebuild_index_db（ssot_enforcer.py）**

```python
def rebuild_index_db(project_root: Path, events=None) -> dict:
    """从事件日志重建 index.db（实体、关系、出场记录等）"""
```

**Step 5 — 迁移兼容**

- 保留 `EventLogStore.read_events()` 作为只读兼容层
- `EventLogStore.write_events()` 标记 deprecated，内部委托给 `publish_event()`
- 旧 `chapter_NNN.events.json` 不删除不迁移

**影响范围：**
- `ssot_enforcer.py` — 扩展 schema + rebuild + SQLite 镜像
- `chapter_commit_service.py` — 替换 write_events 调用
- `event_log_store.py` — write_events deprecated
- `chapter_commit.py` — 移除重复的 publish_event 调用
- `story_event_schema.py` — 可能需要扩展字段

**风险：** 中。改动涉及核心提交链路。需完整测试覆盖。

---

## P0: SSOT 集成深度审查 (publish_event 调用链)

### 扫描结果

`publish_event` 的调用点（全项目）：

| 文件 | 行 | 事件类型 |
|------|-----|---------|
| `chapter_commit.py` | 60 | chapter_status_changed |
| `override_contract_engine.py` | 97 | override_rule_added |
| `ssot_enforcer.py` | 185 | projection_rebuilt |

**共计 3 个调用点，2 种事件类型。**（projection_rebuilt 是自指）

### 应该调用但未调用的位置

| 模块 | 方法 | 应发布的事件 |
|------|------|-------------|
| `state_projection_writer.py` | `apply()` | entity_state_changed × N |
| `index_projection_writer.py` | `apply()` | entity_created, relationship_changed, appearance_recorded |
| `summary_projection_writer.py` | `apply()` | summary_generated |
| `memory_projection_writer.py` | `apply()` | memory_updated |
| `chapter_commit_service.py` | `apply_projections()` | 所有 accepted_events（当前只走 EventLogStore） |
| `state_manager.py` | `set_chapter_status()`, `add_entity()`, `update_entity()`, `record_state_change()`, `add_relationship()` | 各自对应的事件类型 |
| `index_debt_mixin.py` | `create_simple_debt()`, `resolve_debt_by_subject()` | debt_created, debt_resolved |
| `chapter_delete_service.py` | `cmd_delete_chapters()` | chapter_deleted |

**结论：`publish_event` 只覆盖了约 5% 的状态变更路径。**

### 修复方案

**Step 1 — 在 `apply_projections()` 中发布所有 accepted_events**

这不是事后追加，而是在投影写入之前先记录事件到 log。遵循 "先写事件日志，再写投影" 的 Event Sourcing 原则。

```python
# chapter_commit_service.py:apply_projections()
def apply_projections(self, payload):
    if payload["meta"]["status"] != "accepted":
        return payload
    chapter = int(payload.get("meta", {}).get("chapter") or 0)
    
    # Step A: 先写事件日志（immutable）
    for event in payload.get("accepted_events", []):
        publish_event(self.project_root, event["event_type"],
                      event.get("payload", {}), chapter=chapter)
    
    # Step B: 再写投影（materialized views）
    # ... 原有投影逻辑
```

**Step 2 — 在 `chapter_commit.py` 中移除冗余调用**

`apply_projections()` 内部已发布事件，CLI 层不需要再发布 `chapter_status_changed`。改为在 `apply_projections()` 内部发布。

**Step 3 — 在删除服务中发布事件（chapter_delete_service.py）**

```python
# _clean_state_json 成功后
publish_event(project_root, "chapter_deleted",
              {"chapters": chapters}, chapter=min(chapters))
```

**影响范围：**
- `chapter_commit_service.py` — 新增 publish_event 调用
- `chapter_commit.py` — 移除冗余调用
- `chapter_delete_service.py` — 新增事件发布

**风险：** 低。改动集中，不改变外部接口。

---

## P1: Override 系统统一审查

### 现状

存在两套独立的 Override 系统：

| 维度 | index_debt_mixin.override_contracts | override_contract_engine.py |
|------|--------------------------------------|----------------------------|
| 存储 | SQLite `index.db.override_contracts` 表 | `.webnovel/override_contracts.json` |
| 用途 | 追读力债务的软建议违背记录 | 世界规则的版本化演进 |
| record_type | foreshadowing, pacing, reader_pull | world_rule (domain 参数) |
| CLI 入口 | 无独立 CLI，通过 debt tracker 间接操作 | `webnovel override add/list/context` |
| SSOT 集成 | 无 | `publish_event("override_rule_added")` |
| 上下文装配 | 无 | `context_manager._load_override_hints()` |

### 问题

1. **数据孤岛**：`override add` 写入 engine JSON 文件，但 debt 系统的 override 数据没有进入上下文装配
2. **双重入口**：用户不知道应该用哪个系统记录规则变更
3. **engine 有 SSOT 集成但无 SQLite 查询能力**；debt 有 SQLite 但无 SSOT 集成
4. **context_manager 只读 engine 的数据**，debt 系统的 override 数据对 AI 不可见

### 修复方案

**目标：** 统一到一个引擎，一个存储，一个 CLI。

**Step 1 — 统一存储到 SQLite**

将 `override_contract_engine.py` 的读写从 JSON 文件迁移到 `index.db.override_contracts` 表（利用现有 schema + engine 扩展字段）。

```python
# override_contract_engine.py
def add_override(project_root, constraint_id, old_rule, new_rule, 
                 rationale, chapter, domain="world_rule"):
    # 写入 index.db.override_contracts 表
    # 也写入 .webnovel/override_contracts.json 作为离线备份
    # 发布 SSOT 事件
```

**Step 2 — 扩展 context_manager 同时读取两边的 override 数据**

`_load_override_hints()` 已读 engine 数据 — 如果 engine 统一到 SQLite，则自动覆盖 debt 数据。

**Step 3 — 统一 CLI**

`webnovel override list` 应该同时显示 world_rule 和 debt 类型的 override。

**影响范围：**
- `override_contract_engine.py` — 存储层迁移
- `index_debt_mixin.py` — 无需改动（engine 复用现有表）
- `context_manager.py` — 可能无需改动（取决于实现）

---

## P1: Workflow 状态机集成审查

### 现状

`workflow_checkpoint.py` 定义了 5 阶段状态机：

```
PLANNING → DRAFTING → REVIEWING → REVISING → COMMITTED
```

但实际调用情况：

| 阶段 | 应触发位置 | 实际调用 |
|------|-----------|---------|
| PLANNING | context-agent 完成后 | **无** |
| DRAFTING | 正文起草完成后 | **无** |
| REVIEWING | reviewer agent 完成后 | **无** |
| REVISING | 润色完成后 | **无** |
| COMMITTED | data-agent + commit 完成后 | `chapter_commit.py:56` ✓ |

**只有最后 1 个阶段有 checkpoint 记录。** `find_interrupted()` 永远返回空，因为没有中间状态可查。

### 修复方案

**目标：** 在每个 Skill 步骤中插入 checkpoint 调用。

**Step 1 — 修改 webnovel-write SKILL.md**

在每个 Step 完成后嵌入 checkpoint 命令：

```bash
# Step 1 完成后
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  workflow checkpoint --chapter {chapter_num} --stage PLANNING

# Step 2 完成后
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  workflow checkpoint --chapter {chapter_num} --stage DRAFTING

# Step 3 完成后
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  workflow checkpoint --chapter {chapter_num} --stage REVIEWING

# Step 4 完成后
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  workflow checkpoint --chapter {chapter_num} --stage REVISING
```

**Step 2 — 在 webnovel-rewrite 和 webnovel-write-batch 中也添加**

**影响范围：**
- `webnovel-write/SKILL.md` — 4 处新增
- `webnovel-write-batch/SKILL.md` — 批量 checkpoint
- `webnovel-rewrite/SKILL.md` — 重写流程 checkpoint

**风险：** 低。仅新增 bash 命令调用。

---

## P2: 上下文装配层审查

### 4.1 截断风险 — 实际状态

**代码审查发现：** `context_compact_text_enabled` 在 `config.py:231` 定义，但**全项目没有任何地方使用这个配置项**。`_compact_json_text()` 函数不存在于当前代码中。

`context_manager.py` 的 `_assemble_json_payload()` 使用 `SECTION_ORDER` + `TEMPLATE_WEIGHTS` 控制**哪些 section 被包含**，但不做字符串截断。`context_ranker.py` 对列表项做排序（recency + frequency 评分），也不做截断。

**结论：诊断文档第 3 条"机械截断导致信息黑洞"在当前代码中已被缓解。** 旧版的预算截断逻辑已移除或未实现，当前系统按权重决定 section 包含/排除，不按字符数切割内容。

**残留问题：**
- `context_compact_text_enabled` 是死配置（dead config），应清理
- context_ranker 排序结果是否正确传递给 agent 取决于 agent 自身如何使用 context pack

**修复方案：**
- 清理死配置 `context_compact_text_enabled` 及相关字段
- 在 `config.py` 中搜索其他未使用的 context_compact_* 配置项并一并清理

### 4.2 大纲履约校验

`chapter_commit_service.build_commit()` 接收 `fulfillment_result` 但只检查 `missed_nodes` boolean。没有结构化 diff：

- CBN (Core Beat Nodes) 是否全部覆盖？
- CPN (Core Plot Nodes) 是否全部覆盖？
- CEN (Core Event Nodes) 是否全部覆盖？

**修复方案：**

在 `chapter_commit_service.py:43` 增强校验逻辑：

```python
# 当前
rejected = bool(review_result.get("blocking_count")) or bool(
    fulfillment_result.get("missed_nodes")
) or bool(disambiguation_result.get("pending"))

# 新增：按节点类型分类报告
missed_cbn = [n for n in fulfillment_result.get("missed_nodes", [])
              if n.get("type") == "CBN"]
missed_cpn = [n for n in fulfillment_result.get("missed_nodes", [])
              if n.get("type") == "CPN"]
# CBN 遗漏 → blocking
# CPN 遗漏 → warning（不阻断但记录）
```

---

## P2: 数据回写层健壮性

### 5.1 StateManager 双写 — 实际状态

**代码审查发现：**

`StateManager` 有两层写入机制：

1. `_save_state()` (line 665) — 直接 `atomic_write_json` 写 `state.json`，不走 pending 合并。被 `set_chapter_status()` 等方法调用。
2. `_sync_to_sqlite()` (line 390) + `_sync_pending_patches_to_sqlite()` (line 427) — 将内存中的 pending patches 同步到 SQLite。

两个写入路径在 `update_progress()` → `save_state()` 流程中同时触发，但**没有事务协调**：
- `atomic_write_json` 可能成功但 `_sync_pending_patches_to_sqlite` 可能失败
- 恢复逻辑需要更完整的快照机制

**但实际影响有限：** `chapter_commit_service.apply_projections()` 不使用 StateManager —— 它直接通过 5 个 ProjectionWriter 写入。StateManager 主要用于旧版流程（`update-state` CLI），不是主链路。

**当前保护措施：**
- `atomic_write_json(use_lock=True, backup=True)` — 文件级原子写 + 备份
- pending patches 快照 — 崩溃恢复
- ChapterCommitService 链路用 `write_json()`（也是 `atomic_write_json`）+ SQLite 事务

**修复方案：**
- 清理 StateManager 中不再被主链路使用的方法，减少双写复杂度
- 长期：如果要保留 StateManager，其写入应委托给 SSOT `publish_event` + ProjectionWriter 重放

### 5.2 消歧管道 — 实际状态

**代码审查发现：**

`context_manager._build_pack()` line 263-269 将 `disambiguation_warnings` 和 `disambiguation_pending` 直接放入 `alerts` section：

```python
alerts = {
    "disambiguation_warnings": state.get("disambiguation_warnings", [])[-alert_slice:],
    "disambiguation_pending": state.get("disambiguation_pending", [])[-alert_slice:],
}
```

`alert_slice` 默认 0（由 config 决定），这意味着**默认不向后传染**。但如果 `context_alerts_slice > 0`，上一章的消歧遗留会进入下一章上下文。

**修复方案：**
- 在 `context_manager` 中为 `disambiguation_warnings` 添加 confidence 阈值过滤
- 默认 `context_alerts_slice` 应保持 0（当前行为），需要时由用户显式开启
- 确认 `entity_cleanup.py` 的脏实体扫描是否应被定期执行（添加 cron/skill）

---

## P2: Skill × 模块交叉验证

### 新模块引用现状

| 模块 | webnovel-write | webnovel-delete | webnovel-rewrite | webnovel-write-batch | 其他 skill |
|------|:-:|:-:|:-:|:-:|:-:|
| `ssot_enforcer` | - | ✓ (verify) | ✓ (verify) | - | - |
| `workflow_checkpoint` | - | - | - | - | - |
| `override_contract_engine` | - | - | - | - | - |
| `entity_cleanup` | - | - | - | - | - |
| `orchestrate` | - | - | ✓ (write) | - | - |
| `chapter_delete_service` | - | ✓ | ✓ | - | - |

### Agent 指令审查

| Agent | 需要更新 | 内容 |
|-------|---------|------|
| `context-agent.md` | ✓ 已更新 | 包含 override_hints 消费指令 |
| `data-agent.md` | 需确认 | 是否有 SSOT 事件发布指令？当前无 |
| `reviewer.md` | 需更新 | 应知晓 workflow checkpoint（审查完成=REVIEWING checkpoint） |
| `chapter-writer-agent.md` | 无需 | — |
| `deconstruction-agent.md` | 无需 | — |

### 修复清单

1. `webnovel-write` 各 Step 添加 workflow checkpoint（见 P1 修复）
2. `webnovel-write` Step 5.5 写后校验添加 `ssot verify`
3. `webnovel-query` 添加 `override context` 展示当前有效规则
4. `reviewer.md` agent 添加 REVIEWING checkpoint 指令
5. 新建 `webnovel-heal` skill（流程：`entity-clean --mark-invalid` → `orchestrate heal` → `ssot verify`）
6. `data-agent.md` 明确说明提取的 accepted_events 会被 SSOT event log 记录（建立心智模型）

---

## 执行优先级总结

| 优先级 | 项目 | 工作量 | 风险 | 备注 |
|--------|------|--------|------|------|
| **P0** | 统一事件系统 (合并 EventLogStore + SSOT) | ~4h | 中 | 核心架构修复 |
| **P0** | publish_event 调用链补全 (apply_projections 内部调用) | ~1h | 低 | 关键集成点 |
| **P1** | Override 系统统一 (SQLite 迁移) | ~2h | 中 | 消除数据孤岛 |
| **P1** | Workflow checkpoint 集成到 skill | ~1h | 低 | 4 个 skill 添加 bash 命令 |
| **P2** | 大纲履约细化校验 (CBN/CPN 分类) | ~1h | 低 | 增强校验粒度 |
| **P2** | Skill × Agent 交叉验证补充 | ~1h | 低 | 6 项修改 |
| **P2** | 消歧 confidence 阈值过滤 | ~0.5h | 低 | context_manager 微调 |
| **P3** | 死配置清理 (context_compact_text_enabled 等) | ~0.5h | 低 | 代码卫生 |
| **P3** | StateManager 双写简化（委托给 SSOT） | ~2h | 中 | 长期优化 |

**总估计工作量：~13h**（含 P3）
