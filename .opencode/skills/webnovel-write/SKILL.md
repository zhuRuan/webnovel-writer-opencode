---
name: webnovel-write
description: 撰写网文章节。用于用户说"写一章"、"写第X章"、"继续写"、"创作章节"、"起草章节"时，或执行/webnovel-write命令。默认产出2000-2500字，包含完整流程：上下文搜集 → 起草 → 审查 → 润色 → 数据回写。确保审查和状态回写闭环，避免上下文丢失。配合--fast跳过风格转译，--minimal仅基础审查。
allowed-tools: Read Write Edit Grep Bash Task
---

# 网文写作 Skill

## 快速参考

| 模式 | 流程 |
|------|------|
| 标准 | Step 0 → 0.5 → 1 → 2A → 2B → 3 → 4 → 5 → 6 |
| --fast | Step 0 → 0.5 → 1 → 2A → 3 → 4 → 5 → 6 |
| --minimal | Step 0 → 0.5 → 1 → 2A → 3 → 4 → 5 → 6 |

**产出**：`正文/第N卷/第NNNN章-{title}.md`（自动适配卷目录）、`review_metrics`、`.webnovel/summaries/chNNNN.md`

## 路径工具

获取章节文件的默认路径（自动适配卷目录）：
```bash
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter ${CHAPTER_NUM})
echo "章节文件将写入: ${CHAPTER_PATH}"
```

**自动卷目录规则**：根据 `state.json` 的 `volumes_planned` 配置自动选择卷目录；未规划时默认 50 章/卷。

## 核心约束

- **禁止跳步**：审查（Step 3）必须由 Task 子代理执行
- **禁止并步**：每个 Step 独立执行
- **最小回滚**：失败只重跑该 Step，不回滚已通过步骤
- **中文写作**：禁止"先英后中"、英文结论话术

## 引用加载等级（strict, lazy）

- L0：未进入对应步骤前，不加载任何参考文件。
- L1：每步仅加载该步"必读"文件。
- L2：仅在触发条件满足时加载"条件必读/可选"文件。

路径约定：
- `references/...` 相对当前 skill 目录。
- `../../references/...` 指向全局共享参考。

## References（按需加载）

| 文件 | 用途 | 触发 |
|------|------|------|
| `../../checkers/registry.yaml` | 审查器列表 | Step 3 |
| `../../checkers/schema.yaml` | 审查器输出格式 | Step 3 |
| `../../references/shared/core-constraints.md` | 写作硬约束 | Step 2A |
| `references/polish-guide.md` | 问题修复、Anti-AI | Step 4 |
| `references/writing/typesetting.md` | 排版规则 | Step 4 |
| `references/style-adapter.md` | 风格转译 | Step 2B |

条件加载：题材配置、钩子库、战斗/对话/场景专项指南（见完整版）

## 工具

- **Read/Grep**：读取 state、大纲、参考文件
- **Bash**：运行 webnovel.py 命令
- **Task**：调用 context-agent、审查器、data-agent

## 执行流程

### Step 0：预检

```bash
# 确认项目根
SCRIPTS_DIR=".opencode/scripts"
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"

# 优先级：用户指定章节号 > state.json 自动计算
if [ -n "${CHAPTER_NUM}" ]; then
    echo "使用用户指定章节号: ${CHAPTER_NUM}"
else
    CHAPTER_NUM=$(python -X utf8 -c "import json; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json')); print(s['progress'].get('current_chapter', 0) + 1)")
    echo "从 state.json 自动获取下一章: ${CHAPTER_NUM}"
fi

# 确保章节号为整数
CHAPTER_NUM=$((10#${CHAPTER_NUM}))
echo "将撰写第 ${CHAPTER_NUM} 章"
```

**硬门槛**：preflight 必须成功。失败则阻断。

**章节号优先级**：
1. 用户通过命令参数指定（如 `--chapter 53`）
2. 从 state.json 的 `progress.current_chapter` 自动计算下一章

