---
name: webnovel-install
description: 自动安装 Webnovel Writer。触发条件："安装"、"重新安装"、"更新"、"安装依赖"、"setup"、"初始化环境"。
compatibility: opencode
allowed-tools: Bash
---

# Webnovel Writer 安装

## 目标

一键安装或更新 Webnovel Writer 插件到当前 OpenCode 工作区。

## 快速开始

**macOS / Linux：**
```bash
curl -fsSL https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py | python3
```

**Windows（PowerShell）：**
```powershell
Invoke-WebRequest -Uri https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py -OutFile install.py
python install.py
```

运行 `python install.py`（无参数）会进入**可视化交互菜单**，引导你选择操作。

## 所有安装命令

| 命令 | 说明 |
|------|------|
| `python install.py` | **交互式菜单（推荐）** |
| `python install.py --update` | 检查版本 + 全量更新 |
| `python install.py --incremental` | 增量更新（manifest.json diff，仅下载变更文件） |
| `python install.py --clean` | 擦除 `.opencode/` 后全新安装 |
| `python install.py --apply` | 应用暂存更新（关闭 OpenCode 后） |
| `python install.py --uninstall` | 卸载，删除 `.opencode/`，保留项目文件 |
| `python install.py --uninstall --full --yes` | 完全卸载，`.opencode/` + `.venv/` |
| `python install.py --venv` | 创建并使用 `.venv/` 虚拟环境 |
| `python install.py --skip-playwright` | 跳过 Playwright 浏览器安装 |
| `python install.py --mirror URL` | 使用自定义 GitHub 镜像 |

## 交互菜单

```
============================================================
  Webnovel Writer for OpenCode — 安装管理
============================================================
  状态: 已安装 (v2.8.0)
------------------------------------------------------------

  请选择操作:

  [1] 安装 / 更新        下载最新版本并安装
  [2] 增量更新            仅更新变更文件 (快)
  [3] 清洁安装            擦除后全新安装
  [4] 应用暂存更新        关闭 IDE 后执行两阶段更新
  [5] 卸载                移除 .opencode/
  [6] 完全卸载            移除 .opencode/ + .venv/
  [0] 退出

  输入数字选择 (默认=1):
```

菜单会自动检测当前状态（是否已安装、版本号、有无待应用的暂存更新）。

## 安装过程

1. **系统预检** — Python 版本、磁盘空间、网络连通性
2. **下载** — 从 GitHub 下载最新 `.opencode/`（中国大陆自动切换镜像）
3. **安装依赖** — pip install + 可选 playwright
4. **验证** — 运行 preflight 确认安装成功

## 如果 OpenCode 正在运行

安装脚本检测到 OpenCode 正在运行时自动进入 staging 模式：

1. 关闭所有 OpenCode 窗口
2. 运行: `python install.py --apply`
3. 重新打开 OpenCode

## 增量更新 vs 全量更新

| 方式 | 命令 | 适用场景 |
|------|------|---------|
| 增量更新 | `--incremental` | 网络慢、改动少（仅对比 manifest.json，按文件更新） |
| 全量更新 | `--update` 或菜单 [1] | 正常更新（下载完整 zip） |
| 清洁安装 | `--clean` 或菜单 [3] | 安装异常、文件损坏时 |

## 常见问题

| 问题 | 解决 |
|------|------|
| 下载失败 | 网络问题，使用 `--mirror` 指定镜像 |
| OpenCode 占用 | 关闭 OpenCode 后运行 `python install.py --apply` |
| pip 安装失败 | 检查 Python 版本 >= 3.10，或用 `--venv` 创建虚拟环境 |
| 权限不足 | Linux/macOS 尝试 `sudo`，Windows 以管理员运行 |
| 安装后异常 | 运行 `python install.py --clean` 清洁重装 |
| 完全移除 | `python install.py --uninstall --full --yes` |
