# 写作工作流详细分析报告

> **生成日期**：2026-06-08
> **分析范围**：webnovel-writer 全部 4 个阶段 + 6 个 Agent + 数据流

---

## 一、系统总览

### 1.1 架构定位

webnovel-writer 是一个面向长篇中文网络小说的 AI 辅助写作系统，核心解决两个问题：
- **AI 遗忘**：长篇写作中 AI 丢失前期设定、伏笔、角色状态
- **AI 幻觉**：AI 自行编造与已有设定矛盾的内容

### 1.2 技术栈

| 层级 | 技术 |
|------|------|
| 框架 | OpenCode（Agent 编排框架） |
| 后端 | Python（FastAPI Dashboard + CLI 工具链） |
| 前端 | React 19 + ECharts + CodeMirror 6 |
| 数据库 | SQLite（index.db）+ JSON 文件 |
| 事件溯源 | JSONL 事件日志 + 5 路投影 |

### 1.3 核心设计原则

1. **合同驱动**：所有写作行为由 `.story-system/` 合同树约束
2. **事件溯源**：append-only 事件日志为唯一真理源，state.json/index.db 为投影
3. **Agent 分工**：读写分离（context-agent 读，data-agent 写），职责单一
4. **检查点恢复**：每阶段记录 checkpoint，失败只重跑当前阶段

---

## 二、Stage 1：项目初始化（`/webnovel-init`）

### 2.1 目标

通过结构化交互收集完整创作信息，生成可直接进入规划与写作的项目骨架。

### 2.2 输入

| 输入类型 | 来源 | 必需 |
|----------|------|------|
| 创意想法 | 用户自由描述 | ✅ |
| 参考书拆解 | `deconstruction-agent`（可选） | ❌ |
| 市场趋势 | WebSearch/WebFetch（可选） | ❌ |
| 题材模板 | `references/genre-tropes.md` | ✅ |

### 2.3 执行流程

| Step | 内容 | 收集项 |
|------|------|--------|
| 1 | 预检与上下文加载 | 确认目录可写、解析脚本路径、加载题材套路库 |
| 1.5 | 灵感来源询问 | 是否提供参考书（书名+平台+摘录/路径） |
| 2 | 故事核与商业定位 | 书名、题材、目标规模、一句话故事、核心冲突、目标读者/平台 |
| 3 | 角色骨架与关系冲突 | 主角姓名/欲望/缺陷/结构、感情线配置、反派分层 |
| 4 | 金手指与兑现机制 | 类型、名称、风格、可见度、不可逆代价、成长节奏 |
| 5 | 世界观与力量规则 | 世界规模、力量体系、势力格局、社会阶层、货币体系 |
| 6 | 创意约束包 | 反套路规则、硬约束、卖点、开篇钩子（2-3 套方案） |
| 7 | 一致性复述与确认 | 初始化摘要草案，用户确认 |

### 2.4 子代理

**deconstruction-agent**（可选）

| 模式 | 输入 | 输出 |
|------|------|------|
| 快速模式 | 书名/平台/摘录 | 黄金三章拆解 + 整体结构 + 拆文报告 |
| 深度模式 | 完整文本路径 | 逐章摘要 + 情节点 + 聚合分析 + 设定/金手指/关系抽象 |

输出格式：`init_reference_research` JSON，含 `reader_promise`、`opening_hook_patterns`、`cool_point_loops`、`protagonist_patterns`、`borrowable_structures`、`init_candidates`。

### 2.5 门禁（充分性闸门）

6 项必须全部通过：
1. 书名、题材已确定
2. 目标规模可计算
3. 主角姓名 + 欲望 + 缺陷完整
4. 世界规模 + 力量体系类型完整
5. 金手指类型已确定
6. 创意约束已确定（反套路 + 硬约束，或用户明确拒绝）

### 2.6 产出

| 文件 | 内容 |
|------|------|
| `.webnovel/state.json` | 项目配置快照（<5KB） |
| `设定集/世界观.md` | 世界边界、社会结构、关键地点 |
| `设定集/力量体系.md` | 境界链、限制、代价与冷却 |
| `设定集/主角卡.md` | 欲望、缺陷、初始资源与限制 |
| `设定集/反派设计.md` | 小/中/大反派层级与镜像关系 |
| `大纲/总纲.md` | 故事一句话、核心主线、创意约束、反派分层 |
| `.webnovel/idea_bank.json` | 选定创意 + 继承约束 |
| `.story-system/MASTER_SETTING.json` | 主合同（题材、调性、禁忌） |
| `.story-system/anti_patterns.json` | 反模式列表 |

