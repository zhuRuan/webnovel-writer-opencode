# 原项目同步计划 — 2026-06-07

> **来源**：原项目 `22750a5` 以来的 28 个提交
> **目标**：同步有价值的改动，保留本项目特有功能

---

## 一、变更分类

### P0：结构性改进（必须同步）

| 改动 | 文件 | 说明 |
|------|------|------|
| 新增 `commit_artifacts.py` | `data_modules/` | 统一 extraction 数据访问，向后兼容新旧格式 |
| `chapter_commit_service.py` | `data_modules/` | extraction 数据从顶层移入 `extraction_result` 嵌套结构 |
| 5 个 projection writer | `data_modules/` | 使用 `commit_artifacts` 辅助函数替代直接 `.get()` |
| `event_projection_router.py` | `data_modules/` | 同上 |

### P1：增强验证（建议同步）

| 改动 | 文件 | 说明 |
|------|------|------|
| `artifact_validator.py` 增强 | `data_modules/` | 新增常量、结构化错误、便捷函数、嵌套验证 |
| `write_gates/postcommit.py` 增强 | `data_modules/` | 新增 projection_log 优先读取、pending/invalid 检查 |
| 新增测试 | `tests/` | `test_artifact_validator.py`、`test_commit_artifacts.py`、`test_write_gates.py` 增强 |

### P2：Bug 修复（必须同步）

| 改动 | 文件 | 说明 |
|------|------|------|
| `get-recent-state-changes` → `get-state-changes` | `reviewer.md` | CLI 子命令名修正（2 处） |

### P3：Skill 瘦身（需评估）

| 改动 | 文件 | 说明 |
|------|------|------|
| `webnovel-write/SKILL.md` | `skills/` | 480→238 行，details 移到 reference |
| `webnovel-plan/SKILL.md` | `skills/` | 409→233 行，节点规范外移 |
| `webnovel-init/SKILL.md` | `skills/` | 452→228 行，数据模型外移 |
| `context-agent.md` | `agents/` | 220→90 行 |
| `reviewer.md` | `agents/` | 239→131 行 |
| `deconstruction-agent.md` | `agents/` | 298→132 行 |

---

## 二、P0 详细合并计划

### Step 1：新增 `commit_artifacts.py`

**操作**：从原项目复制 `webnovel-writer/scripts/data_modules/commit_artifacts.py` 到 `.opencode/scripts/data_modules/commit_artifacts.py`

**内容**：
- `EXTRACTION_FIELDS` 常量（8 个字段名）
- `extraction_result_from_commit(commit_payload)` — 优先读 `extraction_result` 嵌套，fallback 到顶层（向后兼容）
- `extraction_list(commit_payload, field)` — 获取列表字段
- `extraction_dict(commit_payload, field)` — 获取字典字段
- `extraction_text(commit_payload, field)` — 获取文本字段

**风险**：无，纯新增模块

### Step 2：修改 `chapter_commit_service.py` 的 `build_commit()`

**当前**（本项目，第 101-108 行）：
```python
"accepted_events": extraction_result.get("accepted_events", []),
"state_deltas": extraction_result.get("state_deltas", []),
"entity_deltas": extraction_result.get("entity_deltas", []),
"entities_appeared": extraction_result.get("entities_appeared", []),
"scenes": extraction_result.get("scenes", []),
"chapter_meta": extraction_result.get("chapter_meta", {}),
"dominant_strand": extraction_result.get("dominant_strand", ""),
"summary_text": extraction_result.get("summary_text", ""),
```

**目标**（嵌套结构）：
```python
from .commit_artifacts import extraction_list
...
extraction_payload = dict(extraction_result)
extraction_payload["accepted_events"] = accepted_events
...
"extraction_result": extraction_payload,
```

**保留**：本项目的 `blocking_count` 归一化、`missed_nodes` CBN/CPN/CEN 分类、`contract_refs` 路径前缀、`__init__` 校验

### Step 3：修改 `apply_projections()`

**当前**（本项目，第 170 行）：
```python
for event in payload.get("accepted_events", []):
```

**目标**：
```python
from .commit_artifacts import extraction_list
...
accepted_events = extraction_list(payload, "accepted_events")
extraction = payload.setdefault("extraction_result", {})
if not isinstance(extraction, dict):
    extraction = {}
    payload["extraction_result"] = extraction
extraction["accepted_events"] = event_store.normalize_events(chapter, accepted_events)
```

**保留**：本项目的 SSOT `publish_event`、`_sync_foreshadowing`、markdown projection 渲染

