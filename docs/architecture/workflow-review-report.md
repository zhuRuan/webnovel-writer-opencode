# 写作工作流审查报告

> **审查日期**：2026-06-08
> **审查范围**：Stage 1-4 + 数据流 + 合同一致性
> **审查方法**：5 个独立审查 agent 并行扫描

---

## 审查汇总

| 阶段 | 严重 | 中等 | 低 |
|------|------|------|-----|
| Stage 1 (Init) | 2 | 3 | 1 |
| Stage 2 (Plan) | 0 | 6 | 4 |
| Stage 3 (Write) | 3 | 9 | 6 |
| Stage 4 (Review) | 0 | 2 | 1 |
| 数据流 | 1 | 3 | 3 |
| **合计** | **6** | **23** | **15** |

---

## 一、Stage 1：项目初始化

### 严重问题

**S1-1：`one_liner` 和 `core_conflict` 未持久化到 state.json**

`init_project.py` 的参数列表中没有 `one_liner` 和 `core_conflict`，SKILL.md 的 bash 命令也不传递这两个字段。结果：这两个关键信息只存在于 AI 上下文中，不持久化到任何文件。

**影响**：plan 阶段读取 state.json 时拿不到这些数据，总纲中的"核心冲突"占位符不会被自动填充。

**修复**：在 `init_project.py` 中添加参数，写入 `state.json` 的 `project_info`。

**S1-2：充分性闸门缺少 `one_liner` 和 `core_conflict` 检查**

Step 2 将它们列为"必收"，但闸门不验证它们的存在。

**修复**：在充分性闸门中增加检查。

### 中等问题

**S1-3：`idea_bank.json` 不由脚本生成** — 依赖 AI 手动写入，无 schema 验证。

**S1-4：总纲 Patch 步骤缺少自动化** — 核心冲突、卷末高潮等关键字段依赖 AI 手动填充。

**S1-5：`反派设计.md` 不在验证检查的成功标准中** — 验证清单遗漏了此文件。

### 低问题

**S1-6：`protagonist_desire` 和 `protagonist_flaw` 只写入设定集模板，不写入 state.json** — 功能无断裂但 state.json 不完整。

---

## 二、Stage 2：大纲规划

### 中等问题

**S2-1：6 个 Plan 输出字段在 loader 中无映射**

`爽点`、`视角/主角`、`本章变化`、`与上章时间差`、`钩子`（泛称）、`本章变化` 在 `chapter_outline_loader.py` 的 `_DIRECTIVE_FIELD_MAP` 中没有对应解析，会被静默丢弃。

**影响**：context-agent 无法通过 `load_chapter_execution_directive` 获取这些数据。

**修复**：在 `_DIRECTIVE_FIELD_MAP` 中补充映射，或在 SKILL.md 中明确说明这些字段仅供人类阅读。

**S2-2：`钩子` 字段歧义**

Plan 要求"钩子"，loader 只识别"钩子类型"和"钩子强度"。如果章纲写 `- 钩子：林天发现幕后黑手`，不会被识别。

**修复**：Plan 字段列表明确区分"钩子类型"和"钩子内容"。

**S2-3：验证清单缺少对钩子类型/强度的校验**

Step 7 要求每章有"钩子"，但 Step 9 不验证。

**S2-4：验证清单缺少对 Strand 字段的校验**

**S2-5：验证清单缺少对关键实体的校验**

**S2-6：writeback JSON 示例缺少 `chapters_range` 字段**

`_normalize_anchor` 要求 `chapters_range` 非空，但 SKILL.md 示例中没有。LLM 严格按示例生成 JSON 时 writeback 会失败。

**修复**：在 SKILL.md Step 9 示例 JSON 中补充 `chapters_range` 字段。

### 低问题

**S2-7：时间线单调递增验证无自动化** — 硬约束依赖 LLM 自检。

**S2-8：倒计时推进正确性验证无自动化**

**S2-9：节点格式 `主体 | 动作/变化 | 对象/结果` 无解析器消费** — 纯靠 LLM 自觉。

**S2-10：`chapter-planning.md` 字数标准（3000字/章）与 Write 默认值（2000-2500字）不一致**

---

## 三、Stage 3：章节写作

### 严重问题

**S3-1：settler 输出的 extraction_result 缺少 state_deltas/scenes/summary_text**

`observer_settler.py` 的 `settle()` 函数返回值中 `state_deltas`、`entity_deltas`、`scenes`、`summary_text`、`dominant_strand` 都是硬编码空值。

**影响**：commit 文件中这些字段始终为空。投影 writer 有兜底逻辑（从 accepted_events 二次提取），但 commit 文件不自描述。

**修复**：在 settle() 中从 accepted_events 预提取这些字段，或明确 data-agent 负责补全。

**S3-2：observer heading 匹配脆弱**

settler 的 `_parse_markdown_sections()` 用 `## ` 前缀做 section 切分，精确匹配 heading 名称。observer-agent 是 LLM 驱动的，可能输出"## 角色状态"（少了"变化"）或"## 2. 角色状态变化"（带序号）。

