---
name: webnovel-write
description: |
  撰写网文章节。当用户说"写一章"、"写第X章"、"继续写"、"创作章节"、"起草章节"时，
  或执行/webnovel-write命令时**必须使用此 skill**。默认产出2000-2500字，包含完整流程：
  预检 → 上下文搜集 → 起草 → 审查 → 润色 → 数据回写 → Git备份 → 强制终止确认。
  **禁止在无用户明确指令情况下自动循环写下一章**。
  配合--fast跳过风格转译，--minimal仅基础审查。
allowed-tools: Read Write Edit Grep Bash Task
---

# 网文写作 Skill

## 快速参考

| 模式 | 流程 |
|------|------|
| 标准 | Step 0 → 0.5 → **1.5** → 1 → 2A → 2B → 3 → **3.6** → 4 → 5 → 6 → **Step 7** |
| --fast | Step 0 → 0.5 → **1.5** → 1 → 2A → 3 → **3.6** → 4 → 5 → 6 → **Step 7** |
| --minimal | Step 0 → 0.5 → 1 → 2A → 3 → 4 → 5 → 6 → **Step 7** |

**新增步骤**：
- **Step 1.5**：创作前置检查（债务硬约束阻断）
- **Step 3.6**：分层审查增强（Code Layer → LLM）

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
| `../../data_modules/debt_tracker.py` | 债务追踪模块 | Step 1.5 (新增) |
| `references/polish-guide.md` | 问题修复、Anti-AI | Step 4 |
| `references/writing/typesetting.md` | 排版规则 | Step 4 |
| `references/style-adapter.md` | 风格转译 | Step 2B |
| `references/step-1.5-contract.md` | Context Contract 模板 | Step 1 输出验证 |
| `references/core-constraints.md` | 中文写作约束 | Step 2A |

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

### Step 1.5：创作前置检查（债务硬约束）

```bash
# 债务检查（确保可以写高潮章节）
DEBT_CHECK=$(python -X utf8 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from data_modules.debt_tracker import DebtTracker
tracker = DebtTracker()
try:
    from data_modules.config import DataModulesConfig
    config = DataModulesConfig.from_project_root('${PROJECT_ROOT}')
    tracker = DebtTracker()
    state_file = config.state_file
    if state_file.exists():
        import json
        state = json.loads(state_file.read_text(encoding='utf-8'))
        debts = state.get('debts', [])
        for d in debts:
            if not d.get('repaid'):
                tracker.create_debt(
                    d.get('debt_type', 'explicit'),
                    d.get('content', ''),
                    d.get('created_chapter', 1),
                    d.get('priority', 'medium')
                )
except: pass

can_write, reason = tracker.can_write_climax(int('${CHAPTER_NUM}'))
print(f'{can_write}|{reason}')
" 2>/dev/null || echo "True|")

BLOCKED=$(echo "$DEBT_CHECK" | cut -d'|' -f1)
REASON=$(echo "$DEBT_CHECK" | cut -d'|' -f2-)

if [ "$BLOCKED" = "False" ]; then
    echo "⚠️ 创作阻断: $REASON"
    echo "建议：先偿还高优先级债务，或切换到非高潮章节类型"
    exit 1
fi

# 低于阈值时警告
ACTIVE_DEBTS=$(python -X utf8 -c "
import sys; sys.path.insert(0, '${SCRIPTS_DIR}')
from data_modules.debt_tracker import DebtTracker
t = DebtTracker()
print(len(t.check_active_debts()))
" 2>/dev/null || echo "0")

if [ "$ACTIVE_DEBTS" -gt 3 ]; then
    echo "⚠️ 活跃债务数: $ACTIVE_DEBTS (建议 > 3 时偿还部分)"
fi
```

**阻断条件**：
- 高优先级未偿还债务存在 + 当前为高潮章节 → **强制阻断**
- 活跃债务数 > 3 → **强警告**（不阻断）

**修复建议**：返回债务列表，指导先填坑。

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
- **字数下限（按章节类型，硬性约束）**：
  - 常规推进章：≥1500字
  - 过渡章：≥1000字
  - 高潮章/战斗章：≥2000字
- 默认按 2000-2500 字执行；若大纲为关键战斗章/高潮章/卷末章或用户明确指定，则按大纲/用户优先。
- **字数低于下限必须补充至达标，方可进入审查流程**
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

**⚠️ 必须并行执行，禁止串行**

所有审查器必须在**同一消息中**并行调用，**禁止逐个串行执行**。

