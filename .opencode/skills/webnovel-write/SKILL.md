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
   风格转译已并入Step 2A。--minimal仅统一审查（跳过条件审查器），--legacy-checkers使用6个独立审查agent。
allowed-tools: Read Write Edit Grep Bash Task
---

# 网文写作 Skill

## 快速参考

| 模式 | 流程 |
|------|------|
| 标准（统一审查） | Step 0 → 0.5 → **1.5** → 1 → 2A（含风格） → 3（统一审查） → **3.6** → 4（条件执行） → 5 → 6 → **Step 7** |
| --legacy-checkers | Step 0 → 0.5 → **1.5** → 1 → 2A（含风格） → 3（6独立审查） → **3.6** → 4 → 5 → 6 → **Step 7** |
| --minimal | Step 0 → 0.5 → 1 → 2A（含风格） → 3（统一审查） → 4（条件执行） → 5 → 6 → **Step 7** |

**新增步骤**：
- **Step 1.5**：创作前置检查（债务硬约束阻断）
- **Step 3.6**：分层审查增强（Code Layer → LLM）
- **风格转译已合并**：原 Step 2B 网络风格约束已并入 Step 2A 起草阶段，一步产出符合网文风格的正文。

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
| `../../references/csv/裁决规则.csv` | 题材裁决元数据 | Step 0 / Step 2A |
| `../../references/csv/` (全表) | CSV 结构化知识检索 | Step 2A 按需 |
| `../../data_modules/debt_tracker.py` | 债务追踪模块 | Step 1.5 |
| `references/polish-guide.md` | 问题修复、Anti-AI | Step 4 |
| `references/writing/typesetting.md` | 排版规则 | Step 4 |
| `references/style-adapter.md` | 风格转译（已并入 Step 2A） | Step 2A |
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

**CSV 参考预检**：（Step 2A 检索用，不阻断）
```bash
# 读取题材用于 CSV 检索过滤（state.json 为唯一真源）
GENRE=$(python -X utf8 -c "import json; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json')); print(s.get('project',{}).get('genre',''))")

# story-system 合同树刷新（可选，缺失不阻断）
python -X utf8 "${SCRIPTS_DIR}/story_system.py" "${CHAPTER_NUM}" --project-root "${PROJECT_ROOT}" --chapter "${CHAPTER_NUM}" --persist --emit-runtime-contracts --format json 2>/dev/null || true
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
- `--step-id` 仅允许：`Step 1` / `Step 2A` / `Step 3` / `Step 4` / `Step 5` / `Step 6`。
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

### Step 2A：正文起草（含风格适配）

**CSV 结构化知识检索**（按需触发）：
```bash
# 触发条件：新角色 → 命名规则，战斗 → 场景写法，多角色对话 → 写作技法
#          情感描写 → 写作技法，高频桥段 → 桥段套路，世界观设定 → 金手指与设定
python -X utf8 "${SCRIPTS_DIR}/reference_search.py" --skill write --table "场景写法" --query "战斗描写" --genre "${GENRE}" --max-results 3

