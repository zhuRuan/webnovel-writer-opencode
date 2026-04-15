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

### Step 2: 章节循环（严格版本）

> **重要**：严禁跳过任何子步骤。每章结束必须执行 2.6（数据落盘）和 2.7（状态更新）。

#### 2.0 上章完整性检查（强制防呆）

> **⚠️ 本检查在每章正文开始前必执行，不可跳过。**

在开始撰写第 N 章正文之前，必须执行以下验证：

```
上章完整性验证（第 N-1 章）：
1. 检查第 N-1 章的最终文件是否已存在于章节目录
2. 检查 .batch_state.json 中的 completed_chapters 数组是否包含 N-1
3. 检查 .webnovel/summaries/ch{prevChapter}.md 是否存在（Data Agent 产出）

验证条件：
- 若任一条件不满足 → 立即停止循环
- 错误信息：检测到第 N-1 章状态异常。请执行 /webnovel-write-batch --resume 修复。
- 禁止继续生成新章节
```

> **原理**：防止长循环后期注意力衰减时，Agent 忽略上一轮的状态更新错误。

---

#### 循环控制

```
for chapter in [S, S+1, ..., E]:
    # 1. 先执行 2.0 上章完整性检查
    if chapter > S:
        PREV = chapter - 1
        if PREV not in batch_state.completed_chapters:
            # 立即停止，不允许跳过
            print("❌ 检测到第", PREV, "章状态异常，必须修复后才能继续")
            break

    # 2. 执行 2.1-2.7（写作、审查、数据回写）
    ...

    # 3. 执行 2.8 分批暂停点（每 3 章）
    if (chapter - S + 1) % 3 == 0:
        触发分批暂停点
```

> **⚠️ 两层防护**：2.0 检查防止状态异常积累，2.8 暂停点防止注意力衰减。

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

- 基于简报撰写章节正文
- **字数下限（按章节类型，硬性约束）**：
  - 常规推进章：≥1500字
  - 过渡章：≥1000字
  - 高潮章/战斗章：≥2000字
- 字数低于下限必须补充至达标，方可进入审查
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

**字数检查（硬性）**：
```bash
# 计算实际字数
ACTUAL_WORDS=$(python -X utf8 -c "
import re
text = open('${PROJECT_ROOT}/${CHAPTER_PATH}', encoding='utf-8').read()
words = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
print(words)
")

# 确定字数下限（根据章节类型）
# 默认常规推进章1500字，若有大纲可读取章节类型
MIN_WORDS=1500
# 若为高潮章/战斗章设置为2000字
# 若为过渡章设置为1000字

echo "实际字数: $ACTUAL_WORDS"
echo "字数下限: $MIN_WORDS"

if [ "$ACTUAL_WORDS" -lt "$MIN_WORDS" ]; then
    echo "⚠️ 字数不足，需要补充内容..."
    # 字数不足时，在"未闭合问题"和"期待锚点"处补充
    # 补充策略：
    # 1. 扩展章末钩子描述
    # 2. 增加角色内心活动
    # 3. 补充场景细节描写
    # 4. 增加对话/动作描写
fi
```

1. **字数补充（若不足）**：优先在"未闭合问题"和"期待锚点"处补充
2. 综合所有审查反馈
3. 修复 critical/high 问题
4. 执行 Anti-AI 检测
5. 生成最终正文，覆盖章节文件
6. **字数终检**：润色后再次检查字数，达标后才能输出

---

#### 2.6 Data Agent - 状态与索引回写

> **⚠️ 强制要求**：本步骤**必须执行**，不得跳过。跳过此步骤将导致状态不一致。

**执行前检查**：
- [ ] 章节文件已生成且非空
- [ ] 审查分数已计算（OVERALL_SCORE）
- [ ] review_metrics.json 已保存

**Task 调用（必须执行）**：

```markdown
Task:
  subagent: data-agent
  prompt: |
    处理第 {chapter} 章的数据回写。

    ## 参数
    - 章节文件：{PROJECT_ROOT}/{CHAPTER_PATH}
    - 审查分数：{OVERALL_SCORE}
    - 项目根：{PROJECT_ROOT}
    - 存储路径：.webnovel/
    - 状态文件：.webnovel/state.json

    ## 必须完成的子步骤
    1. 加载上下文
    2. AI 实体提取
    3. 实体消歧
    4. 写入 state.json（更新 progress.current_chapter、entity、relations）
    5. 写入 index.db（RAG 向量索引）
    6. 写入章节摘要 .webnovel/summaries/ch{chapter_padded}.md

    ## 执行后验证
    确认以下文件已更新：
    - .webnovel/state.json
    - .webnovel/index.db
    - .webnovel/summaries/ch{chapter_padded}.md
```

---

#### 2.7 Git 备份

