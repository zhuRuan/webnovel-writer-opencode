# Batch Writer Context Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将批量写作的每章创作闭环（起草+润色）从主线程移入独立 subagent，消除上下文累积导致的逐章质量衰减。

**Architecture:** 新增 `chapter-writer-agent` 在干净上下文中执行起草+润色。编排器（主线程）退化为机械调度器，逐章串行调用 context-agent → chapter-writer-agent → reviewer → data-agent。单章模式（webnovel-write）不动。

**Tech Stack:** Claude Code agent 定义（Markdown frontmatter），SKILL.md（bash + Agent 工具调度），Python CLI（不改动）

---

## 文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `.opencode/agents/chapter-writer-agent.md` | 新增 | 在干净上下文中完成起草+润色 |
| `.opencode/skills/webnovel-write-batch/SKILL.md` | 修改 | 编排器流程重写，用 Agent(chapter-writer-agent) 替换主线程 Step 3+5 |

不变更：`webnovel-write/SKILL.md`、所有现有 agent、所有 data_modules、batch_state.json schema。

---

### Task 1: 创建 chapter-writer-agent 定义

**Files:**
- Create: `.opencode/agents/chapter-writer-agent.md`

- [ ] **Step 1: 编写 agent 定义文件**

```markdown
---
name: chapter-writer-agent
description: 根据写作任务书起草并润色单个章节，在干净上下文中完成创作闭环。
mode: subagent
tools:
  read: true
  grep: true
  bash: true
  write: true
  edit: true
---

# chapter-writer-agent

## 0. 环境

执行任何 bash 命令前，先确保变量已设置：

```bash
export SCRIPTS_DIR="${SCRIPTS_DIR:-${PWD}/.opencode/scripts}"
export PROJECT_ROOT="${PROJECT_ROOT:-${PWD}}"
```

## 输入

从调用方 prompt 中接收：
- **章节号 N** 和 **目标字数**（默认 2000-2500）
- **写作任务书**（context-agent 产出，含硬性约束/CBN/CPNs/CEN/禁区/风格指引）
- **章纲约束**（chapter_directive.goal、time_anchor、countdown 等）
- **润色指南摘要**（polish-guide / typesetting / style-adapter 关键规则）
- **（修复轮）审查反馈**：blocking issue 列表，格式 `[category] description (位置: location)`

## 执行流程

### Step A: 理解任务

阅读任务书和章纲约束，确认：
1. 本章硬性约束（goal / time_anchor / countdown / chapter_end_open_question）
2. CBN / CPNs / CEN 与 must_cover_nodes
3. 本章禁区（forbidden_zones）
4. 风格指引 + OOC 警戒
5. 字数目标

修复轮时额外确认：审查反馈中每条 issue 的具体位置和修改方向。

### Step B: 起草正文

- 只根据任务书起草，不加载额外参考（任务书已内化所有约束）
- 纯正文，无占位符，无元注释
- 有结构化节点时围绕 CBN→CPNs→CEN 展开
- 中文思维写作
- 写入章节文件：

```bash
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter {N})
CHAPTER_FILE="${PROJECT_ROOT}/${CHAPTER_PATH}"
```

### Step C: 自检

对照任务书硬性约束逐项确认：
- 所有 must_cover_nodes 已覆盖
- 无禁区违反
- 时间锚点 / 倒计时一致
- 章节结尾符合 open_question 方向

### Step D: 润色

顺序执行：
1. **修复审查 issue**（修复轮时）：逐条对照审查反馈，只修改指出的具体问题，不改无关段落
2. **风格适配**：确认人称/视角/叙事距离与 MASTER_SETTING 一致，消除 AI 味
3. **排版**：章节标题格式 `## 第{NNNN}章 标题`，段落间空行，对话分行
4. **Anti-AI 终检**：检查以下 AI 味特征并消除——
   - "不是...而是..." 句式
   - 段落首尾的总结性/感叹性语句
   - 冗余的"突然/忽然/却/竟"
   - 动作描写的机械罗列（"一边...一边..."）
   - 情感描写的直接告知（"他感到很..."）

### Step E: 验证

```bash
# 文件存在且非空
test -s "$CHAPTER_FILE" || { echo "❌ 章节文件为空"; exit 1; }

# 字数检查
WORDS=$(python -c "
import re
t = open('$CHAPTER_FILE', encoding='utf-8').read()
print(len(re.findall(r'[一-鿿]', t)))
")
echo "字数: $WORDS"
if [ "$WORDS" -lt 1500 ]; then
  echo "⚠️ 字数不足 1500，需补充"
fi
```

