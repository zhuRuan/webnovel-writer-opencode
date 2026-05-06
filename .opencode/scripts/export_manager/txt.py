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
