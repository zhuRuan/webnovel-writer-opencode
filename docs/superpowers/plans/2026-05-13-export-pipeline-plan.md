# Export Pipeline Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor export_manager from per-format custom Markdown parsing to a unified MD→HTML/AST pipeline, add DOCX/HTML/PDF formats, fix 8 existing code bugs.

**Architecture:** mistune v3 provides a single Markdown→AST→HTML conversion path. HTML-based formats (epub/html/pdf) use md_to_html(); DOCX uses md_to_blocks() (AST). md/txt skip the HTML layer. CSS from styles.py controls typesetting for all HTML-based formats.

**Tech Stack:** `mistune>=3.0`, `python-docx>=1.0`, `ebooklib` (existing), `weasyprint>=60.0` (optional), `Pillow` (existing optional)

**Test runner:** `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py -q --no-cov`

---

### Task 1: parser.py — Unified Markdown → HTML/AST

**Files:**
- Create: `.opencode/scripts/export_manager/parser.py`
- Test: `.opencode/scripts/data_modules/tests/test_export_manager.py` (append)

- [ ] **Step 1: Write failing test**

```python
class TestParser:
    """Tests for unified markdown parser."""

    def test_heading_to_html(self):
        from export_manager.parser import md_to_html
        html = md_to_html("# 第1章 开篇")
        assert '<h1 class="chapter-title">第1章 开篇</h1>' in html

    def test_paragraph_to_html(self):
        from export_manager.parser import md_to_html
        html = md_to_html("这是第一段。")
        assert '<p>这是第一段。</p>' in html

    def test_bold_to_html(self):
        from export_manager.parser import md_to_html
        html = md_to_html("**粗体**文字")
        assert '<strong' in html
        assert '粗体' in html

    def test_scene_break_to_html(self):
        from export_manager.parser import md_to_html
        html = md_to_html("---")
        assert 'class="scene-break"' in html

    def test_empty_input(self):
        from export_manager.parser import md_to_html
        html = md_to_html("")
        assert html == ""

    def test_multi_paragraph(self):
        from export_manager.parser import md_to_html
        html = md_to_html("第一段。\n\n第二段。")
        assert html.count("<p>") == 2

    def test_blocks_output(self):
        from export_manager.parser import md_to_blocks
        blocks = md_to_blocks("正文内容。")
        assert isinstance(blocks, list)
        assert len(blocks) > 0
        first = blocks[0]
        assert isinstance(first, dict)
        assert "type" in first
```

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py::TestParser -q --no-cov`
Expected: FAIL (ImportError)

- [ ] **Step 2: Install dependency**

Run: `pip install "mistune>=3.0"`

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""Unified Markdown parser — mistune v3 based, outputs HTML and AST."""
from __future__ import annotations

import mistune


def md_to_html(text: str) -> str:
    """Convert Markdown text to HTML fragment (no <html>/<body> wrapper)."""
    if not text.strip():
        return ""
    md = mistune.create_markdown(renderer=None)
    html = md(text)
    return html.strip()


def md_to_blocks(text: str) -> list[dict]:
    """Convert Markdown to mistune AST block list."""
    if not text.strip():
        return []
    md = mistune.create_markdown(renderer="ast")
    return md(text)
```

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py::TestParser -q --no-cov`
Expected: 6/7 pass (blocks output test may need adjustment)

- [ ] **Step 4: Verify tests pass and commit**

Adjust the blocks test if mistune AST format differs from expected dict keys.

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py::TestParser -q --no-cov`
Expected: PASS all

```bash
git add .opencode/scripts/export_manager/parser.py .opencode/scripts/data_modules/tests/test_export_manager.py
git commit -m "feat: add parser.py — unified MD→HTML/AST via mistune v3"
```

---

### Task 2: styles.py — CSS Typesetting Templates

**Files:**
- Create: `.opencode/scripts/export_manager/styles.py`
- Test: `.opencode/scripts/data_modules/tests/test_export_manager.py` (append)

- [ ] **Step 1: Write failing test**

```python
class TestStyles:
    def test_default_css(self):
        from export_manager.styles import get_default_css
        css = get_default_css()
        assert "text-indent" in css
        assert "line-height" in css
        assert "chapter-title" in css

    def test_load_custom_css(self, tmp_path):
        from export_manager.styles import load_custom_css
        css_file = tmp_path / "custom.css"
        css_file.write_text("p { color: red; }", encoding="utf-8")
        css = load_custom_css(css_file)
        assert "color: red" in css

    def test_get_css_fallback(self, tmp_path):
        from export_manager.styles import get_css
        css = get_css()
        assert "text-indent" in css  # falls back to default

    def test_get_css_custom(self, tmp_path):
        from export_manager.styles import get_css
        css_file = tmp_path / "custom.css"
        css_file.write_text("body { margin: 0; }", encoding="utf-8")
        css = get_css(custom_path=css_file)
        assert "margin: 0" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py::TestStyles -q --no-cov`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write implementation**

