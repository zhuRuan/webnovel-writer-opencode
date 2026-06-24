# Webnovel Writer for OpenCode

面向长篇中文网文的 AI 辅助写作系统。不是让 AI "代替"作者，而是让 AI "理解"作者创造的世界，并在世界规则的约束下持续创作。

[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![OpenCode](https://img.shields.io/badge/OpenCode-Compatible-purple.svg)](https://opencode.ai)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org)

---

## 它解决什么问题

长篇网文的核心挑战不在"写出一章"，而在"写到第二百章时还记得第一章的伏笔"。传统 AI 写作工具在连载场景下会系统性地退化：

| 失败模式 | 为什么发生 | 本项目的应对 |
|----------|-----------|-------------|
| **遗忘** | 上下文窗口装不下 200 章内容，AI 丢失早期设定 | 三层 RAG 检索 + 故事合约引擎 + 伏笔追踪 |
| **幻觉** | 没有硬约束阻止 AI 凭空编造 | Graph-RAG 实体图谱 + Code Checker 硬阻断 |
| **风格漂移** | 连载越久，写作风格越偏离初始设定 | MASTER_SETTING 合约 + OOC 审查器 + 题材模板 |

> 在《代码大全》中，Steve McConnell 强调："良好的文档能够帮助开发者避免很多不必要的错误和困惑。" 对于 AI 写作，"文档"就是设定集、大纲和故事合约——它们是确保 AI 在二百章后仍能遵循初始设定的关键。

---

## 核心设计理念：故事合约

这个项目的核心创新是一个简单但被证明有效的思路——**把"世界规则"当作代码合约**。

软件开发有 API 契约、数据库 schema、lint 规则来防止系统退化。长篇写作同样需要：每个角色、每条设定、每处伏笔都是一份"合约"，写作时必须遵守，提交时必须验证。

具体来说，一个书项目的数据结构分三层：

```
.webnovel/state.json                 ← 运行态（角色当前状态、能力等级、关系网、伏笔状态）
.story-system/MASTER_SETTING.json    ← 设计态（世界观规则、核心约束、题材模板）
.story-system/chapters/chapter_*.json ← 每章的"施工指令"（目标、禁区、必须覆盖的节点）
```

每写一章的流程就是：从设计态加载合同 → 组装上下文 → 起草 → 对照合同逐项审查 → 修复 → 提交 → 更新运行态。这跟 CI/CD 管线的思路一模一样。

---

## 架构全景

```
┌──────────────────────────────────────────────────────┐
│                    Agent 团队                          │
│                                                      │
│   director-agent      章节编剧 + 演员调度              │
│        │                                              │
│        ├──→ chapter-writer-agent   起草 + 润色         │
│        ├──→ actor-agent            角色视角演绎        │
│        ├──→ reviewer               13 维审查           │
│        └──→ observer-agent         自由事实提取        │
│                                                      │
└──────────────────────────────────────────────────────┘
                         ↑↓
┌──────────────────────────────────────────────────────┐
│               六层数据管道（每写一章走一遍）             │
│                                                      │
│  L1 Knowledge    CSV 知识库 + BM25 检索               │
│       ↓                                              │
│  L2 Reasoning    题材路由 + 反模式排序                 │
│       ↓                                              │
│  L3 Contract     MASTER_SETTING + 卷纲章纲 + 审查合约  │
│       ↓                                              │
│  L4 Context      JSON 拼装写作上下文（RAG 检索组装）    │
│       ↓                                              │
│  L5 Commit       事实提取 + 事件溯源 + 投影路由        │
│       ↓                                              │
│  L6 Projection   5 个 Writer 并行写入（见下方）        │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## 五大核心机制

### 1. 故事合约引擎 — 写作的"类型检查器"

> 正如《人月神话》中所说："良好的文档是软件产品成功的关键。"

合同系统是项目的基石，分三个层级层层约束：

| 层级 | 文件 | 职责 | 示例 |
|------|------|------|------|
| 主合同 | `MASTER_SETTING.json` | 世界观规则、核心约束、题材模板，锁定后不可绕过 | "本世界无复活术"、"主角天赋上限为 SSS 级" |
| 卷级合同 | `volumes/volume_*.json` | 本卷故事线、节奏策略、重要角色出场计划 | "第三卷主打学院线，节奏中速" |
| 章级合同 | `chapters/chapter_*.json` | 本章目标、时间锚点、必须覆盖的节点、禁区 | "本章目标：主角通过入学测试；禁写：越级战斗" |

**Override 合约引擎** 支持世界规则版本化演进——比如"第三卷起开放元婴境界"，可以通过 override 机制在不破坏前文一致性的前提下扩展规则。

**硬约束阻断**：如果 AI 试图写"主角被杀了"但合约规定"主角在本卷不死"，审查阶段会直接标记为 blocking issue，必须重写。

### 2. SSOT 事件溯源 — 永不丢失的事实账本

受 [Narcooo/inkOS](https://github.com/Narcooo/inkOS) 启发，所有状态变更走 append-only 事件日志：

```
.story-system/events/001.event.json   ←  不可变的事实源头
.story-system/events/002.event.json
.story-system/events/003.event.json
             ↓ 投影重建
state.json + index.db                 ←  可随时从事件日志重建的物化视图
```

**Observer→Reflector 双段提取**：Observer（自由文本提取）确保"宁可多提不漏"，Reflector（Pydantic Schema 校验）确保"只要合法的结构化数据"。两段配合，兼顾覆盖率和结构化。

```bash
# 验证一致性：对比投影与事件日志，发现数据漂移
python webnovel.py ssot verify --project-root /path/to/book

# 从事件日志完整重建所有投影
python webnovel.py ssot rebuild --project-root /path/to/book
```

### 3. 分层审查管线 — 三道防线

写完一章不代表它"合格"。审查管线像 CI 一样逐层把关：

```
草稿完成
  │
  ▼
┌─────────────┐
│ Code Checker │  硬约束预处理：正则扫描规则违反（如"破折号>20个"直接标红）
└──────┬──────┘
       ▼
┌─────────────┐
│  Reviewer    │  6 维度结构化检查（设定/时间线/叙事连贯/角色一致性/逻辑/规则）
│  (最多2轮)   │  每轮发现问题 → 修复 → 再审 → 收敛或标记 blocking
└──────┬──────┘
       ▼
┌─────────────┐
│  Polish      │  润色审查：AI 味检测、节奏评估、文风适配
└──────┬──────┘
       ▼
   通过 → 提交
```

审查不是"感觉好不好"的模糊判断，而是精确到行号的证据比对——每条 issue 都带精确位置和引用证据。

### 4. 记忆系统 — 让 AI 记住 200 章

三层记忆，逐层压缩：

| 层 | 存储 | 容量策略 | 例子 |
|----|------|---------|------|
| **工作记忆** | 上下文窗口 | 最近 3-5 章全文 | "刚才主角在洞穴里捡到了什么" |
| **情节记忆** | 章节摘要 + 伏笔表 | 全本，结构化索引 | "第 47 章埋的伏笔：神秘玉佩" |
| **语义记忆** | 向量数据库 | 全本，RAG 按需检索 | "所有提到'古剑宗'的段落" |

BM25（关键词匹配）+ Embedding（语义相似）+ Rerank（精确排序）三层检索确保上下文组装的既全面又精准。

### 5. Graph-RAG + DebtTracker — 关系网与伏笔追债

**Graph-RAG 实体关系图谱**（SQLite 持久化）追踪角色间的关系变化：
```
主角 ──同盟──→ 男二
  │             │
  │敌对         │师徒
  ↓             ↓
反派Boss ←──暗恋── 女主
```

**DebtTracker 伏笔追踪**：每埋一个伏笔就创建一条"债务"，设定偿还期限（默认 10 章内）。到期未还 → 阻塞新章生成 → 强制作者先填坑。

---

## Dashboard 可视化面板

除了命令行，项目提供了一个 React 19 + FastAPI 的全功能 Web 面板：

```bash
cd .opencode/dashboard/frontend && npm install && npm run build
python -m dashboard.server --project-root /path/to/book
# 打开 http://127.0.0.1:8765
```

| 页面 | 功能 |
|------|------|
| 总览仪表盘 | 写作进度、审查分趋势、环境状态一目了然 |
| 上下文健康 | 每章上下文包含/排除的 section、token 预算、关键 section 告警 |
| 角色图鉴 | 全角色列表、状态变更历史、事件追踪 |
| 审查分析 | 审查分趋势、各维度问题分布、收敛轮次 |
| 节奏雷达 | 情节线交替、字数波动、高潮低谷可视化 |
| 伏笔追踪 | 活跃伏笔、即将到期提醒、回收状态 |
| 文档浏览 | 正文/大纲/设定集三目录树，支持在线编辑 |
| 文风编辑器 | 5 级文风约束（全局/禁止模式/写作技法/名家技法/章级合同） |
| 执行追踪 | 每章 trace.json 详情，context.json token 分布 |
| 系统状态 | 向量库、RAG 模式、SSOT 一致性检查 |

**多项目切换**：侧栏下拉框可切换不同书项目，SSE 实时推送刷新。

**名家技法采集**：支持在线搜索作家作品 或 上传 `.txt`/`.md` 整本小说，自动分章后调用本地 Ollama 大模型分析文风（叙事语调 / 描写风格 / 节奏控制 / 对话风格 / 人物塑造五个维度）。

---

## 快速开始

```bash
# 安装
curl -fsSL https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py | python3

# 配置 API Key（编辑 .env）
EMBED_API_KEY=your_embed_key      # Embedding 模型
RERANK_API_KEY=your_rerank_key    # Rerank 模型

# 初始化第一本书
/webnovel-init

# 日常写作流程
/webnovel-plan     # 规划大纲
/webnovel-write    # 写一章
/webnovel-review   # 审查质量
```

## 命令一览

| 命令 | 用途 | 场景 |
|------|------|------|
| `/webnovel-init` | 初始化新书，收集世界观、角色、力量体系 | 开始新书 |
| `/webnovel-plan` | 生成卷纲、时间线、章纲 | 规划故事 |
| `/webnovel-write` | 单章写作：上下文→起草→审查→润色→提交 | 日常写作 |
| `/webnovel-write-batch` | 连续写多章 | 集中赶稿 |
| `/webnovel-review` | 13 维度结构化审查 | 质量把控 |
| `/webnovel-rewrite` | 删除旧章后重写 | 翻修 |
| `/webnovel-heal` | 诊断并修复问题章节（OOC、矛盾） | 修复 |
| `/webnovel-delete` | 安全删除章节并清理关联数据 | 回退 |
| `/webnovel-export` | 导出 MD/TXT/EPUB/DOCX/PDF | 分发 |
| `/webnovel-publish` | 发布到番茄小说等平台 | 上线 |
| `/webnovel-query` | 查询设定、角色、力量体系、伏笔 | 检索 |
| `/webnovel-collect` | 名家文风采集（搜索 + 本地上传） | 学习 |
| `/webnovel-dashboard` | 可视化面板 + 多项目切换 + 文风编辑 | 管理 |
| `/webnovel-style` | 加载导演文风与写作技法 | 风格参考 |

> 正如《C++编程思想》中所说："代码的清晰是优秀软件的基石。" 每个命令都设计为自解释的——告诉系统"做什么"，它会自动处理"怎么做"。

---

## 项目结构

```
webnovel-writer-opencode/
├── install.py                         # 一键安装
├── .env                               # API 配置
│
├── .opencode/                         # OpenCode 引擎核心
│   ├── agents/                        # 10 个 Agent
│   │   ├── director-agent.md          #   导演 — 编剧 + 调度
│   │   ├── chapter-writer-agent.md    #   写手 — 起草 + 润色
│   │   ├── reviewer.md                #   审查 — 13 维检查
│   │   ├── actor-agent.md             #   演员 — 角色视角演绎
│   │   ├── observer-agent.md          #   观察者 — 自由事实提取
│   │   ├── data-agent.md              #   数据 — 结构化提取
│   │   ├── deconstruction-agent.md    #   解构 — 作品分析
│   │   └── style-collector-agent.md   #   采集 — 名家文风
│   │
│   ├── skills/                        # 14 个 Skill
│   │
│   ├── dashboard/                     # 可视化面板
│   │   ├── app.py                     #   FastAPI 入口（80+ 端点）
│   │   ├── server.py                  #   五级项目路径解析
│   │   ├── core/config.py             #   多项目注册与切换
│   │   ├── routers/                   #   路由（files/chapters/entities/contracts）
│   │   ├── services/                  #   分章引擎 + 文风分析 + DB
│   │   └── frontend/                  #   React 19 + ECharts
│   │
│   ├── references/                    # 结构化知识库
│   │   ├── csv/                       #   9 张知识表 + BM25
│   │   ├── writing/                   #   写作技法参考
│   │   └── review/                    #   审查规则
│   │
│   ├── genres/                        # 38+ 题材模板
│   └── scripts/                       # Python 核心
│       ├── webnovel.py                #   CLI 统一入口（28 子命令）
│       └── data_modules/              #   60+ 核心模块
│
└── docs/                              # 架构 / 指南 / 运维文档
```

---

## 技术渊源

本项目有两个主要上游：

| 来源 | 贡献 |
|------|------|
| [lingfengQAQ/webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer) | 原项目，奠定核心写作流程和 Agent 协作模式 |
| [Narcooo/inkOS](https://github.com/Narcooo/inkOS) | SSOT 事件溯源、Observer→Reflector 双段提取、7 文件真相投影 |

在此基础上扩展了：审查器体系（13 维 + 收敛）、CSV 结构化知识库、故事合约引擎、记忆系统、Graph-RAG、DebtTracker、Dashboard 面板、多项目支持、名家技法采集、发布通道。

---

## 贡献

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat: 添加多项目切换支持
Co-Authored-By: AI Assistant <noreply@anthropic.com>
```

常用类型：`feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `perf:`

## 致谢

| 贡献者 | 贡献内容 |
|--------|----------|
| [lingfengQAQ](https://github.com/lingfengQAQ) | 原项目作者 |
| [Narcooo/inkOS](https://github.com/Narcooo/inkOS) | SSOT 架构设计灵感 |
| [Cppys/OpenNovel](https://github.com/Cppys/OpenNovel) | 番茄发布技术参考 |
| [@YuerLee](https://github.com/YuerLee) | macOS 兼容性、安装脚本优化 |

## License

GPL v3 © [lujih](https://github.com/lujih)