# 裁决规则表（题材级梳理路线与毒点权重）
python -X utf8 "${SCRIPTS_DIR}/reference_search.py" --skill write --table "裁决规则" --query "${GENRE}" --max-results 1
```

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

**网文风格约束（从 style-adapter.md 引入，起草时同步执行）**：

禁改红线（不改剧情/事件/角色结果/设定/伏笔内容）：
- 长句（>40字）拆分，避免连续长句压读
- 抽象判断 → 动作/反应/代价
- 删除"总结式旁白"和大段纯解释
- 章内至少有 1 个明确推进点（信息/行动/关系/局势其一）
- 开头尽早进入冲突/风险/强情绪（建议前 200-400 字）
- 后段或章末设置未闭合问题/期待锚点
- 微兑现建议按章型安排 1-3 次
- 钩子类型优先"选择钩/危机钩"

分题材风格加权：
- 玄幻/修仙/高武：动作与结果比重更高
- 都市/直播/电竞：信息节奏更快，"反馈-反应-反制"三连
- 言情/替身/狗血：情绪弧线前置，关键场景有关系位移
- 悬疑/规则怪谈/克苏鲁：线索投放可回收，恐惧来自规则

AI痕迹预防：
- "非常愤怒"改为"动作+生理+决策"三段式
- "总而言之/可以说"改为直接结论动作
- 连续三句同句式时改至少一处为短句爆点

章节类型适配：

| 章节类型 | 字数下限 | 字数上限 | 爽点要求 | 微兑现次数 |
|---------|---------|---------|---------|-----------|
| **常规推进章** | 1500字 | 2500字 | 至少1个爽点 | 1-3次 |
| **过渡章** | 1000字 | 1500字 | 0-1次小爽点 | 0-1次 |
| **高潮章/战斗章** | 2000字 | 4000字 | 多个爽点，至少1个大爽点 | 3-5次 |

中文思维写作约束（硬规则）：
- **禁止"先英后中"**：不得先用英文工程化骨架（如 ABCDE 分段、Summary/Conclusion 框架）组织内容，再翻译成中文。
- **中文叙事单元优先**：以"动作、反应、代价、情绪、场景、关系位移"为基本叙事单元，不使用英文结构标签驱动正文生成。
- **禁止英文结论话术**：正文、审查说明、润色说明、变更摘要、最终报告中不得出现 Overall / PASS / FAIL / Summary / Conclusion 等英文结论标题。
- **英文仅限机器标识**：CLI flag（`--legacy-checkers`）、checker id（`consistency-checker`）、DB 字段名（`anti_ai_force_check`）、JSON 键名等不可改的接口名保持英文，其余一律使用简体中文。

输出：
- 章节草稿（已含网文风格，可直接进入 Step 3 审查）。

### Step 3：审查（必须由 Task 子代理执行）

#### 3.1 审查模式选择

| 模式 | 命令参数 | 审查器 | 说明 |
|------|---------|--------|------|
| **统一审查（默认）** | 无（默认） | unified-reviewer | 1个Agent覆盖所有审查维度 |
| 精细审查 | `--legacy-checkers` | 6个独立Agent | 保留原有多Agent审查 |
| --minimal | 同上 | unified-reviewer | 统一审查 |
| --full | `--legacy-checkers` + `--full` | 6个独立Agent（全部强制） | 完整审查 |

#### 3.2 统一审查执行（默认路径）

使用 Task 调用 `unified-reviewer` agent：

```markdown
Task:
  subagent: unified-reviewer
  prompt: |
    对第 {chapter} 章执行全面审查。
    - 章节文件：{chapter_file}
    - 项目根：{PROJECT_ROOT}
    - 审查器定义见：.opencode/agents/unified-reviewer.md
