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
# 以下命令假设当前目录为 webnovel-writer 仓库根目录
# （即包含 .opencode/ 的目录），而非书项目目录。
export SCRIPTS_DIR="${PWD}/.opencode/scripts"

# 验证工作区正确
test -d "${SCRIPTS_DIR}" || { echo "错误: 未找到 ${SCRIPTS_DIR}，请确保当前目录是 webnovel-writer 仓库根目录"; exit 1; }

# 解析书项目根目录（.webnovel/state.json 所在目录）
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PWD}" where)"
test -n "$PROJECT_ROOT" && test -f "${PROJECT_ROOT}/.webnovel/state.json" || { echo "错误: PROJECT_ROOT 解析失败，请用 --project-root 显式指定"; exit 1; }
echo "项目路径: ${PROJECT_ROOT}"

# 检查正文目录
test -d "${PROJECT_ROOT}/正文" || { echo "错误: ${PROJECT_ROOT}/正文/ 不存在，无章节可导出"; exit 1; }
```

## 执行流程

### Step 1：列出章节

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export list
```

确认章节数量和范围。

### Step 2：导出

```bash
# 全部章节 → Markdown（默认输出: ${PROJECT_ROOT}/导出/书名.md）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export export --format md

# 指定章节范围
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export export --format md --range 1-50

# TXT 纯文本
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export export --format txt

# EPUB（需 ebooklib）
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export export --format epub --author "作者名"

# 自定义输出路径
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" export export --format txt --output "${PROJECT_ROOT}/导出/第一卷.txt"
```

**参数说明**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--format` | md / txt / epub | md |
| `--range` | 1-50 / 1,3,5 / all | all |
| `--volume` | 按卷导出 | - |
| `--output` | 输出文件路径（相对 PROJECT_ROOT） | `导出/{PROJECT_ROOT 目录名}.{ext}` |
| `--title` | 书名 | PROJECT_ROOT 目录名 |
| `--author` | 作者名（EPUB 元数据） | - |
| `--cover` | 封面路径（EPUB） | `图片/封面/` 下最新文件 |
| `--style` | 自定义 CSS（EPUB） | `style.css` |

### Step 3：验证

```bash
ls -la "${PROJECT_ROOT}/导出/" && echo "导出成功"
```

## 充分性闸门

- [ ] 正文/ 目录存在且有章节文件
- [ ] 导出命令返回码为 0
- [ ] ${PROJECT_ROOT}/导出/ 下有非空输出文件

## Windows 注意事项

- **PowerShell 中文乱码**：运行 `chcp 65001` 切换控制台到 UTF-8 代码页
- **路径嵌套**（如 `凡尘之舞\凡尘之舞`）：外目录是 git 仓库，内目录是书项目。`webnovel.py where` 自动解析内层路径，如果失败，在书项目目录下创建 `.claude/.webnovel-current-project` 指针文件指向内层
- **工具目录 vs 项目目录**：skill 命令必须从 `webnovel-writer` 仓库根目录（包含 `.opencode/` 的目录）执行，不能在书项目目录下执行

## 常见问题

| 错误 | 原因 | 解决 |
|------|------|------|
| 未找到章节 | 正文/ 目录不存在 | 先用 `/webnovel-write` 写章节 |
| 找不到 .opencode/scripts | 当前目录不是仓库根目录 | cd 到 webnovel-writer 根目录 |
| PROJECT_ROOT 解析失败 | 书项目路径无法自动探测 | 显式传 `--project-root "完整路径"` |
| EPUB 导出失败 | ebooklib 未安装 | `pip install ebooklib` |
| 封面未裁剪 | Pillow 未安装 | `pip install Pillow`，不影响导出 |
| 中文输出乱码 | PowerShell GBK 编码 | 运行 `chcp 65001` |