### Step 0.5：工作流断点记录（best-effort，不阻断）

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" workflow start-task --command webnovel-write --chapter {chapter_num} || true
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" workflow start-step --step-id "Step 1" --step-name "Context Agent" || true
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" workflow complete-step --step-id "Step 1" --artifacts '{"ok":true}' || true
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" workflow complete-task --artifacts '{"ok":true}' || true
```

要求：
- `--step-id` 仅允许：`Step 1` / `Step 2A` / `Step 2B` / `Step 3` / `Step 4` / `Step 5` / `Step 6`。
- 任何记录失败只记警告，不阻断写作。
- 每个 Step 执行结束后，同样需要 `complete-step`（失败不阻断）。

### Step 1：Context Agent

使用 Task 调用 `context-agent`，参数：
- `chapter`
- `project_root`
- `storage_path=.webnovel/`
- `state_file=.webnovel/state.json`

硬要求：
- 若 `state` 或大纲不可用，立即阻断并返回缺失项。
- 输出必须同时包含：
  - 7 板块任务书（目标/冲突/承接/角色/场景约束/伏笔/追读力）；
  - Context Contract 全字段（目标/阻力/代价/本章变化/未闭合问题/开头类型/情绪节奏/信息密度/过渡章判定/追读力设计）；
  - Step 2A 可直接消费的"写作执行包"（章节节拍、不可变事实清单、禁止事项、终检清单）。
- 合同与任务书出现冲突时，以"大纲与设定约束更严格者"为准。

输出：
- 单一"创作执行包"（任务书 + Context Contract + 直写提示词），供 Step 2A 直接消费，不再拆分独立 Step 1.5。

### Step 2A：正文起草

执行前必须加载：
```bash
cat "${SKILL_ROOT}/../../references/shared/core-constraints.md"

# 获取章节文件的默认路径（自动适配卷目录）
CHAPTER_PATH=$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" chapter-path --chapter ${CHAPTER_NUM})
echo "章节文件将写入: ${CHAPTER_PATH}"
```

硬要求：
- 只输出纯正文到 `${CHAPTER_PATH}` 指定的文件。
- 默认按 2000-2500 字执行；若大纲为关键战斗章/高潮章/卷末章或用户明确指定，则按大纲/用户优先。
- 禁止占位符正文（如 `[TODO]`、`[待补充]`）。
- 保留承接关系：若上章有明确钩子，本章必须回应（可部分兑现）。

中文思维写作约束（硬规则）：
- **禁止"先英后中"**：不得先用英文工程化骨架（如 ABCDE 分段、Summary/Conclusion 框架）组织内容，再翻译成中文。
- **中文叙事单元优先**：以"动作、反应、代价、情绪、场景、关系位移"为基本叙事单元，不使用英文结构标签驱动正文生成。
- **禁止英文结论话术**：正文、审查说明、润色说明、变更摘要、最终报告中不得出现 Overall / PASS / FAIL / Summary / Conclusion 等英文结论标题。
- **英文仅限机器标识**：CLI flag（`--fast`）、checker id（`consistency-checker`）、DB 字段名（`anti_ai_force_check`）、JSON 键名等不可改的接口名保持英文，其余一律使用简体中文。

输出：
- 章节草稿（可进入 Step 2B 或 Step 3）。

### Step 2B：风格适配（`--fast` / `--minimal` 跳过）

执行前加载：
```bash
cat "${SKILL_ROOT}/references/style-adapter.md"
```

硬要求：
- 只做表达层转译，不改剧情事实、事件顺序、角色行为结果、设定规则。
- 对"模板腔、说明腔、机械腔"做定向改写，为 Step 4 留出问题修复空间。

输出：
- 风格化正文（覆盖原章节文件）。

### Step 3：审查（必须由 Task 子代理执行）

#### 3.1 确定应执行的审查器

执行前加载审查器配置：
```bash
# 获取当前模式审查器列表（standard/minimal/full）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" checkers list --mode ${MODE} --format json

