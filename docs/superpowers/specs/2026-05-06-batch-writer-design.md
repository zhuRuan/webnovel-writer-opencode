# Batch Writer Design

## Context

单章写作（webnovel-write）已稳定：context-agent → 起草 → reviewer → 润色 → data-agent → commit。扩展为连续多章，借鉴 subagent-driven-development 的子代理模式：主 AI 编排+创作，子代理执行专项任务。

## Anti-Laziness Rules（硬规则，不可绕过）

这些规则针对 AI 在长循环中的已知偷懒模式。SKILL.md 中必须显式声明每条。

| # | 偷懒模式 | 防御 |
|---|---------|------|
| 1 | 口头描述代替子代理调用 | **禁止**。"context-agent 会输出..." 不等于调用了它。MUST 使用 Agent 工具。 |
| 2 | 跳过审查 | 每章 MUST 运行 reviewer。blocking=false 也不能跳过——审查是结构化记录，不是主观判断 |
| 3 | "看起来没问题" 代替实际验证 | 每步后 MUST 运行验证命令（test -s / ls / python -c），不能用 Read 工具代替 |
| 4 | 伪造 batch_state 更新 | batch_state.json 是唯一真源。更新 MUST 用 python -c 写 JSON，不能"稍后补" |
| 5 | 长循环后期注意力衰减，跳步 | 每章开始前 MUST 重现检查清单。每 3 章 MUST 暂停等待用户确认 |
| 6 | 子代理失败后不重试直接跳过 | 每个 Agent 调用后检查输出文件。若为空/不存在，重试 1 次。仍失败→停止 |
| 7 | 润色步骤被合并到"审查+润色一起做了" | 审查和润色是独立步骤。先拿到审查结果→再修改正文。禁止在审查前修改 |

## Architecture

```
主 AI（控制器 + 创作者）
  │
  ├─ [子代理] context-agent → 写作任务书（结构化文本）
  │   验证: task book 非空，包含5个必要段落
  │
  ├─ [主 AI] 起草正文 → 章节文件
  │   验证: test -s 章节文件, 字数 ≥ 1500
  │
  ├─ [子代理] reviewer → 审查报告 JSON
  │   验证: JSON 有效, 包含 blocking 字段
  │
  ├─ [主 AI] 评估 + 修复 + 润色
  │   规则: blocking issues → 修复 → 重审(最多2轮)
  │
  ├─ [子代理] data-agent → 提取 JSON × 3
  │   验证: 每个文件存在且非空
  │
  ├─ [主 AI] chapter-commit
  │   验证: 返回 status=accepted
  │
  └─ [主 AI] 更新 batch_state.json
      验证: python -c 读取确认 write 成功
```

## Control Flow（逐章 10 步）

每章执行前，主 AI 必须重现以下清单：

```
□ 1. 环境预检: PROJECT_ROOT/SCRIPTS_DIR 已设置
□ 2. 上章完整性: 确认第 N-1 章文件存在、batch_state 包含 N-1
□ 3. context-agent: Agent 工具调用，输出任务书非空
□ 4. 起草正文: 2000-2500字，落盘到章节文件
□ 5. reviewer: Agent 工具调用，输出有效 JSON
□ 6. 评估+修复: blocking→修复→重审(最多2轮)
□ 7. data-agent: Agent 工具调用，输出3个JSON文件
□ 8. chapter-commit: bash 命令，确认 accepted
□ 9. 更新 batch_state: python -c 写 JSON
□ 10. 进度反馈: 输出得分/字数/进度
```

### 逐步详解

**Step 0: 解析范围**
```
"写第9-15章" → S=9, E=15
"连续写3章"  → 读 state.json current_chapter, S=N+1, E=N+3
"批量写5章"  → 同上，E=S+4
```
若无法解析，询问用户。上限 20 章（--force 可绕过）。

**Step 1: 上章完整性检查（第 N 章开始前，N > S 时必做）**
```bash
# 检查 N-1 章文件存在
CHAPTER_FILE=$(python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter $((N-1)))
test -s "${PROJECT_ROOT}/${CHAPTER_FILE}" || echo "MISSING"

# 检查 batch_state 包含 N-1
python -c "import json; s=json.load(open('${PROJECT_ROOT}/.webnovel/batch_state.json')); assert (N-1) in s['completed_chapters']" || echo "NOT_IN_BATCH_STATE"

# 任一失败 → 立即停止，提示修复
```
跳过此步的后果：前一章数据未落盘，继续写会导致状态永久断裂。

**Step 2: context-agent 生成任务书**
```
Agent(
  subagent_type: "context-agent",
  prompt: "chapter={N}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}; storage_path=${PROJECT_ROOT}/.webnovel; state_file=${PROJECT_ROOT}/.webnovel/state.json。先 research，再按 本章硬性约束→CPNs/CPNs/CEN→本章禁区→风格指引→dynamic_context补充参考 的顺序输出五段写作任务书。"
)
```
等待子代理返回后验证：任务书文本非空，包含"硬性约束"或"CBN"字样。
若子代理失败或返回空，重试 1 次。仍失败→停止整批。

**Step 3: 主 AI 起草正文**
- 基于任务书 + 章纲写正文，2000-2500 字
- 使用 chapter_paths.py 确定文件路径：
```bash
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter {N})
```
- 写入后验证：
```bash
WORDS=$(python -c "import re; t=open('${PROJECT_ROOT}/${CHAPTER_PATH}',encoding='utf-8').read(); print(len(re.findall(r'[一-鿿]',t)))")
test "$WORDS" -ge 1500 || echo "字数不足: $WORDS"
```