字数 < 1500 时回到 Step B 补充正文。

## 约束

- 只根据任务书写作，不自发加载额外参考文件
- 修复轮时只改 issue 指向的位置，不大面积重写
- 不在正文中插入占位符（如 `{待补充}`、`[TODO]`）
- Anti-AI 终检不通过不输出
- 章节文件路径由 chapter-path CLI 确定，不自行构造
```

- [ ] **Step 2: 验证文件格式**

```bash
python -c "
import yaml
with open('.opencode/agents/chapter-writer-agent.md', encoding='utf-8') as f:
    content = f.read()
# 检查 frontmatter
assert content.startswith('---'), '缺少 frontmatter'
parts = content.split('---', 2)
assert len(parts) >= 3, 'frontmatter 格式不正确'
frontmatter = yaml.safe_load(parts[1])
assert frontmatter['name'] == 'chapter-writer-agent'
assert frontmatter['mode'] == 'subagent'
assert 'write' in frontmatter['tools']
assert 'edit' in frontmatter['tools']
print('✅ chapter-writer-agent.md 格式验证通过')
"
```

- [ ] **Step 3: Commit**

```bash
git add .opencode/agents/chapter-writer-agent.md
git commit -m "feat: add chapter-writer-agent for context-isolated batch writing"
```

---

### Task 2: 重写 webnovel-write-batch SKILL.md

**Files:**
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

- [ ] **Step 1: 重写 SKILL.md 编排流程**

保持 frontmatter 和 Step 0/0.5/0.6 不变。重写逐章循环部分，核心改动：

1. 原 Step 3（起草）和 Step 5（润色）合并为 Agent(chapter-writer-agent) 调用
2. Step 4（审查）后增加"提取审查反馈 + 修复轮"
3. 步骤重新编号

完整文件内容：

```markdown
---
name: webnovel-write-batch
description: |
  连续写作多章。当用户要求多章写作时必须使用此 skill。

  ## 触发条件
  - "连续写N章"、"写第X-Y章"、"批量写X-Y章"、"一次写N章"
  - "重写第X-Y章"、"修改第X-Y章"
  - "多章"、"多章节"

  ## 区分规则
  - 单章 → webnovel-write
  - 多章 → 必须使用本 skill
compatibility: opencode
allowed-tools: Read Write Edit Grep Bash Agent
---

# 批量写作

## ⛔ 硬规则（Anti-Laziness）

以下规则针对 AI 在长循环中的已知偷懒模式。**逐章执行前必须重现此清单。**

| # | 禁止 | 正确做法 |
|---|------|---------|
| 1 | 口头描述代替 `Agent()` 调用 | 必须使用 Agent 工具调用 context-agent / chapter-writer-agent / reviewer / data-agent |
| 2 | 跳过审查 | 每章必须运行 reviewer Agent + review-pipeline。blocking=false 也不能跳过 |
| 3 | 用 Read 工具代替验证命令 | 每步后必须运行 bash 验证命令（test -s / ls / python -c） |
| 4 | "稍后更新" batch_state | 每章完成后立即用 python -c 写 JSON，写完后重新读取验证 |
| 5 | 章数多了开始跳步/简化流程 | 每章必须完整执行本 skill 的 9 步，不得缩减。3 章后强制暂停 |
| 6 | 子代理失败后假装成功 | 每个 Agent() 调用后检查输出文件是否存在且非空。失败重试 1 次→仍失败则停止 |
| 7 | 审查和润色合并执行 | chapter-writer-agent 先写正文 → reviewer 审查 → 有 blocking 则回传修复。禁止在审查前自行修改 |
| 8 | 用简化版代替完整单章流程 | 每章 = 完整闭环。chapter-writer-agent 在干净上下文中执行创作，质量等同于单章 |

## 环境设置

```bash
export SCRIPTS_DIR="${PWD}/.opencode/scripts"
export SKILL_ROOT="${PWD}/.opencode/skills/webnovel-write"
test -d "${SCRIPTS_DIR}" || { echo "错误: 未找到 ${SCRIPTS_DIR}，请确保当前目录是 webnovel-writer 仓库根目录"; exit 1; }

export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PWD}" where)"
test -n "$PROJECT_ROOT" && test -f "${PROJECT_ROOT}/.webnovel/state.json" || { echo "错误: PROJECT_ROOT 解析失败，请用 --project-root 显式指定"; exit 1; }
```