```bash
cd "${PROJECT_ROOT}"
git add "${CHAPTER_PATH}" ".webnovel/state.json" ".webnovel/index.db" ".webnovel/summaries/"
git -c i18n.commitEncoding=UTF-8 commit -m "第{chapter}章: 写作完成 [review={OVERALL_SCORE}]"
```

> **⚠️ Git 提交失败处理**：如果提交失败（非空仓库无变更可忽略），记录警告但**不得阻断**。已完成的 Data Agent 回写是持久化的。

---

#### 2.8 更新批量状态

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
    'data_agent_completed': True,
    'completed_at': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
}}

with open('${BATCH_STATE_FILE}', 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
"
```

> **⚠️ 状态更新失败处理**：如果 batch_state.json 更新失败，重试 3 次。仍失败则记录到 failed_chapters 并停止批量任务。

---

#### 2.9 进度反馈

```
✅ 第{chapter}章已完成
   - 审查得分: {OVERALL_SCORE}
   - 字数: ~{WORD_COUNT}
   - Data Agent: ✓ 已回写
   - Git: ✓ 已提交
   - 进度: [{chapter}/{E}]
```

---

#### 2.10 分批暂停点（抗注意力衰减）

> **⚠️ 本检查在每 3 章完成后必执行，不可跳过。**

在完成第 3、6、9 章...后（即每 3 章），**必须**暂停并等待用户确认：

```
═══════════════════════════════════════
🚦 分批暂停点 - 第 {batch} 批已完成
═══════════════════════════════════════
已完成：第 {S}-{chapter} 章（{batch_count} 章）

本批次状态：
├── 章节文件：✓ 已落盘
├── Data Agent：✓ 已回写（{data_agent_count} 次成功）
├── Git 提交：✓ 已完成
└── batch_state：✓ 已更新

请确认下一步操作：
1. 输入 "继续" 撰写下一批次（第 {next_batch_start}-{next_batch_end} 章）
2. 输入 "停止" 保存进度并退出
3. 输入 "检查" 查看详细状态

> 注意：超过 3 章未暂停会导致注意力衰减，请及时确认
═══════════════════════════════════════
```

> **原理**：每 3 章强制重置 Agent 注意力，防止长循环导致流程被"内部压缩"。

> **自动模式**（可选）：若用户设置 `AUTO_CONTINUE=1`，跳过暂停点直接继续。

---

### 重置后的循环验证

> **每次暂停点后重新进入循环时，2.0 上章完整性检查仍然生效。**

---

#### 章内验证点（每章必须通过）

**在进入下一章之前，必须验证本章以下项目全部完成**：

```
章内完成检查（第{chapter}章）：
├── [✓] 章节文件存在且非空
├── [✓] Data Agent 已执行（state.json/index.db/summaries 已更新）
├── [✓] Git 已提交（或记录警告）
└── [✓] batch_state.json 已更新

若任何一项未完成，**必须回退完成后再继续**。
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
| **上章完整性检查失败** | **立即停止**，禁止继续，提示执行 --resume 修复 |
| 章节起草失败 | 记录到 `failed_chapters`，继续下一章 |
| 审查 critical | 记录 deviation，继续（除非 `--stop-on-fail`） |
| Data Agent 失败 | 重试 3 次，仍失败则记录到 failed_chapters 并停止 |
| Git 提交失败 | 警告但继续，不阻断 |
| 分批暂停点超时 | 30 秒无响应自动保存当前进度并退出 |

---

## 充分性闸门（每章必须满足）

**未满足以下条件，不得进入下一章或结束批量任务**：

| # | 检查项 | 验证方法 | 对应步骤 |
|---|--------|---------|----------|
| 0 | **上章完整性检查** | completed_chapters 包含上一章 | 2.0 |
| 1 | 章节文件已生成且非空 | `test -s` | 2.2 |
| 2 | **字数达标** | 实际字数 ≥ 字数下限 | 2.5 |
| 3 | 审查分数已计算 | review_metrics.json 存在 | 2.3 |
| 4 | **Data Agent 已回写** | state.json/index.db/summaries 更新 | 2.6 |
| 5 | **batch_state.json 已更新** | completed_chapters 包含当前章 | 2.8 |
| 6 | Git 提交已完成 | commit 存在 | 2.7 |
| - | 分批暂停点（每 3 章） | 用户确认或 AUTO_CONTINUE | 2.10 |

**字数下限标准**：
- 常规推进章：≥1500字
- 过渡章：≥1000字
- 高潮章/战斗章：≥2000字

**⚠️ 关键约束**：
- **上章完整性检查（#0）是**强制防呆**，任何章节开始前必检**
- Data Agent 回写（Step 2.6）是**硬性要求**，不得跳过
- 若 Data Agent 失败，重试 3 次后仍失败，记录到 failed_chapters 并停止批量任务
- 分批暂停点（#-1）是**抗注意力衰减**机制，每 3 章必须触发
- 只有通过全部检查，才能进入下一章

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
