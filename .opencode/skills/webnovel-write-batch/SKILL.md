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
| 2 | 跳过审查 | 每章必须运行 reviewer Agent + review-pipeline。blocking=false 也不能跳过 |
| 3 | 用 Read 工具代替验证命令 | 每步后必须运行 bash 验证命令（test -s / ls / python -c） |
| 4 | "稍后更新" batch_state | 每章完成后立即用 python -c 写 JSON，写完后重新读取验证 |
| 5 | 章数多了开始跳步/简化流程 | 每章必须完整执行 webnovel-write 的 7 步，不得缩减。3 章后强制暂停 |
| 6 | 子代理失败后假装成功 | 每个 Agent() 调用后检查输出文件是否存在且非空。失败重试 1 次→仍失败则停止 |
| 7 | 审查和润色合并执行 | 先拿到审查结果 → 再修改正文。禁止在审查前修改 |
| 8 | 用简化版代替完整单章流程 | 批量中每章 = 单章 webnovel-write 完整流程。不得以"批量模式"为借口降级 |

## 环境设置

```bash
export WORKSPACE_ROOT="${PWD}"
export SCRIPTS_DIR="${PWD}/.opencode/scripts"
export SKILL_ROOT="${PWD}/.opencode/skills/webnovel-write"
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
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

> **每章 = webnovel-write 完整流程。不简化、不跳步、不合步。**

### Step 0: 环境变量验证（每章开始前强制）

```bash
test -n "$PROJECT_ROOT" || { echo "❌ PROJECT_ROOT 未设置"; exit 1; }
test -n "$SCRIPTS_DIR" || { echo "❌ SCRIPTS_DIR 未设置"; exit 1; }
test -d "$PROJECT_ROOT" || { echo "❌ PROJECT_ROOT 目录不存在: $PROJECT_ROOT"; exit 1; }
test -d "${PROJECT_ROOT}/.webnovel" || { echo "❌ ${PROJECT_ROOT}/.webnovel 不存在，PROJECT_ROOT 可能不正确"; exit 1; }
echo "✅ PROJECT_ROOT=${PROJECT_ROOT}"
```

> 每章开始前重现此清单：
> ```
> □ 0. 环境变量验证
> □ A. 上章完整性检查（N > S 时）
> □ 1. 刷新合同树
> □ 2. context-agent → 写作任务书
> □ 3. 起草正文（2000-2500字）
> □ 4. 审查（reviewer Agent + review-pipeline）
> □ 5. 润色（polish-guide + typesetting + style-adapter）
> □ 6. 提交（data-agent → chapter-commit → 验证投影）
> □ 7. Git 备份
> □ B. 更新 batch_state
> □ C. 进度反馈
> ```

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

### Step 2: context-agent → 写作任务书

**必须使用 Agent 工具调用 context-agent，不得由主流程自行整理。**

```text
Agent(
  subagent_type: "context-agent",
  prompt: "chapter={N}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}; storage_path=${PROJECT_ROOT}/.webnovel; state_file=${PROJECT_ROOT}/.webnovel/state.json（projection/read-model，仅兼容读取）。先 research，再按 本章硬性约束→CBN/CPNs/CEN→本章禁区→风格指引→dynamic_context补充参考 的顺序输出五段写作任务书。"
)
```

产物：一份写作任务书，能独立支撑 Step 3 起草。验证任务书非空且包含"硬性约束"或"CBN"字样。若失败或返回空，重试 1 次。仍失败→停止。

---

### Step 3: 起草正文

只根据任务书起草。不加载 core-constraints/anti-ai-guide（已内化到任务书）。只输出纯正文，无占位符。有结构化节点时围绕 CBN→CPNs→CEN 展开。中文思维写作。

```bash
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter $N)
CHAPTER_FILE="${PROJECT_ROOT}/${CHAPTER_PATH}"

# 写入正文后验证
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

### Step 4: 审查

#### 4.1 reviewer Agent

**必须使用 Agent 工具调用 reviewer，不得由主流程伪造审查 JSON。**