## Step 0: 解析章节范围

- "写第9-15章" → S=9, E=15
- "连续写3章" → 读 .webnovel/state.json 的 current_chapter，S=N+1, E=N+3
- "批量写5章" → 同上，E=S+4

若无法解析，询问用户明确范围。上限 3 章（可通过 `--force` 参数绕过，上限 5 章）。

## Step 0.5: 断点恢复

```bash
BATCH_STATE="${PROJECT_ROOT}/.webnovel/batch_state.json"

if [ -f "$BATCH_STATE" ]; then
  STATUS=$(python -c "import json; print(json.load(open('$BATCH_STATE')).get('status',''))")
  if [ "$STATUS" = "running" ]; then
    echo "检测到未完成的批量任务"
    python -c "
import json
s = json.load(open('$BATCH_STATE'))
print(f'  已完成: 第{s[\"completed_chapters\"]}章')
print(f'  待恢复: 第{s[\"current_chapter\"]}章')
"
    # 询问用户：继续 / 重新开始 / 放弃
  elif [ "$STATUS" = "completed" ]; then
    echo "上一次批量任务已完成。"
    # 询问是否开始新批次
  fi
fi
```

## Step 0.6: 初始化 batch_state（新任务）

```bash
if [ ! -f "$BATCH_STATE" ] || [ "$STATUS" != "running" ]; then
  python -c "
import json, datetime
s = {
  'task_id': f'batch_{datetime.datetime.utcnow().strftime(\"%Y%m%d_%H%M%S\")}',
  'range': {'start': $S, 'end': $E},
  'status': 'running',
  'current_chapter': $S,
  'completed_chapters': [],
  'failed_chapters': [],
  'chapter_results': {},
  'created_at': datetime.datetime.utcnow().isoformat() + 'Z'
}
open('$BATCH_STATE', 'w').write(json.dumps(s, ensure_ascii=False, indent=2))
"
fi
```

---

## 批前一次性验证

在进入逐章循环前执行一次 preflight，后续各章不再重复。

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" preflight
```

---

## 逐章循环

> **每章 = 9 步完整闭环。创作在独立 subagent 干净上下文中执行。**

### 逐章检查清单（每章开始前重现）

```
□ 0. 环境变量验证
□ A. 上章完整性检查（N > S 时）
□ 1. 刷新合同树
□ 2. Agent(context-agent) → 写作任务书
□ 3. Agent(chapter-writer-agent) → 起草+润色
□ 4. Agent(reviewer) → 审查结果
□ 5. review-pipeline → 判定 blocking
□ 6. blocking? → 提取反馈 → 回到 3（最多 2 轮）
□ 7. Agent(data-agent) → 事实提取
□ 8. chapter-commit + 验证投影 + Git 备份
□ 9. 更新 batch_state + 进度反馈
```

---

### Step 0: 环境变量验证（每章开始前强制）

```bash
test -n "$PROJECT_ROOT" || { echo "❌ PROJECT_ROOT 未设置"; exit 1; }
test -n "$SCRIPTS_DIR" || { echo "❌ SCRIPTS_DIR 未设置"; exit 1; }
test -d "$PROJECT_ROOT" || { echo "❌ PROJECT_ROOT 目录不存在: $PROJECT_ROOT"; exit 1; }
test -d "${PROJECT_ROOT}/.webnovel" || { echo "❌ ${PROJECT_ROOT}/.webnovel 不存在，PROJECT_ROOT 可能不正确"; exit 1; }
echo "✅ PROJECT_ROOT=${PROJECT_ROOT}"
```

---

### Step A: 上章完整性检查（N > S 时强制）

```bash
if [ "$N" -gt "$S" ]; then
  PREV=$((N - 1))

  CHAPTER_FILE=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter $PREV)
  if [ ! -s "${PROJECT_ROOT}/${CHAPTER_FILE}" ]; then
    echo "❌ 第${PREV}章文件缺失。立即停止。"
    exit 1
  fi

  IN_BATCH=$(python -c "import json; s=json.load(open('$BATCH_STATE')); print($PREV in s.get('completed_chapters',[]))")
  if [ "$IN_BATCH" != "True" ]; then
    echo "❌ 第${PREV}章未在 batch_state 中标记完成。立即停止。"
    exit 1
  fi

  echo "✅ 第${PREV}章完整性检查通过"
fi
```

---

### Step 1: 刷新合同树

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" placeholder-scan --format text
```

