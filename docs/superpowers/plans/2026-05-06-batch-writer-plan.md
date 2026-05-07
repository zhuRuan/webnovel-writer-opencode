# Batch Writer Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写 webnovel-write-batch SKILL.md，实现 7 条 Anti-Laziness 硬规则 + 10 步逐章控制流 + batch_state 断点恢复。

**Architecture:** 纯 skill 定义文件。主 AI 读此文件后按 10 步循环执行每章：context-agent(子代理) → 起草(主AI) → reviewer(子代理) → 润色(主AI) → data-agent(子代理) → commit → batch_state 更新。

**Tech Stack:** 无新依赖。使用现有 Agent 工具 + bash 命令 + python -c 片段。

---

### Task 1: 重写 webnovel-write-batch SKILL.md

**Files:**
- Modify: `.opencode/skills/webnovel-write-batch/SKILL.md`

This is a complete rewrite. The old file is ~600 lines of legacy batch logic. Replace with the new spec-driven skill.

- [ ] **Step 1: 读取当前 SKILL.md 确认 frontmatter 可复用部分**

```bash
head -20 .opencode/skills/webnovel-write-batch/SKILL.md
```

- [ ] **Step 2: 写入新 SKILL.md**

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
| 1 | 口头描述代替 `Agent()` 调用 | 必须使用 Agent 工具调用 context-agent / reviewer / data-agent |
| 2 | 跳过审查 | 每章必须运行 reviewer。blocking=false 也不能跳过 |
| 3 | 用 Read 工具代替验证命令 | 每步后必须运行 bash 验证命令（test -s / ls / python -c） |
| 4 | "稍后更新" batch_state | 每章完成后立即用 python -c 写 JSON，写完后重新读取验证 |
| 5 | 章数多了开始跳步 | 每章开始前重现 Step 0-10 清单。3 章后强制暂停 |
| 6 | 子代理失败后假装成功 | 每个 Agent() 调用后检查输出文件是否存在且非空。失败重试 1 次→仍失败则停止 |
| 7 | 审查和润色合并执行 | 先拿到审查结果 → 再修改正文。禁止在审查前修改 |

## 环境设置

```bash
export WORKSPACE_ROOT="${PWD}"
export SCRIPTS_DIR="${PWD}/.opencode/scripts"
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
```

## Step 0: 解析章节范围

- "写第9-15章" → S=9, E=15
- "连续写3章" → 读 .webnovel/state.json 的 current_chapter，S=N+1, E=N+3
- "批量写5章" → 同上，E=S+4

若无法解析，询问用户明确范围。上限 20 章（可通过 --force 参数绕过）。

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

## 逐章循环（For chapter = S to E）

> 每章执行前，先重现 Step 1-9 清单。长循环中注意力衰减是真实存在的，清单是最后防线。

```
对于第 N 章（N = S, S+1, ..., E）：

  Step 1 □ 上章完整性检查（N > S 时）
  Step 2 □ context-agent → 写作任务书
  Step 3 □ 起草正文（2000-2500字）
  Step 4 □ reviewer → 审查报告
  Step 5 □ 评估 + 修复
  Step 6 □ data-agent → 事实提取
  Step 7 □ chapter-commit
  Step 8 □ 更新 batch_state
  Step 9 □ 进度反馈
```

---

### Step 1: 上章完整性检查（N > S 时强制，不可跳过）

```bash
if [ "$N" -gt "$S" ]; then
  PREV=$((N - 1))
  
  # 检查 N-1 章文件存在
  CHAPTER_FILE=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter $PREV)
  if [ ! -s "${PROJECT_ROOT}/${CHAPTER_FILE}" ]; then
    echo "❌ 第${PREV}章文件缺失。立即停止。"
    echo "   请先修复第${PREV}章再继续。"
    exit 1
  fi

  # 检查 batch_state 包含 N-1
  IN_BATCH=$(python -c "import json; s=json.load(open('$BATCH_STATE')); print($PREV in s.get('completed_chapters',[]))")
  if [ "$IN_BATCH" != "True" ]; then
    echo "❌ 第${PREV}章未在 batch_state 中标记完成。立即停止。"
    exit 1
  fi

  echo "✅ 第${PREV}章完整性检查通过"
fi
```

