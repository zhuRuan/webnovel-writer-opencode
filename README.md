# Webnovel Writer for OpenCode

> 遇到问题？先查阅 [常见问题](./docs/FAQ.md)

[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![OpenCode](https://img.shields.io/badge/OpenCode-Compatible-purple.svg)](https://opencode.ai)
[![GitHub Stars](https://img.shields.io/github/stars/lujih/webnovel-writer-opencode)](https://github.com/lujih/webnovel-writer-opencode/stargazers)
[![Python](https://img.shields.io/badge/Python-3.9+-green.svg)](https://python.org)

---

## 项目介绍

Webnovel Writer 是基于 OpenCode 的长篇网文 AI 创作系统，降低 AI 写作中的"遗忘"和"幻觉"，支持长周期连载创作。

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **完整写作工作流** | 项目初始化 → 大纲规划 → 章节写作 → 审查润色 |
| **RAG 上下文管理** | 智能检索相关设定、角色、伏笔，保持长篇一致性 |
| **多维度质量检查** | 设定一致性、连贯性、OOC、爽点、节奏、追读力 |
| **38+ 题材模板** | 修仙、都市、宫斗、悬疑等主流网文题材 |
| **一键发布番茄** | 浏览器自动化登录，HTTP API 直接上传章节 |
| **Dashboard 可视化** | 实时查看项目状态、角色状态、伏笔追踪 |
| **章节同步工具** | 自动同步缺失章节，验证数据完整性 |

---

## 快速开始

### 1. 安装

在 OpenCode 中输入以下提示词完成安装：

```
根据 https://github.com/lujih/webnovel-writer-opencode/blob/master/INSTALL.md 安装 Webnovel Writer 项目
```

> 安装前建议删除旧的 `install.py`（如有），避免版本冲突。

### 2. 配置 API Key

编辑 `.env` 文件，填入以下配置：

```ini
# ========== Embedding 模型（向量化章节内容）==========
EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EMBED_API_KEY=你的API密钥

# ========== Rerank 模型（检索结果重排）==========
RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=jina-reranker-v3
RERANK_API_KEY=你的API密钥
RERANK_ENABLED=true

# ========== LLM 模型（用于 plot extract 等命令）==========
LLM_BASE_URL=https://api-inference.modelscope.cn/v1
LLM_MODEL=deepseek-ai/DeepSeek-V3.2
LLM_API_KEY=你的API密钥

```

### 3. 开始使用

在 OpenCode 中直接输入命令：

| 命令 | 功能 |
|------|------|
| `/webnovel-init` | 初始化新项目 |
| `/webnovel-plan` | 规划大纲 |
| `/webnovel-write` | 撰写章节 |
| `/webnovel-review` | 审查润色 |
| `/webnovel-export` | 导出正文 |
| `/webnovel-publish` | 发布到番茄小说 |
| `/webnovel-dashboard` | 可视化看板 |
| `/webnovel-query` | 查询设定 |
| `/webnovel-resume` | 恢复写作 |
| `/webnovel-learn` | 学习模式 |

---

## 系统要求

- **Python 3.9+**（必须）
- **OpenCode** 运行环境
- 网络连接（下载依赖、调用 API）

---

## 发布到番茄小说

在 OpenCode 中输入 `/webnovel-publish`，按交互引导完成：

1. 首次配置 → 安装 Playwright 并登录（只需一次）
2. 获取书籍 ID → 创建或选择已有书籍
3. 上传章节 → 选择范围和发布模式
4. 完成 → 查看上传结果

---

## 工作流程

```
项目初始化 (/webnovel-init)   →   生成设定集、大纲、创意约束
        ↓
大纲规划 (/webnovel-plan)    →   生成卷纲、章纲
        ↓
章节写作 (/webnovel-write)   →   上下文搜集 → 撰写正文 → 多维度审查 → 更新索引
        ↓
发布上线 (/webnovel-publish)
```

---

## 项目结构

```
项目目录/
├── .webnovel/              # 状态管理
│   ├── state.json          # 小说状态
│   └── index.db            # 向量索引
├── 正文/                    # 章节正文
├── 设定集/                  # 角色、势力设定
├── 大纲/                    # 卷纲、章纲
├── .opencode/              # 核心配置
│   ├── skills/             # 10个技能
│   ├── agents/             # 8个代理
│   ├── dashboard/          # 可视化看板
│   ├── scripts/            # Python 脚本
│   ├── genres/             # 38+题材模板
│   └── templates/          # 输出模板
├── .env                    # API 配置
└── install.py              # 安装脚本
```

---

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

---

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

---

## 卸载

```bash
# 删除安装文件
rm -rf .opencode/ .env

# 卸载 Python 依赖
pip uninstall aiohttp filelock pydantic pytest pytest-asyncio pytest-cov -y
```

> 卸载不会影响你已创建的网文项目文件（正文、大纲、设定集等）。

---

## 开源协议

[GPL v3](LICENSE)

---

## 致谢

- **[lingfengQAQ](https://github.com/lingfengQAQ)** - 原项目作者
- **[OpenCode](https://opencode.ai)** - AI 编程助手框架
- **[Cppys/OpenNovel](https://github.com/Cppys/OpenNovel)** - 番茄小说发布技术方案参考