# 验证审查器配置完整性
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" checkers validate
```

其中 `${MODE}` 根据写作模式确定：standard（默认）、minimal（--minimal）、full（--full）。

审查器配置来源：`../../checkers/registry.yaml`（配置） + `../../agents/*.md`（实现）

**模式判定**（来自 registry.yaml `modes` 配置）：
- `--minimal`：`--mode minimal`（只执行 core 类别审查器）
- `--fast`/标准：`--mode standard`（执行 core + conditional 类别）
- `--full`：`--mode full`（强制启用所有 conditional 审查器）

**审查器分类**（来自 registry.yaml）：
- 核心审查器（`category: core`）：始终执行，由 registry.yaml 的 `triggers: []` 定义
- 条件审查器（`category: conditional`）：满足 triggers 条件时执行：
  - `reader-pull-checker`：非过渡章、有未闭合问题
  - `high-point-checker`：关键章/高潮章、有战斗/打脸/反转信号
  - `pacing-checker`：章号 >= 10 或节奏失衡风险

**审查器完整配置**请参考 `registry.yaml` 的 `checkers` 节点。

#### 3.2 调用审查器（关键）

**加载审查器配置**：
```bash
# 加载 registry.yaml 获取完整配置（包括 invoke_template）
cat "${SKILL_ROOT}/../../checkers/registry.yaml"

# 根据模式获取应执行的审查器列表
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" checkers list --mode {standard|minimal|full} --format json
```

**动态构建 Task 调用**：
1. 从 registry.yaml 的 `checkers` 节点获取每个审查器的 `invoke_template`
2. 替换模板中的占位符：`{chapter}`、`{chapter_file}`、`{PROJECT_ROOT}`
3. 使用 Task 工具并行调用各审查器

**⚠️ 重要约束**：
- 必须让 OpenCode 加载 agent 文件的完整定义（registry.yaml 的 `file` 字段指向 .opencode/agents/*.md）
- **不要**在 prompt 中包含具体检查项、JSON 模板、评分标准
- prompt 中只传递必要参数（章节号、文件路径、项目根）
- 如需传递额外上下文（如上章钩子、大纲标签），只放在 prompt 最后作为"背景信息"

**Task 调用示例**（动态替换 invoke_template）：
```
并行调用审查器（使用 Task 工具）：

Task 1:
  - agent/subagent: {checker_id}
  - prompt: |
      {invoke_template}
      - 章节文件：{chapter_file}
      - 项目根：{PROJECT_ROOT}
      - 审查器定义见：.opencode/agents/{checker_id}.md
```

#### 3.3 审查器输出格式约束

所有审查器必须返回符合 schema.yaml 的统一格式：

```json
{
  "agent": "审查器ID（必须与 registry.yaml 一致）",
  "chapter": 章节号,
  "overall_score": 0-100,
  "pass": true/false,
  "issues": [
    {
      "id": "ISSUE_001",
      "type": "问题类型",
      "severity": "critical|high|medium|low",
      "description": "问题描述",
      "location": "位置（如第5段）",
      "suggestion": "修复建议"
    }
  ],
  "metrics": {...},
  "summary": "一句话总结"
}
```

**字段统一性要求**：
- ✅ 使用 `overall_score`（不是 `score`）
- ✅ `severity` 使用 `critical/high/medium/low`（全小写）
- ✅ `issues` 是数组，每个 issue 包含 `severity` 和 `suggestion`

#### 3.4 汇总审查结果

各审查器返回后，按以下格式汇总：

```json
{
  "checker_results": [
    {"agent": "审查器ID", "overall_score": 85, "pass": true, "issues": [...]},
    ...
  ],
  "overall_score": "各审查器评分的平均值",
  "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
  "critical_issues": ["关键问题列表"],
  "can_proceed": "severity_counts.critical == 0"
}
```

**汇总规则**：
- `overall_score` = 各审查器 `overall_score` 的加权平均
- dimension_scores 按 registry.yaml 中的 dimension_mapping 映射
- 若 `critical > 0`，必须修复后才能进入 Step 4

#### 3.5 保存审查指标

审查指标落库（必做）：
```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" index save-review-metrics --data "@${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json"
```

review_metrics 字段约束：
```json
{
  "start_chapter": 100,
  "end_chapter": 100,
  "overall_score": 85.0,
  "dimension_scores": {"爽点密度": 8.5, "设定一致性": 8.0, "节奏控制": 7.8, "人物塑造": 8.2, "连贯性": 9.0, "追读力": 8.7},
  "severity_counts": {"critical": 0, "high": 1, "medium": 2, "low": 0},
  "critical_issues": ["问题描述"],
  "report_file": "审查报告/第100-100章审查报告.md",
  "notes": "单个字符串；selected_checkers / timeline_gate 等扩展信息压成单行"
}
```

**硬要求**：
- `--minimal` 也必须产出 `overall_score`
- 未落库 `review_metrics` 不得进入 Step 5

### Step 4：润色（问题修复优先）

执行前必须加载：
```bash
cat "${SKILL_ROOT}/references/polish-guide.md"
cat "${SKILL_ROOT}/references/writing/typesetting.md"
```

执行顺序：
1. 修复 `critical`（必须）
2. 修复 `high`（不能修复则记录 deviation）
3. 处理 `medium/low`（按收益择优）
4. 执行 Anti-AI 与 No-Poison 全文终检（必须输出 `anti_ai_force_check: pass/fail`）

输出：
- 润色后正文（覆盖章节文件）
- 变更摘要（至少含：修复项、保留项、deviation、`anti_ai_force_check`）

### Step 5：Data Agent（状态与索引回写）

使用 Task 调用 `data-agent`，参数：
- `chapter`
- `chapter_file` 必须传入实际章节文件路径（使用 `${CHAPTER_PATH}` 或 `find_chapter_file` 获取）
- `review_score=Step 3 overall_score`
- `project_root`
- `storage_path=.webnovel/`
- `state_file=.webnovel/state.json`

Data Agent 默认子步骤（全部执行）：
- A. 加载上下文
- B. AI 实体提取
- C. 实体消歧
- D. 写入 state/index
- E. 写入章节摘要
- F. AI 场景切片
- G. RAG 向量索引（`rag index-chapter --scenes ...`）
- H. 风格样本评估（`style extract --scenes ...`，仅 `review_score >= 80` 时）
- I. 债务利息（默认跳过）

`--scenes` 来源优先级（G/H 步骤共用）：
1. 优先从 `index.db` 的 scenes 记录获取（Step F 写入的结果）
2. 其次按 `start_line` / `end_line` 从正文切片构造
3. 最后允许单场景退化（整章作为一个 scene）

Step 5 失败隔离规则：
- 若 G/H 失败原因是 `--scenes` 缺失、scene 为空、scene JSON 格式错误：只补跑 G/H 子步骤，不回滚或重跑 Step 1-4。
- 若 A-E 失败（state/index/summary 写入失败）：仅重跑 Step 5，不回滚已通过的 Step 1-4。
- 禁止因 RAG/style 子步骤失败而重跑整个写作链。

执行后检查（最小白名单）：
- `.webnovel/state.json`
- `.webnovel/index.db`
- `.webnovel/summaries/ch{chapter_padded}.md`
- `.webnovel/observability/data_agent_timing.jsonl`（观测日志）

性能要求：
- 读取 timing 日志最近一条；
- 当 `TOTAL > 30000ms` 时，输出最慢 2-3 个环节与原因说明。

观测日志说明：
- `call_trace.jsonl`：外层流程调用链（agent 启动、排队、环境探测等系统开销）。
- `data_agent_timing.jsonl`：Data Agent 内部各子步骤耗时。
- 当外层总耗时远大于内层 timing 之和时，默认先归因为 agent 启动与环境探测开销，不误判为正文或数据处理慢。

债务利息：
- 默认关闭，仅在用户明确要求或开启追踪时执行（见 `step-5-debt-switch.md`）。

### Step 6：Git 备份（可失败但需说明）

```bash
git add .
git -c i18n.commitEncoding=UTF-8 commit -m "第{chapter_num}章: {title}"
```

规则：
- 提交时机：验证、回写、清理全部完成后最后执行。
- 提交信息默认中文，格式：`第{chapter_num}章: {title}`。
- 若 commit 失败，必须给出失败原因与未提交文件范围。

## 工作流终止规则（强制）

完成 Step 6 后，当前写作任务**必须终止**，除非满足以下条件之一：

1. 用户明确要求"继续写下一章"或"写第X章"
2. 用户执行 `/webnovel-write` 命令并指定章节号

**禁止行为**：
- ❌ 不得自动读取 state.json 启动下一章
- ❌ 不得在无用户指令情况下循环回到 Step 0
- ❌ 不得将"写完一章"作为"继续写下一章"的触发条件
- ❌ 不得在完成第N章后自动执行第N+1章

## 任务完成报告

每个写作任务完成后，输出以下格式的报告：

```markdown
## 第{chapter}章写作完成

- **章节文件**: {chapter_path}
- **字数**: 约{words}字
- **审查分数**: {overall_score}
- **状态**: ✅ 已通过 / ⚠️ 需修改
- **下一步**: 等待用户指令
```

### Step 7：工作流终止确认（强制）

完成 Step 6 后，执行以下检查：

```bash
# 检查是否有用户明确的下一步指令
if [ -z "${AUTO_CONTINUE}" ]; then
    echo "⚠️ 工作流终止，等待用户明确指令"
    echo "如需继续写下一章，请说'写第54章'或'继续写'"
    echo "## 本次写作完成"
    echo "- 章节: 第${CHAPTER_NUM}章"
    echo "- 状态: ✅ 已完成"
    echo "- 下一步: 等待用户指令"
    exit 0
fi
```

**触发自动继续的条件**：
- 仅当 `AUTO_CONTINUE=1` 环境变量被设置时
- 该变量必须由用户明确通过命令行参数设置

## 充分性闸门（必须通过）

未满足以下条件前，不得结束流程：

1. 章节正文文件存在且非空：`${PROJECT_ROOT}/${CHAPTER_PATH}`
2. Step 3 已产出 `overall_score` 且 `review_metrics` 成功落库
3. Step 4 已处理全部 `critical`，`high` 未修项有 deviation 记录
4. Step 4 的 `anti_ai_force_check=pass`（基于全文检查；fail 时不得进入 Step 5）
5. Step 5 已回写 `state.json`、`index.db`、`summaries/ch{chapter_padded}.md`
6. 若开启性能观测，已读取最新 timing 记录并输出结论

## 验证与交付

执行检查：

```bash
test -f "${PROJECT_ROOT}/.webnovel/state.json"
test -f "${PROJECT_ROOT}/${CHAPTER_PATH}"
test -f "${PROJECT_ROOT}/.webnovel/summaries/ch${chapter_padded}.md"
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" index get-recent-review-metrics --limit 1
tail -n 1 "${PROJECT_ROOT}/.webnovel/observability/data_agent_timing.jsonl" || true
```

成功标准：
- 章节文件、摘要文件、状态文件齐全且内容可读。
- 审查分数可追溯，`overall_score` 与 Step 5 输入一致。
- 润色后未破坏大纲与设定约束。

## 失败处理（最小回滚）

触发条件：
- 章节文件缺失或空文件；
- 审查结果未落库；
- Data Agent 关键产物缺失；
- 润色引入设定冲突。

恢复流程：
1. 仅重跑失败步骤，不回滚已通过步骤。
2. 常见最小修复：
   - 审查缺失：只重跑 Step 3 并落库；
   - 润色失真：恢复 Step 2A 输出并重做 Step 4；
   - 摘要/状态缺失：只重跑 Step 5；
3. 重新执行"验证与交付"全部检查，通过后结束。
