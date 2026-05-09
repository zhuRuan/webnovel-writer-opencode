# Memory Cleanup & Debt Tracker Activation Spec

## Context

凡尘之舞自检诊断：memory 52.9% 过期（109/206 条目为 outdated）、debt_tracker 完全空转（0 条债务记录、0 条债务事件）。

## F1: Memory — 写入自清洁

### 根因

`memory/writer.py` 更新同 key 条目时，旧版本被标记 `outdated` 而非删除。outdated 条目永不消失。

### 方案

**修改 `memory/store.py` 的 `upsert_item` 方法**：第 78-82 行现有逻辑是将旧值标记为 `outdated`（注释写"保留审计轨迹"）。改为直接从列表删除旧行。

```python
# memory/store.py — upsert_item 第 78-82 行，改前：
if row_key == target_key and row.id != normalized.id:
    # 同 key 旧值降级为 outdated，保留审计轨迹
    if row.status != "outdated":
        row = MemoryItem(**{...asdict(row), "status": "outdated", ...})
        outdated += 1

# 改后：
if row_key == target_key and row.id != normalized.id:
    continue  # 直接丢弃旧值，不保留 outdated
    outdated += 1
```

**同时修复 `compact_scratchpad`**：拆成两个函数：

```python
def collect_garbage(data):      # 每章写后：去重 outdated + 清理已回收伏笔
def enforce_capacity(data, n):  # 仅超阈值：压缩 timeline + 截断
```

在 `skill_runner.py` 新增 `compact-memory` action，供写后校验调用。

### 改动范围

| 文件 | 操作 |
|------|------|
| `data_modules/memory/writer.py` | 修改 upsert 方法，~8 行 |
| `data_modules/memory/compactor.py` | 拆分 collect_garbage / enforce_capacity |
| `scripts/skill_runner.py` | 新增 compact-memory action，~15 行 |

---

## F2: Debt Tracker — 激活完整流程

### 根因

debt_tracker 的 SQLite 表和方法齐全，但无人写入数据。state.json 的 `plot_threads.foreshadowing` 从未被导入 SQLite。

### 方案

**在 `chapter_commit_service.py` 的 commit 流程末尾**，新增 `_sync_debt_events`：

```python
def _sync_debt_events(project_root, chapter, extraction_result):
    events = extraction_result.get("accepted_events", [])
    for evt in events:
        if evt["event_type"] == "open_loop_created":
            index_db.create_debt_event(
                chapter=chapter,
                event_type="loop_created",
                subject=evt["subject"],
                payload=evt["payload"],
                due_chapter=chapter + 10,  # 默认 10 章内偿还
            )
        elif evt["event_type"] == "open_loop_closed":
            index_db.resolve_debt(subject=evt["subject"])
```

**structural_checker 改为从 index.db 读取**（替代 state.json 计数）：

```python
def _check_debt_burden(project_root, chapter):
    db = sqlite3.connect(str(index_db_path))
    # 查询逾期的未偿还债务
    overdue = db.execute(
        "SELECT COUNT(*) FROM chase_debt WHERE status='active' AND due_chapter < ?",
        (chapter,)
    ).fetchone()[0]
    # ...
```

### 改动范围

| 文件 | 操作 |
|------|------|
| `data_modules/chapter_commit_service.py` | 新增 _sync_debt_events，~20 行 |
| `data_modules/structural_checker.py` | _check_debt_burden 改为读 index.db，~10 行 |

---

## 测试

- `test_memory_upsert_deletes_old` — 写入同 key 新条目后旧条目消失
- `test_debt_sync_from_events` — open_loop_created 事件正确写入 debt 表
- `test_structural_debt_from_db` — 读 debt 表计算逾期数
- Manual: 运行 compact-memory 后 memory_bloat 降至 <10%

## 不改变

- memory store schema
- index.db debt 表 schema（已有）
- data-agent 产出格式
- skill 步骤流程
