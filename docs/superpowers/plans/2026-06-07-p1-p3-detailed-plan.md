# P1/P3 详细实施计划

> **P1**：artifact_validator.py 和 postcommit.py 增强 + 新增测试
> **P3**：Skill/Agent 瘦身（保留特有内容）

---

## P1：增强验证

### P1.1：artifact_validator.py 增强

**可直接同步（纯增量，不影响现有功能）：**

| 改动 | 说明 | 行数 |
|------|------|------|
| `SCHEMA_VERSION` 常量 | `"webnovel-artifact-validator/v1"` | 1 |
| `ERROR_*` 错误码常量 | 7 个集中定义的错误码 | 7 |
| `REQUIRED_PROJECTION_WRITERS` | `("state", "index", "summary", "memory", "vector")` | 1 |
| `OK_PROJECTION_STATUSES` | `{"done", "skipped"}` | 1 |
| `_empty_report()` helper | 标准化空报告骨架 | 10 |
| `_read_json_artifact()` helper | 统一 JSON 读取函数 | 25 |
| `_schema_error_message()` helper | Pydantic 错误格式化 | 5 |
| `merge_reports()` helper | 报告合并函数 | 15 |
| 4 个便捷验证函数 | `validate_review_result` 等 | 20 |

**需谨慎同步（涉及语义差异）：**

| 改动 | 差异 | 建议 |
|------|------|------|
| `_issue()` 签名 | 原版有 `path`/`field`/`impact`/`repair` 字段 | 扩展签名，添加可选参数 |
| `validate_artifact_payload()` ok 判定 | 原版只有 blocker 才算失败 | 保持我们的逻辑（任何 error 都算失败） |
| `_policy_issues()` fulfillment 检查 | 原版检查所有 missed_nodes | 保持我们的逻辑（只检查 CBN） |

**不建议同步：**

| 改动 | 原因 |
|------|------|
| `validate_commit_artifact_files()` 签名 | 我们的 CLI 友好签名更好 |
| `validate_chapter_commit()` 签名 | 保留我们的 `(project_root, chapter)` 签名 |
| review_result blocking 检查 | 我们遍历 issues 列表更可靠 |
| `ARTIFACT_FILES` 和 `main()` | 我们独有 |

**执行步骤：**
1. 添加常量（SCHEMA_VERSION, ERROR_*, REQUIRED_PROJECTION_WRITERS, OK_PROJECTION_STATUSES）
2. 添加 helper 函数（_empty_report, _read_json_artifact, _schema_error_message, merge_reports）
3. 添加 4 个便捷验证函数
4. 扩展 `_issue()` 签名（添加可选 path/field/impact/repair 参数）
5. 增强 `validate_chapter_commit()` 的投影检查（missing/pending/invalid）

### P1.2：postcommit.py 增强

**前置依赖：**

| 依赖模块 | 行数 | 说明 |
|----------|------|------|
| `projection_log.py` | 151 | 投影运行日志（JSONL） |
| `project_phase.py` | 398 | 项目阶段感知 |

**建议分步同步：**

1. 先同步 `projection_log.py`（独立模块，无外部依赖）
2. 再同步 `project_phase.py`（依赖 projection_log）
3. 最后增强 `postcommit.py`

**postcommit.py 增强内容：**

| 改动 | 说明 |
|------|------|
| 投影状态 missing 检查 | 检查 5 个 writer 是否全部有状态 |
| 投影状态 pending 检查 | 检查是否有 pending 状态 |
| 投影状态 invalid 检查 | 只接受 done/skipped |
| projection_log 优先读取 | 优先从 JSONL 日志读取投影状态 |
| scratchpad 存在性检查 | warning 级别 |

**不建议同步：**

| 改动 | 原因 |
|------|------|
| `gate_report` 签名变更 | 影响所有 gate 文件和测试 |
| `issue` 签名变更 | 影响所有 gate 文件和测试 |
| commit status 只接受 accepted | 我们接受 rejected 也是合法终态 |

### P1.3：新增测试

**缺失测试清单（35 个）：**

| 文件 | 缺失数 | 关键测试 |
|------|--------|----------|
| `test_commit_artifacts.py` | 2 | **整个文件缺失** — 嵌套格式优先读取 + legacy 向后兼容 |
| `test_artifact_validator.py` | 8 | schema 验证、policy blocker、projection 完整性 |
| `test_write_gates.py` | 12 | 三阶段 gate 集成场景 |
| `test_chapter_commit_service.py` | 9 | malformed 输入拒绝、事件归一化、rejected projection |
| `test_projection_writers.py` | 4 | **幂等性/replay 测试** |

**优先级：**

1. **P1.3a**：创建 `test_commit_artifacts.py`（2 个测试）— 验证嵌套格式优先 + legacy 兼容
2. **P1.3b**：添加幂等性测试（4 个）— 验证 5 个 writer 的 replay 不产生重复数据
3. **P1.3c**：添加 malformed 输入拒绝测试（9 个）— 验证 chapter_commit_service 对异常输入的拒绝
4. **P1.3d**：增强 test_artifact_validator.py（8 个）— schema 验证、projection 完整性
5. **P1.3e**：增强 test_write_gates.py（12 个）— 三阶段 gate 集成

