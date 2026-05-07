# Export Manager Design

## Context

webnovel-writer 需要将已完成章节导出为 Markdown / TXT / EPUB 格式。当前 `.opencode/scripts/` 下无导出模块，CLI `webnovel.py` 无 `export` 子命令。

约束：新增代码独立在 `export_manager/` 目录中，`webnovel.py` 只加 4 行转发，方便后续合并上游。

## Architecture

```
.opencode/scripts/export_manager/
  __init__.py    # CLI 入口 + argparse + 章节收集 + 格式 dispatch
  markdown.py    # Markdown 拼接（~35行）
  txt.py         # 纯文本导出（~25行）
  epub.py        # EPUB 打包（~110行，ebooklib 可选）
```

### Data Flow

```
正文/**/第*章*.md  →  collect_chapters()  →  format_handler  →  导出/小说.{md,txt,epub}
                       (glob + 排序)         (md/txt/epub)
```

### Dependencies

| 模块 | 外部依赖 | 缺失时行为 |
|------|---------|-----------|
| markdown.py | 无 | - |
| txt.py | 无 | - |
| epub.py | ebooklib | 提示 `pip install ebooklib` 并退出 |

## CLI

```
webnovel.py export <subcommand> [options]

Subcommands:
  list                    列出可导出的章节（章号 + 标题 + 文件路径）

Options:
  --format FORMAT         输出格式：md / txt / epub（默认 md）
  --range RANGE           章节范围：1-50 / 1,3,5 / all（默认 all）
  --volume VOLUME         按卷导出（如 --volume 1）
  --output PATH           输出文件路径（默认 导出/小说.{ext}）
  --title TITLE           书名（EPUB 元数据，默认从项目目录名推断）
  --author NAME           作者名（EPUB 元数据）
  --cover PATH            封面图片路径（EPUB）
  --style PATH            自定义 CSS 文件（EPUB）
  --cover-size WxH        封面裁剪尺寸（默认 1200x1600）
```

## Implementation

### `__init__.py` — CLI + Chapter Collection

- `collect_chapters(project_root, range_spec, volume)` — glob `正文/**/第*章*.md`，用 `chapter_paths.extract_chapter_num_from_filename()` 排序，按 range/volume 过滤
- `cmd_list(args)` — 遍历 collect_chapters，输出章号+标题+路径
- `cmd_export(args)` — collect → 调用格式 handler → 写入 `导出/` 目录
- `main()` — argparse，subcommands: `list`, `export`

### `markdown.py`

- `export_markdown(chapters, output_path, title)` — 拼接：`# 书名\n\n` + 每章原文 + `\n\n---\n\n` 分隔
- 保留原章节内的 markdown 格式

### `txt.py`

- `export_txt(chapters, output_path)` — 拼接：每章标题 + 空行 + 正文 + 空行
- 不做格式转换，纯文本输出

### `epub.py`

- `export_epub(chapters, output_path, title, author, cover, style, cover_size)` — 使用 ebooklib 构建 EPUB
- 每章一个 HTML 文件
- 自动生成 TOC（目录）
- 默认内嵌 CSS：宋体/楷体，首行缩进 2em，行高 1.8
- 封面：直接使用指定图片或自动检测的封面图，嵌入 EPUB。裁剪 (`--cover-size`) 依赖 Pillow，未安装时使用原图尺寸并给 warning
- 封面和 CSS 自动检测：`图片/封面/` 下最新图片 + `style.css`

### `webnovel.py` changes (4 lines)

1. `p_export = sub.add_parser("export", help="导出正文为 Markdown/TXT/EPUB")`
2. `p_export.add_argument("args", nargs=argparse.REMAINDER)`
3. `if tool == "export":`
4. `    raise SystemExit(_run_script("export_manager/__init__.py", [*forward_args, *rest]))`

## Edge Cases

| 场景 | 处理 |
|------|------|
| 正文目录不存在 | 预检报错，提示先写章节 |
| 无匹配章节 | 输出 "无章节文件" |
| range 超出实际章节 | 裁剪到实际范围，给出 warning |
| 输出目录不存在 | 自动创建 `导出/` |
| EPUB 无作者 | 提示 `--author` 必填 |
| ebooklib 未安装 | 提示 `pip install ebooklib` 并退出(EPUB only) |
| 章节文件编码 | UTF-8，与项目统一 |

## Test Plan

- `test_collect_chapters` — 模拟 正文/ 目录，验证章节发现+排序+过滤
- `test_collect_chapters_mixed_layout` — 同时存在平铺和卷布局
- `test_export_markdown` — 验证拼接格式+分隔符
- `test_export_txt` — 验证纯文本输出
- `test_epub_import_error` — 模拟 ebooklib 未安装
- `test_cli_list` — 验证 `export list` 输出
- `test_cli_export_md` — 端到端 Markdown 导出
