---
name: webnovel-export
description: 将网文正文导出为 Markdown/TXT/EPUB 格式。立即使用此 skill 当用户说：导出、导出小说、导出章节、生成电子书、导出 TXT、导出 Markdown、导出 EPUB、下载小说、输出正文。
compatibility: opencode
allowed-tools: Read Bash
---

# 正文导出

## 目标

将网文正文导出为 Markdown / TXT / EPUB 格式，便于发布或存档。导出是只读操作，不修改项目文件。

## 支持格式

| 格式 | 扩展名 | 依赖 |
|------|--------|------|
| Markdown | `.md` | 无 |
| TXT | `.txt` | 无 |
| EPUB | `.epub` | ebooklib（未安装时提示） |

## 环境设置

```bash
export WORKSPACE_ROOT="${PWD}"
export SCRIPTS_DIR="${PWD}/.opencode/scripts"
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
test -n "$PROJECT_ROOT" && test -f "${PROJECT_ROOT}/.webnovel/state.json" || { echo "❌ PROJECT_ROOT 解析失败"; exit 1; }
```

## 执行流程

### Step 1：列出章节

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export list
```

验证输出并确认导出范围。

### Step 2：导出

| 场景 | 命令 |
|------|------|
| 交互式导出（推荐） | `webnovel.py export export` |
| 全部章节 Markdown | `webnovel.py export export --format md` |
| 指定范围 | `webnovel.py export export --format md --range 1-50` |
| 按卷导出 | `webnovel.py export export --format epub --volume 1 --author "作者名"` |
| 指定输出路径 | `webnovel.py export export --format txt --output 导出/第一卷.txt` |

**参数说明**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--format` | 输出格式：md / txt / epub | md |
| `--range` | 章节范围：1-50 / 1,3,5 / all | all |
| `--volume` | 按卷导出 | - |
| `--output` | 输出文件路径 | 导出/{书名}.{ext} |
| `--title` | 书名 | 项目目录名 |
| `--author` | 作者名（EPUB 元数据） | - |
| `--cover` | 封面图片路径（EPUB） | 自动检测 图片/封面/ |
| `--style` | 自定义 CSS 文件（EPUB） | 默认内嵌样式 |
| `--cover-size` | 封面裁剪尺寸（EPUB） | 1200x1600 |

### Step 3：验证

```bash
# 检查文件存在且非空
test -s "${PROJECT_ROOT}/导出/小说.md" && echo "导出成功"
```

## 充分性闸门

- [ ] 项目存在 正文/ 目录且有章节文件
- [ ] 导出命令返回码为 0
- [ ] 输出文件存在且大小 > 0

## 常见问题

| 错误 | 原因 | 解决 |
|------|------|------|
| 未找到章节 | 正文/ 目录不存在 | 先用 `/webnovel-write` 写章节 |
| EPUB 导出失败 | ebooklib 未安装 | `pip install ebooklib` |
| 封面未裁剪 | Pillow 未安装 | `pip install Pillow`，不影响导出 |

## EPUB 封面与样式

**自动检测**：
- `图片/封面/` — 目录下最新的 jpg/png 图片作为封面
- `style.css` — 项目根目录下自动加载

**默认内嵌 CSS**：宋体/楷体，首行缩进 2em，行高 1.8。
