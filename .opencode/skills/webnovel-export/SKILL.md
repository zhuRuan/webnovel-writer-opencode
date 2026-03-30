---
name: webnovel-export
description: 将网文正文导出为 Markdown/TXT/EPUB 格式。立即使用此 skill 当用户说：导出、发布小说、导出章节、生成电子书、导出 TXT、导出 Markdown、导出 EPUB、下载小说、输出正文章节。无论用户是否明确说"导出"，只要意图是将章节内容输出为文件，就使用此 skill。包含预检、导出、验证、workflow 记录的完整流程。
allowed-tools: Read Write Edit Bash Task
---

# 正文导出

## 快速开始

```bash
# 交互式导出（推荐）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export

# 命令行导出
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export --format markdown --range 1-50
```

## 目标

将网文正文导出为不同格式，便于发布或存档。导出是只读操作，不需要审查/润色。

## 支持格式

| 格式 | 文件扩展 | 说明 |
|------|----------|------|
| Markdown | `.md` | 可用任何编辑器打开，推荐 |
| TXT | `.txt` | 纯文本，最通用 |
| EPUB | `.epub` | 电子书，阅读器可用 |

## 环境设置

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="$(cd "$(dirname "$0")/../../scripts" && pwd)"

# 获取项目根目录
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
```

## 执行流程

### Step 1：预检

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export list
```

验证：
- 项目存在 `.webnovel/state.json` 或 `正文/` 目录
- 有可导出的章节文件

### Step 2：导出

| 场景 | 命令 |
|------|------|
| 交互式导出 | `export` |
| 导出全部 | `export --format markdown` |
| 导出前50章 | `export --range 1-50 --format txt` |
| 导出第1卷 | `export --volume 1 --format epub --author "作者名"` |
| 指定文件名 | `export --format markdown --output 我的小说.md` |

**参数说明**：

| 参数 | 说明 | 示例 |
|------|------|------|
| `--format` | 输出格式 | `markdown`, `txt`, `epub` |
| `--range` | 章节范围 | `1-10`, `1,3,5`, `all` |
| `--volume` | 按卷导出 | `1`, `2` |
| `--output` | 输出路径 | `小说.md`, `导出/第一卷.txt` |
| `--author` | 作者名 | 仅 EPUB 需要 |
| `--cover` | 封面图路径 | `cover.jpg`, `images/封面.png` |
| `--style` | 自定义 CSS | `style.css` |
| `--cover-size` | 封面裁剪尺寸 | `1200x1600` |

### Step 3：验证

```bash
# 检查文件存在且非空
test -s "${PROJECT_ROOT}/导出/小说.md"
```

### Step 4：记录 workflow

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" workflow complete-task --artifacts '{"ok": true}' || true
```

## 输出格式定义

导出文件必须满足：

1. **文件位置**：默认在 `{PROJECT_ROOT}/导出/` 目录
2. **文件命名**：
   - `小说.md` / `小说.txt` / `小说.epub`（全部章节）
   - 用户指定名称（使用 `--output` 时）
3. **内容要求**：
   - 去除 frontmatter（`---` 之间的元数据）
   - 保留章节标题
   - 章节之间有分隔符
4. **EPUB 特殊**：
   - 包含书名和作者
   - 章节作为独立 HTML 文件

## 充分性闸门

完成前必须验证：

- [ ] 预检通过（章节文件存在）
- [ ] 导出命令返回码为 0
- [ ] 输出文件存在且大小 > 0

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| 未找到章节 | `正文/` 目录不存在 | 先用 `/webnovel-write` 创建章节 |
| 导出失败 | ebooklib 未安装 | `pip install ebooklib` |
| 格式不支持 | 用了不支持的格式 | 使用 markdown/txt/epub |

## 封面和样式配置

### 自动检测

EPUB 导出时会自动检测以下文件：
- `{project_root}/cover.jpg` - 封面图片
- `{project_root}/style.css` - 自定义样式

### 自定义 CSS 示例

```css
/* 首行缩进（默认样式）*/
body {
    font-family: "SimSun", "Songti SC", serif;
    line-height: 1.8;
    text-indent: 2em;
    margin: 1em;
}
h1, h2, h3 {
    text-align: center;
    text-indent: 0;
}
```

### 封面裁剪

封面会自动裁剪到标准尺寸（默认 1200x1600），使用居中裁剪。

### 使用示例

```bash
# 使用默认封面和样式
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export --format epub

# 指定自定义封面
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export --format epub --cover images/my_cover.jpg

# 指定自定义样式
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export --format epub --style my_style.css

# 同时指定封面和样式
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export --format epub --cover cover.jpg --style style.css --cover-size 1200x1600 --author "作者名"
```

## 依赖

- Python 3.10+
- `ebooklib`（EPUB 导出需要）

> 注意：`ebooklib` 已在 `init.bat`/`init.sh` 安装 requirements.txt 时一并安装。
