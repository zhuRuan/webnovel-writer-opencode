---
name: webnovel-write
description: |
  撰写网文章节。当用户说"写一章"、"写第X章"、"继续写"、"创作章节"、"起草章节"时，
  或执行/webnovel-write命令时**必须使用此 skill**。
  
  ## 触发条件
  - 单章操作："写第64章"、"写第5章"、"重写第64章"、"继续写下一章"
  - 注意：多章操作（如"写第64-70章"、"重写64-70章"、"连续写5章"）→ 使用 webnovel-write-batch
  
  ## 功能说明
  默认产出2000-2500字，包含完整流程：
  预检 → 上下文搜集 → 起草 → 审查 → 润色 → 数据回写 → Git备份 → 强制终止确认。
  **禁止在无用户明确指令情况下自动循环写下一章**。
 
allowed-tools: Read Write Edit Grep Bash Task
---

# 网文写作 Skill

## 快速参考

| 步骤 | 说明 |
|------|------|
| Step 0 | 预检（项目根、章节号、题材） |
| Step 1 | Context Agent（生成创作执行包） |
| Step 2 | 正文起草（含风格适配） |
| Step 3 | 统一审查（unified-reviewer → review-pipeline） |
| Step 4 | 润色（问题修复 → Anti-AI 终检） |
| Step 5 | Data Agent（实体提取 → state/index/memory 回写） |
| Step 6 | Git 备份 + 终止确认 |

**产出**：`正文/第N卷/第NNNN章-{title}.md`（自动适配卷目录）、`审查报告/第N章审查报告.md`、`.webnovel/summaries/chNNNN.md`

## 路径工具

获取章节文件的默认路径（自动适配卷目录）：
```bash
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter ${CHAPTER_NUM})
echo "章节文件将写入: ${CHAPTER_PATH}"
```

## 核心约束

- **禁止跳步**：审查（Step 3）必须由 Task 子代理执行
- **禁止并步**：每个 Step 独立执行
- **最小回滚**：失败只重跑该 Step，不回滚已通过步骤
- **中文写作**：禁止"先英后中"、英文结论话术

## References（按需加载）

| 文件 | 用途 | 触发 |
|------|------|------|
| `../../references/shared/core-constraints.md` | 写作硬约束 | Step 2 |
| `../../references/csv/裁决规则.csv` | 题材裁决元数据 | Step 0 / Step 2 |
| `../../references/csv/` (全表) | CSV 结构化知识检索 | Step 2 按需 |
| `references/polish-guide.md` | 问题修复、Anti-AI | Step 4 |
| `references/writing/typesetting.md` | 排版规则 | Step 4 |

## 工具

- **Read/Grep**：读取 state、大纲、参考文件
- **Bash**：运行 webnovel.py 命令
- **Task**：调用 context-agent、unified-reviewer、data-agent

## 执行流程

### Step 0：预检

```bash
# 确认项目根
SCRIPTS_DIR=".opencode/scripts"
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" preflight
PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" where)"

# 优先级：用户指定章节号 > state.json 自动计算
if [ -n "${CHAPTER_NUM}" ]; then
    echo "使用用户指定章节号: ${CHAPTER_NUM}"
else
    CHAPTER_NUM=$(python -X utf8 -c "
import json
s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json'))
print(s['progress'].get('current_chapter', 0) + 1)
")
    echo "从 state.json 自动获取下一章: ${CHAPTER_NUM}"
fi

# 确保章节号为整数
CHAPTER_NUM=$((10#${CHAPTER_NUM}))
echo "将撰写第 ${CHAPTER_NUM} 章"

# 读取题材
GENRE=$(python -X utf8 -c "
import json
s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json'))
print(s.get('project',{}).get('genre',''))
")
```

**硬门槛**：preflight 必须成功。

### Step 1：Context Agent

使用 Task 调用 `context-agent`，生成3层创作执行包。

```markdown
Task:
  subagent: context-agent
  prompt: |
    chapter={chapter_num}
    project_root=${PROJECT_ROOT}
    scripts_dir=${SCRIPTS_DIR}
    storage_path=${PROJECT_ROOT}/.webnovel
    state_file=${PROJECT_ROOT}/.webnovel/state.json
```

硬要求：
- 若 `state` 或大纲不可用，立即阻断并返回缺失项。
- 输出必须包含3层执行包：任务书（8板块）+ Context Contract + 直写提示词。

### Step 2：正文起草（含风格适配）

**CSV 结构化知识检索**（按需触发）：
```bash
python -X utf8 "${SCRIPTS_DIR}/reference_search.py" --skill write --table "场景写法" --query "战斗描写" --genre "${GENRE}" --max-results 3
python -X utf8 "${SCRIPTS_DIR}/reference_search.py" --skill write --table "裁决规则" --query "${GENRE}" --max-results 1
```