```python
#!/usr/bin/env python3
"""CSS typesetting templates for Chinese web novel export."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_DEFAULT_CSS = """\
body {
    font-family: "Source Han Serif SC", "Noto Serif CJK SC", "SimSun", serif;
    font-size: 16px;
    max-width: 42em;
    margin: 0 auto;
    padding: 2em;
}
p {
    text-indent: 2em;
    margin: 0.5em 0;
    line-height: 1.8;
}
h1.chapter-title {
    text-align: center;
    margin: 2em 0 1em;
    font-size: 1.5em;
}
hr.scene-break {
    border: none;
    text-align: center;
    margin: 1.5em 0;
}
hr.scene-break::after {
    content: "* * *";
    letter-spacing: 1em;
    color: #666;
}
"""


def get_default_css() -> str:
    """Return the default CSS template for Chinese web novel typesetting."""
    return _DEFAULT_CSS


def load_custom_css(path: Path) -> str:
    """Load CSS from a custom file path."""
    return Path(path).read_text(encoding="utf-8")


def get_css(custom_path: Optional[Path] = None) -> str:
    """Get CSS: prefer custom path, fallback to default template."""
    if custom_path is not None and Path(custom_path).is_file():
        return load_custom_css(custom_path)
    return _DEFAULT_CSS
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py::TestStyles -q --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/export_manager/styles.py .opencode/scripts/data_modules/tests/test_export_manager.py
git commit -m "feat: add styles.py — CSS typesetting templates for web novel export"
```

---

### Task 3: chapter_collector.py — Extract Chapter Collection Logic

**Files:**
- Create: `.opencode/scripts/export_manager/chapter_collector.py`
- Modify: `.opencode/scripts/export_manager/__init__.py`
- Test: `.opencode/scripts/data_modules/tests/test_export_manager.py` (modify imports + add new tests)

- [ ] **Step 1: Write ChapterInfo and move collect_chapters + _parse_range**

Create `chapter_collector.py` by extracting from `__init__.py`:

```python
#!/usr/bin/env python3
"""Chapter collector — scan 正文/ for chapter files, validate, extract titles."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional, NamedTuple


class ChapterInfo(NamedTuple):
    index: int
    title: str
    path: Path
    volume: int


def collect_chapters(
    project_root: Path,
    range_spec: Optional[str] = None,
    volume: Optional[int] = None,
) -> list[ChapterInfo]:
    """Scan 正文/ for chapter files, return sorted list with metadata."""
    chapters_dir = project_root / "正文"
    if not chapters_dir.is_dir():
        return []

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

    # Volume filter (use file-system directory layout)
    if volume is not None:
        filtered: list[tuple[int, Path]] = []
        for n, f in candidates:
            vol = _resolve_volume_from_path(f, project_root)
            if vol == volume:
                filtered.append((n, f))
        candidates = filtered

    # Range filter
    if range_spec and range_spec != "all":
        max_num = max(c[0] for c in candidates) if candidates else 0
        allowed = _parse_range(range_spec, max_num=max_num)
        candidates = [(n, f) for n, f in candidates if n in allowed]

    # Build result with title extraction and progress feedback
    total = len(candidates)
    result: list[ChapterInfo] = []
    for i, (num, path) in enumerate(candidates, 1):
        title = _extract_title(path)
        vol = _resolve_volume_from_path(path, project_root)
        result.append(ChapterInfo(index=num, title=title, path=path, volume=vol))
        print(f"  [{i}/{total}] 第{num}章 {title}")

    # Validation: detect gaps and duplicates
    _validate(result)

    return result


def _resolve_volume_from_path(path: Path, project_root: Path) -> int:
    """Determine volume number from chapter file's directory structure.

    Priority:
    1. If file is under 正文/第N卷/ — return N
    2. Fallback: (chapter_num - 1) // 50 + 1
    """
    try:
        from chapter_paths import extract_chapter_num_from_filename
    except ImportError:
        from scripts.chapter_paths import extract_chapter_num_from_filename

    rel = path.relative_to(project_root)
    parts = rel.parts
    for part in parts:
        m = re.match(r"第(\d+)卷", part)
        if m:
            return int(m.group(1))

    num = extract_chapter_num_from_filename(path.name)
    if num is not None:
        return (num - 1) // 50 + 1
    return 1


def _extract_title(path: Path) -> str:
    """Extract chapter title from file content. Skips leading blank lines."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return f"第?章"

    lines = text.split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^#{1,3}\s+(.*)", stripped)
        if m:
            return m.group(1).strip()
        # No heading marker — use the first non-empty line as-is
        return stripped if not stripped.startswith("#") else stripped.lstrip("#").strip()

    # No non-empty content — fallback to filename
    from chapter_paths import extract_chapter_num_from_filename
    num = extract_chapter_num_from_filename(path.name)
    return f"第{num}章" if num else "无标题"


def _validate(chapters: list[ChapterInfo]) -> None:
    """Validate chapter list: detect gaps and duplicates. Print warnings/errors."""
    if not chapters:
        return
    indices = sorted(ch.index for ch in chapters)
    # Duplicates
    seen: set[int] = set()
    dups: set[int] = set()
    for idx in indices:
        if idx in seen:
            dups.add(idx)
        seen.add(idx)
    if dups:
        dup_str = ", ".join(str(d) for d in sorted(dups))
        print(f"错误: 存在重复章节号: {dup_str}")
        raise SystemExit(1)

    # Gaps
    for i in range(indices[0], indices[-1]):
        if i not in seen:
            print(f"警告: 第{i}章缺失")
            if len([x for x in range(indices[0], indices[-1]) if x not in seen]) > 20:
                print("  ... (超过 20 章缺失，省略后续警告)")
                break


def _parse_range(spec: str, max_num: int = 0) -> set[int]:
    """Parse range string: '1-50', '1,3,5', 'all'."""
    allowed: set[int] = set()
    try:
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                lo_s, hi_s = part.split("-", 1)
                lo, hi = int(lo_s.strip()), int(hi_s.strip())
                allowed.update(range(lo, hi + 1))
            else:
                allowed.add(int(part))
    except ValueError:
        print(f"错误: 章节范围格式无效，预期格式: 1-50 / 1,3,5，实际收到: {spec}")
        return set()
    if max_num > 0:
        before = len(allowed)
        allowed = {n for n in allowed if 1 <= n <= max_num}
        dropped = before - len(allowed)
        if dropped > 0:
            print(f"警告: {dropped} 个章节号超出实际范围(1-{max_num})，已忽略")
    return allowed
```

