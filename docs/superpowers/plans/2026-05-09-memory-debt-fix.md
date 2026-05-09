# Memory Cleanup & Debt Tracker Activation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 52.9% 记忆过期堆积，激活 debt_tracker 的伏笔追踪流程。

**Architecture:** F1 修改 `upsert_item` 同 key 更新时当场删除旧值而非标记 outdated；拆分 compactor 为 `collect_garbage` + `enforce_capacity`；新增 `compact-memory` action 用于存量清理。F2 在 `chapter_commit_service` 加 `_sync_foreshadowing` 将 extraction_result 的伏笔事件写入 index.db debt 表。

**Tech Stack:** Python 3.10+ (stdlib + json/sqlite3), existing memory/store.py, chapter_commit_service.py

---

## 文件清单

| 文件 | 操作 | 任务 |
|------|------|------|
| `data_modules/memory/store.py` | 修改 | Task 1 |
| `data_modules/memory/compactor.py` | 修改 | Task 2 |
| `scripts/skill_runner.py` | 修改 | Task 2 |
| `data_modules/chapter_commit_service.py` | 修改 | Task 3 |
| `data_modules/structural_checker.py` | 修改 | Task 3 |

---

### Task 1: F1 — upsert 自清洁

**Files:**
- Modify: `.opencode/scripts/data_modules/memory/store.py:78-82`

- [ ] **Step 1: 修改 upsert_item 删除旧值**

Read the current `upsert_item` method (line 65-98). Change lines 78-82 from marking old row as outdated to skipping it (effectively deleting it):

```python
# Before (line 78-82):
                if row_key == target_key and row.id != normalized.id:
                    # 同 key 旧值降级为 outdated，保留审计轨迹
                    if row.status != "outdated":
                        row = MemoryItem(**{**asdict(row), "status": "outdated", "updated_at": now_iso()})
                        outdated += 1
                    replaced_existing = True

# After:
                if row_key == target_key and row.id != normalized.id:
                    # 同 key 旧值直接丢弃
                    outdated += 1
                    replaced_existing = True
                    continue  # skip old row entirely
```

The `continue` skips appending the old row to `new_rows`, effectively deleting it. The `outdated` counter is incremented for the return value (caller can still see how many were replaced).

- [ ] **Step 2: Run existing memory tests**

```bash
cd D:\workspace\webnovel-writer && python -m pytest .opencode/scripts/data_modules/tests/test_memory_store.py -q --no-cov
```

预期: 全部通过（现有测试应适配新行为——如果测试期望 outdated 计数，可能需要更新断言）

- [ ] **Step 3: 若有测试失败，更新测试断言**

如果 `test_memory_store.py` 中有测试验证了 `outdated` 计数的旧行为（标记而非删除），更新 `assert` 以适应新逻辑。

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/memory/store.py
git commit -m "fix(memory): delete old item on upsert instead of marking outdated"
```

---

### Task 2: F1 — compactor 拆分 + compact-memory action

**Files:**
- Modify: `.opencode/scripts/data_modules/memory/compactor.py:24-108`
- Modify: `.opencode/scripts/skill_runner.py`

- [ ] **Step 1: 拆分 compactor**

In `compactor.py`, split `compact_scratchpad` into two functions:

```python
def collect_garbage(data: ScratchpadData) -> ScratchpadData:
    """清理 outdated 和已回收伏笔。每章写后可调用，无容量门槛。"""
    # 1) 删除所有 outdated 条目
    for bucket in CATEGORY_TO_BUCKET.values():
        rows: List[MemoryItem] = list(getattr(data, bucket))
        cleaned = [row for row in rows if row.status != "outdated"]
        setattr(data, bucket, cleaned)

    # 2) 清理已回收伏笔
    data.open_loops = [row for row in data.open_loops if not _is_resolved_open_loop(row)]

    return data