```

unified-reviewer 覆盖所有审查维度：
- 设定一致性（战力/地点/时间线/实体）
- 连贯性（场景过渡/情节线/伏笔管理/逻辑流/大纲一致性）
- 人物OOC（行为/语言风格/情感反应/成长轨迹）
- 追读力（硬约束/软建议/钩子强度/微兑现/模式重复）
- 爽点密度（模式识别/密度/类型多样性/执行质量）
- 节奏（Strand Weave 平衡/疲劳风险）

#### 3.3 精细审查执行（`--legacy-checkers` 路径，保留兼容）

**⚠️ 必须并行执行，禁止串行**

所有审查器必须在**同一消息中**并行调用。

加载审查器配置：
```bash
cat "${SKILL_ROOT}/../../checkers/registry.yaml"
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" checkers list --mode {standard|minimal|full} --format json
```

并行调用（同一消息中全部发出）：
```
Task: subagent=consistency-checker, prompt={invoke_template} + 章节文件/项目根
Task: subagent=continuity-checker, prompt={invoke_template} + 章节文件/项目根
Task: subagent=ooc-checker, prompt={invoke_template} + 章节文件/项目根
Task: subagent=reader-pull-checker, prompt=...（条件触发）
Task: subagent=high-point-checker, prompt=...（条件触发）
Task: subagent=pacing-checker, prompt=...（条件触发）
```

**审查器分类**（来自 registry.yaml）：
- 核心审查器（`category: core`）：always execute
- 条件审查器（`category: conditional`）：trigger condition-based
  - `reader-pull-checker`：非过渡章、有未闭合问题
  - `high-point-checker`：关键章/高潮章、有战斗/打脸/反转信号
  - `pacing-checker`：章号 >= 10 或节奏失衡风险

#### 3.4 审查器输出格式

所有审查器返回遵循 schema.yaml 的 JSON：
```json
{
  "agent": "审查器ID",
  "chapter": 章节号,
  "overall_score": 0-100,
  "pass": true/false,
  "issues": [{"id":"ISSUE_001","type":"问题类型","severity":"critical|high|medium|low","description":"..","location":"..","suggestion":".."}],
  "metrics": {...},
  "summary": "一句话总结"
}
```

#### 3.5 汇总审查结果

```json
{
  "checker_results": [...],
  "overall_score": "加权平均",
  "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
  "critical_issues": ["清单"],
  "can_proceed": "severity_counts.critical == 0"
}
```

若 `critical > 0`，必须修复后才能进入 Step 4。

#### 3.6 分层审查增强（Code → LLM）

Code 层检查（战力/道具一致性 + 债务）：
```bash
LAYERED_RESULT=$(python -X utf8 -c "
import sys; sys.path.insert(0, '${SCRIPTS_DIR}')
from data_modules.checkers_manager import CheckersManager
result = CheckersManager.run_layered_checkers(
    ${CHAPTER_NUM}, '''${CHAPTER_CONTENT}''',
    {'project_root': '${PROJECT_ROOT}'}, run_llm=False
)
import json; print(json.dumps(result, ensure_ascii=False))
" 2>/dev/null || echo '{}')
echo "Code Layer 结果: $LAYERED_RESULT"
```

阻断规则：Code layer 发现 critical → 阻断；债务硬约束违反 → 阻断；**字数不足 → 阻断**

#### 3.7 字数硬性检查

```bash
MIN_WORDS=1500  # 过渡章=1000，高潮章/战斗章=2000
ACTUAL_WORDS=$(python -X utf8 -c "
import re
text = open('${PROJECT_ROOT}/${CHAPTER_PATH}', encoding='utf-8').read()
words = sum(len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', line)) for line in text.split('\n'))
print(words)
")
if [ "$ACTUAL_WORDS" -lt "$MIN_WORDS" ]; then
    echo "⚠️ 字数不足: $ACTUAL_WORDS < $MIN_WORDS，需补充"
    echo "SKIP_REVIEW=true"
fi
```

#### 3.8 保存审查指标

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" index save-review-metrics --data "@${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json"
```

硬要求：`--minimal` 也必须产出 `overall_score`；未落库不得进入 Step 5。

### Step 4：润色（问题修复优先，**条件执行**）

**条件执行判定**：
- 审查汇总后：若 `critical == 0` 且 `high == 0` 且字数达标 → **跳过 Step 4，直接进入 Step 5**
- 若 `critical > 0` 或 `high > 0` 或字数不足 → 执行 Step 4 修复
- 跳过时必须输出简化报告："审查无 critical/high 问题，跳过润色"

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
        # 补充策略：
        # 1. 在章末添加'未闭合问题'扩展
        # 2. 在章节中部补充'期待锚点'场景
        # 3. 增加对话/动作细节描写
        # 4. 补充角色内心活动
        # 补充完成后重新计算字数
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
