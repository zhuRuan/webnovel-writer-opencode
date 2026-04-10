---
name: webnovel-write-batch
description: |
  批量写作技能。当用户要求"连续写第X-Y章"、"批量生成章节"、"一次写N章"时使用。
  由 Agent 在单次回复中循环执行，支持断点恢复和灵活审查级别。
allowed-tools: Task Read Write Bash
---

# 批量写作技能

## 🧠 Agent 执行前必读

**触发条件**：用户输入包含以下表述时，按本技能执行：
- "连续写N章"
- "写第X-Y章"
- "批量写X-Y章"
- "一次写N章"
- 执行 `/webnovel-write-batch` 命令

**核心原则**：
1. 在**本次回复**内完成所有章节的生成，**不要**多次调用单章命令
2. 每完成一章立即更新 `.batch_state.json`，支持随时中断恢复
3. 循环结束后输出汇总报告

**禁止行为**：
- ❌ 在单次回复中多次调用 `/webnovel-write` 命令
- ❌ 每章单独输出"是否继续写下一章？"
- ❌ 在无用户指令时自动启动下一批次

---

## 参数解析规则

| 用户表述示例 | 解析逻辑 |
|-------------|---------|
| "连续写2章" | 读取 `state.json` 中 `current_chapter`，范围 = `current+1` 到 `current+2` |
| "写第53-60章" | 范围 = `53` 到 `60` |
| "批量写53-60章" | 同上 |

**审查级别选项**：
| 选项 | 说明 |
|------|------|
| `--review-level minimal` | 只执行核心审查器（一致性、连贯性、OOC） |
| `--review-level standard` | 核心 + 条件触发审查器（默认） |
| `--review-level full` | 强制执行所有审查器 |

---

## 快速参考

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--range` | 章节范围，如 53-60 | 自动解析 |
| `--review-level` | 审查级别 | standard |
| `--resume` | 从断点恢复 | - |
| `--force` | 绕过 20 章上限 | - |

---

## 执行清单

### Step 0: 预检与初始化

#### 0.1 解析章节范围

1. 从用户输入提取起始章 `S` 和结束章 `E`
2. 若用户说"连续写N章"，读取 `state.json` 获取 `current_chapter`，设 `S = current + 1`
3. 若无法解析，询问用户明确范围

#### 0.2 检查大纲存在性

```bash
# 检查章节大纲目录
OUTLINE_DIR="${PROJECT_ROOT}/大纲"

# 抽样检查前3章和后3章的大纲
for ch in $(seq "$S" "$((S+2))" "$E" | head -6); do
    CHAPTER_OUTLINE="${OUTLINE_DIR}/第${ch}章.md"
    if [ ! -f "$CHAPTER_OUTLINE" ]; then
        echo "⚠️ 缺少大纲：第${ch}章"
    fi
done
```

#### 0.3 检测断点

```bash
BATCH_STATE_FILE=".opencode/skills/webnovel-write-batch/.batch_state.json"

if [ -f "$BATCH_STATE_FILE" ]; then
    STATUS=$(python -c "import json; d=json.load(open('${BATCH_STATE_FILE}')); print(d.get('status'))")
    if [ "$STATUS" = "running" ]; then
        echo "检测到未完成的批量任务"
        # 询问用户是否恢复或重新开始
    fi
fi
```

---

### Step 1: 初始化批量状态

创建或更新 `.batch_state.json`：

```json
{
  "task_id": "batch_YYYYMMDD_HHMM",
  "range": {"start": S, "end": E},
  "status": "running",
  "current_chapter": S,
  "completed_chapters": [],
  "failed_chapters": [],
  "chapter_results": {},
  "metadata": {
    "review_level": "standard",
    "created_at": "ISO timestamp"
  }
}
```

---

### Step 2: 章节循环（核心）

> **重要**：以下循环体在**同一个回复**中连续执行。每完成一章输出进度并更新状态文件。

#### 循环变量

```
for chapter in [S, S+1, ..., E]:
```

---

#### 2.1 获取上下文

```markdown
Task:
  subagent: context-agent
  prompt: |
    为第 {chapter} 章收集创作上下文。

    ## 项目信息
    - 项目根：{PROJECT_ROOT}
    - 当前章节：{chapter}
    - 总范围：第 {S} 章到第 {E} 章

    ## 任务
    1. 读取本章大纲：{OUTLINE_DIR}/第{chapter}章.md
    2. 读取总纲：{PROJECT_ROOT}/大纲/总纲.md
    3. 读取 state.json 获取项目状态
    4. 如有前两章，读取其结尾 2000 字用于承接

    ## 输出
    输出创作执行包，包含：
    - 7 板块任务书
    - Context Contract 全字段
    - 写作执行包（章节节拍、不可变事实清单、禁止事项）
```

---

#### 2.2 起草正文

- 基于简报撰写 **2000-2500 字**章节正文
- 规则：
  - 开头：承接上章钩子，建立本章基调
  - 发展：通过冲突/行动推进剧情
  - 高潮：关键转折或爽点
  - 结尾：留下本章钩子，为下章铺垫

- 输出到章节文件：
```bash
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" \
    --project-root "${PROJECT_ROOT}" \
    chapter-path --chapter {chapter})
echo "$DRAFT_CONTENT" > "${PROJECT_ROOT}/${CHAPTER_PATH}"
```

---

#### 2.3 并行审查（核心审查器）

```markdown
Task 1:
  subagent: consistency-checker
  prompt: |
    对第 {chapter} 章执行设定一致性审查。
    - 章节文件：{PROJECT_ROOT}/{CHAPTER_PATH}
    - 项目根：{PROJECT_ROOT}