**影响**：settler 会漏掉整个 section，extraction 数据不完整。

**修复**：settler 增加容错匹配（strip 序号前缀、模糊匹配）。

**S3-3：自查脚本 evidence 匹配不鲁棒**

`self-check-evidence.md` 的自查逻辑取 evidence 前 80 字符匹配正文。如果 reviewer 的 evidence 是概括性描述或正文被润色，会产生假阴性或假阳性。

**修复**：考虑归一化后匹配，或检查 category + location 是否已被修复。

### 中等问题

**S3-4：reviewer SKILL.md 调用 prompt 未传入 CHAPTER_FILE 完整路径**

**S3-5：SKILL.md 描述"13 维度审查"但 reviewer agent 只覆盖 6 维度**

**S3-6：chapter-writer-agent 修复轮输入格式不清晰**

**S3-7：修复循环缺少对"修复引入新问题"的检测**

**S3-8：data-agent description 与实际职责不匹配**

**S3-9：充分性闸门缺少 extraction_result 完整性检查**

**S3-10：Step 5.4 "projection 失败→只补跑失败项"无具体命令**

**S3-11：清除 blocking 脚本未重置 `has_blocking` 字段**

**S3-12：Step 5 缺少 checkpoint**

### 低问题

**S3-13：`--minimal` 模式 checkpoint 覆盖不完整**

**S3-14：reviewer 输出 JSON 格式不符时无重试**

**S3-15："最多 2 轮"无代码级计数器**

**S3-16：settler 的 power_breakthrough payload 字段名与 writer 期望不对齐**

**S3-17：event_id 生成策略不一致**

**S3-18：`_get_overdue_debts` 查询 status='pending'（已修复）**

---

## 四、Stage 4：独立审查

### 中等问题

**S4-1：review_metrics 表的 `dimension_scores` 使用 8 维度但 SKILL.md 描述 6 维度**

`review_schema.py` 的 `SCORE_CATEGORIES` 有 8 个（continuity, setting, character, timeline, ai_flavor, logic, pacing, other），但 SKILL.md 和 reviewer.md 都只描述 6 个。

**修复**：统一维度列表描述。

**S4-2：`critical_issues` 是 `List[str]` 但 dashboard 假设是 `List[dict]`**

`review_schema.py` 中 `critical_issues` 是纯文本列表，但 dashboard 的 `ReviewAnalyticsPage` 尝试按 `type` 字段分类。

**影响**：dashboard 的 issue 类型分布图无法工作。

### 低问题

**S4-3：review-pipeline 的 metrics 保存与 state.json 投影写入存在时序依赖**

---

## 五、数据流与合同一致性

### 严重问题

**D-1：power_breakthrough 字段名不对齐**

observer_settler 产出 `new_realm`，但 StateProjectionWriter 查找 `new`/`to`/`new_value`/`new_state`。正常流程下 state delta 提取静默失败。

**修复**：StateProjectionWriter 增加对 `new_realm` 的 fallback。

### 中等问题

**D-2：SSOT publish_event 的事件类型与 StoryEvent Literal 不完全对齐**

SSOT 专有事件（`chapter_status_changed` 等）不经过 StoryEvent 验证。`rebuild_state_json()` 需要处理所有事件类型，新增事件类型忘记添加 handler 会导致静默数据丢失。

**修复**：在 `rebuild_state_json()` 末尾添加未知事件类型的 warning log。

**D-3：projection_log 未同步**

`apply_projections()` 不写 `projection_log.jsonl`，但 postcommit gate 优先从 projection_log 读取。

**修复**：在 `apply_projections()` 结束时调用 `append_projection_run()`。

**D-4：state.json 结构双轨**

StateProjectionWriter 写 `entity_state`，SSOT rebuild 写 `entities_v3`。两者 key 不同。

### 低问题

**D-5：EventProjectionRouter TABLE 未覆盖所有 SSOT 事件类型**

**D-6：REQUIRED_PROJECTION_WRITERS 在 3 处硬编码**

**D-7：extraction_result 不自描述（state_deltas/entity_deltas 永远为空）**

---

## 六、优先修复建议

### P0（必须修复）

1. **S1-1**：`init_project.py` 添加 `one_liner` 和 `core_conflict` 参数
2. **S3-1**：settler 输出补全 state_deltas/scenes/summary_text
3. **D-1**：StateProjectionWriter 增加 `new_realm` fallback
4. **S2-6**：writeback JSON 示例补充 `chapters_range`

### P1（建议修复）

5. **S3-2**：settler heading 匹配增加容错
6. **S3-3**：自查脚本 evidence 匹配改进
7. **D-3**：apply_projections 同步写 projection_log
8. **S1-2**：充分性闸门增加 one_liner/core_conflict 检查
9. **S2-1**：loader 补充缺失字段映射

### P2（可选优化）

10. **S3-5**：统一维度描述（6 vs 8）
11. **S2-7/S2-8**：时间线/倒计时自动化验证
12. **S1-3**：idea_bank.json 生成自动化
13. **D-6**：REQUIRED_PROJECTION_WRITERS 抽取为单一常量
