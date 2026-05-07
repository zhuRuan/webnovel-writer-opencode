# Batch Writer Context Isolation Redesign

## Context

[2026-05-06-batch-writer-design.md](./2026-05-06-batch-writer-design.md) 定义了批量写作的原始架构。用户反馈：连续写作模式（3 章）从第 2 章开始全面崩盘——正文质量下降、流程走样、审查松弛。

**根因**：原架构将"起草正文"和"评估+修复+润色"放在主 AI 线程执行。第 1 章完成后，主线程上下文被正文、审查结果、工具输出污染。第 2 章起所有步骤在噪音中运行——LLM 注意力衰减、行文惯性传导、审查标准松弛。

**解法**：将每章的创作闭环（起草+润色）移入独立 subagent，享受干净上下文。编排器退化为机械调度器。

## Key Constraint

Claude Code 官方文档明确：**subagent 不能嵌套调用 subagent**。现有 subagent（context-agent、reviewer、data-agent）的 tools 均为 `read/grep/bash`，不含 `Agent`。

因此不能设计一个"超级 agent"内部调用 context-agent + reviewer。编排器必须保持在主线程，逐次启动各独立 subagent。

## Architecture

```
Batch Orchestrator（主线程，仅机械调度）
  │
  │  For each chapter N = S to E:
  │
  ├─ 1. 刷新合同树 (bash)
  │     placeholder-scan + story-system
  │
  ├─ 2. Agent(context-agent)               ← 干净上下文
  │     输出: 写作任务书
  │     验证: 非空 + 含"CBN"字样
  │
  ├─ 3. Agent(chapter-writer-agent)         ← 干净上下文（新增）
  │     输入: 任务书 + 章纲约束 + 润色指南 + [审查反馈]
  │     执行: 起草 → 自检 → 润色(风格+排版+Anti-AI)
  │     输出: 章节正文文件
  │     验证: 文件存在 + 字数 ≥ 1500
  │
  ├─ 4. Agent(reviewer)                    ← 干净上下文
  │     输出: review_results.json
  │
  ├─ 5. review-pipeline (bash)
  │     解析 blocking 状态
  │
  ├─ 6. blocking > 0?
  │     是 → 提取 blocking issues 文本 → 回到 3（最多 2 轮）
  │     2 轮后仍 blocking → 标记 failed
  │     否 → 继续
  │
  ├─ 7. Agent(data-agent)                  ← 干净上下文
  │     输出: fulfillment/disambiguation/extraction × 3
  │
  ├─ 8. chapter-commit + 验证投影 + Git 备份 (bash)
  │
  └─ 9. 更新 batch_state → 进度反馈
       每 3 章暂停点
```

### 与原架构的关键差异

| | 原版 | 新版 |
|---|---|---|
| 起草正文 | 主 AI 线程 | chapter-writer-agent（干净上下文） |
| 润色修复 | 主 AI 线程 | 合并到 chapter-writer-agent 内 |
| 审查反馈 | 主 AI 手动改 | 编排器提取 issue → 注入 agent prompt |
| 新增文件 | 无 | `.opencode/agents/chapter-writer-agent.md` |

## New Agent: chapter-writer-agent

### 定义文件

`.opencode/agents/chapter-writer-agent.md`

### 职责边界

| 输入 | 输出 |
|------|------|
| 章节号 N | `正文/第{NNNN}章-{title}.md` |
| 上下文 agent 产出的任务书 | 字数统计 |
| 章纲约束（chapter_directive, CBN/CPNs/CEN, 禁区） | 润色后的最终正文 |
| 润色指南（polish-guide / typesetting / style-adapter） | |
| （修复轮）审查反馈 issue 列表 | |

### 执行流程

```
Step A: 阅读任务书 + 章纲约束，确认理解本章目标
Step B: 起草正文（2000-2500 字，中文思维，无占位符，围绕 CBN→CPNs→CEN 展开）
Step C: 自检——对照任务书硬性约束逐项确认
Step D: 润色
  1. 修复审查指出的 issue（修复轮时）
  2. 风格适配（加载 style-adapter）
  3. 排版（加载 typesetting）
  4. Anti-AI 终检
Step E: 写入章节文件
```

### 工具权限

```yaml
tools:
  read: true    # 读取任务书、章纲、MASTER_SETTING、前章正文（了解承接点）
  grep: true    # 检索关键设定
  bash: true    # 字数检查、文件验证
  write: true   # 写入正文
  edit: true    # 润色修改
```

不含 `Agent`——不嵌套调用其他 agent。

### 约束

- 只根据任务书写作，不自行加载额外参考（任务书已内化所有约束）
- 修复轮时：只修改审查指出的具体问题，不大面积重写
- Anti-AI 终检必须执行，不通过不输出
- 字数不足 1500 时继续补充

## Orchestrator Changes

### 1. 用 Agent(chapter-writer-agent) 替换主线程创作

原版 Step 3（起草）和 Step 5（润色）是主线程执行 → 改为 Agent(chapter-writer-agent) 调用。

### 2. 审查反馈传递机制

编排器从 `review_results.json` 提取 blocking issues：

```bash
python -c "
import json
d = json.load(open('${PROJECT_ROOT}/.webnovel/tmp/review_results.json'))
issues = d.get('issues', [])
blocking = [i for i in issues if i.get('severity') == 'blocking']
for b in blocking:
    print(f\"- [{b.get('category','')}] {b.get('description','')} (位置: {b.get('location','')})\")
"
```

提取后的文本直接注入 chapter-writer-agent 的 prompt，agent 无需理解审查 schema。

### 3. 修复轮流程

```
blocking = 解析 review_results.json
round = 0
while blocking > 0 and round < 2:
    feedback = 提取 blocking issues 文本
    Agent(chapter-writer-agent, prompt="修复模式: {feedback}")
    Agent(reviewer)
    review-pipeline
    blocking = 重新解析
    round += 1
if blocking > 0:
    标记本章 failed，记录原因，继续下一章
```

### 4. 编排器上下文管理

编排器主线程上下文随章数累积（batch_state 更新、审查分数、进度反馈），但编排器只执行机械操作：
- 固定格式的 Agent 调用 prompt
- bash 命令
- JSON 解析

这些操作不受上下文累积影响。创作类工作全部在 subagent 干净上下文中完成。

## Files Changed

| 文件 | 操作 | 说明 |
|------|------|------|
| `.opencode/agents/chapter-writer-agent.md` | 新增 | 章节创作 agent 定义 |
| `.opencode/skills/webnovel-write-batch/SKILL.md` | 修改 | 编排流程重写，用 Agent(chapter-writer-agent) 替换主线程创作 |
| `docs/superpowers/specs/2026-05-07-batch-writer-context-isolation-design.md` | 新增 | 本设计文档 |

## Test Plan

- Manual: 连续写 3 章，验证第 2-3 章质量不低于单章模式
- Manual: 验证修复轮——blocking issue 正确反馈给 chapter-writer-agent
- Manual: 验证断点恢复——中断后从 batch_state 正确恢复
- Existing: `test_batch_state_*` 系列测试保持不变（batch_state 格式未变）
