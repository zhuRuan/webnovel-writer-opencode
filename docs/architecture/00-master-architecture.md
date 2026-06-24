# Webnovel Writer — 主架构文档

> 版本: 2.9 | 更新: 2026-06 | 模板: arc42 精简版

## 1. 引言与目标

### 1.1 系统概述

Webnovel Writer for OpenCode 是一个面向长篇中文网文的 AI 辅助写作系统。核心挑战：在长达数百章的连载中保持一致性。系统通过六层数据流管道、SSOT 事件溯源、Theater 协同创作模式和结构化质量审查来解决 AI 的"遗忘"和"幻觉"问题。

项目 fork 自 [lingfengQAQ/webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer)，深度重构为 OpenCode 架构。v2.8 起借鉴 [Narcooo/inkOS](https://github.com/Narcooo/inkOS) 的核心设计，引入 Observer→Reflector 双段事实提取、SSOT 事件溯源和 Markdown 真相文件投影。

### 1.2 核心目标

- **记忆连续性**: AI 在 200 章后仍记住第 1 章的伏笔，通过三层记忆系统（工作/情节/语义）+ Wickelgren 衰减公式实现
- **风格一致性**: 长篇连载中写作风格不漂移，通过 MASTER_SETTING 合约 + 13 维度审查 + 反 AI 味检测保障
- **角色深度**: 每个角色有独立的记忆库、状态快照、计划追踪和私有知识，通过 character_memories + character_state + character_events 三表实现
- **质量保障**: 13 维度结构化审查 + 7 层反 AI 规则 + 200+ 词库 + E-check 质量闸门

### 1.3 关键干系人

| 干系人 | 角色 | 交互方式 |
|--------|------|----------|
| 网文作者 | 创作决策者 | OpenCode 斜杠命令（14 个 Skills） |
| AI Agent 集群 | 执行者 | 8 个活跃 Agent 协同完成写作/审查/提取 |
| Dashboard 用户 | 可视化监控 | React 19 SPA（11 个页面） |
| 外部平台 | 发布目标 | Playwright 浏览器自动化 → 番茄小说 |

## 2. 约束

### 2.1 技术约束

- Python 3.10+, React 19, SQLite（零配置本地数据库）
- OpenCode 框架（Skills + Agents 运行时）
- 本地文件系统存储，无需外部数据库或容器化
- 前端 CORS 限制为 localhost

### 2.2 业务约束

- 2000-2500 字/章的网文标准
- 中国网文读者期望的爽点节奏（Strand Weave: Quest 60% / Fire 20% / Constellation 20%）
- 反 AI 写作检测（7 层规则，200+ 禁用词库）
- 章节审查 blocking=true 时阻断提交

## 3. 系统上下文

### 3.1 系统边界

```
用户(作者) ──→ OpenCode CLI ──→ Webnovel Writer
                                    ├── Agent 集群 (8个活跃)
                                    ├── Dashboard (FastAPI + React 19)
                                    ├── 数据层 (8个DAO + SQLite + 文件)
                                    └── 外部服务 (OpenAI/Embedding API)
```

### 3.2 外部接口

| 接口 | 说明 | 协议 |
|------|------|------|
| OpenCode Skills/Agents 运行时 | 斜杠命令调度 + Agent 生命周期 | OpenCode 框架 |
| Embedding API | 文本向量化（Qwen3-Embedding-8B） | HTTP REST |
| Rerank API | 检索结果重排（jina-reranker-v3） | HTTP REST |
| 番茄小说发布 API | 章节自动发布 | Playwright 浏览器自动化 |
| LLM API | 写作/审查/提取的底层模型调用 | 通过 OpenCode 框架代理 |

## 4. 解决方案策略

### 4.1 核心架构决策

1. **六层数据流**: Knowledge → Reasoning → Contract → Context → Commit → Projection，每层为下一层提供加工后的数据
2. **SSOT 事件溯源**: append-only 事件日志（14 种事件类型）→ 5 路投影写入，状态 = 所有事件的重放结果
3. **DAO 统一数据访问**: 所有 SQL 收敛到 `dao/` 层（8 个 DAO），单例缓存，参数化查询
4. **Theater 协同创作**: 导演（粗粒度规划）+ 演员（细粒度演绎）协商机制，碰撞产生深度
5. **数据库优先**: 所有结构化数据存入 SQLite，避免文件散落

### 4.2 关键技术选型

| 决策 | 选择 | 原因 |
|------|------|------|
| 数据库 | SQLite | 零配置，本地文件，足够性能 |
| 记忆检索 | RAG（关键词+向量混合） | 平衡精度与成本 |
| 前端 | React 19 + ECharts | 可视化需求 |
| Agent 框架 | OpenCode Skills/Agents | 项目基础架构 |
| 后端 | FastAPI (端口 8765) | 异步支持，SSE 实时推送 |
| 前端构建 | Vite (端口 5173) | 快速 HMR，代理到 8765 |

## 5. 构建块视图（模块分解）

### 5.1 一级模块

```
webnovel-writer-opencode/
├── .opencode/
│   ├── agents/           → Agent 定义 (11个 .md，8个活跃)
│   ├── skills/           → Skill 命令 (16个目录)
│   ├── dashboard/        → 可视化面板 (FastAPI + React 19)
│   │   ├── app.py        → 后端入口 (91个 API 端点)
│   │   └── frontend/     → React SPA (11个页面)
│   ├── scripts/          → Python 核心
│   │   ├── webnovel.py   → CLI 统一入口 (50个子命令)
│   │   └── data_modules/ → 核心数据模块
│   │       └── dao/      → 数据访问层 (8个DAO)
│   ├── references/       → 知识库 (CSV + MD)
│   └── genres/           → 38+ 题材模板
├── docs/                 → 文档
│   ├── architecture/     → 架构文档
│   ├── guides/           → 使用指南
│   └── operations/       → 运维文档
└── .webnovel/            → 运行时数据 (index.db + state.json)
```

### 5.2 模块详细文档索引

| 模块 | 文档 | 说明 |
|------|------|------|
| DAO 层 | [01-dao-layer.md](01-dao-layer.md) | 统一数据访问接口（8 个 DAO） |
| 角色记忆系统 | [02-character-memory.md](02-character-memory.md) | 记忆库 + 状态 + 计划 |
| Theater 管线 | [03-theater-pipeline.md](03-theater-pipeline.md) | 导演-演员协同创作 |
| Dashboard | [04-dashboard.md](04-dashboard.md) | 可视化面板设计 |
| 文风系统 | [05-style-system.md](05-style-system.md) | 写作技法 + 风格管理 |
| SSOT 事件溯源 | [06-ssot-event-sourcing.md](06-ssot-event-sourcing.md) | 事件日志 + 投影重建 |
| 审查管线 | [07-review-pipeline.md](07-review-pipeline.md) | 13 维度结构化审查 |
| 记忆系统 | [08-memory-system.md](08-memory-system.md) | 三层记忆 + 遗忘机制 |

### 5.3 Agent 清单 (v3.0)

| Agent | 角色 | 状态 |
|-------|------|------|
| 导演智能体 | 制定剧本、粗粒度规划、可访问全部数据 | ✅ 活跃 (原 editor-agent + context-agent) |
| actor-agent | 按剧本演绎主角/配角，输出文学散文 | ✅ 活跃 |
| actor-agent-budget | 快速演绎路人角色 | ✅ 活跃 |
| chapter-writer-agent | 润色成文、环境描写、动作校验、自搜索 | ✅ 活跃 (吸收 scene/physics-director) |
| reviewer | 13维度审查 | ✅ 活跃 |
| observer-agent | 自由文本事实提取 | ✅ 活跃 |
| data-agent | 契约校验与消歧 | ✅ 活跃 |
| deconstruction-agent | 作品解构 | ✅ 活跃 |
| ~~context-agent~~ | 已合并入导演智能体 | ❌ 废弃 |
| ~~scene-director-agent~~ | 已合并入 chapter-writer-agent | ❌ 废弃 |
| ~~physics-director-agent~~ | 已合并入 chapter-writer-agent | ❌ 废弃 |

### 5.4 Skill 清单（16 个）

| Skill | 目录 | 功能 |
|-------|------|------|
| webnovel-init | `webnovel-init/` | 深度初始化新书项目 |
| webnovel-plan | `webnovel-plan/` | 生成卷纲、时间线和章纲 |
| webnovel-write | `webnovel-write/` | 单章写作（上下文→起草→审查→润色→提交） |
| webnovel-write-batch | `webnovel-write-batch/` | 批量连续写作多章 |
| webnovel-review | `webnovel-review/` | 章节质量审查 |
| webnovel-rewrite | `webnovel-rewrite/` | 重写指定章节 |
| webnovel-heal | `webnovel-heal/` | 修复问题章节 |
| webnovel-delete | `webnovel-delete/` | 安全删除章节 + 清理投影 |
| webnovel-query | `webnovel-query/` | 查询设定、角色、伏笔 |
| webnovel-export | `webnovel-export/` | 导出 MD/TXT/EPUB/HTML/DOCX/PDF |
| webnovel-publish | `webnovel-publish/` | 发布到番茄小说平台 |
| webnovel-dashboard | `webnovel-dashboard/` | 启动可视化面板 |
| webnovel-learn | `webnovel-learn/` | 提取成功模式写入 project_memory |
| webnovel-doctor | `webnovel-doctor/` | 项目健康诊断 |
| webnovel-style | `webnovel-style/` | 文风素材管理 |
| spec | `spec/` | 架构 spec 管理 |

### 5.5 DAO 层（8 个）

| DAO | 文件 | 职责 |
|-----|------|------|
| BaseDAO | `base.py` | 连接管理 + 安全查询（`_fetch`/`_execute`/`_exists`） |
| EntityDAO | `entity_dao.py` | 实体/别名/状态变化 |
| CharacterEventDAO | `character_event_dao.py` | 角色事件 CRUD + 逾期查询 |
| KnowledgeDAO | `knowledge_dao.py` | 角色知识（theater + skills） |
| FactionDAO | `faction_dao.py` | 势力聚合查询 |
| RelationshipDAO | `relationship_dao.py` | 关系/关系事件 |
| MemoryDAO | `memory_dao.py` | 角色记忆 CRUD + RAG 检索 |
| StateDAO | `state_dao.py` | 角色状态快照 |
| DirectorDAO | `director_dao.py` | 导演全局记忆读取 |

### 5.6 Dashboard 页面（11 个）

| 页面 | 文件 | 功能 |
|------|------|------|
| 总览 | `OverviewPage.jsx` | 统计卡片、审查趋势、字数分布、伏笔提醒 |
| 上下文健康 | `ContextHealthPage.jsx` | Token 预算、Section 状态、权重分布 |
| 角色图鉴 | `CharactersPage.jsx` | 实体列表、关系图谱、时间线、角色计划 |
| 审查分析 | `ReviewAnalyticsPage.jsx` | 8 维度雷达图、严重程度分布、趋势折线图 |
| 节奏雷达 | `PacingPage.jsx` | 钩子强度趋势、Strand 堆叠分布、字数箱线图 |
| 伏笔追踪 | `ForeshadowingPage.jsx` | 伏笔甘特图、债务表 |
| 文档浏览 | `FilesPage.jsx` | 文件树、正文预览 |
| 文风约束 | `StyleEditorPage.jsx` | 6 Tab：自定义提示词、全局文风、禁止模式、写作技法、章级合同、审查维度 |
| 系统状态 | `SystemPage.jsx` | 合同树、提交历史、RAG 环境、批量操作 |
| 知识库 | `KnowledgePage.jsx` | 结构化知识浏览 |
| 知识库管理 | `KnowledgeBasePage.jsx` | 知识库编辑管理 |

## 6. 运行时视图

### 6.1 写作流程（Theater 模式 v3.0）

```
/ webnovel-write --theater
  → preflight → story-system
  → 导演智能体（Step 1）
      ├── research（合同刷新、五段任务书）
      ├── 读取全部章节全文 + 全部角色情报板 + 互联网
      ├── 制定分场剧本 → scene_scripts.json
      └── 输出: 写作任务书 + 分场剧本
  → 角色演绎（Step 2，并行）
      ├── Actor A 按剧本演绎 → 文学散文段落
      │       └── 只能访问: 自己的记忆/状态/计划 + 互联网
      ├── Actor B ...
      └── 输出: theater/chapters/ch{NNNN}/performances.json
  → ChapterWriter 润色成文（Step 3）
      ├── 加载文风 (webnovel-style skill)
      ├── 搜索自己写过的相关段落 (ChapterDAO RAG)
      ├── 补充环境描写 (原 scene-director 职责)
      ├── 校验动作合理性 (原 physics-director 职责)
      └── 润色: 剧本 + 演绎 → 章节正文
  → 审查 (Step 4) → 润色 (Step 5)
  → chapter-commit → 章节入库 + 过程数据入库 → done
```

### 6.2 章节提交流程

```
正文 → observer-agent（自由文本提取，覆盖优先）
     → observer_settler（Pydantic Schema 校验 + 实体消歧）
     → chapter_commit_service
         ├── SSOT 事件发布（14 种事件类型）
         ├── 5 路投影（state / index / summary / memory / vector）
         ├── 角色记忆自动提取
         └── theater actor 同步
```

### 6.3 Dashboard 数据流

```
Browser → React 19 SPA → FastAPI (/api/*, 91 个端点) → DAO 层 → SQLite
                              ↓
                         SSE (/api/events) 实时推送
```

### 6.4 记忆检索流程

```
actor-agent 准备演绎
  → character_memories 查询（按 retention DESC, importance DESC）
  → memory_embeddings 语义搜索（向量相似度）
  → 混合排序: similarity × 0.5 + retention × 0.3 + importance × 0.2
  → top-K 注入 actor-agent prompt
```

## 7. 部署视图

- **后端**: `python -m .opencode.dashboard`（FastAPI，端口 8765）
- **前端**: `cd .opencode/dashboard/frontend && npm run dev`（Vite，端口 5173，代理到 8765）
- **数据**: `.webnovel/index.db`（SQLite）+ `.webnovel/state.json`
- **环境**: 本地开发，无需容器化
- **安装**: `python install.py`（交互式菜单，6 种操作选项）

## 8. 横切概念

### 8.1 记忆遗忘机制

Wickelgren 衰减公式: `retention = importance × e^(-λ × Δchapter / memory_strength)`

- 记忆力强度 1-10，决定衰减半衰期（3-100 章）
- retention < 0.3 的记忆不返回（视为"遗忘"）
- 检索增强: 每次检索 retention × 1.2
- 竞争-抑制: 超容量时低分记忆被抑制

### 8.2 导演-演员协商

三阶段协同：导演智能体（剧本）→ 角色演员（演绎）→ ChapterWriter（润色成文）。

- 角色认知优先: Actor 对"角色会怎么做"的意见优先
- 剧情目标优先: 导演对"这场戏要达成什么"的规划优先
- 所有异议和裁决记录在 debate_records 表
- 导演从 debate_records 学习历史协商模式

### 8.3 DAO 单例模式

`get_dao(Class, db_path)` 缓存实例，同路径复用连接。所有 SQL 使用参数化 `?` 占位符，`_fetch` 内置表不存在降级。

### 8.4 事件溯源

SSOT: 状态 = 所有事件的重放结果。`publish_event()` 是唯一写路径，`rebuild_state_json()` 确定性重放 14 种事件类型重建投影。`verify_consistency()` 检测 state.json 与事件日志的漂移。

### 8.5 防幻觉三定律

| 定律 | 说明 | 执行方式 |
|------|------|----------|
| 大纲即法律 | 遵循大纲，不擅自发挥 | Context Agent 强制加载章节大纲 |
| 设定即物理 | 遵守设定，不自相矛盾 | Reviewer Agent 内置一致性审查 |
| 发明需识别 | 新实体必须入库管理 | Data Agent 自动提取并消歧 |

### 8.6 Strand Weave 节奏系统

| Strand | 含义 | 理想占比 | 红线 |
|--------|------|----------|------|
| Quest | 主线剧情 | 60% | 连续不超过 5 章 |
| Fire | 感情线 | 20% | 断档不超过 10 章 |
| Constellation | 世界观扩展 | 20% | 断档不超过 15 章 |

## 9. 架构决策记录

| ADR | 决策 | 日期 |
|-----|------|------|
| ADR-001 | 采用 arc42 精简模板组织架构文档 | 2026-06 |
| ADR-002 | DAO 层替代零散 SQL，统一数据访问 | 2026-06 |
| ADR-003 | 角色记忆存入 SQLite（character_memories 表） | 2026-06 |
| ADR-004 | actor 输出改为文学散文格式（非 JSON 数组） | 2026-06 |
| ADR-005 | Theater 管线采用导演-演员协商机制 | 2026-06 |
| ADR-006 | SSOT 事件溯源替代多头写入 | 2026-05 |
| ADR-007 | Observer→Reflector 双段提取分离"观察"与"反思" | 2026-05 |

## 10. 质量要求

- **章节审查**: 13 维度结构化检查，blocking=true 阻断提交，最多 3 轮收敛
- **Anti-AI**: 7 层规则，200+ 禁用词库，禁止 em-dash/en-dash
- **性能**: Dashboard 批量操作使用 `asyncio.create_subprocess_exec` 避免阻塞
- **安全**: SQL 参数化查询，路径防穿越，CORS 限制 localhost
- **数据完整性**: SSOT 一致性校验，filelock 保护 state.json 原子写入

## 11. 风险与技术债

| 风险/债务 | 影响 | 状态 |
|-----------|------|------|
| 旧 state.json 文件数据未完全迁移到 SQLite | 双写维护成本 | 待迁移 |
| memory_embeddings 表已建但嵌入向量管线未完成 | RAG 检索精度受限 | 待实现 |
| 部分 Agent 定义文件中的 prompt 需持续调优 | 输出质量波动 | 持续优化 |
| 前端 CharactersPage 体积较大（1331 行） | 维护困难 | 待拆分 |
| 24 个预存测试失败（网络 mock/异步问题） | CI 不可靠 | 待修复 |

## 12. 术语表

| 术语 | 定义 |
|------|------|
| SSOT | Single Source of Truth — append-only 事件日志 |
| DAO | Data Access Object — 数据访问层，统一 SQL 入口 |
| Theater | 导演-演员协同创作模式 |
| 5W | Who/What/When/Where/Why — 情景记忆框架 |
| E-check | Editor 整合后质量闸门（4 项检查） |
| Observer→Reflector | 双段事实提取：自由文本提取 + Schema 校验 |
| Strand Weave | 三线节奏系统（Quest/Fire/Constellation） |
| DebtTracker | 伏笔追踪系统，硬约束阻塞 |
| Wickelgren 衰减 | 记忆随时间衰减的数学模型 |
| 角色情报板 | 导演在写作前组装的角色综合信息快照 |