**加载审查器配置**：
```bash
# 加载 registry.yaml 获取完整配置（包括 invoke_template）
cat "${SKILL_ROOT}/../../checkers/registry.yaml"

# 根据模式获取应执行的审查器列表
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" checkers list --mode {standard|minimal|full} --format json
```

**并行调用模板**（必须按此格式执行）：

```markdown
# 错误示例（串行，禁止）
Task 1: 调用 consistency-checker，等待完成
Task 2: 调用 continuity-checker，等待完成  ← 错误！

# 正确示例（并行，同一消息中全部发出）
Task 1:
  subagent: consistency-checker
  prompt: |
    {invoke_template}
    - 章节文件：{chapter_file}
    - 项目根：{PROJECT_ROOT}

Task 2:
  subagent: continuity-checker
  prompt: |
    {invoke_template}
    - 章节文件：{chapter_file}
    - 项目根：{PROJECT_ROOT}

Task 3:
  subagent: ooc-checker
  prompt: |
    {invoke_template}
    - 章节文件：{chapter_file}
    - 项目根：{PROJECT_ROOT}
```

**动态构建步骤**：
1. 从 registry.yaml 的 `checkers` 节点获取每个审查器的 `invoke_template`
2. 替换模板中的占位符：`{chapter}`、`{chapter_file}`、`{PROJECT_ROOT}`
3. 在**同一条消息中**使用多个 Task 工具调用所有审查器（非串行等待）

