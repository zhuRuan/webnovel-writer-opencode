# Export Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现独立目录 `export_manager/`，支持 Markdown / TXT / EPUB 三种导出格式，`webnovel.py` 只加 4 行转发。

**Architecture:** 4 文件独立目录。`__init__.py` 负责 CLI + 章节收集 + 格式 dispatch，三个格式文件各含一个 `export_*` 函数。所有格式接收相同的 `chapters: list[tuple[int, Path]]` 接口（章号 + 文件路径）。

**Tech Stack:** Python 3.10+ stdlib (pathlib, argparse, glob)，ebooklib (EPUB 可选)，Pillow (封面裁剪可选)

---

### Task 1: 创建 export_manager 目录结构和 __init__.py 骨架

**Files:**
- Create: `.opencode/scripts/export_manager/__init__.py`

- [ ] **Step 1: 创建目录和文件**

```bash
mkdir -p .opencode/scripts/export_manager
```

- [ ] **Step 2: 编写 __init__.py 骨架 — collect_chapters + argparse + dispatch**

```python
#!/usr/bin/env python3
"""Export manager CLI — 章节收集 + 格式 dispatch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional


# ── 章节收集 ─────────────────────────────────────────────

def collect_chapters(
    project_root: Path,
    range_spec: Optional[str] = None,
    volume: Optional[int] = None,
) -> list[tuple[int, str, Path]]:
    """
    收集 正文/ 下所有章节文件，返回 [(章号, 标题文本, 文件路径), ...]，
    按章号升序排列。支持 --range / --volume 过滤。

    章号从文件名提取，兼容:
      - 正文/第0001章-标题.md  (平铺布局)
      - 正文/第1卷/第001章-标题.md  (卷布局)
    """
    chapters_dir = project_root / "正文"
    if not chapters_dir.is_dir():
        return []

    # 兼容导入路径
    try:
        from chapter_paths import extract_chapter_num_from_filename
    except ImportError:
        from scripts.chapter_paths import extract_chapter_num_from_filename

    candidates: list[tuple[int, Path]] = []
    for f in sorted(chapters_dir.rglob("第*章*.md")):
        num = extract_chapter_num_from_filename(f.name)
        if num is not None:
            candidates.append((num, f))

    candidates.sort(key=lambda x: x[0])

    # 按卷过滤
    if volume is not None:
        try:
            from chapter_paths import volume_num_for_chapter
        except ImportError:
            from scripts.chapter_paths import volume_num_for_chapter
        candidates = [(n, f) for n, f in candidates if volume_num_for_chapter(n) == volume]

    # 按范围过滤
    if range_spec and range_spec != "all":
        allowed = _parse_range(range_spec, max_num=max(c[0] for c in candidates) if candidates else 0)
        candidates = [(n, f) for n, f in candidates if n in allowed]

    # 读取每章第一行作为标题
    result: list[tuple[int, str, Path]] = []
    for num, path in candidates:
        try:
            first_line = path.read_text(encoding="utf-8").split("\n", 1)[0].strip()
            # 去掉 markdown heading 符号
            title = first_line.lstrip("#").strip() if first_line.startswith("#") else first_line
        except Exception:
            title = f"第{num}章"
        result.append((num, title, path))

    return result


def _parse_range(spec: str, max_num: int = 0) -> set[int]:
    """解析范围字符串: '1-50', '1,3,5', 'all'"""
    allowed: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo, hi = int(lo_s.strip()), int(hi_s.strip())
            allowed.update(range(lo, hi + 1))
        else:
            allowed.add(int(part))
    if max_num > 0:
        allowed = {n for n in allowed if 1 <= n <= max_num}
    return allowed


# ── CLI ──────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace) -> int:
    chapters = collect_chapters(args.project_root)
    if not chapters:
        print("无章节文件")
        return 1
    for num, title, path in chapters:
        print(f"第{num:04d}章  {title}  ({path})")
    print(f"\n共 {len(chapters)} 章")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    project_root = args.project_root
    chapters = collect_chapters(project_root, range_spec=args.range, volume=args.volume)

    if not chapters:
        print("错误：正文/ 目录不存在或无章节文件。请先使用 /webnovel-write 创建章节。")
        return 1

    fmt = args.format or "md"
    output = args.output
    if not output:
        title = args.title or project_root.name
        output = str(project_root / "导出" / f"{title}.{fmt}")

    # 确保输出目录存在
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    if fmt == "md":
        from .markdown import export_markdown
        title = args.title or project_root.name
        export_markdown(chapters, Path(output), title)
    elif fmt == "txt":
        from .txt import export_txt
        export_txt(chapters, Path(output))
    elif fmt == "epub":
        from .epub import export_epub
        export_epub(
            chapters=chapters,
            output_path=Path(output),
            title=args.title or project_root.name,
            author=args.author,
            cover=args.cover,
            style=args.style,
            cover_size=args.cover_size,
        )
    else:
        print(f"不支持的格式: {fmt}，可选: md, txt, epub")
        return 1

    print(f"导出完成: {output}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="webnovel export manager")
    parser.add_argument("--project-root", type=Path, required=True, help="项目根目录")

    sub = parser.add_subparsers(dest="action")

    # export list
    sub.add_parser("list", help="列出可导出章节")

    # export (执行导出)
    p_export = sub.add_parser("export", help="执行导出")
    p_export.add_argument("--format", choices=["md", "txt", "epub"], default="md", help="输出格式")
    p_export.add_argument("--range", help="章节范围: 1-50 / 1,3,5 / all")
    p_export.add_argument("--volume", type=int, help="按卷导出")
    p_export.add_argument("--output", help="输出文件路径")
    p_export.add_argument("--title", help="书名")
    p_export.add_argument("--author", help="作者名 (EPUB)")
    p_export.add_argument("--cover", help="封面图路径 (EPUB)")
    p_export.add_argument("--style", help="自定义 CSS 路径 (EPUB)")
    p_export.add_argument("--cover-size", default="1200x1600", help="封面裁剪尺寸 (EPUB)")

    args = parser.parse_args()

    if args.action == "list":
        code = cmd_list(args)
    elif args.action == "export":
        code = cmd_export(args)
    else:
        parser.print_help()
        code = 1

    raise SystemExit(code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 验证脚本可被 Python 导入**

```bash
cd .opencode/scripts && python -c "from export_manager import collect_chapters; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/export_manager/__init__.py
git commit -m "feat(export): add export_manager skeleton with chapter collection and CLI"
```

---

### Task 2: 实现 Markdown 导出

**Files:**
- Create: `.opencode/scripts/export_manager/markdown.py`

- [ ] **Step 1: 编写 markdown.py**

```python
#!/usr/bin/env python3
"""Markdown 格式导出 — 拼接章节原文，章节间用 --- 分隔。"""