```text
Agent(
  subagent_type: "reviewer",
  prompt: "chapter={N}; chapter_file=${CHAPTER_FILE}; project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。严格输出 reviewer schema JSON，并保存到 ${PROJECT_ROOT}/.webnovel/tmp/review_results.json。"
)
```

#### 4.2 review-pipeline

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
print(f'blocking: {d.get(\"blocking\",\"unknown\")}, score: {d.get(\"score\",\"unknown\")}')
"
```

blocking=true → 修复后重审，不进 Step 5。

---

### Step 5: 润色

加载 polish-guide、typesetting、style-adapter：
```bash
POLISH_GUIDE="${SKILL_ROOT}/polish-guide.md"
TYPESETTING="${SKILL_ROOT}/typesetting.md"
STYLE_ADAPTER="${SKILL_ROOT}/style-adapter.md"
```

顺序：修复非 blocking issue → 风格适配 → 排版 → Anti-AI 终检。

只改表达不改事实。`anti_ai_force_check=fail` 时不进 Step 6。

**blocking issue 处理：**
```
读取 review_results.json:
  if blocking_issues 数量 > 0:
    1. 修复正文中每个 blocking issue
    2. 重新运行 Step 4（reviewer Agent + review-pipeline）
    3. 若仍有 blocking → 再修再审（最多 2 轮）
    4. 2 轮后仍有 blocking → 标记本章 failed，记录原因，继续下一章

  if blocking = 0:
    针对 suggestions 做轻量润色（措辞/节奏/钩子强度）
```

---

### Step 6: 提交

#### 6.1 data-agent 提取事实

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

#### 6.2 chapter-commit

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-commit \
  --chapter {N} \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json"
```

自动判定：blocking_count>0 或 missed_nodes 非空 或 pending 非空 → rejected，否则 accepted。

#### 6.3 验证投影

projection_status 五项（state/index/summary/memory/vector）全部 done 或 skipped。

chapter_status 由 projection writer 自动推进：accepted→committed，rejected→rejected。

#### 6.4 失败隔离

commit 未生成→重跑 6.2。projection 失败→只补跑失败项。不回退 Step 1-5。

---

### Step 7: Git 备份

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" backup \
  --chapter {N} \
  --chapter-title "{title}"
```

备份必须以解析后的 `PROJECT_ROOT` 为准，禁止从工作区父目录执行裸全量 Git add。

---

### Step B: 更新 batch_state

```bash
python -c "
import json, pathlib, datetime, os

# 1) 读取审查得分
review_path = os.path.join('${PROJECT_ROOT}', '.webnovel', 'tmp', 'review_results.json')
score = json.load(open(review_path)).get('score', 0)

# 2) 更新 batch_state
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

# 3) 验证写入
assert $N in s['completed_chapters'], '写入验证失败'
print('✅ batch_state 已验证')
"
```

更新失败→重试 3 次。仍失败→停止。

---

### Step C: 进度反馈

```
✅ 第{N}章完成 | 审查: {SCORE}/100 | 字数: {WORDS} | 进度: {N-S+1}/{E-S+1}
```

---

## 充分性闸门（每章）

1. 正文文件存在且非空
2. 审查已落库
3. blocking=true 必须停在 Step 4
4. anti_ai_force_check=pass
5. accepted CHAPTER_COMMIT，projection 五项 done/skipped
6. chapter_status=committed（projection 自动推进）

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
| 字数不足 | 补充→重检 | 章内 |
| reviewer blocking(1-2轮) | 修→审（Agent + pipeline） | 章内 |
| reviewer blocking(3轮) | 标记failed→继续 | 否 |
| 润色 anti_ai=fail | 修复→重检 | 章内 |
| data-agent 失败 | 重试1次→标记failed并停止 | 阻断 |
| chapter-commit 失败 | 修复→重试(3次)→停止 | 阻断 |
| projection 失败 | 只补跑失败项 | 章内 |
| batch_state 更新失败 | 重试3次→停止 | 阻断 |
