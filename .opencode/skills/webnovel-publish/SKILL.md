---
name: webnovel-publish
description: 将网文章节发布到番茄小说平台。立即使用此 skill 当用户说：发布小说、发布章节、上传到番茄、发布到番茄小说、上传章节、发布草稿。包含登录认证、书籍管理、章节上传的完整交互式流程引导。
compatibility: opencode
allowed-tools: Read Write Edit Glob Grep Bash Question Task
---

# 番茄小说发布

## 概述

此 skill 通过交互式问答引导用户完成番茄小说发布流程。底层使用 Playwright + Chromium 实现浏览器自动化，由 `publisher/` 模块提供核心功能。

## 交互式流程

当用户启动此 skill 时，按照以下步骤引导：

### 步骤 1：检查 Playwright 环境

使用 Bash 工具检查 Playwright 是否已安装：

```bash
python -c "import playwright; print('Playwright', playwright.__version__)"
```

如果未安装：
```bash
pip install playwright
playwright install chromium
```

> **注意**：首次安装 Chromium 需要约 300MB 磁盘空间。在网络受限环境下可使用 `--skip-playwright` 跳过。

### 步骤 2：询问用户当前状态

使用 Question 工具询问用户：

**问题**："请问您现在需要做什么？"
**选项**：
1. 首次配置 - 登录番茄作家后台
2. 查看已创建的书单
3. 创建新书
4. 上传章节
5. 其他问题

### 步骤 3：根据用户选择执行

#### 选择 1：首次配置（登录）

执行登录命令：
```bash
python .opencode/scripts/webnovel.py publish setup-browser
```

告诉用户：
- 会弹出浏览器窗口
- 使用番茄小说账号扫码登录
- 登录成功后状态自动保存到 `~/.opencode/fanqie_auth_state.json`
- 后续无需重复登录

> **故障排除**：
> - 登录超时（默认 3 分钟）：重新运行命令
> - 浏览器不弹出：检查 `--headed` 参数或显示器配置
> - 状态文件损坏：删除 `~/.opencode/fanqie_auth_state.json` 重新登录

#### 选择 2：查看书单

首先确认项目路径，询问用户（如未指定），然后执行：

```bash
python .opencode/scripts/webnovel.py publish list-books --project-root <项目路径>
```

展示结果给用户，并询问是否需要记录 `book_id`。

#### 选择 3：创建新书

**步骤 3.1：自动检测项目路径**

优先通过以下方式获取项目路径：
1. 用户当前工作目录是否包含 `.webnovel` 目录
2. 用户明确指定的项目路径
3. 使用命令自动检测：
```bash
python .opencode/scripts/webnovel.py where
```

**步骤 3.2：自动读取项目信息**

检测到项目路径后，尝试自动读取以下信息：

1. **title**（小说标题）：从 `[项目]/.webnovel/state.json` → `project_info.title`
2. **genre**（题材类型）：从 `[项目]/.webnovel/state.json` → `project_info.genre`
3. **protagonist1**（主角1）：从 `[项目]/.webnovel/state.json` → `protagonist_state.name`
4. **protagonist2**（主角2/女主）：从 `[项目]/.webnovel/state.json` → `project_info.heroine_names`
5. **synopsis**（小说简介）：从 `[项目]/大纲/总纲.md` 提取"故事一句话"部分（至少50字）

读取逻辑：
```
读取 state.json 的 project_info 部分
如果存在 protagonist_state.name，作为主角1
如果存在 heroine_names，作为女主/主角2
读取总纲.md 的第3-4行（"故事一句话"部分）作为简介基础
```

**步骤 3.3：展示并确认信息**

将读取到的信息展示给用户，格式如下：

```
检测到您的项目：[项目名]

以下信息已自动读取：

| 字段 | 值 | 确认? |
|------|-----|-------|
| 小说标题 | xxx | ✓ |
| 题材类型 | xxx | ✓ |
| 主角1 | xxx | ✓ |
| 主角2 | xxx | ✓/待补充 |
| 小说简介 | xxx... | 修改? |

请确认以上信息，或输入您想修改的部分。
```

**步骤 3.4：执行创建**

确认信息后执行：
```bash
python .opencode/scripts/webnovel.py publish create-book \
  --title "<标题>" \
  --genre "<题材>" \
  --synopsis "<简介>" \
  --protagonist1 "<主角1>" \
  --protagonist2 "<主角2>" \
  --project-root <项目路径>
```

成功后将 `book_id` 告知用户，建议记录。

#### 选择 4：上传章节

询问用户以下信息：
1. 番茄书籍 ID（必填）
2. 要上传的章节范围，如：1-10、1,3,5、all（必填）
3. 发布模式：draft（草稿）或 publish（直接发布）（必填）

确认后执行：
```bash
python .opencode/scripts/webnovel.py publish upload \
  --book-id <书籍ID> \
  --range <章节范围> \
  --mode <模式> \
  --project-root <项目路径>
```

或者上传全部：
```bash
python .opencode/scripts/webnovel.py publish upload-all \
  --book-id <书籍ID> \
  --mode <模式> \
  --project-root <项目路径>
```

展示上传结果（成功/失败数量）。

#### 选择 5：其他问题

根据用户具体问题，提供相应帮助。

## 项目路径获取

如果用户未指定项目路径，按以下优先级获取：

1. 询问用户指定
2. 使用命令自动检测：
```bash
python .opencode/scripts/webnovel.py where
```

## 常见问题处理

| 用户问题 | 解答 |
|---------|------|
| 登录失败 | 重新运行 setup-browser，检查网络，确认番茄平台可访问 |
| 浏览器不弹出 | 检查显示器配置，确认 `--headed` 模式，尝试 `DISPLAY=:0`（Linux） |
| 不知道 book_id | 运行 list-books 查看，或在番茄后台获取 |
| 每天只能创建 1 本书 | 番茄平台限制，已创建需明天再试 |
| 上传失败 | 检查网络连接，确认番茄后台可访问，查看日志分析具体错误 |
| Playwright 安装失败 | 使用 `--skip-playwright` 跳过，手动安装 Chromium 后重试 |
| 登录状态过期 | 删除 `~/.opencode/fanqie_auth_state.json`，重新执行 setup-browser |

## 输出格式示例

### 询问用户

```
您好！我是番茄小说发布助手。

请问您现在需要做什么？

1. 首次配置 - 登录番茄作家后台
2. 查看已创建的书单
3. 创建新书
4. 上传章节
5. 其他问题
```

### 上传结果

```
上传完成！

成功: 10 章
失败: 0 章

✓ 第 1 章 少年出山
✓ 第 2 章 初入江湖
✓ 第 3 章 宗门大比
...
```