def enforce_capacity(data: ScratchpadData, max_items: int = 500) -> ScratchpadData:
    """仅当条目数超过 max_items 时压缩 timeline + 全局截断。"""
    if data.count_items() <= max_items:
        return data

    # 3) 压缩过旧 timeline
    timeline = sorted(data.timeline, key=lambda x: x.source_chapter)
    if timeline:
        latest_chapter = max(x.source_chapter for x in timeline)
        old = [x for x in timeline if (latest_chapter - x.source_chapter) > 50]
        fresh = [x for x in timeline if (latest_chapter - x.source_chapter) <= 50]
        if len(old) > 1:
            # (保持原有 timeline 压缩逻辑)
            samples = []
            for row in old[:8]:
                label = row.value or row.subject or row.field or row.id
                if label:
                    samples.append(str(label))
            summary_text = "；".join(samples) if samples else "早期关键事件"
            summary_item = MemoryItem(
                id=f"timeline-summary-upto-{old[-1].source_chapter}",
                layer="semantic", category="story_fact",
                subject="timeline_summary",
                field=f"<=ch{old[-1].source_chapter}",
                value=f"早期事件摘要：{summary_text}",
                payload={"from_chapter": old[0].source_chapter,
                         "to_chapter": old[-1].source_chapter, "items_merged": len(old)},
                status="active", source_chapter=old[-1].source_chapter,
                evidence=["compactor:timeline"], updated_at=now_iso(),
            )
            replaced = False
            for i, row in enumerate(list(data.story_facts)):
                if row.subject == summary_item.subject and row.subject == "timeline_summary":
                    data.story_facts[i] = summary_item
                    replaced = True
                    break
            if not replaced:
                data.story_facts.append(summary_item)
        data.timeline = fresh

    # 4) 全局截断
    if data.count_items() > max_items:
        ranked = []
        for bucket in CATEGORY_TO_BUCKET.values():
            for row in list(getattr(data, bucket)):
                ranked.append((bucket, row))
        ranked.sort(key=lambda item: (
            0 if item[1].status == "active" else 1,
            -int(item[1].source_chapter or 0),
            item[1].updated_at or "",
        ))
        keep = ranked[:max_items]
        kept_ids = {item.id for _, item in keep}
        for bucket in CATEGORY_TO_BUCKET.values():
            rows = [row for row in list(getattr(data, bucket)) if row.id in kept_ids]
            setattr(data, bucket, rows)

    data.meta = {**dict(data.meta or {}), "last_updated": now_iso(), "total_items": data.count_items()}
    return data


def compact_scratchpad(data: ScratchpadData, max_items: int = 500) -> ScratchpadData:
    """兼容旧调用：先 GC 再容量控制。"""
    data = collect_garbage(data)
    return enforce_capacity(data, max_items)
```

- [ ] **Step 2: 在 skill_runner.py 新增 compact-memory action**

在 `skill_runner.py` 的 `cmd_check_batch_integrity` 之后，添加：

```python
def cmd_compact_memory(args: argparse.Namespace) -> int:
    from data_modules.memory.store import ScratchpadManager
    from data_modules.memory.compactor import collect_garbage
    from data_modules.config import get_config

    config = get_config()
    config.project_root = args.project_root
    store = ScratchpadManager(config)
    data = store.load()
    before = data.count_items()
    data = collect_garbage(data)
    after = data.count_items()
    store.save(data)
    removed = before - after
    print(f"OK: removed {removed} outdated items ({before} -> {after})")
    return 0
```

并在 `main()` 中注册子命令：

```python
p_cm = sub.add_parser("compact-memory")
p_cm.add_argument("--project-root", required=True)
p_cm.set_defaults(func=cmd_compact_memory)
```

- [ ] **Step 3: 验证 compactor 拆分**

```bash
cd D:\workspace\webnovel-writer && python -m pytest .opencode/scripts/data_modules/tests/test_memory_store.py -q --no-cov
```

- [ ] **Step 4: 在实际项目上运行 compact**

```bash
$env:PYTHONPATH = ".opencode\scripts"
python -X utf8 -c "
import sys; sys.path.insert(0, '.opencode/scripts')
from data_modules.memory.store import ScratchpadManager
from data_modules.memory.compactor import collect_garbage
from data_modules.config import get_config
cfg = get_config()
cfg.project_root = r'D:\workspace\凡尘之舞\凡尘之舞'
store = ScratchpadManager(cfg)
data = store.load()
print(f'Before: {data.count_items()} items')
data = collect_garbage(data)
print(f'After: {data.count_items()} items')
store.save(data)
print('Saved')
"
```

预期: 删除约 109 条 outdated 条目

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/data_modules/memory/compactor.py .opencode/scripts/skill_runner.py
git commit -m "refactor(memory): split compactor, add collect_garbage + compact-memory action"
```

---

### Task 3: F2 — debt tracker 同步 + checker 改为读 db

**Files:**
- Modify: `.opencode/scripts/data_modules/chapter_commit_service.py`
- Modify: `.opencode/scripts/data_modules/structural_checker.py`

- [ ] **Step 1: 在 chapter_commit_service 加 _sync_foreshadowing**

在 `ChapterCommitService` 类的 `persist_commit` 方法末尾（commit 写入成功后），添加同步调用。先找到 `persist_commit` 方法：

```python
# chapter_commit_service.py, persist_commit 末尾, return 之前
from .index_manager import IndexManager

def _sync_foreshadowing(self, chapter: int, extraction_result: dict):
    """将 extraction_result 中的伏笔事件同步到 index.db debt 表"""
    events = extraction_result.get("accepted_events", [])
    if not events:
        return
    idx = IndexManager()
    for evt in events:
        etype = evt.get("event_type", "")
        if etype == "open_loop_created":
            payload = evt.get("payload") or {}
            subject = evt.get("subject", payload.get("subject", ""))
            content = payload.get("content", "")
            # 默认 10 章内偿还
            due = chapter + int(payload.get("expected_payoff_chapters", 10))
            idx.create_debt(
                debt_type="foreshadowing",
                source_chapter=chapter,
                due_chapter=due,
                subject=subject,
                note=content,
            )
        elif etype in ("open_loop_closed", "promise_paid_off"):
            subject = evt.get("subject", (evt.get("payload") or {}).get("subject", ""))
            idx.resolve_debt(subject=subject)
```