---

## P3：Skill/Agent 瘦身

### P3.1：Agent 文件瘦身

| 文件 | 当前 | 目标 | 可减 | 主要手段 |
|------|------|------|------|----------|
| `deconstruction-agent.md` | 298 | ~188 | 110 | JSON schema 从逐行改为单行格式 |
| `reviewer.md` | 239 | ~200 | 39 | 内联 bash/python 脚本移到参考文件 |
| `context-agent.md` | 220 | ~176 | 44 | 输出示例移到参考文件 |
| `data-agent.md` | 142 | ~137 | 5 | 身份段压缩 |
| `chapter-writer-agent.md` | 168 | ~156 | 12 | 验证脚本压缩、校验清单去重 |
| `observer-agent.md` | 77 | 77 | 0 | 无变化 |
| **合计** | **1144** | **~934** | **~210** | |

**不可精简的核心功能：**
- SSOT 事件溯源集成
- Observer-Settler 管道
- 情节线追踪 strand_tracker
- override 世界规则覆盖
- 第 6 审查维度"项目规则"
- workflow checkpoint
- 合同树验证 + Anti-AI 终检

### P3.2：Skill 文件瘦身

| 文件 | 当前 | 目标 | 可减 | 主要手段 |
|------|------|------|------|----------|
| `webnovel-write/SKILL.md` | 480 | ~380 | 100 | Step 0/结构自检/evidence 自查提取为独立脚本 |
| `webnovel-plan/SKILL.md` | 409 | ~330 | 80 | 结构化节点规范外移到 chapter-planning.md |
| `webnovel-init/SKILL.md` | 452 | ~350 | 100 | 内部数据模型外移到 init-collection-schema.md |
| `webnovel-review/SKILL.md` | 176 | ~150 | 25 | 常见误区/优先级/决策树用"红线"替代 |
| `webnovel-query/SKILL.md` | 113 | ~108 | 5 | 采用原版"最窄工具"策略 |
| `webnovel-learn/SKILL.md` | 82 | ~67 | 15 | 删除输入输出示例和独立去重段 |
| `webnovel-dashboard/SKILL.md` | 163 | ~108 | 55 | 功能概览和 API 文档移到 reference |
| `webnovel-doctor/SKILL.md` | 65 | ~53 | 12 | 删除诊断类别表和修复命令 |
| **合计** | **1940** | **~1549** | **~392** | |

**不可精简的核心功能：**
- Observer→Settler 两阶段提取（webnovel-write）
- 修复-重审循环 + evidence 子串匹配（webnovel-write）
- 自定义文风提示词（webnovel-write）
- 结构自检（webnovel-write）
- 第 6 维度项目规则（webnovel-review）
- 内部数据模型（webnovel-init，移到 reference 后仍可用）

### P3.3：新建参考文件

| 文件 | 内容来源 | 行数 |
|------|----------|------|
| `references/init-collection-schema.md` | webnovel-init 内部数据模型 JSON | ~50 |
| `references/context-agent-example.md` | context-agent 输出示例 | ~38 |
| `references/reviewer-checks.md` | reviewer 内联 bash/python 脚本 | ~36 |
| `references/dashboard-api.md` | dashboard SKILL.md API 文档 | ~50 |

---

## 执行顺序

```
P1.1: artifact_validator.py 增强          → 验证：现有测试通过
P1.2a: 同步 projection_log.py            → 验证：import 成功
P1.2b: 同步 project_phase.py             → 验证：import 成功
P1.2c: 增强 postcommit.py                → 验证：现有测试通过
P1.3a: 创建 test_commit_artifacts.py     → 验证：新测试通过
P1.3b: 添加幂等性测试                    → 验证：新测试通过
P1.3c: 添加 malformed 输入拒绝测试       → 验证：新测试通过
P3.1a: deconstruction-agent.md 瘦身      → 验证：内容无丢失
P3.1b: reviewer.md 瘦身                  → 验证：内容无丢失
P3.1c: context-agent.md 瘦身             → 验证：内容无丢失
P3.2a: webnovel-init 瘦身                → 验证：内容无丢失
P3.2b: webnovel-dashboard 瘦身           → 验证：内容无丢失
P3.2c: webnovel-write 瘦身               → 验证：内容无丢失
```

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| projection_log.py 依赖不存在 | import 失败 | 先检查依赖模块是否存在 |
| project_phase.py 依赖 chapter_outline_loader | import 失败 | 已有此模块 |
| artifact_validator _issue() 签名变更 | 破坏现有调用 | 使用可选参数，保持向后兼容 |
| Skill 瘦身丢失功能 | 文档与实际流程不一致 | 逐文件对比，保留所有独有内容 |
| 测试覆盖不足 | 回归未被发现 | 先运行现有测试确认基线 |