genre 从 `.webnovel/state.json` 的初始化配置快照读取。调用 story-system 前必须先从详细大纲解析真实本章目标，禁止传 `{章纲目标}`、`第N章章纲目标` 等占位 query。

```bash
GENRE="$(python -X utf8 -c "import json,sys; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json',encoding='utf-8')); print(s.get('project',{}).get('genre',''))")"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  story-system "${CHAPTER_GOAL}" --genre "${GENRE}" --chapter {N} --persist --emit-runtime-contracts --format both
```

必备文件：`MASTER_SETTING.json`、`volume_{NNN}.json`、`chapter_{NNN}.review.json`。缺失则阻断。

`chapter_{NNN}.json` 必须优先检查顶层 `chapter_directive`。`chapter_focus` 只能来自 `chapter_directive.goal` 或真实 query，不得从 `dynamic_context` 的参考摘要继承。

---

### Step 2: Agent(context-agent) → 写作任务书

**必须使用 Agent 工具调用 context-agent，不得由主流程自行整理。**

```text
Agent(
  subagent_type: "context-agent",
  prompt: "chapter={N}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}; storage_path=${PROJECT_ROOT}/.webnovel; state_file=${PROJECT_ROOT}/.webnovel/state.json（projection/read-model，仅兼容读取）。先 research，再按 本章硬性约束→CBN/CPNs/CEN→本章禁区→风格指引→dynamic_context补充参考 的顺序输出五段写作任务书。"
)
```

验证：任务书非空且包含"硬性约束"或"CBN"字样。失败或返回空→重试 1 次→仍失败则停止。

---

### Step 3: Agent(chapter-writer-agent) → 起草+润色

**核心变更：原来主线程的起草(Step 3)和润色(Step 5)合并为一次 Agent 调用，在干净上下文中完成完整创作闭环。**

传入 prompt 结构：

```text
Agent(
  subagent_type: "chapter-writer-agent",
  prompt: """
【章节】第{N}章
【字数】2000-2500 字

【写作任务书】
{context-agent 产出的完整任务书}

【章纲约束】
{从 chapter_{NNN}.json 提取的 chapter_directive.goal / time_anchor / countdown / chapter_end_open_question / must_cover_nodes / forbidden_zones}

【润色指南】
- 风格适配：与 MASTER_SETTING 保持一致的人称/视角/叙事距离
- 排版：标题格式 `## 第{NNNN}章 标题`，段落间空行，对话分行
- Anti-AI 终检：消除"不是...而是..."句式、段落首尾总结句、冗余"突然/忽然"、机械动作罗列、直接情感告知

