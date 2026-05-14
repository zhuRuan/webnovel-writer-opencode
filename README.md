# Webnovel Writer for OpenCode

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
| **Graph-RAG + 持久化** | 实体关系图谱，SQLite 持久化 |
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
| **一键发布番茄** | Playwright 浏览器自动化 + HTTP API 直接上传章节 |
| **正文导出** | 支持 Markdown / TXT / EPUB / HTML / DOCX / PDF 六种格式 |
| **Dashboard 可视化** | FastAPI + React 19，ECharts 图表，实时查看项目状态 |
| **批量写作** | 连续撰写多章节，断点自动保存，每章完整审查流程 |
| **中断恢复** | 精确的工作流状态追踪，检测断点并提供安全恢复选项 |
| **增量更新** | manifest.json SHA256 diff，只下载变更文件 |

## 快速开始

### 安装

> **前置要求**：Python 3.10+，已添加到 PATH。

**macOS / Linux**：

```bash
curl -fsSL https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py | python3
```

**Windows**（PowerShell）：

```powershell
Invoke-WebRequest -Uri https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py -OutFile install.py
python install.py
```

运行 `python install.py`（无参数）进入**交互式菜单**，自动检测安装状态并提供 6 种操作选项。也可直接命令行调用：

```bash
python install.py              # 交互菜单（推荐）
python install.py --update     # 更新到最新版
python install.py --incremental # 增量更新（仅变更文件）
python install.py --clean      # 清洁安装
python install.py --uninstall  # 卸载
python install.py --venv       # 虚拟环境安装
```

中国大陆用户下载失败时自动切换 GitHub 镜像。详细说明见 [INSTALL.md](./INSTALL.md)。

安装过程自动完成：系统预检 → 下载 → pip 安装依赖 → 验证。如果 OpenCode 正在运行，新版本保存到 `.opencode_staging/`，关闭后运行 `python install.py --apply` 完成更新。

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
/webnovel-dashboard    # 启动可视化看板
/webnovel-query        # 查询设定
/webnovel-learn        # 学习模式

```

## 项目结构

```
webnovel-writer/            # 仓库根目录（OpenCode 工作区）
├── install.py              # 一键安装引导脚本
├── manifest.json           # 文件清单（SHA256，增量更新用）
├── .env                    # API 配置（不提交）
├── .opencode/              # OpenCode 引擎核心
│   ├── agents/             # Agent 定义（context-agent, data-agent, reviewer 等）
│   ├── skills/             # 11 个 Skills（webnovel-*）
│   ├── dashboard/          # 可视化面板（FastAPI + React 19）
│   │   ├── app.py          # FastAPI 应用入口
│   │   ├── server.py       # 服务器配置
│   │   ├── watcher.py      # 文件监听
│   │   └── frontend/       # React 前端（ECharts）
│   ├── installer/          # 安装器模块（纯 stdlib，pip 安装前可运行）
│   ├── genres/             # 题材模板（38+）
│   ├── references/         # 参考文档
│   │   ├── shared/         # 核心约束 / 爽点 / Strand 平衡
│   │   ├── csv/            # 9 张结构化知识表 + BM25 检索
│   │   ├── writing/        # 写作技法参考
│   │   ├── review/         # 审查规则
│   │   ├── index/          # 引用加载映射
│   │   └── outlining/      # 大纲参考
│   ├── templates/          # 输出模板
│   └── scripts/            # Python 核心脚本
│       ├── webnovel.py     # CLI 统一入口
│       ├── gen_manifest.py # manifest.json 生成器
│       ├── conftest.py     # pytest 配置
│       ├── data_modules/   # 核心数据模块
│       │   ├── config.py                  # 配置系统
│       │   ├── context_manager.py         # 自适应上下文
│       │   ├── story_system_engine.py     # 故事合约引擎
│       │   ├── story_contracts.py         # 合约数据模型
│       │   ├── event_log_store.py         # 事件溯源
│       │   ├── event_projection_router.py # 事件投影路由
│       │   ├── chapter_commit_service.py  # 章节提交
│       │   ├── memory/                    # 记忆系统
│       │   ├── debt_tracker.py            # 债务追踪
│       │   ├── state_manager.py           # 状态管理
│       │   ├── index_manager.py           # 索引管理
│       │   ├── reference_search.py        # CSV BM25 检索
│       │   └── tests/                     # 59 个测试文件
│       ├── publisher/                     # 发布模块
│       └── tests/                         # 安装器测试
├── docs/                  # 文档
│   ├── architecture/      # 系统架构
│   ├── guides/            # 使用指南
│   ├── operations/        # 运维文档
│   ├── memory/            # 记忆系统设计
│   ├── research/          # 研究笔记
│   └── superpowers/       # 设计规格 & 实现计划
└── .gitignore
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
   ├─→ 每章完整单章流程（不简化、不跳步）
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
| `backup` | Git 备份 |
| `export` | 正文导出 |
| `publish` | 番茄小说发布 |
| `dashboard` | 可视化面板启动 |
| `chapter-path` | 打印章节文件路径 |
| `story-system` | 故事合约命令行 |
| `story-events` | 事件日志命令行 |
| `chapter-commit` | 章节提交命令行 |
| `review-pipeline` | 审查管线命令行 |

## Agents

| Agent | 功能描述 |
|-------|----------|
| `context-agent` | 上下文搜集，生成写作任务书供写作直接使用 |
| `data-agent` | 数据处理，实体提取、场景切片、索引构建 |
| `reviewer` | 综合审查：设定一致性、连贯性、OOC、爽点、节奏、追读力 |
| `deconstruction-agent` | 作品解构分析 |

## 卸载

```bash
python install.py --uninstall              # 卸载 .opencode/，保留项目文件
python install.py --uninstall --full --yes # 完全卸载 .opencode/ + .venv/
```

> 卸载不会影响你已创建的网文项目文件（正文、大纲、设定集等）。`.env` 文件在工作区根目录，需单独删除。

## 测试

```bash
# 全量测试
python -m pytest .opencode/scripts/data_modules/tests/ -q --no-cov

# 安装器测试
python -m pytest .opencode/scripts/tests/installer/ -v --no-cov

# 快速冒烟测试
pwsh .opencode/scripts/run_tests.ps1 -Mode smoke
```

## 贡献

欢迎提交 Issue 和 Pull Request！

## 开源协议

[GPL v3](LICENSE) - 继承自原项目

## 致谢

- **[lingfengQAQ](https://github.com/lingfengQAQ)** - 原项目作者
- **[OpenCode](https://opencode.ai)** - AI 编程助手框架
- **[Cppys/OpenNovel](https://github.com/Cppys/OpenNovel)** - 番茄小说发布技术方案参考
