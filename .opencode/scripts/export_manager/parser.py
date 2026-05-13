#!/usr/bin/env python3
"""Unified Markdown parser — mistune v3 based, outputs HTML and AST."""
from __future__ import annotations

import mistune


class WebnovelRenderer(mistune.HTMLRenderer):
    """Custom HTML renderer for Chinese web novel content."""

    def heading(self, text: str, level: int, **attrs) -> str:
        if level == 1:
            return f'<h1 class="chapter-title">{text}</h1>\n'
        return super().heading(text, level, **attrs)

    def thematic_break(self) -> str:
        return '<hr class="scene-break" />\n'


def md_to_html(text: str) -> str:
    """Convert Markdown text to HTML fragment (no html/body wrapper)."""
    if not text.strip():
        return ""
    md = mistune.create_markdown(renderer=WebnovelRenderer())
    html = md(text)
    return html.strip()


def md_to_blocks(text: str) -> list[dict]:
    """Convert Markdown to mistune AST block list."""
    if not text.strip():
        return []
    md = mistune.create_markdown()
    _, state = md.parse(text)
    return state.tokens
