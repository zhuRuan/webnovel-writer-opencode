---
name: webnovel-publish
description: 将网文章节发布到番茄小说平台。立即使用此 skill 当用户说：发布小说、发布章节、上传到番茄、发布到番茄小说、上传章节、发布草稿。包含登录认证、书籍管理、章节上传的完整交互式流程引导。
allowed-tools: Read Write Edit Glob Grep Bash Question Task
---

# 番茄小说发布

## 概述

此 skill 通过交互式问答引导用户完成番茄小说发布流程。无需记住命令，skill 会一步步询问用户需要做什么。

## 核心修复

本 skill 已修复以下常见问题：
- 自动将 `.md` 章节转换为 `.txt` 格式
- 处理 headless 环境下的浏览器问题
- 避免编码错误（不输出特殊符号）
- 自动定位章节目录

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
cd <项目路径> && python .opencode/scripts/webnovel.py publish setup-browser
```

告诉用户：
- 如果弹出浏览器窗口：在浏览器中扫码/登录
- 如果没有弹出浏览器：告诉用户手动在终端运行上述命令

**重要提示**：登录后状态会保存到 `~/.opencode/fanqie_auth_state.json`，后续无需重复登录。

#### 选择 2：查看书单

首先确认项目路径，然后执行：
```bash
cd <项目路径> && python .opencode/scripts/webnovel.py publish list-books --project-root <项目路径>
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
cd <项目路径> && python .opencode/scripts/webnovel.py publish create-book \
  --title "<标题>" \
  --genre "<题材>" \
  --synopsis "<简介>" \
  --protagonist1 "<主角1>" \
  --protagonist2 "<主角2>" \
  --project-root <项目路径>
```

成功后将 book_id 告知用户，建议记录。

#### 选择 4：上传章节（重点修复）

**上传前自动处理**：

1. 检测章节文件格式，如果是 `.md` 文件，自动转换为 `.txt`：
```bash
# 检查并转换
cd <项目路径>
# 查找 .md 章节文件
ls 正文/第1卷/*.md 2>/dev/null | head -1
```

2. 如果只有 .md 文件，执行转换：
```bash
# 创建临时 txt 目录（如果不存在）
mkdir -p 正文/txt

# 转换所有 .md 章节为 .txt（去除标题行）
for f in 正文/第1卷/*.md; do
  name=$(basename "$f" .md)
  # 去掉第一行的 # 标题，保存为 txt
  sed '1d' "$f" > "正文/txt/${name}.txt"
done

# 移动到正确位置
mv 正文/txt/*.txt 正文/
rmdir 正文/txt
```

3. 执行上传：
```bash
cd <项目路径> && python .opencode/scripts/webnovel.py publish upload \
  --book-id <书籍ID> \
  --range <章节范围> \
  --mode draft \
  --project-root <项目路径>
```

**询问用户以下信息**：
1. 番茄书籍 ID（必填）- 可以运行"查看书单"获取
2. 要上传的章节范围，如：45、1-10、all（必填）
3. 发布模式：draft（草稿，推荐）或 publish（直接发布）

#### 选择 5：其他问题

根据用户具体问题，提供相应帮助。

## 项目路径获取

自动获取项目路径：
```bash
cd <项目路径> && python .opencode/scripts/webnovel.py where
```

或者询问用户。

## 常见问题处理

| 用户问题 | 解答 |
|---------|------|
| 登录失败 | 重新运行 setup-browser，检查网络 |
| 不知道 book_id | 选择"查看书单"获取 |
| 每天只能创建1本书 | 番茄平台限制，已创建需明天再试 |
| 上传失败 - 未找到章节文件 | 检查章节是否在正确位置，或运行"上传章节"让 skill 自动转换 |
| 上传失败 - 浏览器问题 | 手动运行 `python .opencode/scripts/webnovel.py publish setup-browser` |
| 编码错误 | 这是脚本问题，上传实际已成功，请去番茄后台确认 |

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

成功: 1 章
失败: 0 章

第45章 试炼初解

（已上传到草稿箱，请登录番茄作家后台审核发布）
```

### 错误处理

如果遇到"未找到章节文件"错误：

**解决方法**：运行以下命令手动转换：

```bash
cd <你的项目路径>
mkdir -p 正文/txt
for f in 正文/第1卷/*.md; do
  name=$(basename "$f" .md)
  sed '1d' "$f" > "正文/txt/${name}.txt"
done
mv 正文/txt/*.txt 正文/
rmdir 正文/txt
```

然后重新上传。