### 2.7 失败恢复

最小回滚：仅补缺失字段，不全量重问。文件缺失→重跑 init_project.py，总纲缺字段→只 patch 总纲。

---

## 三、Stage 2：大纲规划（`/webnovel-plan`）

### 3.1 目标

将总纲细化为卷纲、时间线与章纲，为下游写作提供中层情节结构。

### 3.2 输入

| 输入 | 来源 |
|------|------|
| 总纲 | `大纲/总纲.md` |
| 设定集 | `设定集/世界观.md`、`力量体系.md`、`主角卡.md`、`反派设计.md` |
| 前卷摘要 | `.webnovel/summaries/ch*.md` |
| 活跃伏笔 | `memory-contract get-open-loops` |
| 实体状态 | `knowledge query-entity-state` |
| 关系状态 | `knowledge query-relationships` |

### 3.3 执行流程

| Step | 内容 | 产出 |
|------|------|------|
| 1 | 加载项目数据并确认前置条件 | 已知信息清单 |
| 2 | 补齐设定基线 | 增量补充世界观/力量体系/主角卡/反派设计 |
| 3 | 选择目标卷并确认范围 | 卷名、章节范围、核心冲突 |
| 4 | 生成卷节拍表 | `大纲/第{N}卷-节拍表.md` |
| 5 | 生成卷时间线表 | `大纲/第{N}卷-时间线.md` |
| 6 | 生成卷纲骨架 | 卷摘要、关键人物、Strand 分布、爽点密度、伏笔规划 |
| 7 | 批量生成章纲（10 章/批） | `大纲/第{N}卷-详细大纲.md` |
| 8 | 写回新增设定到设定集 | 增量补充角色/势力/地点/规则 |
| 9 | 验证、保存并更新状态 | `大纲/第{N}卷-总纲写回.json` |

### 3.4 结构化节点规范

每章必须包含：

| 节点 | 数量 | 格式 |
|------|------|------|
| CBN（章节起点） | 1 个 | `主体 \| 动作/变化 \| 对象/结果` |
| CPN（推进节点） | 2-4 个 | 同上 |
| CEN（章节终点） | 1 个 | 同上 |

**规则**：
- 相邻章节 CEN → 下一章 CBN 必须逻辑承接
- CPNs 按时间顺序排列
- 必须覆盖节点最多 4 个
- 本章禁区不超过 5 条

### 3.5 门禁（9 项硬失败条件）

1. 节拍表不存在或为空
2. 中段反转缺失且未给出理由
3. 时间线表不存在或为空
4. 详细大纲不存在或为空
5. 任一章节缺少时间字段
6. 时间回跳且未标注闪回
7. 倒计时算术冲突
8. 与总纲核心冲突或卷末高潮明显冲突
9. 存在 BLOCKER 未裁决

### 3.6 产出

| 文件 | 内容 |
|------|------|
| `大纲/第{N}卷-节拍表.md` | 卷级节奏（危机链、中段反转、卷末钩子） |
| `大纲/第{N}卷-时间线.md` | 时间体系、跨度、倒计时事件 |
| `大纲/第{N}卷-详细大纲.md` | 每章完整信息（目标/阻力/代价/时间/节点/禁区） |
| `大纲/第{N}卷-总纲写回.json` | 结构化写回（下一卷锚点、伏笔、开放环） |
| 更新的设定集 | 增量补充 |
| 更新的总纲 | 仅下一卷概要 + 伏笔表 |

---

## 四、Stage 3：章节写作（`/webnovel-write`）

### 4.1 目标

产出可发布章节到 `正文/第{NNNN}章-{title}.md`。

### 4.2 输入

| 输入 | 来源 |
|------|------|
| 合同树 | `.story-system/`（MASTER_SETTING + volume + chapter + review） |
| 章纲 | CBN/CPNs/CEN、must_cover_nodes、forbidden_zones |
| 自定义提示词 | `设定集/prompts/*.md`（可选） |
| 上章文件 | 用于过渡承接 |

### 4.3 执行流程

#### Step 0：确定章节号

扫描 `正文/` 目录找最大章节号，下一章 = 最大+1。不依赖对话记忆或 state.json。

#### 准备：预检 + 合同刷新 + 结构自检

- `preflight` + `placeholder-scan` 并行执行
- 刷新 `.story-system/` 合同树（从详细大纲解析真实目标）
- `check-structural` 验证 intended_strand

#### Step 1：context-agent 生成写作任务书

**Agent**：`context-agent`

