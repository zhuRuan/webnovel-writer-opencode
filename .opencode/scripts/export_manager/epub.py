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
        detected = _detect_style(output_path.parent.parent)
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
