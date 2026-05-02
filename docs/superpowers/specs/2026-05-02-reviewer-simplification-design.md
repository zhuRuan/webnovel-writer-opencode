# 审查器精简设计 — 单Agent + Pipeline

**日期**: 2026-05-02
**版本**: v2.6.0

## 目标

将当前多层审查体系（7 LLM Agent + 2 Code Checker + registry/schema/条件触发）精简为原项目同款的单 Agent + Pipeline 模式：
- 1 个 unified-reviewer Agent 覆盖全部维度
- review_pipeline.py 解析输出 → 生成报告 → 落库 metrics
- 完全移除 code checkers、专项 Agent、registry/schema、条件触发

## 动机

当前体系问题：
1. **复杂度失控** — 7+1 Agent、registry.yaml、schema.yaml、condition_evaluator、checkers_manager 层层嵌套
2. **Token 浪费** — 多 Agent 多次调用 LLM，每个都要传完整章节文本
3. **维护成本高** — 新增审查维度需同时更新 registry → schema → agent prompt → checkers_manager
4. **偏离原意** — 我们是评分器（打分 + pass/fail），原项目是问题查找器（只找问题不评分），后者更适合写作流程

## 架构对比

### 当前（移除前）
```
webnovel-review SKILL
  → CheckersManager.run_layered_checkers()
    → Code Layer: world_consistency_checker + DebtTracker
    → LLM Layer: 6 专项 Agent + 1 unified (按 registry.yaml 配置)
    → condition_evaluator 决定哪些 Agent 触发
    → checkers_manager 聚合结果
  → review_pipeline.py 解析 → 报告 → 落库
```

### 目标（精简后 = 原项目）
```
webnovel-review SKILL
  → Agent("reviewer") — 单次调用，6维度 + AI flavor
  → review_pipeline.py 解析 → 报告 → anti_patterns → 落库
```

## 移除清单

### 完全移除
```
checkers/                                    # registry.yaml + schema.yaml + templates/
agents/consistency-checker.md               # 专项 Agent x6
agents/continuity-checker.md
agents/ooc-checker.md
agents/reader-pull-checker.md
agents/high-point-checker.md
agents/pacing-checker.md
scripts/data_modules/checkers_manager.py     # 分层执行引擎
scripts/data_modules/checkers_cli.py         # checkers CLI 命令
scripts/data_modules/condition_evaluator.py  # 条件触发评估
scripts/data_modules/world_consistency_checker.py  # 代码检查器 x3
scripts/data_modules/world_state_tracker.py
scripts/data_modules/debt_tracker.py
scripts/golden_three_checker.py
```

### 移除测试
```
tests/test_checkers_manager.py        # 删除
tests/test_condition_evaluator.py     # 删除
tests/test_world_consistency.py       # 删除（如存在）
tests/test_debt_tracker.py            # 删除（如存在）
```

## 对齐清单

### 1. `agents/unified-reviewer.md` → 重写为原项目 reviewer.md

关键差异：
| 维度 | 当前 | 目标 |
|------|------|------|
| 输出 | overall_score + pass + dimension_scores | issues 清单（无评分） |
| 维度 | 6 维度 + cross_dimension_notes | 6 维度（setting/timeline/continuity/character/logic/ai_flavor/pacing/other） |
| AI flavor | 无详细检查 | 5 子维度（词汇层/句式层/叙事层/情感层/对话层） |
| 工具 | 无 | Read/Grep/Bash（查询角色状态） |
| 思维链 | 无 | ReAct：读取→对比→判断→记录 |

对齐后：只找问题、给证据、给修复方向，不评分、不评价文笔、不建议情节改动。

### 2. `scripts/data_modules/review_schema.py` — 对齐原项目

补充：
- `security_utils` import（`atomic_write_json`）
- `_read_json_if_exists()` 辅助函数
- `_write_json()` 辅助函数
- `append_ai_flavor_anti_patterns()` 函数（提取 AI flavor issues → anti_patterns.json）

不变：`ReviewIssue`、`ReviewResult` dataclass 完全兼容（字段一致）。

### 3. `scripts/review_pipeline.py` — 对齐原项目

补充：
- `_resolve_report_path()` — 路径安全检查
- `_format_issue()` — 问题格式化（Markdown 列表）
- `render_review_report()` — 报告内容生成
- `write_review_report()` — 报告文件写入
- `_build_review_metrics_record()` — 构建 ReviewMetrics 对象
- `build_review_artifacts()` 中调用 `append_ai_flavor_anti_patterns()`
- 返回 payload 中增加 `anti_patterns_added` 字段

### 4. `skills/webnovel-review/SKILL.md` — 对齐原项目

核心变化：
- Step 4：从 `checkers list → Task 遍历调用` 改为 `Agent("reviewer") 单次调用`
- Step 5：补全 `review-pipeline` 标准文件流命令
- Step 6：补全阻断处理 + state.json 兼容投影
- 参数简化：移除 `--full`（全在单 Agent 内）、`--minimal`（无此概念）
- 参考文件引用对齐

### 5. `scripts/data_modules/webnovel.py` — 移除 checkers 命令

- 移除 COMMAND_REGISTRY 中 `checkers` 条目
- 移除 argparse sub-parser 中 `checkers` 子命令块
- 保留 `review-pipeline` 命令（不变）

## 清理引用

### `skills/webnovel-write/SKILL.md`
- 移除 `--minimal` 和 `--legacy-checkers` 参数引用
- 审查步骤简化为：Agent("reviewer") → review-pipeline

### `skills/webnovel-write-batch/SKILL.md`
- 同步更新审查引用

### `llm_invoker.py`
- 检查并移除 checkers 相关代码（如有）

## 不变部分

```
scripts/data_modules/index_manager.py       # review_metrics 存储不变
scripts/data_modules/index_reading_mixin.py # metrics 读写不变
scripts/data_modules/review_schema.py       # 核心 dataclass 不变（只补充）
scripts/review_pipeline.py                  # 核心 pipeline 不变（只补充）
agents/unified-reviewer.md                  # 文件名保留（内容对齐原 reviewer.md）
tests/test_review_schema.py                 # 保留
skills/webnovel-review/references/          # 保留
```

## 风险与回滚

- **风险**：删除 code checkers 后失去确定性战力/物品/债务检查能力
  - 缓解：single reviewer Agent 中已包含设定一致性检查（category: setting），LLM 可覆盖
- **回滚**：所有删除的文件在 git 历史中可恢复，commit 前确保当前测试全绿

## 验收标准

1. 只有 1 个审查 Agent（`agents/unified-reviewer.md`）
2. 不再存在 `checkers/` 目录
3. 不再存在 `checkers_manager.py`、`checkers_cli.py`、`condition_evaluator.py`
4. 不再存在专项 Agent（6 个 .md 文件）
5. 不再存在 code checkers（3 个 .py 文件）
6. `webnovel.py checkers` 命令已移除
7. `webnovel.py review-pipeline` 正常工作（含报告生成 + anti_patterns）
8. `review_schema.py` 含 `append_ai_flavor_anti_patterns`
9. `review_pipeline.py` 含 `render_review_report`/`write_review_report`
10. 全量测试 532+ passed / 0 failed（删除相关测试后线数可能减少）
