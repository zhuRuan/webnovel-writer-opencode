#!/usr/bin/env python3
"""TXT plain text export — strips markdown via mistune text renderer."""
from __future__ import annotations

from pathlib import Path

import mistune


def _strip_markdown(text: str) -> str:
    """Remove inline markdown formatting, return plain text."""
    result_parts: list[str] = []
    md = mistune.create_markdown(renderer=None)
    blocks = md(text)

    for block in blocks:
        if not isinstance(block, dict):
            continue
        text_content = _extract_inline_text(block)
        if text_content:
            result_parts.append(text_content)
    return "\n".join(result_parts)


def _extract_inline_text(block: dict) -> str:
    """Recursively extract text from inline children, stripping formatting."""
    if "raw" in block:
        return block["raw"]
    if "text" in block and isinstance(block["text"], str):
        return block["text"]
    children = block.get("children", [])
    if not children:
        return ""
    texts = []
    for child in children:
        if isinstance(child, dict):
            texts.append(_extract_inline_text(child))
        elif isinstance(child, str):
            texts.append(child)
    return "".join(texts)


def export_txt(chapters: list, output_path: Path) -> None:
    """Export all chapters as plain text .txt file."""
    lines: list[str] = []

    for ch in chapters:
        if not isinstance(ch, tuple):
            ch_index, ch_title, ch_path = ch.index, ch.title, ch.path
        else:
            ch_index, ch_title, ch_path = ch[0], ch[1], ch[2]
        lines.append(f"第{ch_index}章  {ch_title}")
        lines.append("")
        text = ch_path.read_text(encoding="utf-8")
        clean = _strip_markdown(text)
        lines.append(clean.rstrip())
        lines.append("")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