from __future__ import annotations

from pathlib import Path


def export_markdown(
    chapters: list[tuple[int, str, Path]],
    output_path: Path,
    title: str = "",
) -> None:
    """将所有章节拼接为单个 .md 文件。"""
    lines: list[str] = []

    if title:
        lines.append(f"# {title}\n")

    for num, chapter_title, path in chapters:
        text = path.read_text(encoding="utf-8")
        lines.append(text.rstrip())
        lines.append("\n\n---\n")

    output_path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 2: 验证导入**

```bash
cd .opencode/scripts && python -c "from export_manager.markdown import export_markdown; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/export_manager/markdown.py
git commit -m "feat(export): add markdown export"
```

---

### Task 3: 实现 TXT 导出

**Files:**
- Create: `.opencode/scripts/export_manager/txt.py`

- [ ] **Step 1: 编写 txt.py**

```python
#!/usr/bin/env python3
"""TXT 纯文本导出 — 去除 markdown 标记，输出纯文本。"""

from __future__ import annotations

import re
from pathlib import Path

# 匹配 markdown 标记: **bold**, *italic*, `code`, ~~strikethrough~~, [link](url), ![img](url)
_MD_PAT = re.compile(r"(\*\*|__)(.*?)\1|(\*|_)(.*?)\3|`(.*?)`|~~(.*?)~~|\[([^\]]*?)\]\([^)]*?\)|!\[[^\]]*?\]\([^)]*?\)")


def _strip_markdown(text: str) -> str:
    """移除常见行内 markdown 标记，保留纯文本。"""
    def _repl(m: re.Match) -> str:
        return m.group(2) or m.group(4) or m.group(5) or m.group(6) or m.group(7) or ""
    return _MD_PAT.sub(_repl, text)


def export_txt(chapters: list[tuple[int, str, Path]], output_path: Path) -> None:
    """将所有章节导出为纯文本 .txt 文件。"""
    lines: list[str] = []

    for num, chapter_title, path in chapters:
        lines.append(f"第{num}章  {chapter_title}")
        lines.append("")
        text = path.read_text(encoding="utf-8")
        # 去除 markdown 行内标记
        clean = _strip_markdown(text)
        lines.append(clean.rstrip())
        lines.append("")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 2: 验证导入**

```bash
cd .opencode/scripts && python -c "from export_manager.txt import export_txt; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/export_manager/txt.py
git commit -m "feat(export): add TXT export with markdown stripping"
```

---

### Task 4: 实现 EPUB 导出

**Files:**
- Create: `.opencode/scripts/export_manager/epub.py`

- [ ] **Step 1: 编写 epub.py**

```python
#!/usr/bin/env python3
"""EPUB 导出 — 使用 ebooklib 打包，每章一个 HTML 文件。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_DEFAULT_CSS = """
body {
    font-family: "Songti SC", "SimSun", serif;
    line-height: 1.8;
    text-indent: 2em;
    margin: 1em 0.5em;
}
h1, h2 {
    text-align: center;
    text-indent: 0;
    margin-top: 1.5em;
}
p { margin: 0.3em 0; }
"""


def _detect_cover(project_root: Path) -> Optional[Path]:
    """检测 图片/封面/ 下最新图片作为封面。"""
    cover_dir = project_root / "图片" / "封面"
    if not cover_dir.is_dir():
        return None
    images = sorted(
        cover_dir.glob("*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for img in images:
        if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            return img
    return None


def _detect_style(project_root: Path) -> Optional[str]:
    """检测 style.css，存在时返回内容。"""
    style_path = project_root / "style.css"
    if style_path.is_file():
        return style_path.read_text(encoding="utf-8")
    return None


def _crop_cover(src: Path, size: str) -> bytes:
    """裁剪封面到指定尺寸（居中裁剪），返回 PNG 字节。未安装 Pillow 时直接返回原图。"""
    try:
        from PIL import Image
    except ImportError:
        print("警告: Pillow 未安装，封面将使用原图尺寸。安装: pip install Pillow")
        return src.read_bytes()

    w_s, h_s = size.split("x")
    target_w, target_h = int(w_s), int(h_s)

    img = Image.open(src).convert("RGB")
    orig_w, orig_h = img.size

    # 居中裁剪到目标比例
    target_ratio = target_w / target_h
    orig_ratio = orig_w / orig_h

    if orig_ratio > target_ratio:
        # 原图更宽，裁左右
        new_w = int(orig_h * target_ratio)
        offset = (orig_w - new_w) // 2
        img = img.crop((offset, 0, offset + new_w, orig_h))
    else:
        # 原图更高，裁上下
        new_h = int(orig_w / target_ratio)
        offset = (orig_h - new_h) // 2
        img = img.crop((0, offset, orig_w, offset + new_h))

    img = img.resize((target_w, target_h), Image.LANCZOS)

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def export_epub(
    chapters: list[tuple[int, str, Path]],
    output_path: Path,
    title: str,
    author: Optional[str] = None,
    cover: Optional[str] = None,
    style: Optional[str] = None,
    cover_size: str = "1200x1600",
) -> None:
    try:
        from ebooklib import epub
    except ImportError:
        print("EPUB 导出需要 ebooklib，请运行: pip install ebooklib")
        raise SystemExit(1)

    book = epub.EpubBook()
    book.set_identifier(f"webnovel-{title}")
    book.set_title(title)
    book.set_language("zh-CN")

    if author:
        book.add_author(author)

    # 样式
    css_text = _DEFAULT_CSS
    if style:
        try:
            css_text = Path(style).read_text(encoding="utf-8")
        except Exception:
            pass
    else:
        detected = _detect_style(output_path.parent.parent)  # 从导出目录推断 project_root
        if detected:
            css_text = detected

    book.add_item(epub.EpubItem(
        uid="style",
        file_name="style.css",
        media_type="text/css",
        content=css_text.encode("utf-8"),
    ))

    # 封面
    cover_path = None
    if cover:
        cover_path = Path(cover)
    else:
        project_root = output_path.parent.parent
        detected = _detect_cover(project_root)
        if detected:
            cover_path = detected

    if cover_path and cover_path.is_file():
        cover_bytes = _crop_cover(cover_path, cover_size)
        book.set_cover("cover.png", cover_bytes)

    # 章节
    spine = ["nav"]
    toc: list = []

    for num, chapter_title, path in chapters:
        text = path.read_text(encoding="utf-8")
        # 将 markdown 转为简单 HTML
        html_body = _md_to_html(text)

        c = epub.EpubHtml(
            title=f"第{num}章",
            file_name=f"ch{num:04d}.xhtml",
            lang="zh-CN",
        )
        c.content = (
            f'<html><head>'
            f'<link rel="stylesheet" type="text/css" href="style.css"/>'
            f'</head><body>{html_body}</body></html>'
        ).encode("utf-8")
        c.add_item(book.get_item_with_id("style"))

        book.add_item(c)
        spine.append(c)
        toc.append(epub.Link(f"ch{num:04d}.xhtml", f"第{num}章  {chapter_title}", f"ch{num:04d}"))

    book.toc = toc
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(output_path), book)


def _md_to_html(text: str) -> str:
    """将 markdown 正文转为简单 HTML。"""
    from html import escape

    lines = text.split("\n")
    html_lines: list[str] = []
    in_para = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_para:
                html_lines.append("</p>")
                in_para = False
            continue

        if stripped.startswith("# "):
            if in_para:
                html_lines.append("</p>")
                in_para = False
            html_lines.append(f"<h1>{escape(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            if in_para:
                html_lines.append("</p>")
                in_para = False
            html_lines.append(f"<h2>{escape(stripped[3:])}</h2>")
        elif stripped.startswith("---"):
            if in_para:
                html_lines.append("</p>")
                in_para = False
            html_lines.append("<hr/>")
        else:
            if not in_para:
                html_lines.append("<p>")
                in_para = True
            else:
                html_lines.append("<br/>")
            html_lines.append(escape(stripped))

    if in_para:
        html_lines.append("</p>")

    return "\n".join(html_lines)
```

- [ ] **Step 2: 验证导入**

```bash
cd .opencode/scripts && python -c "from export_manager.epub import export_epub; print('OK')"
```
Expected: `OK`（ebooklib 未安装时也应该通过 — import 在函数内部）

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/export_manager/epub.py
git commit -m "feat(export): add EPUB export with ebooklib"
```

---

### Task 5: 在 webnovel.py 中注册 export 子命令

**Files:**
- Modify: `.opencode/scripts/data_modules/webnovel.py`

- [ ] **Step 1: 添加 subparser（在 knowledge_parser 之前，约第370行）**

在 `p_master_outline_sync` 注册之后、`knowledge_parser` 之前插入:

```python
    p_export = sub.add_parser("export", help="导出正文为 Markdown/TXT/EPUB")
    p_export.add_argument("args", nargs=argparse.REMAINDER)
```

- [ ] **Step 2: 添加 dispatch（在 master-outline-sync 之后、knowledge 之前，约第485行）**

在 `if tool == "master-outline-sync":` 块结束之后、`if tool == "knowledge":` 之前插入:

```python
    if tool == "export":
        raise SystemExit(_run_script("export_manager/__init__.py", [*forward_args, *rest]))
```

- [ ] **Step 3: 验证 CLI 注册**

```bash
python .opencode/scripts/webnovel.py export --help
```
Expected: 显示 export 命令帮助

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/webnovel.py
git commit -m "feat(export): register export subcommand in webnovel CLI"
```

---

### Task 6: 编写测试

**Files:**
- Create: `.opencode/scripts/data_modules/tests/test_export_manager.py`

- [ ] **Step 1: 编写测试文件**

```python
"""Tests for export_manager module."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# Ensure scripts/ is on the path
_scripts_dir = Path(__file__).resolve().parents[2]
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from export_manager import collect_chapters, _parse_range
from export_manager.markdown import export_markdown
from export_manager.txt import export_txt, _strip_markdown