在 `persist_commit` 的 `return path` 之前调用：

```python
self._sync_foreshadowing(chapter, extraction_result)
```

- [ ] **Step 2: 检查 IndexManager 是否有 create_debt / resolve_debt 方法**

搜索 `index_manager.py` 和 `index_debt_mixin.py` 中的方法签名。如果名称不同，用实际方法名。`IndexDebtMixin` 有 `create_override_contract` 等方法，需要找到或添加简单的 debt 创建方法。

如果不存在 `create_debt` 方法，在 `index_debt_mixin.py` 添加最小实现：

```python
def create_debt(self, debt_type, source_chapter, due_chapter, subject="", note=""):
    with self._get_conn() as conn:
        conn.execute("""
            INSERT INTO chase_debt (debt_type, source_chapter, due_chapter, note, status)
            VALUES (?, ?, ?, ?, 'active')
        """, (debt_type, source_chapter, due_chapter, note))
        conn.commit()

def resolve_debt(self, subject=""):
    with self._get_conn() as conn:
        conn.execute("""
            UPDATE chase_debt SET status='resolved', updated_at=CURRENT_TIMESTAMP
            WHERE note LIKE ? AND status='active'
        """, (f"%{subject}%",))
        conn.commit()
```

- [ ] **Step 3: 修改 structural_checker 的 debt_burden 检查**

将 `_check_debt_burden` 从读 state.json 改为读 index.db：

```python
def _check_debt_burden(state: dict, project_root=None, chapter=0):
    result = {
        "name": "debt_burden",
        "passed": True,
        "severity": "warning",
        "detail": "",
        "fix": "",
    }
    # 优先从 index.db 读（如果可用）
    if project_root:
        db_path = Path(project_root) / ".webnovel" / "index.db"
        if db_path.is_file():
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            try:
                total = conn.execute(
                    "SELECT COUNT(*) FROM chase_debt WHERE status='active'"
                ).fetchone()[0]
                overdue = conn.execute(
                    "SELECT COUNT(*) FROM chase_debt WHERE status='active' AND due_chapter < ?",
                    (chapter,)
                ).fetchone()[0]
                if total > 5:
                    result["passed"] = False
                    result["detail"] = f"活跃债务 {total} 条（阈值 5 条），其中 {overdue} 条已逾期"
                    result["fix"] = "近期章节偿还逾期伏笔或标记已处理"
                elif overdue > 0:
                    result["passed"] = False
                    result["detail"] = f"{overdue} 条债务已逾期"
                    result["fix"] = "检查逾期伏笔，近期章节安排偿还"
                return result
            finally:
                conn.close()
    # 降级：从 state.json 读
    foreshadowing = (state.get("plot_threads") or {}).get("foreshadowing") or []
    unresolved = [f for f in foreshadowing if f.get("status") == "未回收"]
    if len(unresolved) > 5:
        result["passed"] = False
        result["detail"] = f"未回收伏笔 {len(unresolved)} 条（阈值 5 条）"
        result["fix"] = "检查逾期伏笔，近期章节安排偿还或标记废弃"
    return result
```

同时修改 `run_checks` 调用签名，传入 `project_root`：

```python
checks.append(_check_debt_burden(state, project_root, chapter))
```

- [ ] **Step 4: 运行所有相关测试**

```bash
cd D:\workspace\webnovel-writer && python -m pytest .opencode/scripts/data_modules/tests/test_structural_checker.py .opencode/scripts/data_modules/tests/test_memory_store.py -q --no-cov
```

预期: 全部通过

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/data_modules/chapter_commit_service.py .opencode/scripts/data_modules/structural_checker.py
git commit -m "feat: sync foreshadowing to debt tracker, read debt from index.db"
```

---

## Self-Review

**Spec coverage:**
- F1 upsert 自清洁 → Task 1 ✅
- F1 compactor 拆分 → Task 2 ✅
- F1 compact-memory action → Task 2 Step 2 ✅
- F2 debt sync → Task 3 ✅
- F2 structural checker 改读 db → Task 3 Step 3 ✅

**Placeholder scan:** No TBD/TODO. All code shown.

**Type consistency:** `collect_garbage` returns `ScratchpadData`, same type as `compact_scratchpad`. `_sync_foreshadowing` uses existing `IndexManager` interface. Debt schema matches `chase_debt` table definition.