**5 段写作任务书**：
1. 开头指令（章节号 + 标题 + 一句话方向）
2. 上章衔接（上章结尾摘要 + 跨章线索 + 遗留悬念）
3. 本章叙事引擎（核心冲突 + 结构化节点 + 不可遗漏点）
4. 角色卡（本章出场角色 + 状态 + 关系）
5. 文风与节奏约束（题材气质 + 文风 + 节奏 + 情绪约束 + 钩子方向）

**关键行为**：
- 情节线检查：同一 strand 连续 >5 章警告，Fire/Constellation 断档 >10 章警告
- 数据权重层级：章纲约束 > CBN/CPNs/CEN > 禁区 > 风格指引 > dynamic_context

#### Step 2：chapter-writer-agent 起草正文

**Agent**：`chapter-writer-agent`

**流程**：
1. 确认硬性约束（过渡承接、must_cover_nodes、forbidden_zones、字数 2000-2500）
2. 围绕 CBN→CPNs→CEN 展开起草
3. 硬性约束验证（逐条回填确认具体段号）
4. 润色（修复 issue → 风格适配 → 排版 → Anti-AI 终检）
5. 写入文件

**Anti-AI 终检**：
- "不是...而是..." 句式
- 段落首尾的总结性/感叹性语句
- 冗余的"突然/忽然/却/竟"
- 动作描写的机械罗列
- 情感描写的直接告知

#### Step 3：reviewer 审查

**Agent**：`reviewer`

**6 维度审查**：

| 维度 | 检查项 | bash 查询 |
|------|--------|-----------|
| 设定一致性 | 角色能力/地点/物品与 state.json 一致 | `get-entity --id protagonist` + `get-state-changes` |
| 时间线 | 事件顺序/时间跨度合理 | 读取上章结尾 500 字 |
| 叙事连贯 | 视角统一/场景切换有过渡 | — |
| 角色一致性 | 对话风格/行为动机符合人设 | — |
| 逻辑 | 因果关系/行为后果合理 | — |
| 项目规则 | 破折号≤20、但≤6、不是X是Y≤1、句号≤70/千字 | python 统计脚本 |

**修复-重审循环**（最多 2 轮）：
1. chapter-writer-agent 修复 blocking issues
2. 自查（evidence 子串匹配）
3. 自查通过 → 跳过重审
4. 自查未通过 → 重新审查
5. 2 轮后仍有 blocking → AskUserQuestion 三选一

#### Step 4：润色

加载 `polish-guide.md`、`typesetting.md`、`style-adapter.md`

顺序：修复非 blocking issue → 风格适配 → 排版 → Anti-AI 终检

#### Step 5：提交（三阶段事实提取）

**5.1a Observer**：自由提取 → `raw_facts.txt`
**5.1b Settler**：Schema 校验 → `extraction_result.json`
**5.1c Data Agent**：契约校验 + 消歧 → `fulfillment_result.json` + `disambiguation_result.json`

**5.2 CHAPTER_COMMIT**：
- blocking_count > 0 或 missed_nodes 非空或 pending 非空 → rejected
- 否则 → accepted

**5.3 投影验证**：state/index/summary/memory/vector 五项全部 done/skipped

**5.5 写后校验**：`verify-chapter-files` + `ssot verify`

#### Step 6：Git 备份

`backup --chapter {N} --chapter-title "{title}"`

### 4.4 门禁（充分性闸门）

1. 正文文件存在且非空
2. 审查已落库（`--minimal` 除外）
3. blocking=true 必须停在 Step 3
4. anti_ai_force_check=pass（`--minimal` 除外）
5. accepted CHAPTER_COMMIT，projection 五项 done/skipped
6. chapter_status=committed

### 4.5 三种模式

| 模式 | 流程 | 适用场景 |
|------|------|----------|
| 默认 | Step 1→2→3→4→5→6 | 正常写作 |
| `--fast` | Step 1→2→3(轻量)→4→5→6 | 快速迭代 |
| `--minimal` | Step 1→2→4(仅排版)→5→6 | 轻量修改 |

---

## 五、Stage 4：独立审查（`/webnovel-review`）

### 5.1 目标

对已有章节做独立质量审查，生成报告并写回审查指标。

### 5.2 输入

| 输入 | 来源 |
|------|------|
| 章节文件 | `正文/第{N}章-*.md` |
| 合同 | `.story-system/reviews/chapter_{NNN}.review.json` |
| 最近 commit | accepted CHAPTER_COMMIT |

### 5.3 执行流程

