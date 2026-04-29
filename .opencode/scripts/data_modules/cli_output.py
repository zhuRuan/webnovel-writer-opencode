#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI output helpers for data_modules.

All CLI tools should emit output via these helpers.
Supports dual mode: text (human-readable with colors) and json (machine-readable).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

import colorama
from colorama import Fore, Style

# Initialize colorama for cross-platform ANSI color support
colorama.init()

_OUTPUT_FORMAT = "json"  # "text" | "json"


def set_output_format(fmt: str) -> None:
    """Set global output format: text | json"""
    global _OUTPUT_FORMAT
    if fmt not in ("text", "json"):
        fmt = "text"
    _OUTPUT_FORMAT = fmt


def _resolve_format(fmt: Optional[str]) -> str:
    return fmt if fmt is not None else _OUTPUT_FORMAT


def _print_text(text: str, *, file=sys.stdout) -> None:
    print(text, file=file)


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


@dataclass
class ErrorPayload:
    code: str
    message: str
    suggestion: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


def build_success(data: Any = None, message: str = "ok", warnings: Optional[list] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"status": "success", "message": message}
    if data is not None:
        payload["data"] = data
    if warnings:
        payload["warnings"] = warnings
    return payload


def build_error(code: str, message: str, suggestion: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if suggestion:
        error["suggestion"] = suggestion
    if details:
        error["details"] = details
    return {"status": "error", "error": error}


def print_info(message: str, *, format: Optional[str] = None) -> None:
    fmt = _resolve_format(format)
    if fmt == "json":
        _print_json(build_success(message=message))
    else:
        _print_text(f"{Fore.CYAN}→{Style.RESET_ALL} {message}")


def print_warning(message: str, *, format: Optional[str] = None) -> None:
    fmt = _resolve_format(format)
    if fmt == "json":
        _print_json(build_success(message=message, warnings=[message]))
    else:
        _print_text(f"{Fore.YELLOW}⚠{Style.RESET_ALL} {message}")


def print_success(data: Any = None, message: str = "ok", warnings: Optional[list] = None, *, format: Optional[str] = None) -> None:
    fmt = _resolve_format(format)
    if fmt == "json":
        _print_json(build_success(data=data, message=message, warnings=warnings))
    else:
        text = message
        if warnings:
            text += f" ({', '.join(str(w) for w in warnings)})"
        _print_text(f"{Fore.GREEN}✓{Style.RESET_ALL} {text}")


def print_error(code: str, message: str, suggestion: Optional[str] = None, details: Optional[Dict[str, Any]] = None, *, format: Optional[str] = None) -> None:
    fmt = _resolve_format(format)
    if fmt == "json":
        _print_json(build_error(code=code, message=message, suggestion=suggestion, details=details))
    else:
        text = f"{Fore.RED}✗{Style.RESET_ALL} [{code}] {message}"
        if suggestion:
            text += f"\n  {Fore.YELLOW}建议:{Style.RESET_ALL} {suggestion}"
        _print_text(text, file=sys.stderr)


def print_table(headers: list[str], rows: list[list[str]], *, format: Optional[str] = None) -> None:
    """Print a text table or JSON array."""
    fmt = _resolve_format(format)
    if fmt == "json":
        data = [dict(zip(headers, row)) for row in rows]
        _print_json(build_success(data=data))
    else:
        if not rows:
            _print_text("无数据。")
            return
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        _print_text(header_line)
        _print_text("  ".join("─" * w for w in col_widths))
        for row in rows:
            line = "  ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
            _print_text(line)


# Legacy aliases for backward compatibility
def print_json(payload: Dict[str, Any]) -> None:
    _print_json(payload)