【审查反馈】
（首轮为空。修复轮时填入：）
- [{category}] {description} (位置: {location})
"""
)
```

**验证：**

```bash
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter {N})
CHAPTER_FILE="${PROJECT_ROOT}/${CHAPTER_PATH}"

test -s "$CHAPTER_FILE" || { echo "❌ 章节文件为空"; exit 1; }

WORDS=$(python -c "
import re
t = open('$CHAPTER_FILE', encoding='utf-8').read()
print(len(re.findall(r'[一-鿿]', t)))
")
echo "字数: $WORDS"
if [ "$WORDS" -lt 1500 ]; then
  echo "⚠️ 字数不足 1500"
fi
```

字数不足→重试 chapter-writer-agent（提示字数不足）。仍不足→标记 warning 继续。

---

### Step 4: Agent(reviewer) → 审查

**必须使用 Agent 工具调用 reviewer，不得由主流程伪造审查 JSON。**

```text
Agent(
  subagent_type: "reviewer",
  prompt: "chapter={N}; chapter_file=${CHAPTER_FILE}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。严格输出 reviewer schema JSON，并保存到 ${PROJECT_ROOT}/.webnovel/tmp/review_results.json。"
)
```

---

### Step 5: review-pipeline

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline \
  --chapter {N} \
  --review-results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --metrics-out "${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json" \
  --report-file "审查报告/第{N}章审查报告.md" \
  --save-metrics
```

验证审查结果：

```bash
python -c "
import json
d = json.load(open('${PROJECT_ROOT}/.webnovel/tmp/review_results.json'))
assert isinstance(d, dict), 'review_results 不是 JSON 对象'
blocking_count = len([i for i in d.get('issues',[]) if i.get('severity')=='blocking'])
print(f'blocking: {blocking_count}, score: {d.get(\"score\",\"unknown\")}')
"
```

---

### Step 6: 修复轮

```
blocking_count > 0 → 进入修复轮（最多 2 轮）

修复轮流程：
  round = 0
  while blocking_count > 0 and round < 2:
    1. 从 review_results.json 提取 blocking issues 文本：
       python -c "import json; d=json.load(open('${PROJECT_ROOT}/.webnovel/tmp/review_results.json')); [print(f\"- [{i.get('category','')}] {i.get('description','')} (位置: {i.get('location','')})\") for i in d.get('issues',[]) if i.get('severity')=='blocking']"

    2. Agent(chapter-writer-agent) 修复模式
       将提取的 issue 列表填入 prompt 的【审查反馈】部分
       prompt 明确指出："修复模式：只修改上述审查反馈指出的具体问题，不大面积重写。保留未涉及部分的原文。"

    3. Agent(reviewer) 重新审查
       → 覆盖更新 review_results.json

    4. review-pipeline 重新判定 blocking

    5. round += 1

  if blocking_count > 0:
    标记本章 failed，记录 blocking issues 到 batch_state，继续下一章
  else:
    阻塞已清除，继续 Step 7
```

---

### Step 7: Agent(data-agent) → 事实提取

**必须使用 Agent 工具调用 data-agent，不得跳过或手动模拟。**

```text
Agent(
  subagent_type: "data-agent",
  prompt: "chapter={N}; chapter_file=${CHAPTER_FILE}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。从正文提取事实，生成 .webnovel/tmp/ 下的 fulfillment_result.json、disambiguation_result.json、extraction_result.json；不直接写 state/index/summaries/memory。"
)
```

验证输出文件：

```bash
for f in fulfillment_result.json disambiguation_result.json extraction_result.json; do
  FP="${PROJECT_ROOT}/.webnovel/tmp/${f}"
  if [ ! -s "$FP" ]; then
    echo "❌ 缺失: $f"
  else
    echo "✅ $f ($(wc -c < $FP) bytes)"
  fi
done
```

任一缺失→重试 Agent 调用 1 次。仍缺失→标记 failed 并停止。

---

### Step 8: chapter-commit + 验证投影 + Git 备份

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-commit \
  --chapter {N} \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```

自动判定：blocking_count>0 或 missed_nodes 非空 或 pending 非空 → rejected，否则 accepted。

验证投影：projection_status 五项（state/index/summary/memory/vector）全部 done 或 skipped。

失败隔离：commit 未生成→重跑 2 次。projection 失败→只补跑失败项。不回退 Step 1-7。

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" backup \
  --chapter {N} \
  --chapter-title "{title}"
```

备份必须以解析后的 `PROJECT_ROOT` 为准，禁止从工作区父目录执行裸全量 Git add。

---

### Step 9: 更新 batch_state + 进度反馈

```bash
python -c "
import json, pathlib, datetime

# 读取审查得分
review_path = '${PROJECT_ROOT}/.webnovel/tmp/review_results.json'
score = json.load(open(review_path)).get('score', 0)

# 更新 batch_state
p = pathlib.Path('$BATCH_STATE')
s = json.loads(p.read_text())
s['completed_chapters'].append($N)
s['current_chapter'] = $N + 1
s['chapter_results'][str($N)] = {
    'status': 'success',
    'score': score,
    'words': $WORDS,
    'completed_at': datetime.datetime.utcnow().isoformat() + 'Z'
}
p.write_text(json.dumps(s, ensure_ascii=False, indent=2))

# 验证写入
assert $N in s['completed_chapters'], '写入验证失败'
print('✅ batch_state 已验证')
"
```

更新失败→重试 3 次。仍失败→停止。

```
✅ 第{N}章完成 | 审查: {SCORE}/100 | 字数: {WORDS} | 进度: {N-S+1}/{E-S+1}
```

---

## 分批暂停点（每 3 章）

```
当 (N - S + 1) % 3 == 0 且 N != E:
  ═══════════════════════════════════════
  🚦 已完成第 {S}-{N} 章（共 {N-S+1} 章）

  章节摘要：
  第{S}章 ✅ score:{xx} words:{xxxx}
  ...

  batch_state 完整性: ✅

  确认下一步：
  - "继续" 撰写第 {N+1}-{min(N+3, E)} 章
  - "停止" 保存进度并退出
  ═══════════════════════════════════════

若用户设置 AUTO_CONTINUE=1，跳过暂停直接继续。
```

---

## 循环完成：汇总报告

```
═══════════════════════════════════════
📊 批量写作完成

| 章节 | 状态 | 得分 | 字数 |
|------|------|------|------|
| ... | ... | ... | ... |

总计: {count} 章 | 成功: {success} | 失败: {failed}
平均得分: {avg}
═══════════════════════════════════════
```

更新 batch_state status = "completed"。

---

## 失败处理速查

| 场景 | 处理 | 阻断 |
|------|------|------|
| 环境变量未设置/PROJECT_ROOT 错误 | 立即停止 | 阻断 |
| 上章完整性失败 | 立即停止 | 阻断 |
| preflight 失败（批前） | 修复环境→重试1次→停止 | 阻断 |
| 合同树刷新失败 | 检查缺失文件→修复→重试1次→停止 | 阻断 |
| context-agent 失败 | 重试1次→停止 | 阻断 |
| chapter-writer-agent 失败 | 重试1次→停止 | 阻断 |
| 字数不足 | 重试 chapter-writer-agent | 章内 |
| reviewer blocking(1-2轮) | 提取反馈→回传 chapter-writer-agent→重审 | 章内 |
| reviewer blocking(3轮) | 标记failed→继续 | 否 |
| data-agent 失败 | 重试1次→标记failed并停止 | 阻断 |
| chapter-commit 失败 | 修复→重试(3次)→停止 | 阻断 |
| projection 失败 | 只补跑失败项 | 章内 |
| batch_state 更新失败 | 重试3次→停止 | 阻断 |
```

- [ ] **Step 2: 确认修改只影响批量模式**

```bash
# 验证 webnovel-write SKILL.md 未被修改
git diff --name-only HEAD | grep -v webnovel-write-batch | grep -v chapter-writer-agent
# 预期输出为空（仅 batch 相关文件被修改）
```

- [ ] **Step 3: Commit**

```bash
git add .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "refactor(batch): isolate per-chapter writing to chapter-writer-agent

Move drafting+polishing from main thread to chapter-writer-agent subagent
for clean context per chapter. Fixes quality degradation observed in batch mode
from chapter 2 onwards.

Single-chapter mode (webnovel-write) unchanged."
```
```

- [ ] **Step 2: Commit** — 见上方 commit 命令

---

### Task 3: 验证单章模式不受影响

**Files:** 无改动，纯验证

- [ ] **Step 1: 确认 webnovel-write SKILL.md 未被修改**

```bash
git diff HEAD~2 -- .opencode/skills/webnovel-write/SKILL.md
# 预期：无输出（文件未变更）
```

- [ ] **Step 2: 确认现有 agent 定义未被修改**

```bash
git diff HEAD~2 -- .opencode/agents/context-agent.md .opencode/agents/reviewer.md .opencode/agents/data-agent.md
# 预期：无输出
```

- [ ] **Step 3: 确认 batch_state.json schema 未变**

对比 spec `2026-05-06-batch-writer-design.md` 中定义的 schema 与新 skill 中的 batch_state 操作——字段名和结构一致（task_id, range, status, current_chapter, completed_chapters, failed_chapters, chapter_results）。

---

### Task 4: 手动端到端验证

**Files:** 无改动

- [ ] **Step 1: 单章模式冒烟**

执行 `/webnovel-write` 写一章，确认流程正常：context-agent → 起草 → reviewer → 润色 → data-agent → commit → 备份。预期和改前行为一致。

- [ ] **Step 2: 批量模式 3 章测试**

执行 `/webnovel-write-batch` 连续写 3 章，观察：
- 每章 chapter-writer-agent 是否在干净上下文中执行
- 第 2-3 章正文质量是否与第 1 章持平
- 审查 feedback 修复轮是否正常工作
- batch_state 是否正确跟踪进度

- [ ] **Step 3: 修复轮验证**

在批量模式中构造一个 blocking issue（如故意违反禁区），观察：
- reviewer 是否检测到 blocking
- 编排器是否正确提取 issue 并回传 chapter-writer-agent
- 修复后重审是否通过
```

---

## Self-Review

Spec coverage check:
- ✅ chapter-writer-agent 定义 → Task 1
- ✅ 编排器流程重写 → Task 2
- ✅ 审查反馈传递机制 → Task 2 Step 6
- ✅ 修复轮流程 → Task 2 Step 6
- ✅ 单章模式不动 → Task 3
- ✅ 3 章暂停点 → Task 2 分批暂停点部分

No placeholders, TBDs, or TODO items found.