- [ ] **Step 2: Update __init__.py to delegate to chapter_collector**

Replace `collect_chapters` and `_parse_range` in `__init__.py` with:

```python
from export_manager.chapter_collector import collect_chapters, ChapterInfo
```

Delete `_parse_range` function and `collect_chapters` function from `__init__.py`.

- [ ] **Step 3: Update existing tests — fix imports**

The existing tests import `from export_manager import collect_chapters, _parse_range`.
Update them to import from `export_manager.chapter_collector`:

```python
from export_manager.chapter_collector import collect_chapters, _parse_range, _validate
```

- [ ] **Step 4: Add new tests for collector enhancements**

```python
class TestCollectorValidation:
    def test_gap_warning(self, tmp_path, capsys):
        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text("# 第1章", encoding="utf-8")
        (tmp_path / "正文" / "第0003章.md").write_text("# 第3章", encoding="utf-8")
        result = collect_chapters(tmp_path)
        captured = capsys.readouterr()
        assert len(result) == 2
        assert "缺失" in captured.out

    def test_duplicate_error(self, tmp_path):
        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text("# 第1章", encoding="utf-8")
        (tmp_path / "正文" / "第1卷").mkdir()
        (tmp_path / "正文" / "第1卷" / "第001章-b.md").write_text("# 第1章b", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            collect_chapters(tmp_path)
        assert exc.value.code == 1

    def test_empty_file_title_fallback(self, tmp_path):
        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text("", encoding="utf-8")
        result = collect_chapters(tmp_path)
        assert result[0].title == "第1章"

    def test_no_heading_title(self, tmp_path):
        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text("正文直接开始，没有标题。", encoding="utf-8")
        result = collect_chapters(tmp_path)
        assert "正文直接开始" in result[0].title

    def test_progress_output(self, tmp_path, capsys):
        (tmp_path / "正文").mkdir()
        for i in range(1, 4):
            (tmp_path / "正文" / f"第{i:04d}章.md").write_text(f"# 第{i}章", encoding="utf-8")
        collect_chapters(tmp_path)
        captured = capsys.readouterr()
        assert "[1/3]" in captured.out
        assert "[3/3]" in captured.out

    def test_volume_from_dir(self, tmp_path):
        (tmp_path / "正文" / "第2卷").mkdir(parents=True)
        (tmp_path / "正文" / "第2卷" / "第051章.md").write_text("# 第51章", encoding="utf-8")
        result = collect_chapters(tmp_path)
        assert result[0].volume == 2

    def test_volume_fallback(self, tmp_path):
        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0051章.md").write_text("# 第51章", encoding="utf-8")
        result = collect_chapters(tmp_path)
        assert result[0].volume == 2  # (51-1)//50+1 = 2
```

- [ ] **Step 5: Run all existing + new tests**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py -q --no-cov`
Expected: All existing TestParseRange and TestCollectChapters pass; new TestCollectorValidation pass.

Note: TestCollectChapters may need import path updates since `collect_chapters` moved. But `export_manager/__init__.py` re-exports it, so existing imports `from export_manager import collect_chapters` should still work.

- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/export_manager/chapter_collector.py .opencode/scripts/export_manager/__init__.py .opencode/scripts/data_modules/tests/test_export_manager.py
git commit -m "refactor: extract chapter_collector.py — volume detection, validation, progress"
```

---

### Task 4: html.py — New HTML Single-File Exporter

**Files:**
- Create: `.opencode/scripts/export_manager/formats/__init__.py`
- Create: `.opencode/scripts/export_manager/formats/html.py`
- Modify: `.opencode/scripts/export_manager/__init__.py` (add html to choices + dispatch)
- Test: `.opencode/scripts/data_modules/tests/test_export_manager.py` (append)

- [ ] **Step 1: Create formats/__init__.py**

```python
#!/usr/bin/env python3
"""Export format registry. Each format module provides an export_* function."""
```

- [ ] **Step 2: Write html.py**

```python
#!/usr/bin/env python3
"""HTML single-file export — all chapters in one HTML document with inline CSS."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from export_manager.parser import md_to_html
from export_manager.styles import get_css


def export_html(
    chapters: list,  # list[ChapterInfo]
    output_path: Path,
    title: str = "",
    custom_css: Optional[Path] = None,
) -> None:
    """Export chapters as a single HTML file with navigation TOC."""
    css = get_css(custom_css)

    html_parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{_escape(title) or '小说导出'}</title>",
        "<style>",
        css,
        "</style>",
        "</head>",
        "<body>",
    ]

    if title:
        html_parts.append(f"<h1 class='book-title'>{_escape(title)}</h1>")

    # TOC
    html_parts.append('<nav class="toc"><h2>目录</h2><ol>')
    for ch in chapters:
        html_parts.append(
            f'<li><a href="#ch{ch.index:04d}">第{ch.index}章 {_escape(ch.title)}</a></li>'
        )
    html_parts.append("</ol></nav>")

    # Chapters
    for ch in chapters:
        text = ch.path.read_text(encoding="utf-8")
        body_html = md_to_html(text)
        html_parts.append(
            f'<section id="ch{ch.index:04d}">'
            f'<h1 class="chapter-title">第{ch.index}章 {_escape(ch.title)}</h1>'
            f"{body_html}"
            f"</section>"
        )

    html_parts.append("</body></html>")

    output_path.write_text("\n".join(html_parts), encoding="utf-8")


def _escape(text: str) -> str:
    """Minimal HTML entity escaping."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
```

