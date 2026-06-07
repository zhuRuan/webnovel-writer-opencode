# 系统架构与模块设计

## 核心理念

### Phase 5 真源划分

- 写前真源：`.story-system/MASTER_SETTING.json`、`volumes/`、`chapters/`、`reviews/`
- 写后真源：accepted `CHAPTER_COMMIT`
- `.webnovel/state.json`、`index.db`、`summaries/`、`memory_scratchpad.json`：只作为投影 / read-model
- `references/genre-profiles.md`：fallback-only

### 防幻觉三定律

| 定律 | 说明 | 执行方式 |
|------|------|----------|
| **大纲即法律** | 遵循大纲，不擅自发挥 | Context Agent 强制加载章节大纲 |
| **设定即物理** | 遵守设定，不自相矛盾 | Reviewer Agent 内置一致性审查 |
| **发明需识别** | 新实体必须入库管理 | Data Agent 自动提取并消歧 |

### Strand Weave 节奏系统

| Strand | 含义 | 理想占比 | 说明 |
|--------|------|----------|------|
| **Quest** | 主线剧情 | 60% | 推动核心冲突 |
| **Fire** | 感情线 | 20% | 人物关系发展 |
| **Constellation** | 世界观扩展 | 20% | 背景/势力/设定 |

节奏红线：

- Quest 连续不超过 5 章
- Fire 断档不超过 10 章
- Constellation 断档不超过 15 章

## 总体架构图

```text
┌─────────────────────────────────────────────────────────────┐
│                      OpenCode                              │
├─────────────────────────────────────────────────────────────┤
│  Skills (13个):                                            │
│    init / plan / write / write-batch / review / query       │
│    export / publish / learn / dashboard / webnovel-delete   │
│    webnovel-rewrite / webnovel-heal                         │
├─────────────────────────────────────────────────────────────┤
│  Agents (6个):                                             │
│    context-agent / data-agent / reviewer /                  │
│    chapter-writer-agent / deconstruction-agent /            │
│    observer-agent                                           │
├─────────────────────────────────────────────────────────────┤
│  Data Layer:                                               │
│    state.json / index.db (SQLite) / vectors.db             │
├─────────────────────────────────────────────────────────────┤
│  Story System:                                             │
│    .story-system/ (合同·提交·事件)                           │
└─────────────────────────────────────────────────────────────┘
```

## Agent 分工

### Context Agent（读）

- 文件：`.opencode/agents/context-agent.md`
- 职责：在写作前构建"创作任务书"，提供本章上下文、约束和追读力策略。

### Data Agent（写）

- 文件：`.opencode/agents/data-agent.md`
- 职责：从正文提取 `accepted_events / state_deltas / entity_deltas / summary_text` 等 commit artifacts，交给 `chapter-commit` 驱动 projection writers 更新 `state.json`、`index.db`、摘要与长期记忆。

### Reviewer（审）

- 文件：`.opencode/agents/reviewer.md`
- 职责：章节质量审查，内部包含以下六个审查维度：

| 审查维度 | 检查重点 |
|----------|----------|
| 设定一致性 | 角色状态/世界规则/物品属性是否与 state.json 一致 |
| 时间线 | 事件顺序/时间跨度是否合理 |
| 叙事连贯 | 视角是否统一/场景切换是否有过渡 |
| 角色一致性 | 对话风格/行为动机是否符合人设 |
| 逻辑 | 因果关系/行为后果是否合理 |
| 项目规则 | 破折号≤20、但≤6、不是X是Y≤1、句号≤70/千字、系统【】格式 |

### Observer Agent（提）

- 文件：`.opencode/agents/observer-agent.md`
- 职责：自由文本事实提取，覆盖优先（coverage-first），不设 schema 约束，捕获所有潜在实体与关系。输出经 `observer_settler.py` 沉降为结构化事实。

### Chapter Writer Agent（写）

- 文件：`.opencode/agents/chapter-writer-agent.md`
- 职责：根据 Context Agent 生成的创作任务书，起草章节正文。

## Story System（合同驱动体系）

Story System 以 `.story-system/` 为独立运行面，分五段递进：

1. **Phase 1**：合同种子 — `MASTER_SETTING.json` + 章节合同 + 反模式配置
2. **Phase 2**：合同优先运行时 — 卷合同 (`volumes/`) + 审查合同 (`reviews/`) + 写前校验
3. **Phase 3**：章节提交链 — `commits/chapter_XXX.commit.json` + state/index/summary/memory 投影
4. **Phase 4**：事件审计链 — `events/chapter_XXX.events.json` + 修订提案 + 覆写账本
5. **Phase 5**：旧链路降级 — contract-first + commit-first 默认化，`preflight` / dashboard 暴露 runtime health，legacy data 降级为 fallback/read-model

核心链路：

```text
story-system --persist
    -> 写入合同种子（MASTER_SETTING.json 等）
story-system --emit-runtime-contracts --chapter N
    -> 生成运行时合同 + 写前校验
chapter-commit --chapter N
    -> 提交 accepted commit + 执行各投影写入
story-events --chapter N / --health
    -> 事件审计与健康检查
preflight / dashboard
    -> story runtime health / fallback 状态 / latest commit 状态
```

其中 Phase 4 不起第二套投影循环，事件路由仅负责声明式激活 writer，
实际执行入口仍是 `ChapterCommitService.apply_projections()`。

Phase 5 文档见：`docs/architecture/story-system-phase5.md`

## Dashboard（可视化管理面板）

FastAPI 后端 + React 19 前端，提供 9 个页面：

| 页面 | 功能 |
|------|------|
| 总览 | 统计卡片、审查趋势、字数分布、伏笔提醒、workflow 进度 |
| 上下文健康 | Token 预算、Section 状态、权重分布、历史趋势 |
| 角色图鉴 | 实体列表、关系图谱、时间线（状态变化+出场记录+异常检测） |
| 审查分析 | 8 维度雷达图、严重程度分布、趋势折线图、Critical Issues |
| 节奏雷达 | 钩子强度趋势、Strand 堆叠分布、字数箱线图 |
| 伏笔追踪 | 伏笔甘特图、债务表 |
| 文档浏览 | 文件树、正文预览 |
| 文风约束 | 自定义提示词、全局文风、禁止模式、写作技法、章级合同、审查维度 |
| 系统状态 | 合同树、提交历史、RAG 环境、运维操作、批量操作 |

支持亮色/暗色主题切换。关键 Section 列表可通过 `.webnovel/dashboard_config.json` 自定义。

后端：`.opencode/dashboard/app.py`。前端：`.opencode/dashboard/frontend/`。发展规划：`docs/superpowers/specs/2026-06-06-dashboard-development-roadmap.md`。

## inkOS 启发改进

受 inkOS 状态空间设计启发，近期引入以下改进：

- **Observer→Reflector 双段提取**：observer-agent 做覆盖优先的无约束提取，observer_settler.py 做沉降消歧，分离"观察"与"反思"两阶段。
- **SSOT 事件日志**：`ssot_enforcer.py` 统一所有状态变更路径，终结多头真理问题。
- **运行时产物持久化**：`.webnovel/runtime/chapter-NNN.{context,trace}.json` 保留每次写作的上下文装配与推理轨迹。
- **Markdown 投影**：`story/` 目录下 5 个自动渲染文件，将内部状态投影为人类可读的 Markdown 真相文件。