| Step | 内容 |
|------|------|
| 1 | 解析项目根目录，必要时补齐 runtime 合同 |
| 2 | 按需加载参考资料 |
| 3 | 加载项目投影状态与待审正文 |
| 4 | 调用 reviewer agent（同 Stage 3 Step 3） |
| 5 | 生成审查报告 + 指标落库 |
| 6 | 写入兼容审查记录 + 处理阻断 |

### 5.4 产出

| 文件 | 内容 |
|------|------|
| `审查报告/第{N}章审查报告.md` | 总览 + 阻断问题 + 其他问题 + 修复方向 |
| `review_metrics` 表 | overall_score、dimension_scores、severity_counts、critical_issues |
| `state.json` 投影 | 审查记录写入兼容投影 |

---

## 六、Agent 架构

### 6.1 Agent 分工

| Agent | 职责 | 读取 | 写入 | 关键行为 |
|-------|------|------|------|----------|
| deconstruction-agent | 参考书拆解 | 参考文本 | 返回 JSON | 快速/深度模式，只提取模式不复制事实 |
| context-agent | 写前研究 | state.json + index.db + 合同 + 摘要 | 5 段任务书 | 数据权重层级，情节线检查 |
| chapter-writer-agent | 起草正文 | 任务书 | 章节 .md | 硬性约束验证，Anti-AI 终检 |
| reviewer | 事实审查 | 章节 + index.db | review_results.json | 6 维度，ReAct 推理，evidence 基础 |
| observer-agent | 自由提取 | 章节 | raw_facts.txt | 覆盖优先，9 类输出 |
| data-agent | 契约校验 | extraction_result.json | fulfillment + disambiguation | 不重新提取，置信度消歧 |

### 6.2 Agent 调用链

```
webnovel-write
  ├── Step 1: context-agent (读)
  ├── Step 2: chapter-writer-agent (写)
  ├── Step 3: reviewer (审)
  │   └── 修复循环: chapter-writer-agent → reviewer (最多 2 轮)
  └── Step 5:
      ├── observer-agent (提取)
      ├── observer_settler.py (沉降)
      └── data-agent (校验)
```

---

## 七、数据流

### 7.1 写前数据流

```
state.json + index.db + .story-system/contracts
  ↓ context-agent
5 段写作任务书
  ↓ chapter-writer-agent
正文草稿
```

### 7.2 审查数据流

```
正文 + index.db (entity state, state changes)
  ↓ reviewer
review_results.json (6 维度 issues)
  ↓ review-pipeline
review_metrics → index.db (review_metrics 表)
  ↓ 审查报告.md
```

### 7.3 提交数据流

```
正文
  ↓ observer-agent
raw_facts.txt
  ↓ observer_settler.py
extraction_result.json
  ↓ data-agent
fulfillment_result.json + disambiguation_result.json
  ↓ chapter-commit CLI
CHAPTER_COMMIT (accepted/rejected)
  ↓ projection chain
state.json + index.db + summaries/ + vectors.db + memory
  ↓ ssot verify
事件日志一致性确认
```

### 7.4 事件溯源数据流

```
chapter-commit
  ↓ publish_event()
.story-system/events/chapter_{N}.events.json (append-only)
  ↓ rebuild_state_json()
state.json + index.db (投影重建)
  ↓ verify_consistency()
SSOT 一致性确认
```

---

## 八、合同树结构

```
.story-system/
├── MASTER_SETTING.json          # 主合同（题材、调性、禁忌）
├── anti_patterns.json           # 反模式列表
├── volumes/
│   └── volume_{NNN}.json        # 卷级合同（节奏、Strand 分布）
├── chapters/
│   └── chapter_{NNN}.json       # 章级合同（目标、节点、禁区）
├── reviews/
│   └── chapter_{NNN}.review.json # 审查合同
├── commits/
│   └── chapter_{NNN}.commit.json # 提交记录
└── events/
    └── chapter_{NNN}.events.json # 事件日志（SSOT）
```

### 合同层级约束

| 层级 | 约束来源 | 优先级 |
|------|----------|--------|
| 用户要求 | 用户明确指示 | 最高 |
| MASTER_SETTING | 调性/禁忌 | 高 |
| volume contract | 卷级节奏 | 中 |
| chapter contract | 章级指令 | 中 |
| review contract | 审查标准 | 低 |

---

## 九、关键数据表

### 9.1 index.db 表结构