- [ ] **Step 3: Write failing test**

```python
class TestHtmlExport:
    def test_basic(self, tmp_path):
        from export_manager.chapter_collector import collect_chapters
        from export_manager.formats.html import export_html

        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text("# 第1章 开篇\n\n正文内容。", encoding="utf-8")
        (tmp_path / "正文" / "第0002章.md").write_text("# 第2章 发展\n\n更多内容。", encoding="utf-8")

        chapters = collect_chapters(tmp_path)
        output = tmp_path / "导出" / "小说.html"
        output.parent.mkdir()

        export_html(chapters, output, title="测试小说")

        content = output.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert '<html lang="zh-CN"' in content
        assert '<meta charset="utf-8">' in content
        assert "测试小说" in content
        assert "第1章 开篇" in content
        assert "正文内容。" in content
        assert 'class="toc"' in content
        assert 'id="ch0001"' in content
```

- [ ] **Step 4: Run test**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py::TestHtmlExport -q --no-cov`
Expected: PASS

- [ ] **Step 5: Wire up in __init__.py — add html to CLI**

In `__init__.py`:
- Change `choices=["md", "txt", "epub"]` to `choices=["md", "txt", "epub", "html", "docx", "pdf"]`
- Add to `cmd_export` dispatch:

```python
elif fmt == "html":
    from export_manager.formats.html import export_html
    export_html(
        chapters=chapters,
        output_path=Path(output),
        title=args.title or project_root.name,
        custom_css=Path(args.style) if args.style else None,
    )
```

- Add `--style` argument to p_export:
```python
p_export.add_argument("--style", help="自定义 CSS 文件路径（覆盖默认排版）")
```

- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/export_manager/formats/__init__.py .opencode/scripts/export_manager/formats/html.py .opencode/scripts/export_manager/__init__.py .opencode/scripts/data_modules/tests/test_export_manager.py
git commit -m "feat: add HTML single-file export with inline CSS and TOC"
```

---

### Task 5: epub.py Refactor — Use parser.py + Fix Exception Handling

**Files:**
- Move: `.opencode/scripts/export_manager/epub.py` → `.opencode/scripts/export_manager/formats/epub.py`
- Modify: `.opencode/scripts/export_manager/__init__.py` (update import paths)
- Test: `.opencode/scripts/data_modules/tests/test_export_manager.py` (modify)

- [ ] **Step 1: Move epub.py to formats/ and refactor**

Move `epub.py` to `formats/epub.py`. Replace `_md_to_html` with `from export_manager.parser import md_to_html`. Replace the hardcoded `_DEFAULT_CSS` with `from export_manager.styles import get_default_css`. Fix `_crop_cover` exception handling.

The key changes in `formats/epub.py`:

```python
# Remove _md_to_html entirely. Replace with:
from export_manager.parser import md_to_html
from export_manager.styles import get_default_css

# Replace _DEFAULT_CSS usage with:
css_text = get_default_css()
```

Fix `_crop_cover` exception handling:

```python
def _crop_cover(src: Path, size: str) -> bytes:
    try:
        from PIL import Image
    except ImportError:
        print("警告: Pillow 未安装，封面将使用原图尺寸。安装: pip install Pillow")
        return src.read_bytes()

    w_s, h_s = size.split("x")
    target_w, target_h = int(w_s), int(h_s)

    try:
        img = Image.open(src).convert("RGB")
    except Exception:
        print(f"警告: 无法打开封面图片 {src}，将使用原图字节")
        return src.read_bytes()
    # ... rest unchanged
```

- [ ] **Step 2: Update __init__.py import path**

```python
elif fmt == "epub":
    from export_manager.formats.epub import export_epub
    # ... rest unchanged
```

Delete the old `epub.py` at `export_manager/epub.py`.

- [ ] **Step 3: Update existing EPUB test imports**

In `test_export_manager.py`, update the epub import:

```python
from export_manager.formats.epub import export_epub
```

- [ ] **Step 4: Run all existing tests to verify no regression**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py -q --no-cov`
Expected: All existing tests pass (TestMarkdownExport, TestTxtExport, TestEpubImportError, TestCollectChapters, etc.)

- [ ] **Step 5: Add forward EPUB creation test**

```python
class TestEpubForward:
    def test_epub_creates_file(self, tmp_path):
        """Test that EPUB export produces a non-empty file (requires ebooklib)."""
        try:
            from ebooklib import epub  # noqa: F401
        except ImportError:
            pytest.skip("ebooklib not installed")

        from export_manager.chapter_collector import collect_chapters
        from export_manager.formats.epub import export_epub

        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text(
            "# 第1章 开篇\n\n这是正文。\n\n第二段。", encoding="utf-8"
        )

        chapters = collect_chapters(tmp_path)
        output = tmp_path / "导出" / "小说.epub"
        output.parent.mkdir()

        export_epub(chapters, output, title="测试", author="作者")

        assert output.is_file()
        assert output.stat().st_size > 0