**⚠️ 重要约束**：
- 必须让 OpenCode 加载 agent 文件的完整定义（registry.yaml 的 `file` 字段指向 .opencode/agents/*.md）
- **不要**在 prompt 中包含具体检查项、JSON 模板、评分标准
- prompt 中只传递必要参数（章节号、文件路径、项目根）
- 如需传递额外上下文（如上章钩子、大纲标签），只放在 prompt 最后作为"背景信息"

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

#### 3.6 分层审查增强（Code → LLM）

执行 Code 层检查（战力/道具一致性 + 债务）：
```bash
# 分层审查（Code Layer 快速）
LAYERED_RESULT=$(python -X utf8 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from data_modules.checkers_manager import CheckersManager
result = CheckersManager.run_layered_checkers(
    ${CHAPTER_NUM},
    '''${CHAPTER_CONTENT}''',  # 需要读取章节文件
    {'project_root': '${PROJECT_ROOT}'},
    run_llm=False  # 先只运行 Code checkers
)
import json
print(json.dumps(result, ensure_ascii=False))
" 2>/dev/null || echo '{}')

echo "Code Layer 结果: $LAYERED_RESULT"

# 检查阻断
if echo "$LAYERED_RESULT" | grep -q '"blocked": true'; then
    echo "⚠️ Code 层阻断: 检测到严重问题"
    echo "请修复后重新提交审查"
fi
```

**阻断规则**：
- Code layer (world-consistency) 发现 critical 问题 → 阻断
- 债务硬约束违反 → 阻断
- **字数不足 → 阻断（必须补充达标）**

#### 3.7 字数硬性检查（必须执行）

**⚠️ 此检查在所有审查之前执行，字数不足将阻断流程**

```bash
# 字数检查（硬性，阻断流程）
CHAPTER_TYPE=$(python -X utf8 -c "
import sys, json
sys.path.insert(0, '${SCRIPTS_DIR}')
from data_modules.config import DataModulesConfig
config = DataModulesConfig.from_project_root('${PROJECT_ROOT}')
state_file = config.state_file
if state_file.exists():
    state = json.loads(state_file.read_text(encoding='utf-8'))
    # 尝试从大纲获取章节类型
    plot_outline = state.get('plot_outline', {})
    # 默认为常规推进章
    print('常规推进章')
else:
    print('常规推进章')
" 2>/dev/null || echo "常规推进章")

# 确定字数下限
MIN_WORDS=1500
if [ "$CHAPTER_TYPE" = "过渡章" ]; then
    MIN_WORDS=1000
elif [ "$CHAPTER_TYPE" = "高潮章" ] || [ "$CHAPTER_TYPE" = "战斗章" ]; then
    MIN_WORDS=2000
fi

# 计算实际字数
ACTUAL_WORDS=$(python -X utf8 -c "
import re
text = open('${PROJECT_ROOT}/${CHAPTER_PATH}', encoding='utf-8').read()
# 统计中文字符数
words = sum(len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', line)) for line in text.split('\n'))
print(words)
" 2>/dev/null || echo "0")

echo "章节类型: $CHAPTER_TYPE"
echo "字数下限: $MIN_WORDS"
echo "实际字数: $ACTUAL_WORDS"

if [ "$ACTUAL_WORDS" -lt "$MIN_WORDS" ]; then
    echo "⚠️ 字数不足: $ACTUAL_WORDS < $MIN_WORDS"
    echo "必须补充至 $MIN_WORDS 字以上才能进入审查"
    # 字数不足时，跳过审查直接进入Step 4补充
    echo "SKIP_REVIEW=true" > /tmp/word_check_${CHAPTER_NUM}.txt
fi
```

**字数不足处理流程**：
1. 字数不足 → 记录 `SKIP_REVIEW=true` → 直接进入 Step 4
2. Step 4 优先在"未闭合问题"和"期待锚点"处补充内容
3. 补充后重新计算字数，达标后退出 Step 4
4. 若多次补充仍不足，标记为 deviation 但允许继续

### Step 4：润色（问题修复优先）

执行前必须加载：
```bash
cat "${SKILL_ROOT}/references/polish-guide.md"
cat "${SKILL_ROOT}/references/writing/typesetting.md"
```

**字数补充逻辑（字数不足时优先执行）**：
```bash
# 检查是否需要补充字数
if [ -f "/tmp/word_check_${CHAPTER_NUM}.txt" ]; then
    source "/tmp/word_check_${CHAPTER_NUM}.txt"
    if [ "$SKIP_REVIEW" = "true" ]; then
        echo "字数不足，优先补充内容..."
        # 读取当前正文
        CURRENT_CONTENT=$(cat "${PROJECT_ROOT}/${CHAPTER_PATH}")
        # 计算当前字数
        CURRENT_WORDS=$(python -X utf8 -c "
import re
text = '''$CURRENT_CONTENT'''
words = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
print(words)
")
        # 补充目标字数（按章节类型）
        TARGET_WORDS=$((MIN_WORDS - CURRENT_WORDS + 500))  # 多补500字缓冲
        echo "需要补充: 约 $TARGET_WORDS 字"
        echo "补充策略："
        echo "1. 在章末添加'未闭合问题'扩展"
        echo "2. 在章节中部补充'期待锚点'场景"
        echo "3. 增加对话/动作细节描写"
        echo "4. 补充角色内心活动"
        # 补充完成后重新计算字数
        NEW_WORDS=$(python -X utf8 -c "
import re
text = open('${PROJECT_ROOT}/${CHAPTER_PATH}', encoding='utf-8').read()
words = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
print(words)
")
        if [ "$NEW_WORDS" -ge "$MIN_WORDS" ]; then
            echo "字数补充完成: $NEW_WORDS 字 ≥ $MIN_WORDS 字"
            rm -f "/tmp/word_check_${CHAPTER_NUM}.txt"
        else
            echo "⚠️ 字数仍不足: $NEW_WORDS < $MIN_WORDS"
            echo "标记为 deviation，继续流程"
        fi
    fi
fi
```

执行顺序：
1. **字数补充（若不足）**：优先在"未闭合问题"和"期待锚点"处补充
2. 修复 `critical`（必须）
3. 修复 `high`（不能修复则记录 deviation）
4. 处理 `medium/low`（按收益择优）
5. 执行 Anti-AI 与 No-Poison 全文终检（必须输出 `anti_ai_force_check: pass/fail`）
6. **字数终检**：润色后再次检查字数，达标后才能输出

输出：
- 润色后正文（覆盖章节文件）
- 变更摘要（至少含：修复项、保留项、deviation、`anti_ai_force_check`、`word_count`）

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

完成 Step 6 后，**必须执行此步骤**：

```bash
# 检查是否有用户明确的下一步指令
if [ -z "${AUTO_CONTINUE}" ]; then
    echo "========================================"
    echo "⚠️  工作流终止，等待用户明确指令"
    echo "========================================"
    echo "如需继续写下一章，请明确说："
    echo "  - '写第54章'"
    echo "  - '继续写'"
    echo "  - '/webnovel-write --chapter 54'"
    echo ""
    echo "## 第${CHAPTER_NUM}章写作完成"
    echo "- 章节文件: ${CHAPTER_PATH}"
    echo "- 状态: ✅ 已完成"
    echo "- 下一步: 等待用户指令"
    echo "========================================"
    # 工作流结束，不再执行任何后续步骤
    return 0 2>/dev/null || true
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