| 表 | 用途 | 关键字段 |
|----|------|----------|
| `entities` | 实体主表 | id, canonical_name, type, tier, is_protagonist, first_appearance, last_appearance |
| `aliases` | 别名映射 | entity_id, alias |
| `relationships` | 关系 | from_entity, to_entity, type, description, chapter |
| `relationship_events` | 关系事件 | from_entity, to_entity, event_type, chapter |
| `state_changes` | 状态变化 | entity_id, field, old_value, new_value, reason, chapter |
| `chapters` | 章节元数据 | chapter, title, location, word_count, characters, summary |
| `scenes` | 场景 | chapter, scene_index, location, summary, characters |
| `chapter_reading_power` | 追读力 | chapter, hook_type, hook_strength, is_transition |
| `review_metrics` | 审查指标 | start_chapter, end_chapter, overall_score, dimension_scores, severity_counts |
| `chase_debt` | 伏笔债务 | debt_type, source_chapter, due_chapter, status |
| `override_contracts` | 覆盖规则 | chapter, field, override_value, status |
| `story_events` | 故事事件 | event_id, chapter, event_type, subject, payload_json |
| `invalid_facts` | 无效事实 | entity_id, field, reason, status |
| `rag_query_log` | RAG 查询日志 | query_type, query_text, results_count |
| `tool_call_stats` | 工具调用统计 | tool_name, duration_ms, success |

### 9.2 state.json 结构

```json
{
  "project_info": {"title": "", "genre": "", "target_words": 0, "target_chapters": 0},
  "progress": {"current_chapter": 0, "current_volume": 1, "total_words": 0, "chapter_status": {}},
  "protagonist_state": {"entity_id": "", "name": "", "location": {"current": "", "last_chapter": 0}},
  "entity_state": {"entity_id": {"field": "value"}},
  "strand_tracker": {"current_dominant": "", "chapters_since_switch": 0, "history": []},
  "disambiguation": {"pending": []}
}
```

---

## 十、Dashboard 集成

### 10.1 看板页面与工作流的对应关系

| 看板页面 | 对应工作流阶段 | 数据来源 |
|----------|---------------|----------|
| 总览 | 全阶段 | state.json + index.db |
| 上下文健康 | Stage 3 Step 1 | runtime/chapter-NNN.trace.json + context.json |
| 角色图鉴 | Stage 3 Step 5 | index.db (entities, relationships, state_changes) |
| 审查分析 | Stage 3 Step 3 / Stage 4 | index.db (review_metrics) |
| 节奏雷达 | Stage 2 / Stage 3 | index.db (chapters, chapter_reading_power) |
| 伏笔追踪 | Stage 2 / Stage 3 | index.db (chase_debt) |
| 文档浏览 | 全阶段 | 正文/大纲/设定集 目录 |
| 文风约束 | Stage 1 / Stage 3 | MASTER_SETTING.json, anti_patterns.json, prompts/ |
| 系统状态 | 全阶段 | .story-system/, .webnovel/ |

### 10.2 看板写入能力

| 操作 | 端点 | 影响 |
|------|------|------|
| 编辑文风约束 | PUT /api/style/master-setting | MASTER_SETTING.json |
| 管理反模式 | POST/DELETE /api/style/anti-patterns | anti_patterns.json |
| 管理提示词 | POST/PUT/DELETE /api/style/prompts | 设定集/prompts/ |
| 编辑章节 | PUT /api/files/write | 正文/大纲/设定集 文件 |
| 批量写入 | POST /api/batch/write | 触发 orchestrate write |
| 批量删除 | POST /api/batch/delete | 触发 delete-chapters |
| 运维操作 | POST /api/actions/{action} | ssot-verify/rebuild, entity-clean |

---

## 十一、待改进项

### 11.1 已知限制

| 限制 | 影响 | 优先级 |
|------|------|--------|
| Token 估算使用 len/2 | 中文内容偏差约 30% | 中 |
| 无并发写入保护 | 多 tab 编辑可能覆盖 | 低 |
| .bak 文件无限堆积 | 磁盘空间 | 低 |
| projection_log 无文件锁 | 并发写入可能截断 | 中 |
| reviewer 不检查 AI 味/节奏 | 由 polish 阶段处理 | 设计如此 |

### 11.2 可优化方向

| 方向 | 说明 | 优先级 |
|------|------|--------|
| Token 精确计数 | 集成 tiktoken 或在 trace 中记录 token 数 | 中 |
| 并发写入保护 | 文件编辑加 filelock | 低 |
| 审查维度可视化 | 看板审查分析页增加维度趋势图 | 已完成 |
| 伏笔主动管理 | 看板伏笔页增加 CRUD 功能 | 已完成 |
| 多项目管理 | 看板支持切换项目 | P3 |