**Step 4: reviewer 审查**
```
Agent(
  subagent_type: "reviewer",
  prompt: "chapter={N}; chapter_file=${PROJECT_ROOT}/${CHAPTER_PATH}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。严格输出 reviewer schema JSON，并保存到 ${PROJECT_ROOT}/.webnovel/tmp/review_results.json。"
)
```
验证：
```bash
python -c "import json; d=json.load(open('${PROJECT_ROOT}/.webnovel/tmp/review_results.json')); assert 'blocking' in str(type(d)) or isinstance(d, dict)"
```

**Step 5: 评估 + 修复**
```
if blocking issues > 0:
  修复正文 → 重新运行 reviewer（Step 4）→ 最多 2 轮
  2 轮后仍有 blocking → 标记 failed，记录原因，继续下一章
else:
  针对 non-blocking suggestions 做轻量润色
```
限制重审次数防止无限循环。

**Step 6: data-agent 事实提取**
```
Agent(
  subagent_type: "data-agent",
  prompt: "chapter={N}; chapter_file=${PROJECT_ROOT}/${CHAPTER_PATH}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。从正文提取事实，生成 .webnovel/tmp/ 下的 fulfillment_result.json、disambiguation_result.json、extraction_result.json；不直接写 state/index/summaries/memory。"
)
```
验证：
```bash
for f in fulfillment_result.json disambiguation_result.json extraction_result.json; do
  test -s "${PROJECT_ROOT}/.webnovel/tmp/${f}" || echo "MISSING: $f"
done
```
任一缺失→重试 1 次。仍缺失→标记 failed 并停止。

**Step 7: chapter-commit**
```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-commit \
  --chapter {N} \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```
检查输出包含 `status: accepted`。失败→检查 JSON→修复→重试(最多3次)。仍失败→标记 failed 并停止。

**Step 8: 更新 batch_state.json**
```bash
python -c "
import json, pathlib, datetime
p = pathlib.Path('${PROJECT_ROOT}/.webnovel/batch_state.json')
s = json.loads(p.read_text())
s['completed_chapters'].append(${N})
s['current_chapter'] = ${N} + 1
s['chapter_results']['${N}'] = {'status': 'success', 'score': ${SCORE}, 'words': ${WORDS}, 'completed_at': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'}
p.write_text(json.dumps(s, ensure_ascii=False, indent=2))
"
```
然后用 `python -c` 重新读取验证写入成功。
更新失败→重试 3 次。仍失败→停止。

**Step 9: 进度反馈**
```
✅ 第{N}章完成 | 得分: {SCORE} | 字数: {WORDS} | 进度: {N-S+1}/{E-S+1}
```

**Step 10: 分批暂停点（每 3 章）**
```
当 (N - S + 1) % 3 == 0 或 N == E:
  输出已完成章节摘要（每章一行：章号/得分/字数/状态）
  显示 batch_state 完整性检查结果
  等待用户确认：继续 / 停止 / 检查
```
用户可选择 AUTO_CONTINUE=1 跳过暂停。

## batch_state.json

位置：`{PROJECT_ROOT}/.webnovel/batch_state.json`

```json
{
  "task_id": "batch_20260506_143000",
  "range": {"start": 9, "end": 15},
  "status": "running",
  "current_chapter": 11,
  "completed_chapters": [9, 10],
  "failed_chapters": [],
  "chapter_results": {
    "9": {"status": "success", "score": 87, "words": 2340},
    "10": {"status": "success", "score": 85, "words": 2280}
  },
  "created_at": "2026-05-06T14:30:00Z"
}
```

`status` 枚举：`running | completed | stopped | failed`

## Interruption Recovery

```
启动时检测 batch_state.json:
  running   → 从 current_chapter 恢复，显示已完成章节
  completed → 显示汇总，询问新批次
  stopped   → 询问继续/重启/放弃
  failed    → 显示失败原因，要求手动修复
```

恢复时 MUST 重新运行 Step 1（上章完整性检查）确认数据一致。

## Failure Handling

| 场景 | 处理 | 是否阻断 |
|------|------|---------|
| 上章完整性检查失败 | 立即停止，提示缺失项 | 阻断 |
| context-agent 失败 | 重试 1 次 → 停止 | 阻断 |
| 字数不足 | 补充内容后重检 | 章内循环 |
| reviewer blocking(1-2轮) | 修复 → 重审 | 章内循环 |
| reviewer blocking(3轮) | 标记 failed，记录原因，继续 | 不阻断 |
| data-agent 失败 | 重试 1 次 → 标记 failed 并停止 | 阻断 |
| chapter-commit 失败 | 修复 → 重试(最多3次) → 停止 | 阻断 |
| batch_state 更新失败 | 重试 3 次 → 停止 | 阻断 |
| 大纲缺失 | 警告，使用章节号推断标题 | 不阻断 |

## SKILL.md Structure（待实现）

```markdown
---
name: webnovel-write-batch
description: 连续写作多章节...
compatibility: opencode
allowed-tools: Read Write Edit Grep Bash Agent
---

# 批量写作

## 硬规则（Anti-Laziness）
[7 条规则，逐条列出]

## 环境设置
[变量初始化]

## Step 0: 解析范围

## Step 1-10: 逐章循环
[每步含：命令 + 验证 + 失败处理]

## 断点恢复

## 分批暂停点

## 汇总报告
```

## Test Plan

- `test_batch_state_create` — 创建初始 batch_state.json
- `test_batch_state_update` — 追加 completed_chapters
- `test_batch_state_resume` — 从 current_chapter 恢复
- `test_batch_range_parse` — "9-15" / "连续3章"
- `test_step1_integrity_check` — 上章缺失时正确阻止
- Manual E2E: 连续写 3 章