```

- [ ] **Step 6: Run and commit**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py -q --no-cov`
Expected: All pass

```bash
git add .opencode/scripts/export_manager/formats/epub.py .opencode/scripts/export_manager/__init__.py .opencode/scripts/data_modules/tests/test_export_manager.py
git rm .opencode/scripts/export_manager/epub.py
git commit -m "refactor: move epub.py to formats/, use parser.py, fix exception handling"
```

---

### Task 6: docx.py — New DOCX Exporter via AST

**Files:**
- Create: `.opencode/scripts/export_manager/formats/docx.py`
- Modify: `.opencode/scripts/export_manager/__init__.py` (already has docx in choices from Task 5)
- Test: `.opencode/scripts/data_modules/tests/test_export_manager.py` (append)

- [ ] **Step 1: Install dependency**

Run: `pip install "python-docx>=1.0"`

- [ ] **Step 2: Write docx.py**

```python
#!/usr/bin/env python3
"""DOCX export — builds Word documents from chapter AST via python-docx."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from docx import Document
from docx.shared import Pt, Cm, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from export_manager.parser import md_to_blocks


def export_docx(
    chapters: list,  # list[ChapterInfo]
    output_path: Path,
    title: str = "",
    author: Optional[str] = None,
) -> None:
    """Export chapters as a .docx file with Chinese novel typesetting."""
    doc = Document()

    # Page setup: A4
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)

    # Default paragraph style: first-line indent, line spacing
    style = doc.styles["Normal"]
    style.font.size = Pt(12)
    style.font.name = "宋体"
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    pf = style.paragraph_format
    pf.first_line_indent = Pt(24)  # ~2 Chinese characters
    pf.line_spacing = 1.8
    pf.space_after = Pt(4)

    # Title page
    if title:
        h = doc.add_heading(title, level=0)
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if author:
        doc.add_paragraph(f"作者: {author}").alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Chapters
    for ch in chapters:
        doc.add_page_break()
        # Chapter heading
        heading = doc.add_heading(f"第{ch.index}章 {ch.title}", level=1)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

        text = ch.path.read_text(encoding="utf-8")
        try:
            blocks = md_to_blocks(text)
        except Exception:
            # Fallback: plain text paragraph
            doc.add_paragraph(text)
            continue

        for block in blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")

            if btype == "heading":
                # Skip headings (already added chapter heading above)
                continue
            elif btype == "thematic_break":
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run("* * *")
                run.font.size = Pt(10)
                run.font.color.rgb = None
            elif btype == "paragraph":
                text_content = _extract_block_text(block)
                if not text_content.strip():
                    continue
                p = doc.add_paragraph()
                _add_runs_with_bold(p, block)
            elif btype == "blank_line":
                doc.add_paragraph("")
            elif btype == "block_code":
                p = doc.add_paragraph()
                p.style = doc.styles["Normal"]
                run = p.add_run(_extract_block_text(block))
                run.font.name = "Courier New"
                run.font.size = Pt(10)
            else:
                # Unknown block type — add as plain paragraph
                text_content = _extract_block_text(block)
                if text_content.strip():
                    doc.add_paragraph(text_content)

    doc.save(str(output_path))


def _extract_block_text(block: dict) -> str:
    """Extract plain text from a mistune AST block dict."""
    # Handle simple text field
    if "text" in block:
        return block["text"]

    children = block.get("children", [])
    texts = []
    for child in children:
        if isinstance(child, dict):
            if child.get("type") == "text":
                texts.append(child.get("raw", "") or child.get("text", ""))
            elif child.get("type") == "strong":
                inner = child.get("children", [])
                for c in inner:
                    if isinstance(c, dict) and c.get("type") == "text":
                        texts.append(c.get("raw", "") or c.get("text", ""))
            else:
                texts.append(_extract_block_text(child))
        elif isinstance(child, str):
            texts.append(child)
    return "".join(texts)


def _add_runs_with_bold(paragraph, block: dict) -> None:
    """Add runs to a paragraph, handling inline strong/bold formatting."""
    children = block.get("children", [])
    if not children:
        text = block.get("text", "")
        if text:
            paragraph.add_run(text)
        return

    for child in children:
        if not isinstance(child, dict):
            continue
        ctype = child.get("type", "")
        if ctype == "text":
            paragraph.add_run(child.get("raw", "") or child.get("text", ""))
        elif ctype == "strong":
            inner = child.get("children", [])
            for c in inner:
                if isinstance(c, dict) and c.get("type") == "text":
                    run = paragraph.add_run(c.get("raw", "") or c.get("text", ""))
                    run.bold = True
        elif ctype in ("emphasis", "codespan", "link", "image"):
            # Extract text for simple inline handling
            text = _extract_block_text(child)
            if text:
                run = paragraph.add_run(text)
                if ctype == "emphasis":
                    run.italic = True
        else:
            text = _extract_block_text(child)
            if text:
                paragraph.add_run(text)
```

- [ ] **Step 3: Write failing test**