class TestParseRange:
    def test_single(self):
        assert _parse_range("5") == {5}

    def test_range(self):
        assert _parse_range("1-5") == {1, 2, 3, 4, 5}

    def test_comma_mix(self):
        assert _parse_range("1-3,5,7-9") == {1, 2, 3, 5, 7, 8, 9}

    def test_clamped(self):
        assert _parse_range("1-100", max_num=5) == {1, 2, 3, 4, 5}


class TestCollectChapters:
    def test_empty_dir(self, tmp_path):
        (tmp_path / "正文").mkdir()
        result = collect_chapters(tmp_path)
        assert result == []

    def test_no_chapters_dir(self, tmp_path):
        result = collect_chapters(tmp_path)
        assert result == []

    def test_flat_layout(self, tmp_path):
        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章-标题.md").write_text("# 第1章 测试", encoding="utf-8")
        (tmp_path / "正文" / "第0002章-继续.md").write_text("# 第2章 继续", encoding="utf-8")

        result = collect_chapters(tmp_path)
        assert len(result) == 2
        assert result[0][0] == 1
        assert result[0][1] == "第1章 测试"
        assert result[1][0] == 2

    def test_volume_layout(self, tmp_path):
        vol_dir = tmp_path / "正文" / "第1卷"
        vol_dir.mkdir(parents=True)
        (vol_dir / "第001章-开篇.md").write_text("# 第1章 开篇", encoding="utf-8")
        (vol_dir / "第002章-发展.md").write_text("# 第2章 发展", encoding="utf-8")

        result = collect_chapters(tmp_path)
        assert len(result) == 2

    def test_mixed_layout(self, tmp_path):
        """平铺和卷布局混合时正确收集。"""
        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章-旧格式.md").write_text("# 旧1", encoding="utf-8")
        vol_dir = tmp_path / "正文" / "第1卷"
        vol_dir.mkdir(parents=True)
        (vol_dir / "第002章-新格式.md").write_text("# 新2", encoding="utf-8")

        result = collect_chapters(tmp_path)
        assert len(result) == 2

    def test_range_filter(self, tmp_path):
        (tmp_path / "正文").mkdir()
        for i in range(1, 6):
            (tmp_path / "正文" / f"第{i:04d}章.md").write_text(f"# 第{i}章", encoding="utf-8")

        result = collect_chapters(tmp_path, range_spec="2-4")
        assert len(result) == 3
        assert [r[0] for r in result] == [2, 3, 4]

    def test_volume_filter(self, tmp_path):
        from chapter_paths import volume_num_for_chapter
        v1_dir = tmp_path / "正文" / "第1卷"
        v1_dir.mkdir(parents=True)
        v2_dir = tmp_path / "正文" / "第2卷"
        v2_dir.mkdir(parents=True)
        # 第1卷: 章 1-50; 第2卷: 章 51-100
        (v1_dir / "第001章.md").write_text("# 1", encoding="utf-8")
        (v2_dir / "第051章.md").write_text("# 51", encoding="utf-8")

        result = collect_chapters(tmp_path, volume=1)
        assert len(result) == 1
        assert result[0][0] == 1

        result = collect_chapters(tmp_path, volume=2)
        assert len(result) == 1
        assert result[0][0] == 51