Task 2:
  subagent: continuity-checker
  prompt: |
    对第 {chapter} 章执行连贯性审查。
    - 章节文件：{PROJECT_ROOT}/{CHAPTER_PATH}
    - 项目根：{PROJECT_ROOT}

Task 3:
  subagent: ooc-checker
  prompt: |
    对第 {chapter} 章执行人物 OOC 审查。
    - 章节文件：{PROJECT_ROOT}/{CHAPTER_PATH}
    - 项目根：{PROJECT_ROOT}
```

---

#### 2.4 可选审查（条件触发）

```markdown
# 当 --review-level 不是 minimal 时执行
Task 4:
  subagent: reader-pull-checker
  prompt: |
    对第 {chapter} 章执行追读力审查。
    - 章节文件：{PROJECT_ROOT}/{CHAPTER_PATH}
    - 项目根：{PROJECT_ROOT}

Task 5:
  subagent: pacing-checker
  prompt: |
    对第 {chapter} 章执行节奏审查。
    - 章节文件：{PROJECT_ROOT}/{CHAPTER_PATH}
    - 项目根：{PROJECT_ROOT}
```

---

#### 2.5 润色定稿

1. 综合所有审查反馈
2. 修复 critical/high 问题
3. 执行 Anti-AI 检测
4. 生成最终正文，覆盖章节文件

---

#### 2.6 数据落盘与备份

```markdown
# Data Agent - 状态回写
Task:
  subagent: data-agent
  prompt: |
    处理第 {chapter} 章的数据回写。
    - 章节文件：{PROJECT_ROOT}/{CHAPTER_PATH}
    - 审查分数：{OVERALL_SCORE}
    - 项目根：{PROJECT_ROOT}
```

```bash
# Git 备份
cd "${PROJECT_ROOT}"
git add "${CHAPTER_PATH}" ".webnovel/state.json" ".webnovel/index.db"
git -c i18n.commitEncoding=UTF-8 commit -m "第{chapter}章: 写作完成"
```

---

#### 2.7 更新批量状态

```bash
python -c "
import json
with open('${BATCH_STATE_FILE}', 'r', encoding='utf-8') as f:
    state = json.load(f)

state['completed_chapters'].append({chapter})
state['current_chapter'] = {chapter} + 1
state['chapter_results']['{chapter}'] = {{
    'status': 'success',
    'score': {OVERALL_SCORE},
    'words': {WORD_COUNT},
    'completed_at': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
}}

with open('${BATCH_STATE_FILE}', 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
"
```

#### 2.8 进度反馈

```
[chapter/E] ✅ 第{chapter}章已完成 | 得分: {OVERALL_SCORE} | 字数: ~{WORD_COUNT}
```

---

### Step 3: 汇总报告

循环结束后：

1. 更新 `.batch_state.json`：`status = "completed"`

2. 输出汇总表格：

```
## 批量写作完成报告

| 章节 | 状态 | 得分 | 字数 |
|------|------|------|------|
| 第53章 | ✅ | 87 | 2340 |
| 第54章 | ✅ | 85 | 2280 |
| ... | ... | ... | ... |

**总计**：N 章节完成，平均得分 XX.X
```

3. Git 批量提交（可选）：

```bash
cd "${PROJECT_ROOT}"
git add -A
git -c i18n.commitEncoding=UTF-8 commit -m "批量写作完成: 第{S}-{E}章"
```

---

## 断点恢复（--resume）

### 检测与恢复流程

```
1. 检测 .batch_state.json 是否存在
2. 读取 status 字段
3. 若 status = "running":
   - 获取 current_chapter 作为新的 S
   - 继续执行 Step 2 循环
4. 若 status = "completed":
   - 显示汇总报告
   - 询问是否执行新批次
```

### 恢复选项

| 选项 | 说明 |
|------|------|
| 继续当前章节 | 从 `current_chapter` 重新开始 |
| 跳过已完成章节 | 从 `completed_chapters[-1] + 1` 开始 |
| 重新开始 | 删除 batch_state，重新执行 |

---

## 状态文件格式

详见 `references/batch-protocol.md`：

```json
{
  "task_id": "batch_20260410_103000",
  "range": {"start": 53, "end": 60},
  "mode": "standard",
  "status": "running|completed|failed|stopped",
  "current_chapter": 55,
  "completed_chapters": [53, 54],
  "failed_chapters": [],
  "chapter_results": {
    "53": {"status": "success", "score": 87, "words": 2340}
  }
}
```

---

## 失败处理

| 失败场景 | 处理方式 |
|---------|---------|
| 章节起草失败 | 记录到 `failed_chapters`，继续下一章 |
| 审查 critical | 记录 deviation，继续（除非 `--stop-on-fail`） |
| Data Agent 失败 | 重试 3 次，仍失败则跳过 |
| Git 提交失败 | 警告但继续，不阻断 |

---

## 充分性闸门

未满足以下条件不得结束流程：

1. ✅ 所有章节文件已生成且非空
2. ✅ 审查指标已落库
3. ✅ `.batch_state.json` 状态为 `completed`
4. ✅ Git 提交已完成

---

## 工作流终止规则

批量任务完成后**必须终止**，除非用户明确要求：

```
⚠️ 批量写作任务已终止

如需执行其他操作，请明确说明：
- "继续写下一批章节"
- "/webnovel-write-batch --range 61-68"
- "/webnovel-review --range 53-60"
```

---

## 故障排除

| 问题 | 解决方案 |
|------|---------|
| 批量上限报错 | 添加 `--force` 参数 |
| 大纲缺失警告 | 继续执行，使用通用章节结构 |
| 审查失败 | 检查 chapter_results 中的 issues |
| Git 提交失败 | 检查 Git 状态，可能是无新变更 |
| batch_state 损坏 | 删除后重新执行 |