```python
class TestDocxExport:
    def test_basic(self, tmp_path):
        try:
            from docx import Document  # noqa: F401
        except ImportError:
            pytest.skip("python-docx not installed")

        from export_manager.chapter_collector import collect_chapters
        from export_manager.formats.docx import export_docx

        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text(
            "# 第1章 开篇\n\n这是正文内容。\n\n第二段。", encoding="utf-8"
        )

        chapters = collect_chapters(tmp_path)
        output = tmp_path / "导出" / "小说.docx"
        output.parent.mkdir()

        export_docx(chapters, output, title="测试", author="作者")

        assert output.is_file()
        assert output.stat().st_size > 0

    def test_scene_break(self, tmp_path):
        try:
            from docx import Document  # noqa: F401
        except ImportError:
            pytest.skip("python-docx not installed")

        from export_manager.chapter_collector import collect_chapters
        from export_manager.formats.docx import export_docx

        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text(
            "第一场景。\n\n---\n\n第二场景。", encoding="utf-8"
        )

        chapters = collect_chapters(tmp_path)
        output = tmp_path / "导出" / "小说.docx"
        output.parent.mkdir()

        export_docx(chapters, output, title="测试")

        from docx import Document
        doc = Document(str(output))
        # Find the scene break paragraph
        texts = [p.text for p in doc.paragraphs]
        assert any("* * *" in t for t in texts), f"Scene break not found in: {texts}"

    def test_bold_text(self, tmp_path):
        try:
            from docx import Document  # noqa: F401
        except ImportError:
            pytest.skip("python-docx not installed")

        from export_manager.chapter_collector import collect_chapters
        from export_manager.formats.docx import export_docx

        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text(
            "这是**粗体**文字。", encoding="utf-8"
        )

        chapters = collect_chapters(tmp_path)
        output = tmp_path / "导出" / "小说.docx"
        output.parent.mkdir()

        export_docx(chapters, output, title="测试")

        from docx import Document
        doc = Document(str(output))
        # Find a paragraph with bold run
        found_bold = False
        for p in doc.paragraphs:
            for run in p.runs:
                if run.bold and "粗体" in run.text:
                    found_bold = True
        assert found_bold, "Bold text not found in document"
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py::TestDocxExport -q --no-cov`
Expected: PASS

- [ ] **Step 5: Wire up in __init__.py**

Add to `cmd_export`:

```python
elif fmt == "docx":
    from export_manager.formats.docx import export_docx
    export_docx(
        chapters=chapters,
        output_path=Path(output),
        title=args.title or project_root.name,
        author=args.author,
    )
```

- [ ] **Step 6: Commit**

```bash
git add .opencode/scripts/export_manager/formats/docx.py .opencode/scripts/export_manager/__init__.py .opencode/scripts/data_modules/tests/test_export_manager.py
git commit -m "feat: add DOCX export — AST-path via python-docx with Chinese typesetting"
```

---

### Task 7: pdf.py — New PDF Exporter (Optional Dependency)

**Files:**
- Create: `.opencode/scripts/export_manager/formats/pdf.py`
- Modify: `.opencode/scripts/export_manager/__init__.py` (already has pdf in choices from Task 5)
- Test: `.opencode/scripts/data_modules/tests/test_export_manager.py` (append)

- [ ] **Step 1: Write pdf.py**

```python
#!/usr/bin/env python3
"""PDF export — renders HTML to PDF via weasyprint (optional dependency)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from export_manager.parser import md_to_html
from export_manager.styles import get_css


_PDF_EXTRA_CSS = """
@page {
    size: A4;
    margin: 2cm;
}
h1.chapter-title {
    page-break-before: always;
}
"""


def export_pdf(
    chapters: list,  # list[ChapterInfo]
    output_path: Path,
    title: str = "",
    custom_css: Optional[Path] = None,
) -> None:
    """Export chapters as a PDF file. Requires weasyprint."""
    try:
        from weasyprint import HTML
    except ImportError:
        print("PDF 导出需要 weasyprint，请运行: pip install weasyprint")
        raise SystemExit(1)

    css = get_css(custom_css) + _PDF_EXTRA_CSS

    html_parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{_escape(title) or '小说导出'}</title>",
        "<style>",
        css,
        "</style>",
        "</head>",
        "<body>",
    ]

    if title:
        html_parts.append(f"<h1 class='book-title'>{_escape(title)}</h1>")

    # TOC
    html_parts.append('<nav class="toc"><h2>目录</h2><ol>')
    for ch in chapters:
        html_parts.append(
            f'<li><a href="#ch{ch.index:04d}">第{ch.index}章 {_escape(ch.title)}</a></li>'
        )
    html_parts.append("</ol></nav>")

    for ch in chapters:
        text = ch.path.read_text(encoding="utf-8")
        body_html = md_to_html(text)
        html_parts.append(
            f'<section id="ch{ch.index:04d}">'
            f'<h1 class="chapter-title">第{ch.index}章 {_escape(ch.title)}</h1>'
            f"{body_html}"
            f"</section>"
        )

    html_parts.append("</body></html>")

    html_str = "\n".join(html_parts)
    HTML(string=html_str).write_pdf(str(output_path))


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
```

- [ ] **Step 2: Write test**

```python
class TestPdfExport:
    def test_missing_dependency(self, tmp_path, monkeypatch):
        """PDF exits gracefully when weasyprint is not installed."""
        from export_manager.chapter_collector import collect_chapters

        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text("# 第1章\n\n正文。", encoding="utf-8")
        chapters = collect_chapters(tmp_path)
        output = tmp_path / "导出" / "小说.pdf"
        output.parent.mkdir()

        import builtins
        _orig_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "weasyprint":
                raise ImportError("No module named 'weasyprint'")
            return _orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _mock_import)

        from export_manager.formats.pdf import export_pdf

        with pytest.raises(SystemExit) as exc:
            export_pdf(chapters, output, title="测试")
        assert exc.value.code == 1
```