class TestMarkdownExport:
    def test_basic(self, tmp_path):
        chapters_dir = tmp_path / "正文"
        chapters_dir.mkdir()
        ch1 = chapters_dir / "第0001章.md"
        ch1.write_text("# 第1章 开始\n\n正文内容。", encoding="utf-8")
        ch2 = chapters_dir / "第0002章.md"
        ch2.write_text("# 第2章 继续\n\n更多内容。", encoding="utf-8")

        chapters = collect_chapters(tmp_path)
        output = tmp_path / "导出" / "小说.md"
        output.parent.mkdir()

        export_markdown(chapters, output, title="测试小说")

        content = output.read_text(encoding="utf-8")
        assert "# 测试小说" in content
        assert "# 第1章 开始" in content
        assert "正文内容。" in content
        assert "---" in content


class TestTxtExport:
    def test_basic(self, tmp_path):
        chapters_dir = tmp_path / "正文"
        chapters_dir.mkdir()
        ch1 = chapters_dir / "第0001章.md"
        ch1.write_text("# 第1章 测试\n\n**粗体**和*斜体*。", encoding="utf-8")

        chapters = collect_chapters(tmp_path)
        output = tmp_path / "导出" / "小说.txt"
        output.parent.mkdir()

        export_txt(chapters, output)

        content = output.read_text(encoding="utf-8")
        assert "第1章" in content
        assert "粗体" in content
        assert "斜体" in content
        assert "**" not in content  # markdown stripped

    def test_strip_markdown(self):
        assert _strip_markdown("**粗体**文字") == "粗体文字"
        assert _strip_markdown("*斜体*文字") == "斜体文字"
        assert _strip_markdown("[链接](http://x.com)") == "链接"
        assert _strip_markdown("普通文字") == "普通文字"