### Step 4：修改 5 个 projection writer + router

对每个文件，将 `commit_payload.get("xxx")` 替换为 `extraction_xxx(commit_payload, "xxx")`：

| 文件 | 修改行 | 替换 |
|------|--------|------|
| `index_projection_writer.py` | 多处 | `.get()` → `extraction_list()`/`extraction_dict()`/`extraction_text()` |
| `state_projection_writer.py` | 多处 | 同上 |
| `summary_projection_writer.py` | 1 处 | `.get("summary_text")` → `extraction_text(payload, "summary_text")` |
| `vector_projection_writer.py` | 多处 | 同上 |
| `event_projection_router.py` | 多处 | 同上 |

**注意**：每个文件需添加 `from .commit_artifacts import ...` 导入

---

## 三、P1 详细合并计划

### Step 5：增强 `artifact_validator.py`

从原项目同步以下内容：
- `SCHEMA_VERSION` 和 7 个 `ERROR_*` 常量
- `REQUIRED_PROJECTION_WRITERS` 和 `OK_PROJECTION_STATUSES` 常量
- `_empty_report()` 标准化报告模板
- `_read_json_artifact()` 统一读取函数
- `_schema_error_message()` Pydantic 错误格式化
- 4 个便捷验证函数
- `merge_reports()` 报告合并函数
- `validate_chapter_commit()` 中的嵌套 artifact 验证

**保留**：本项目的 `main()` CLI 入口

### Step 6：增强 `write_gates/postcommit.py`

从原项目同步以下内容：
- `_projection_status_from_runtime()` — projection_log 优先读取
- `resolve_project_phase()` — 项目阶段快照
- pending/invalid 投影状态检查
- scratchpad 文件存在性检查

**保留**：本项目的 `_check_commit_file()` 和 `_check_projections()` 逻辑（如有差异）

### Step 7：新增/增强测试

- 复制 `test_artifact_validator.py`（如果本项目没有）
- 复制 `test_commit_artifacts.py`（如果本项目没有）
- 增强 `test_write_gates.py`（添加 negative schema coverage）

---

## 四、P2 详细合并计划

### Step 8：修复 `reviewer.md` 命令名

**文件**：`.opencode/agents/reviewer.md`

**修改 2 处**：
- 第 52 行：`get-recent-state-changes` → `get-state-changes`
- 第 82 行：`get-recent-state-changes` → `get-state-changes`

---

## 五、P3 评估（暂不同步）

Skill/Agent 瘦身需要逐文件对比，保留本项目特有内容。建议在 P0-P2 完成后单独处理。

**不适用的精简**：
- `reviewer.md` 第 6 维度（项目规则）— 本项目特有功能
- `data-agent.md` observer 架构说明 — 本项目特有架构
- `webnovel-write/SKILL.md` observer/settler 管道 — 本项目特有流程
- `webnovel-init/SKILL.md` 内部数据模型 — 本项目特有

**可考虑的精简**：
- `webnovel-plan/SKILL.md` Step 7 结构化节点规范（~40 行）→ 移到 `chapter-planning.md`
- `webnovel-write/SKILL.md` Step 3 evidence 自查 Python 脚本（~40 行）→ 移到 reference

---

## 六、执行顺序

```
Step 1: 新增 commit_artifacts.py           → 验证：import 成功
Step 2: 修改 build_commit()                → 验证：commit JSON 结构正确
Step 3: 修改 apply_projections()           → 验证：projection 正常运行
Step 4: 修改 5 个 projection writer        → 验证：所有 writer 能读取数据
Step 5: 增强 artifact_validator.py         → 验证：现有测试通过
Step 6: 增强 postcommit.py                 → 验证：现有测试通过
Step 7: 新增/增强测试                      → 验证：新测试通过
Step 8: 修复 reviewer.md                   → 验证：CLI 命令名正确
```

---

## 七、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| extraction 结构变更破坏现有 commit 文件 | 旧 commit 文件无法被新代码读取 | `commit_artifacts.py` 的 `extraction_result_from_commit()` 有向后兼容逻辑 |
| projection writer 改动导致写入失败 | state.json/index.db 数据丢失 | 保留本项目的 SSOT event sourcing 作为兜底 |
| artifact_validator 改动破坏现有测试 | 测试红灯 | 先运行现有测试确认基线，再应用改动 |
| postcommit 改动依赖不存在的模块 | import 失败 | 检查 `projection_log` 模块是否存在，不存在则跳过 |