- [ ] **Step 3: Run test**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py::TestPdfExport -q --no-cov`
Expected: PASS

- [ ] **Step 4: Wire up in __init__.py**

Add to `cmd_export`:

```python
elif fmt == "pdf":
    from export_manager.formats.pdf import export_pdf
    export_pdf(
        chapters=chapters,
        output_path=Path(output),
        title=args.title or project_root.name,
        custom_css=Path(args.style) if args.style else None,
    )
```

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/export_manager/formats/pdf.py .opencode/scripts/export_manager/__init__.py .opencode/scripts/data_modules/tests/test_export_manager.py
git commit -m "feat: add PDF export via weasyprint (optional dependency)"
```

---

### Task 8: txt.py + markdown.py — Move to formats/ + Refactor txt.py

**Files:**
- Move: `.opencode/scripts/export_manager/txt.py` → `.opencode/scripts/export_manager/formats/txt.py`
- Move: `.opencode/scripts/export_manager/markdown.py` → `.opencode/scripts/export_manager/formats/markdown.py`
- Modify: `.opencode/scripts/export_manager/formats/txt.py` (replace _strip_markdown with mistune)
- Modify: `.opencode/scripts/export_manager/__init__.py` (update imports)
- Test: Update imports

- [ ] **Step 1: Move files and refactor txt.py**

Move `txt.py` and `markdown.py` into `formats/`. In `formats/txt.py`, replace `_strip_markdown` with a mistune-based plain text renderer:

```python
#!/usr/bin/env python3
"""TXT plain text export — strips markdown via mistune text renderer."""
from __future__ import annotations

from pathlib import Path

import mistune


def _strip_markdown(text: str) -> str:
    """Remove inline markdown formatting, return plain text."""
    md = mistune.create_markdown(renderer=mistune.AstRenderer())
    blocks = md(text)
    return _render_blocks_plain(blocks)


def _render_blocks_plain(blocks: list) -> str:
    """Walk mistune AST and extract plain text."""
    lines: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "paragraph":
            text = _extract_inline_text(block)
            if text.strip():
                lines.append(text)
        elif btype == "heading":
            text = _extract_inline_text(block)
            if text.strip():
                lines.append(text)
        elif btype == "blank_line":
            lines.append("")
        elif btype == "thematic_break":
            lines.append("")
        elif btype == "block_code":
            text = _extract_inline_text(block)
            if text:
                lines.append(text)
        elif "text" in block:
            lines.append(block["text"])
    return "\n".join(lines)


def _extract_inline_text(block: dict) -> str:
    """Recursively extract text from inline children, stripping formatting."""
    children = block.get("children", [])
    if not children:
        return block.get("text", "")
    texts = []
    for child in children:
        if isinstance(child, dict):
            ctype = child.get("type", "text")
            if ctype == "text":
                texts.append(child.get("raw", "") or child.get("text", ""))
            elif ctype == "strong":
                inner = child.get("children", [])
                for c in inner:
                    if isinstance(c, dict):
                        texts.append(c.get("raw", "") or c.get("text", ""))
            elif ctype in ("emphasis", "codespan", "link"):
                texts.append(_extract_inline_text(child))
            else:
                texts.append(_extract_inline_text(child))
        elif isinstance(child, str):
            texts.append(child)
    return "".join(texts)


def export_txt(chapters: list, output_path: Path) -> None:
    """Export all chapters as plain text .txt file."""
    lines: list[str] = []

    for ch in chapters:
        lines.append(f"第{ch.index}章  {ch.title}")
        lines.append("")
        text = ch.path.read_text(encoding="utf-8")
        clean = _strip_markdown(text)
        lines.append(clean.rstrip())
        lines.append("")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 2: Update __init__.py imports**

```python
if fmt == "md":
    from export_manager.formats.markdown import export_markdown
elif fmt == "txt":
    from export_manager.formats.txt import export_txt