class TestEpubImportError:
    def test_import_error(self, tmp_path, monkeypatch):
        """模拟 ebooklib 未安装时退出。"""
        chapters_dir = tmp_path / "正文"
        chapters_dir.mkdir()
        (chapters_dir / "第0001章.md").write_text("# 测试", encoding="utf-8")
        chapters = collect_chapters(tmp_path)

        output = tmp_path / "导出" / "小说.epub"
        output.parent.mkdir()

        monkeypatch.setitem(sys.modules, "ebooklib", None)

        from export_manager.epub import export_epub
        with pytest.raises(SystemExit) as exc:
            export_epub(chapters, output, title="测试", author="作者")
        assert exc.value.code == 1
```

- [ ] **Step 2: 运行测试**

```bash
cd .opencode/scripts && python -m pytest data_modules/tests/test_export_manager.py -q --no-cov
```
Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/data_modules/tests/test_export_manager.py
git commit -m "test(export): add export_manager tests"
```

---

### Task 7: 端到端验证

- [ ] **Step 1: 用测试项目验证 export list**

```bash
python .opencode/scripts/webnovel.py --project-root "D:/workspace/凡尘之舞/凡尘之舞" export list
```
Expected: 列出第1-8章，共8章

- [ ] **Step 2: 验证 Markdown 导出**

```bash
python .opencode/scripts/webnovel.py --project-root "D:/workspace/凡尘之舞/凡尘之舞" export export --format md --range 1-3 --output "D:/workspace/凡尘之舞/凡尘之舞/导出/test.md"
```
Expected: 生成 test.md，包含3章内容

- [ ] **Step 3: 验证 TXT 导出**

```bash
python .opencode/scripts/webnovel.py --project-root "D:/workspace/凡尘之舞/凡尘之舞" export export --format txt --range 1-3 --output "D:/workspace/凡尘之舞/凡尘之舞/导出/test.txt"
```
Expected: 生成 test.txt，markdown 标记已移除

- [ ] **Step 4: 验证 EPUB 导出**

```bash
python .opencode/scripts/webnovel.py --project-root "D:/workspace/凡尘之舞/凡尘之舞" export export --format epub --range 1-5 --author "测试作者" --output "D:/workspace/凡尘之舞/凡尘之舞/导出/test.epub"
```
Expected: 生成 test.epub（如 ebooklib 未安装则提示安装）

- [ ] **Step 5: Commit (if any fixes)**

```bash
git status
```
