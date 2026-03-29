---
name: webnovel-publish
description: 将网文章节发布到番茄小说平台。立即使用此 skill 当用户说：发布小说、发布章节、上传到番茄、发布到番茄小说、上传章节、发布草稿。包含登录认证、书籍管理、章节上传的完整交互式流程引导。
allowed-tools: Read Write Edit Glob Grep Bash Question Task
---

# 番茄小说发布

## 概述

此 skill 通过交互式问答引导用户完成番茄小说发布流程。无需记住命令，skill 会一步步询问用户需要做什么。

## 交互式流程

当用户启动此 skill 时，按照以下步骤引导：

### 步骤 1：检查 Playwright 是否已安装

使用 Bash 工具检查 Playwright 是否已安装：
```bash
pip show playwright
```

如果未安装或安装不完整，自动执行安装：
```bash
pip install playwright
playwright install chromium --with-deps
```

如果浏览器已安装但不可用，会提示用户重新安装。

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

**自动检查并安装 Playwright**（如果需要）：

1. 首先检查 Playwright 是否已安装：
```bash
pip show playwright
```

2. 如果未安装或不可用，执行安装：
```bash
pip install playwright
playwright install chromium --with-deps
```

3. 安装完成后，执行登录：
```bash
python .opencode/scripts/webnovel.py publish setup-browser
```

告诉用户：
- 会弹出浏览器窗口
- 使用番茄小说账号扫码登录
- 登录成功后状态自动保存
- 后续无需重复登录

#### 选择 2：查看书单

首先确认项目路径，询问用户：
- "请告诉我您的项目路径"（如果用户未指定）

然后执行：
```bash
python .opencode/scripts/webnovel.py publish list-books --project-root <项目路径>
```

展示结果给用户，并询问是否需要记录 book_id。

#### 选择 3：创建新书

询问用户以下信息：
1. 小说标题（必填）
2. 题材类型（必填），如：玄幻、都市、仙侠、言情等
3. 小说简介（必填，至少50字）
4. 主角1名字（可选）
5. 主角2名字（可选）

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

成功后将 book_id 告知用户，建议记录。

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
| 登录失败 | 重新运行 setup-browser，检查网络 |
| 不知道 book_id | 运行 list-books 查看，或在番茄后台获取 |
| 每天只能创建1本书 | 番茄平台限制，已创建需明天再试 |
| 上传失败 | 检查网络连接，确保番茄后台可访问 |

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