```

Delete old `export_manager/txt.py` and `export_manager/markdown.py`.

- [ ] **Step 3: Update test imports**

Change imports in test file:
```python
from export_manager.formats.markdown import export_markdown
from export_manager.formats.txt import export_txt, _strip_markdown
```

- [ ] **Step 4: Run all tests to verify no regression**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py -q --no-cov`
Expected: All existing tests pass

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/export_manager/formats/txt.py .opencode/scripts/export_manager/formats/markdown.py .opencode/scripts/export_manager/__init__.py .opencode/scripts/data_modules/tests/test_export_manager.py
git rm .opencode/scripts/export_manager/txt.py .opencode/scripts/export_manager/markdown.py
git commit -m "refactor: move md/txt to formats/, replace txt regex with mistune renderer"
```

---

### Task 9: __init__.py Final Cleanup + Integration Test

**Files:**
- Modify: `.opencode/scripts/export_manager/__init__.py` (final cleanup)
- Test: `.opencode/scripts/data_modules/tests/test_export_manager.py` (add integration test)

- [ ] **Step 1: Clean up __init__.py — remove leftover functions**

After all moves, `__init__.py` should be:

```python
#!/usr/bin/env python3
"""Export manager CLI — chapter collection + format dispatch."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_scripts_root = Path(__file__).resolve().parent.parent
if str(_scripts_root) not in sys.path:
    sys.path.insert(0, str(_scripts_root))

from export_manager.chapter_collector import collect_chapters


def cmd_list(args: argparse.Namespace) -> int:
    chapters = collect_chapters(args.project_root)
    if not chapters:
        print("无章节文件")
        return 1
    for ch in chapters:
        print(f"第{ch.index:04d}章  {ch.title}  ({ch.path})")
    print(f"\n共 {len(chapters)} 章")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    project_root = args.project_root
    chapters = collect_chapters(project_root, range_spec=args.range, volume=args.volume)

    if not chapters:
        print("错误: 正文/ 目录不存在或无章节文件。请先使用 /webnovel-write 创建章节。")
        return 1

    fmt = args.format
    output = args.output
    if not output:
        title = args.title or project_root.name
        output = str(project_root / "导出" / f"{title}.{fmt}")

    Path(output).parent.mkdir(parents=True, exist_ok=True)

    if fmt == "md":
        from export_manager.formats.markdown import export_markdown
        export_markdown(chapters, Path(output), title=args.title or project_root.name)
    elif fmt == "txt":
        from export_manager.formats.txt import export_txt
        export_txt(chapters, Path(output))
    elif fmt == "epub":
        from export_manager.formats.epub import export_epub
        export_epub(
            chapters=chapters,
            output_path=Path(output),
            title=args.title or project_root.name,
            author=args.author,
            cover=args.cover,
            style=args.style,
            cover_size=args.cover_size,
        )
    elif fmt == "html":
        from export_manager.formats.html import export_html
        export_html(
            chapters=chapters,
            output_path=Path(output),
            title=args.title or project_root.name,
            custom_css=Path(args.style) if args.style else None,
        )
    elif fmt == "docx":
        from export_manager.formats.docx import export_docx
        export_docx(
            chapters=chapters,
            output_path=Path(output),
            title=args.title or project_root.name,
            author=args.author,
        )
    elif fmt == "pdf":
        from export_manager.formats.pdf import export_pdf
        export_pdf(
            chapters=chapters,
            output_path=Path(output),
            title=args.title or project_root.name,
            custom_css=Path(args.style) if args.style else None,
        )
    else:
        print(f"不支持的格式: {fmt}，可选: md, txt, epub, html, docx, pdf")
        return 1

    print(f"导出完成: {output}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="webnovel export manager")
    parser.add_argument("--project-root", type=Path, required=True, help="项目根目录")

    sub = parser.add_subparsers(dest="action")

    sub.add_parser("list", help="列出可导出章节")

    p_export = sub.add_parser("export", help="执行导出")
    p_export.add_argument("--format", choices=["md", "txt", "epub", "html", "docx", "pdf"],
                          default="md", help="输出格式")
    p_export.add_argument("--range", help="章节范围: 1-50 / 1,3,5 / all")
    p_export.add_argument("--volume", type=int, help="按卷导出")
    p_export.add_argument("--output", help="输出文件路径")
    p_export.add_argument("--title", help="书名")
    p_export.add_argument("--author", help="作者名")
    p_export.add_argument("--cover", help="封面图路径")
    p_export.add_argument("--style", help="自定义 CSS 文件路径（覆盖默认排版）")
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

- [ ] **Step 2: Add CLI integration test**

```python
class TestExportCli:
    def test_export_html_integration(self, tmp_path, monkeypatch):
        """End-to-end CLI test for HTML export."""
        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第0001章.md").write_text("# 第1章\n\n内容。", encoding="utf-8")

        monkeypatch.setattr("sys.argv", [
            "export_manager",
            "--project-root", str(tmp_path),
            "export",
            "--format", "html",
            "--range", "1",
        ])

        with pytest.raises(SystemExit) as exc:
            from export_manager.__init__ import main
            main()
        assert exc.value.code == 0

        # Verify file was created
        export_dir = tmp_path / "导出"
        html_files = list(export_dir.glob("*.html"))
        assert len(html_files) == 1
        content = html_files[0].read_text(encoding="utf-8")
        assert "第1章" in content
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py -q --no-cov -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/export_manager/__init__.py .opencode/scripts/data_modules/tests/test_export_manager.py
git commit -m "refactor: finalize __init__.py cleanup, add CLI integration test"
```

---

### Test Summary

After all 9 tasks complete, the test file should contain:

| Test Class | Tests | What it covers |
|-----------|-------|---------------|
| TestParseRange | 4 | Range string parsing (existing) |
| TestCollectChapters | 6 | Chapter collection (existing, imports updated) |
| TestMarkdownExport | 1 | MD concatenation (existing, imports updated) |
| TestTxtExport | 2 | TXT export + strip markdown (existing, imports updated) |
| TestEpubImportError | 1 | Missing ebooklib (existing, imports updated) |
| TestParser | 7 | Unified parser: heading, paragraph, bold, scene break, empty, multi-para, blocks AST |
| TestStyles | 4 | CSS templates: default, custom load, fallback, custom preference |
| TestCollectorValidation | 7 | Gaps, duplicates, empty file fallback, no-heading title, progress output, volume from dir, volume fallback |
| TestHtmlExport | 1 | HTML file creation with TOC and structure |
| TestDocxExport | 3 | DOCX basic, scene break, bold text |
| TestPdfExport | 1 | Graceful exit when weasyprint missing |
| TestEpubForward | 1 | EPUB creates non-empty file |
| TestExportCli | 1 | End-to-end CLI HTML export |
| **Total** | **39** | |

Run all: `python -m pytest .opencode/scripts/data_modules/tests/test_export_manager.py -q --no-cov -v`