跳过此步的后果：前一章数据未落盘，继续写会导致状态永久断裂。

---

### Step 2: context-agent → 写作任务书

**使用 Agent 工具调用 context-agent，不得口头描述代替。调用后检查输出。**

```
Agent(
  subagent_type: "context-agent",
  prompt: "chapter=N; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}; storage_path=${PROJECT_ROOT}/.webnovel; state_file=${PROJECT_ROOT}/.webnovel/state.json（projection/read-model）。先 research，再按 本章硬性约束→CPNs/CEN→本章禁区→风格指引→dynamic_context补充参考 的顺序输出五段写作任务书。"
)
```

验证任务书非空且包含关键段落。若失败或返回空，重试 1 次。仍失败→停止。

---

### Step 3: 起草正文

主 AI 基于任务书 + 章纲写正文，2000-2500 字。

```bash
# 确定章节文件路径
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter $N)

# 写入正文后验证
CHAPTER_FILE="${PROJECT_ROOT}/${CHAPTER_PATH}"
test -s "$CHAPTER_FILE" || echo "❌ 章节文件为空"

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

字数不足时补充，直到 ≥1500。

---

### Step 4: reviewer → 审查

**使用 Agent 工具调用 reviewer，不得跳过。blocking=false 也不能跳过。**

```
Agent(
  subagent_type: "reviewer",
  prompt: "chapter=N; chapter_file=${PROJECT_ROOT}/${CHAPTER_PATH}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。严格输出 reviewer schema JSON，并保存到 ${PROJECT_ROOT}/.webnovel/tmp/review_results.json。"
)
```

验证审查结果：
```bash
python -c "
import json
d = json.load(open('${PROJECT_ROOT}/.webnovel/tmp/review_results.json'))
assert isinstance(d, dict), 'review_results 不是 JSON 对象'
print(f'blocking: {d.get(\"blocking\",\"unknown\")}, score: {d.get(\"score\",\"unknown\")}')
"
```

---

### Step 5: 评估 + 修复

```
读取 review_results.json:
  if blocking_issues 数量 > 0:
    1. 修复正文中每个 blocking issue
    2. 重新运行 Step 4（reviewer）
    3. 若仍有 blocking → 再修再审（最多 2 轮）
    4. 2 轮后仍有 blocking → 标记本章 failed，记录原因，继续下一章
  
  if blocking = 0（或 non-blocking only）:
    针对 suggestions 做轻量润色（措辞/节奏/钩子强度）
