---
name: webnovel-install
description: 自动安装 Webnovel Writer。立即使用此 skill 当用户说：安装、重新安装、更新、安装依赖、setup、初始化环境，或者执行/webnovel-install命令时。自动检测Python环境、下载配置文件、安装依赖。
---

# Webnovel Writer 自动安装

## 目标

自动执行完整的安装流程：
1. 检测系统依赖（Python 3.9+, pip）
2. 下载/更新配置文件（.env, requirements.txt）
3. 安装/更新 .opencode 核心文件
4. 安装 Python 依赖
5. 可选：安装 playwright（用于发布功能）

## 执行流程

### Step 1：检测环境

检查 Python 和 pip 是否可用：

```bash
python --version
pip --version
```

如果 Python < 3.9 或缺少 pip，提示用户先安装。

### Step 2：下载安装脚本

从 GitHub 下载安装脚本：

```
https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py
```

保存为 `install.py`（如果已存在，先删除再下载）。

### Step 3：执行安装

运行安装脚本：

```bash
python install.py
```

或带参数运行（跳过 playwright 安装）：

```bash
python install.py --skip-playwright
```

### Step 4：验证安装

检查以下文件/目录是否存在：
- `.opencode/` 目录
- `.env` 文件

### Step 5：配置 API Key

提醒用户编辑 `.env` 文件填入必要的 API Key：
- `EMBED_API_KEY` - ModelScope 或其他 Embedding 服务
- `RERANK_API_KEY` - Jina AI 或其他 Rerank 服务

## 参数选项

安装脚本支持以下参数：

| 参数 | 说明 | 默认 |
|------|------|------|
| `--yes`, `-y` | 自动确认所有交互 | 需交互确认 |
| `--skip-playwright` | 跳过 playwright 安装 | 会询问 |
| `--timeout`, `-t` | 网络超时秒数 | 30 |

## 常见问题

**Q: 安装失败，提示"权限不足"**
A: 关闭 OpenCode 后重试，或手动删除 `.opencode` 目录后重新安装。

**Q: 已有 .env 配置，安装会覆盖吗？**
A: 不会。安装脚本会保留现有的 API Key，只更新新增的配置项。

**Q: 如何更新到最新版本？**
A: 重新运行 `python install.py`，脚本会自动覆盖安装 `.opencode`。

## 引用文件

安装完成后，用户可以开始新项目：

```bash
/webnovel-init
```

或查看帮助：

```bash
python .opencode/scripts/webnovel.py --help
```