执行前加载：
```bash
cat "${SKILL_ROOT}/../../references/shared/core-constraints.md"

# 获取章节文件的默认路径（自动适配卷目录）
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter ${CHAPTER_NUM})
echo "章节文件将写入: ${CHAPTER_PATH}"
```

硬要求：
- 只输出纯正文到 `${CHAPTER_PATH}`。
- **字数下限（按章节类型）**：
  - 常规推进章：≥1500字
  - 过渡章：≥1000字
  - 高潮章/战斗章：≥2000字
- 默认 2000-2500 字；大纲/用户更高要求时从之。
- 禁止占位符正文。保留上章钩子承接。

**网文风格约束**：
- 长句（>40字）拆分，避免连续长句
- 抽象判断 → 动作/反应/代价
- 删除"总结式旁白"和大段纯解释
- 章内至少 1 个明确推进点
- 开头尽早进入冲突（前 200-400 字）
- 章末设置未闭合问题/期待锚点
- 微兑现按章型安排 1-3 次

AI痕迹预防：
- "非常愤怒" → "动作+生理+决策"三段式
- "总而言之/可以说" → 直接结论动作
- 连续三句同句式时改至少一处为短句爆点

章节类型适配：

| 类型 | 字数下限 | 字数上限 | 爽点要求 | 微兑现次数 |
|------|---------|---------|---------|-----------|
| 常规推进章 | 1500 | 2500 | ≥1个爽点 | 1-3 |
| 过渡章 | 1000 | 1500 | 0-1次小爽点 | 0-1 |
| 高潮/战斗章 | 2000 | 4000 | ≥1个大爽点 | 3-5 |

### Step 3：统一审查

使用 Task 调用 `unified-reviewer` agent：

```markdown
Task:
  subagent: unified-reviewer
  prompt: |
    chapter={chapter_num}; chapter_file=${CHAPTER_PATH};
    project_root=${PROJECT_ROOT}; scripts_dir=${SCRIPTS_DIR}。
    严格输出 reviewer schema JSON，并保存到 ${PROJECT_ROOT}/.webnovel/tmp/review_results.json。
```

unified-reviewer 覆盖 6 维度：设定一致性 / 时间线 / 叙事连贯 / 角色一致性 / 逻辑 / AI味。

**审查流水线**：
```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline \
  --chapter ${CHAPTER_NUM} \
  --review-results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --metrics-out "${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json" \
  --report-file "审查报告/第${CHAPTER_NUM}章审查报告.md"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" index save-review-metrics \
  --data "@${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json"
```

`blocking=true` → 修复后重审，不进 Step 4。

### Step 4：润色（条件执行）

**条件**：`blocking=true` 必须已修复。仅有 `high/medium/low` issue 时执行修复。

加载：
```bash
cat "${SKILL_ROOT}/references/polish-guide.md"
cat "${SKILL_ROOT}/references/writing/typesetting.md"
```

执行顺序：
1. 修复 blocking issue（若存在）
2. 修复 high/medium issue
3. 执行 Anti-AI 全文终检
4. 字数终检（达标后才能输出）

输出：
- 润色后正文（覆盖章节文件）
- 变更摘要（修复项、anti_ai_force_check、word_count）

### Step 5：Data Agent

使用 Task 调用 `data-agent`：

```markdown
Task:
  subagent: data-agent
  prompt: |
    chapter=${CHAPTER_NUM}
    chapter_file=${CHAPTER_PATH}
    project_root=${PROJECT_ROOT}
    scripts_dir=${SCRIPTS_DIR}
    storage_path=${PROJECT_ROOT}/.webnovel
    state_file=${PROJECT_ROOT}/.webnovel/state.json
```

Data Agent 执行：实体提取 → 消歧 → 写入 state.json / index.db / 摘要 / 向量索引。

检查产物（最小白名单）：
- `.webnovel/state.json`
- `.webnovel/index.db`
- `.webnovel/summaries/ch{chapter_padded}.md`

### Step 6：Git 备份 + 终止确认

```bash
git add .
git -c i18n.commitEncoding=UTF-8 commit -m "第${CHAPTER_NUM}章: ${title}"
```

```bash
if [ -z "${AUTO_CONTINUE}" ]; then
    echo "========================================"
    echo "⚠️  工作流终止，等待用户明确指令"
    echo "========================================"
    echo "如需继续写下一章，请明确说："
    echo "  - '写第${NEXT_CHAPTER}章'"
    echo "  - '继续写'"
    echo "========================================"
    return 0 2>/dev/null || true
fi
```

## 充分性闸门

1. 章节正文文件存在且非空
2. 审查已落库（review_metrics 已写入 index.db）
3. blocking=true 必须停在 Step 3
4. Step 5 已回写 state.json、index.db、summaries
5. 章节文件、摘要文件齐全

## 失败恢复

- 审查缺失 → 重跑 Step 3
- 润色失真 → 恢复 Step 2 输出并重做 Step 4
- 摘要/状态缺失 → 重跑 Step 5
