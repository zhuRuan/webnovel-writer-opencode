# Webnovel Writer for OpenCode

> 遇到问题？先查阅 [常见问题](./docs/FAQ.md)

[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![OpenCode](https://img.shields.io/badge/OpenCode-Compatible-purple.svg)](https://opencode.ai)
[![GitHub Stars](https://img.shields.io/github/stars/lujih/webnovel-writer-opencode)](https://github.com/lujih/webnovel-writer-opencode/stargazers)
[![Python](https://img.shields.io/badge/Python-3.9+-green.svg)](https://python.org)

## 项目介绍

Webnovel Writer for OpenCode 是一个基于 OpenCode 的长篇网文 AI 创作系统，目标降低 AI 写作中的"遗忘"和"幻觉"，支持长周期连载创作。

本项目是基于 [lingfengQAQ/webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer) 改编的 OpenCode 版本。

## 系统要求

- **Python 3.9 或更高版本**（安装和运行核心脚本必需）
- **OpenCode** 运行环境
- 网络连接（用于下载依赖、调用 API 等）

## 核心特性

| 特性 | 说明 |
|------|------|
| **完整写作工作流** | 项目初始化 → 大纲规划 → 章节写作 → 审查润色 |
| **RAG 上下文管理** | 智能检索相关设定、角色、伏笔，保持长篇一致性 |
| **多维度质量检查** | 设定一致性、连贯性、OOC、爽点、节奏、追读力 |
| **38+ 题材模板** | 修仙、都市、宫斗、悬疑等主流网文题材 |
| **一键发布番茄** | 浏览器自动化登录，HTTP API 直接上传章节 |
| **状态 JSON 导出** | 健康报告支持 JSON 格式，便于程序处理 |
| **Dashboard 可视化** | 独立模块（FastAPI + React），实时查看项目状态 |
| **插件系统** | 支持扩展 Agent/Skill/Checker/Publisher/Hook |
| **章节同步工具** | 自动同步缺失章节，验证数据完整性 |

## 快速开始

### 安装

> **前置要求**：请确保已安装 Python 3.9+，并已添加到 PATH 环境变量。  
> 如果你尚未安装 Python，请访问 [python.org](https://www.python.org/downloads/) 下载并安装。

复制下方到 OpenCode 完成安装：

    搜索并执行这套安装 Webnovel Writer 的提示词 https://github.com/lujih/webnovel-writer-opencode/blob/master/INSTALL.md

安装前，建议先删除旧的 install.py（如有），避免版本冲突。

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
```

### 在 OpenCode 中使用

```
/webnovel-init      # 初始化新项目
/webnovel-plan      # 规划大纲
/webnovel-write     # 撰写章节
/webnovel-review    # 审查润色
/webnovel-export    # 导出正文
/webnovel-publish   # 发布到番茄小说
/webnovel-dashboard # 看板可视化
/webnovel-query     # 查询设定
/webnovel-resume    # 恢复写作
/webnovel-learn     # 学习模式
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



## Skills（10个）

| 命令 | 功能描述 |
|------|----------|
| `/webnovel-init` | 深度初始化网文项目，收集创作信息生成项目骨架 |
| `/webnovel-plan` | 构建卷纲和章节大纲，继承创意约束 |
| `/webnovel-write` | 撰写章节，支持 `--fast` 和 `--minimal` 模式 |
| `/webnovel-review` | 使用检查器审查章节质量 |
| `/webnovel-export` | 导出正文为 Markdown/TXT/EPUB 格式 |
| `/webnovel-publish` | 发布章节到番茄小说平台 |
| `/webnovel-dashboard` | 小说架构看板，可视化卷结构、角色状态、伏笔追踪 |
| `/webnovel-query` | 查询项目设定、角色、伏笔信息 |
| `/webnovel-resume` | 恢复中断的写作任务 |
| `/webnovel-learn` | 从当前会话提取可复用写作模式 |

## Agents（8个）

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
├── .opencode/              # OpenCode 配置
│   ├── agents/           # Agent 定义（context-agent, data-agent）
│   ├── checkers/         # 审查器配置（registry.yaml, schema.yaml, agents/）
│   ├── skills/           # 10个 Skills
│   ├── dashboard/        # 可视化面板（FastAPI + React 前端）
│   │   ├── app.py        # FastAPI 应用入口
│   │   ├── server.py     # 服务器配置
│   │   ├── watcher.py    # 文件监听
│   │   ├── plugin_bridge.py  # 插件桥接
│   │   ├── publish_bridge.py # 发布桥接
│   │   └── frontend/     # React 前端
│   ├── plugins/          # 插件目录
│   │   ├── demo_checker/ # 示例插件
│   │   └── auto_fix_hook/# 自动修复钩子
│   ├── scripts/          # Python 核心脚本
│   │   ├── publisher/    # 番茄小说发布模块
│   │   ├── data_modules/ # 核心数据模块
│   │   ├── sync_chapters_to_db.py   # 章节同步
│   │   ├── sync_missing_chapters.py # 缺失章节同步
│   │   └── verify_chapters.py       # 章节验证
│   ├── references/       # 参考文档
│   ├── genres/           # 题材参考（38+）
│   └── templates/        # 输出模板
├── .env                   # API 配置
└── install.py             # 跨平台安装脚本
```

## 工作流程

```
1. 项目初始化 (/webnovel-init)
   └─→ 生成设定集、大纲、创意约束

2. 大纲规划 (/webnovel-plan)
   └─→ 生成卷纲、章纲

3. 章节写作 (/webnovel-write)
   ├─→ context-agent 搜集上下文
   ├─→ 撰写章节正文
   ├─→ 多维度审查（6个检查器）
   └─→ data-agent 更新索引

4. 查询设定 (/webnovel-query)
   └─→ RAG 检索相关上下文

5. 发布上线 (/webnovel-publish)
   ├─→ 交互式引导选择操作
   ├─→ 配置登录/创建书籍/上传章节
   └─→ 番茄小说平台发布
```

## 卸载

```bash
# 删除安装文件
rm -rf .opencode/ .env

# 卸载 Python 依赖
pip uninstall aiohttp filelock pydantic pytest pytest-asyncio pytest-cov -y
```

> 卸载不会影响你已创建的网文项目文件（正文、大纲、设定集等）。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 开源协议

[GPL v3](LICENSE) - 继承自原项目

## 致谢

- **[lingfengQAQ](https://github.com/lingfengQAQ)** - 原项目作者
- **[OpenCode](https://opencode.ai)** - AI 编程助手框架
- **[Cppys/OpenNovel](https://github.com/Cppys/OpenNovel)** - 番茄小说发布技术方案参考