```

这是创意判断环节，不自动化。

---

### Step 6: data-agent → 事实提取

**使用 Agent 工具调用 data-agent，不得跳过。**

```
Agent(
  subagent_type: "data-agent",
  prompt: "chapter=N; chapter_file=${PROJECT_ROOT}/${CHAPTER_PATH}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。从正文提取事实，生成 .webnovel/tmp/ 下的 fulfillment_result.json、disambiguation_result.json、extraction_result.json；不直接写 state/index/summaries/memory。"
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

### Step 7: chapter-commit

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-commit \
  --chapter $N \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```

检查输出包含 `accepted`。失败→检查 JSON 格式→修复→重试(最多3次)。仍失败→标记 failed 并停止。

---

### Step 8: 更新 batch_state

```bash
SCORE=$(python -c "import json; print(json.load(open('${PROJECT_ROOT}/.webnovel/tmp/review_results.json')).get('score',0))")

python -c "
import json, pathlib, datetime
p = pathlib.Path('$BATCH_STATE')
s = json.loads(p.read_text())
s['completed_chapters'].append($N)
s['current_chapter'] = $N + 1
s['chapter_results'][str($N)] = {
    'status': 'success',
    'score': $SCORE,
    'words': $WORDS,
    'completed_at': datetime.datetime.utcnow().isoformat() + 'Z'
}
p.write_text(json.dumps(s, ensure_ascii=False, indent=2))
"

# 验证写入
python -c "import json; s=json.load(open('$BATCH_STATE')); assert $N in s['completed_chapters'], '写入验证失败'; print('✅ batch_state 已验证')"
```

更新失败→重试 3 次。仍失败→停止。

---

### Step 9: 进度反馈

```
✅ 第{N}章完成 | 审查: {SCORE}/100 | 字数: {WORDS} | 进度: {N-S+1}/{E-S+1}
```

---

### Step 10: 分批暂停点（每 3 章）

```
当 (N - S + 1) % 3 == 0 且 N != E:
  ═══════════════════════════════════════
  🚦 已完成第 {S}-{N} 章（共 {N-S+1} 章）
  
  章节摘要：
  第{S}章 ✅ score:{xx} words:{xxxx}
  第{S+1}章 ✅ score:{xx} words:{xxxx}
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

## 失败处理速查

| 场景 | 处理 | 阻断 |
|------|------|------|
| 上章完整性失败 | 立即停止 | 阻断 |
| context-agent 失败 | 重试1次→停止 | 阻断 |
| 字数不足 | 补充→重检 | 章内 |
| reviewer blocking(1-2轮) | 修→审 | 章内 |
| reviewer blocking(3轮) | 标记failed→继续 | 否 |
| data-agent 失败 | 重试1次→标记failed并停止 | 阻断 |
| chapter-commit 失败 | 修复→重试(3次)→停止 | 阻断 |
| batch_state 更新失败 | 重试3次→停止 | 阻断 |
```

- [ ] **Step 3: 验证 skill frontmatter 格式**

```bash
python -c "
import yaml
text = open('.opencode/skills/webnovel-write-batch/SKILL.md').read()
fm = yaml.safe_load(text.split('---')[1])
assert fm['name'] == 'webnovel-write-batch'
assert 'compatibility' in fm
assert 'allowed-tools' in fm
print('frontmatter OK')
"
```

- [ ] **Step 4: 验证 skill 内容包含所有必须项**

```bash
SKILL=".opencode/skills/webnovel-write-batch/SKILL.md"
# 检查硬规则逐条存在
grep -q "口头描述代替" "$SKILL" && echo "✅ Rule 1" || echo "❌ Rule 1 missing"
grep -q "跳过审查" "$SKILL" && echo "✅ Rule 2" || echo "❌ Rule 2 missing"
grep -q "验证命令" "$SKILL" && echo "✅ Rule 3" || echo "❌ Rule 3 missing"
grep -q "batch_state" "$SKILL" && echo "✅ Rule 4" || echo "❌ Rule 4 missing"
grep -q "每章开始前" "$SKILL" && echo "✅ Rule 5" || echo "❌ Rule 5 missing"
grep -q "重试 1 次" "$SKILL" && echo "✅ Rule 6" || echo "❌ Rule 6 missing"
grep -q "审查和润色合并" "$SKILL" && echo "✅ Rule 7" || echo "❌ Rule 7 missing"
# 检查 10 步都存在
for step in "Step 1" "Step 2" "Step 3" "Step 4" "Step 5" "Step 6" "Step 7" "Step 8" "Step 9"; do
  grep -q "$step" "$SKILL" && echo "✅ $step" || echo "❌ $step missing"
done
```

- [ ] **Step 5: 运行 prompt integrity test**

```bash
cd .opencode/scripts && python -m pytest data_modules/tests/test_prompt_integrity.py -q --no-cov -p no:cacheprovider -p no:asyncio -k "batch"
```

- [ ] **Step 6: Commit**

```bash
git add .opencode/skills/webnovel-write-batch/SKILL.md
git commit -m "feat(batch): rewrite webnovel-write-batch skill with anti-laziness rules and subagent orchestration"
```
