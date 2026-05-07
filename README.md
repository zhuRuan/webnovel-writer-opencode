# Webnovel Writer for OpenCode

> **新手入门？先看 [新手引导](./docs/新手引导.md)**
> 
> 遇到问题？先查阅 [常见问题](./docs/FAQ.md)

[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![OpenCode](https://img.shields.io/badge/OpenCode-Compatible-purple.svg)](https://opencode.ai)
[![GitHub Stars](https://img.shields.io/github/stars/lujih/webnovel-writer-opencode)](https://github.com/lujih/webnovel-writer-opencode/stargazers)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org)

## 项目介绍

Webnovel Writer for OpenCode 是一个基于 OpenCode 的长篇网文 AI 创作系统，目标降低 AI 写作中的"遗忘"和"幻觉"，支持长周期连载创作。

本项目源于 [lingfengQAQ/webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer)，已深度重构为 OpenCode 架构，扩展了审查器体系、CSV 结构化知识库、故事合约引擎、记忆系统、发布通道等模块。

## 系统要求

- **Python 3.10 或更高版本**（安装和运行核心脚本必需）
- **OpenCode** 运行环境
- 网络连接（用于下载依赖、调用 API 等）

## 核心特性

| 特性 | 说明 |
|------|------|
| **完整写作工作流** | 项目初始化 → 大纲规划 → 章节写作 → 审查润色 → 发布 |
| **RAG 上下文管理** | 智能检索相关设定、角色、伏笔，保持长篇一致性 |
| **Graph-RAG + 持久化** | 三层子图架构，支持 SQLite 持久化 |
| **Code + LLM 分层审查** | Code Checkers 优先阻断严重问题 → 6 个并行 LLM 审查器 |
| **故事合约引擎** | MASTER_SETTING 合约 + Runtime 合同 + 事件溯源 + 投影写入 |
| **CSV 结构化知识库** | 9 张知识表 + BM25 检索（命名规则、写作技法、爽点节奏等） |
| **记忆系统** | 三层记忆（工作/情节/语义）+ 压缩器 + 编排器 + 持久化 |
| **DebtTracker 债务追踪** | 伏笔创建 → 偿还 → 硬约束阻塞 |
| **债务感知上下文预算** | 活跃债务 > 2 时自动分配 15% Token 给伏笔列表 |
| **多维度质量检查** | 设定一致性、连贯性、OOC、爽点、节奏、追读力 |
| **条件评估器** | 评估章节触发的世界规则，判断是否符合预设 |
| **题材预设通用化** | xianxia/urban/scifi 战力体系一键切换 |
| **自定义词典** | 改进中文分词质量，自动增量重建 |
| **38+ 题材模板** | 修仙、都市、宫斗、悬疑等主流网文题材 |
| **一键发布番茄** | 浏览器自动化登录，HTTP API 直接上传章节 |
| **图片生成** | ModelScope API 生成小说封面和角色图片 |
| **正文导出** | 支持 Markdown / TXT / EPUB 格式 |
| **Dashboard 可视化** | 独立模块（FastAPI + React），实时查看项目状态 |
| **批量写作** | 连续撰写多章节，断点自动保存，可配置审查级别 |
| **中断恢复** | 精确的工作流状态追踪，检测断点并提供安全恢复选项 |

## 快速开始

### 安装

> **前置要求**：Python 3.10+，已添加到 PATH。

**一键安装**（推荐）：

```bash
curl -fsSL https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py | python3
```

或[下载 install.py](https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py) 后运行：

```bash
python install.py          # 全新安装
python install.py --update # 更新到最新版
python install.py --venv   # 虚拟环境安装
```

中国大陆用户下载失败时自动切换镜像。详细说明见 [INSTALL.md](./INSTALL.md)。

脚本会自动：
- 增量更新 .env 配置（保留您的 API Key）
- 覆盖安装 .opencode（更新到最新版本）

### 更新项目
重新运行 `python install.py` 即可更新到最新版本：
- 同步最新的 Skills、Agents 和配置模板
- 更新 Python 核心脚本和依赖

### 配置 API Key

编辑 `.env` 文件：

```bash
# Embedding 模型（向量化章节内容）
EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EMBED_API_KEY=your_api_key

# Rerank 模型（检索结果重排）
RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=jina-reranker-v3
RERANK_API_KEY=your_api_key

# 图片生成（ModelScope）
IMAGE_BASE_URL=https://api-inference.modelscope.cn/v1
IMAGE_MODEL=Qwen/Qwen-Image-2512
IMAGE_API_KEY=your_api_key
IMAGE_SIZE=1:1
```

### 在 OpenCode 中使用

```
/webnovel-init         # 初始化新项目
/webnovel-plan         # 规划大纲
/webnovel-write        # 撰写章节
/webnovel-write-batch  # 批量写作
/webnovel-review       # 审查润色
/webnovel-export       # 导出正文
/webnovel-publish      # 发布到番茄小说
/webnovel-dashboard    # 看板可视化
/webnovel-query        # 查询设定
/webnovel-learn        # 学习模式
/webnovel-image-gen    # 图片生成（封面/角色）
```

### 发布到番茄小说

在 OpenCode 中直接输入 `/webnovel-publish`，会通过交互式问答引导完成发布流程，无需记忆命令。

发布流程共 4 步：

1. **首次配置** - 安装 Playwright 并登录番茄作家后台（只需一次）
2. **获取书籍 ID** - 创建新书或查看已有书单
3. **上传章节** - 选择章节范围和发布模式
4. **完成** - 查看上传结果

详细命令说明见下方（可选）：

```bash
# 第1步：首次配置（只需运行一次）
pip install playwright
playwright install chromium
python .opencode/scripts/webnovel.py publish setup-browser

# 第2步：获取书籍 ID
python .opencode/scripts/webnovel.py publish list-books --project-root <项目路径>
python .opencode/scripts/webnovel.py publish create-book --title "标题" --genre "玄幻" --synopsis "简介" --project-root <项目路径>

# 第3步：上传章节
python .opencode/scripts/webnovel.py publish upload --book-id <ID> --range "1-10" --mode draft --project-root <项目路径>
```

## Skills（11个）

| 命令 | 功能描述 |
|------|----------|
| `/webnovel-init` | 深度初始化网文项目，收集创作信息生成项目骨架 |
| `/webnovel-plan` | 构建卷纲和章节大纲，继承创意约束 |
| `/webnovel-write` | 撰写章节，支持 `--fast` 和 `--minimal` 模式 |
| `/webnovel-write-batch` | 批量写作多章节，支持断点恢复和灵活审查级别 |
| `/webnovel-review` | 使用检查器审查章节质量 |
| `/webnovel-export` | 导出正文为 Markdown/TXT/EPUB 格式 |
| `/webnovel-publish` | 发布章节到番茄小说平台 |
| `/webnovel-dashboard` | 小说架构看板，可视化卷结构、角色状态、伏笔追踪 |
| `/webnovel-query` | 查询项目设定、角色、伏笔信息 |
| `/webnovel-learn` | 从当前会话提取可复用写作模式 |
| `/webnovel-image-gen` | 使用 ModelScope API 生成小说封面和角色图片 |

## Agents（10+ 个）

### Code Checkers（代码层）

确定性检查，运行在 LLM 之前，用于快速阻断严重问题：

| 检查器 | 说明 | 阻塞级别 |
|--------|------|----------|
| `world-consistency` | 战力/道具/时间线一致性 | critical 阻断 |
| `DebtTracker` | 债务追踪（伏笔/承诺/偿还） | high 阻断 |

### LLM Agents（语言模型层）

| Agent | 功能描述 |
|-------|----------|
| `context-agent` | 上下文搜集，生成创作执行包供写作直接使用 |
| `data-agent` | 数据处理，实体提取、场景切片、索引构建 |
| `consistency-checker` | 设定一致性检查，战力/地点/时间线/实体 |
| `continuity-checker` | 连贯性检查，场景过渡、伏笔管理 |
| `ooc-checker` | 人物 OOC 检查，防止角色行为与人设冲突 |
| `high-point-checker` | 爽点密度检查，支持迪化误解/身份掉马模式 |
| `pacing-checker` | Strand Weave 节奏检查，防止读者疲劳 |
| `reader-pull-checker` | 追读力检查，评估钩子/微兑现/约束分层 |

> 审查器配置驱动管理，配置文件位于 `.opencode/checkers/registry.yaml`
> 
> 详细开发指南请参阅 [审查器开发指南](docs/checkers.md)

### 审查器管理命令

```bash
# 列出审查器
python .opencode/scripts/webnovel.py checkers list

# 验证配置
python .opencode/scripts/webnovel.py checkers validate

# 创建新审查器
python .opencode/scripts/webnovel.py checkers create --id new-checker --name "新检查项" --category core
```

## 项目结构

```
项目目录/
├── .opencode/              # OpenCode 引擎核心
│   ├── agents/           # 10+ Agent 定义
│   ├── checkers/         # 审查器配置（registry.yaml, schema.yaml）
│   ├── skills/           # 12 个 Skills
│   ├── dashboard/        # 可视化面板（FastAPI + React）
│   │   ├── app.py        # FastAPI 应用入口
│   │   ├── server.py     # 服务器配置
│   │   ├── watcher.py    # 文件监听
│   │   ├── export_bridge.py  # 导出桥接
│   │   ├── publish_bridge.py # 发布桥接
│   │   └── frontend/     # React 前端
│   ├── dicts/            # 自定义词典（中文分词优化）
│   ├── genres/           # 题材参考（38+）
│   ├── references/       # 参考文档
│   │   ├── shared/       # 核心约束 / 爽点 / Strand 平衡
│   │   ├── csv/          # 9 张结构化知识表 + BM25 检索
│   │   ├── writing/      # 写作技法参考
│   │   ├── review/       # 审查规则
│   │   ├── index/        # 引用加载映射
│   │   └── outlining/    # 大纲参考
│   ├── templates/        # 输出模板
│   ├── scripts/          # Python 核心脚本
│   │   ├── data_modules/ # 核心数据模块（43+ .py）
│   │   │   ├── config.py           # 配置系统
│   │   │   ├── exceptions.py       # 统一异常体系
│   │   │   ├── rag_adapter/backend  # RAG 抽象
│   │   │   ├── context_manager.py   # 自适应上下文
│   │   │   ├── checkers_manager.py  # 分层审查管理
│   │   │   ├── state_manager.py     # 状态管理
│   │   │   ├── index_manager.py     # 索引管理
│   │   │   ├── webnovel.py         # CLI 入口 + COMMAND_REGISTRY
│   │   │   ├── story_system_engine.py  # 故事合约引擎
│   │   │   ├── story_contracts.py      # 合约数据模型
│   │   │   ├── event_log_store.py      # 事件溯源
│   │   │   ├── event_projection_router.py # 事件投影路由
│   │   │   ├── chapter_commit_service.py  # 章节提交
│   │   │   ├── memory/             # 记忆系统（8 模块）
│   │   │   ├── knowledge_query.py  # 时序知识查询
│   │   │   ├── reference_search.py # CSV BM25 检索
│   │   │   ├── debt_tracker.py     # 债务追踪
│   │   │   ├── condition_evaluator.py # 条件评估器
│   │   │   ├── temporal_graph.py   # Graph-RAG
│   │   │   └── image_generator.py  # ModelScope 图片生成
│   │   ├── story_system.py      # 故事系统 CLI
│   │   ├── story_events.py      # 事件日志 CLI
│   │   ├── chapter_commit.py    # 章节提交 CLI
│   │   ├── review_pipeline.py   # 审查管线 CLI
│   │   ├── reference_search.py  # BM25 检索 CLI
│   │   ├── validate_csv.py      # CSV 校验
│   │   └── export_manager.py    # 正文导出
│   └── .gitignore
├── docs/                  # 文档
│   ├── 新手引导.md / architecture.md / commands.md
│   ├── checkers.md / FAQ.md / genres.md
│   ├── operations.md / rag-and-config.md
│   ├── memory/            # 记忆系统架构
│   └── research/          # 研究笔记
├── .env                   # API 配置（不提交）
├── .gitignore
└── install.py             # 跨平台安装脚本
```

## 工作流程

```
1. 项目初始化 (/webnovel-init)
   └─→ 生成设定集、大纲、创意约束

2. 大纲规划 (/webnovel-plan)
   └─→ 生成卷纲、章纲 + 故事合约种子

3. 章节写作 (/webnovel-write)
   ├─→ CSV 知识检索（按需：命名规则/场景写法/写作技法）
   ├─→ story-system 刷新合约树
   ├─→ context-agent 搜集上下文
   ├─→ 分层审查 (Code Checkers → 6 个并行 LLM Agents)
   ├─→ 债务感知上下文预算
   ├─→ 撰写 + 润色 + Anti-AI 终检
   ├─→ data-agent 更新索引 + 事件溯源
   └─→ Git 备份 + 工作流断点记录

   批量写作 (/webnovel-write-batch)
   ├─→ 连续撰写多章节
   ├─→ 每章独立审查（minimal/standard/full）
   ├─→ 断点自动保存
   └─→ 完成后汇总报告

4. 查询设定 (/webnovel-query)
   └─→ RAG + Graph-RAG + CSV BM25 检索

5. 发布上线 (/webnovel-publish)
   └─→ 番茄小说平台发布
```

## CLI 命令索引

所有命令统一入口：

```bash
python .opencode/scripts/webnovel.py <command> [args]
```

| 命令 | 说明 |
|------|------|
| `where` | 显示当前项目根路径 |
| `preflight` | 校验运行环境 |
| `status` | 生成全书健康报告 |
| `state` | 状态管理（进度/实体/伏笔） |
| `index` | 索引管理 |
| `rag` | RAG 检索 |
| `entity` | 实体管理 |
| `context` | 上下文管理 |
| `checkers` | 审查器配置管理 |
| `workflow` | 工作流状态管理 |
| `backup` | Git 备份 |
| `export` | 正文导出 |
| `publish` | 番茄小说发布 |
| `dashboard` | 可视化面板启动 |
| `genimg` | 图片生成 |
| `chapter-path` | 打印章节文件路径 |
| `story-system` | 故事合约命令行 |
| `story-events` | 事件日志命令行 |
| `chapter-commit` | 章节提交命令行 |
| `review-pipeline` | 审查管线命令行 |

## 卸载

```bash
# 删除安装文件
rm -rf .opencode/ .env

# 卸载 Python 依赖
pip uninstall aiohttp filelock pydantic pytest pytest-asyncio pytest-cov -y
```

> 卸载不会影响你已创建的网文项目文件（正文、大纲、设定集等）。

## 测试

```bash
# 全量测试
python .opencode/scripts/run_all_tests.py

# 仅新增模块测试
python .opencode/scripts/run_new_tests.py
```

## 贡献

欢迎提交 Issue 和 Pull Request！

## 开源协议

[GPL v3](LICENSE) - 继承自原项目

## 致谢

- **[lingfengQAQ](https://github.com/lingfengQAQ)** - 原项目作者
- **[OpenCode](https://opencode.ai)** - AI 编程助手框架
- **[Cppys/OpenNovel](https://github.com/Cppys/OpenNovel)** - 番茄小说发布技术方案参考
