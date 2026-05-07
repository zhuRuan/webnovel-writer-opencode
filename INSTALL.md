---
name: webnovel-install
description: 自动安装 Webnovel Writer。触发条件："安装"、"重新安装"、"更新"、"安装依赖"、"setup"、"初始化环境"。
compatibility: opencode
allowed-tools: Bash
---

# Webnovel Writer 安装

## 目标

一键安装或更新 Webnovel Writer 插件到当前 OpenCode 工作区。

## 执行流程

### 方式 1：curl 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py | python3
```

### 方式 2：下载后运行

```bash
# 下载安装脚本
python -c "import urllib.request; urllib.request.urlretrieve('https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/install.py', 'install.py')"

# 全新安装
python install.py

# 更新到最新版本
python install.py --update

# 创建虚拟环境安装
python install.py --venv

# 跳过 playwright 浏览器（节省时间）
python install.py --skip-playwright
```

### 安装过程（4步）

1. **系统预检** — Python 版本、磁盘空间、网络连通性
2. **下载** — 从 GitHub 下载最新 .opencode/（中国大陆自动切换镜像）
3. **安装依赖** — pip install + 可选 playwright
4. **验证** — 运行 preflight 确认安装成功

### 如果 OpenCode 正在运行

安装脚本检测到 OpenCode 正在运行时自动进入 staging 模式：

```
1. 关闭所有 OpenCode 窗口
2. 运行: python install.py --apply
3. 重新打开 OpenCode
```

### 更新

```bash
# 检查并安装更新
python install.py --update
```

增量更新机制：对比 manifest.json，只下载变更文件。

## 常见问题

| 问题 | 解决 |
|------|------|
| 下载失败 | 网络问题，使用 `--mirror` 指定镜像 |
| OpenCode 占用 | 关闭 OpenCode 后运行 `python install.py --apply` |
| pip 安装失败 | 检查 Python 版本 >= 3.10，或用 `--venv` 创建虚拟环境 |
| 权限不足 | Linux/macOS 尝试 `sudo`，Windows 以管理员运行 |
