# CLI Output Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance cli_output.py with color support and dual text/json mode, migrate all CLI commands.

**Architecture:** Three tasks. Task 1 enhances cli_output.py (color, format, new helpers) and adds colorama dependency. Task 2 migrates checkers_cli.py. Task 3 migrates observability_cli.py.

**Tech Stack:** Python 3.10+, colorama

---

### Task 1: Enhance cli_output.py + add colorama dependency

**Files:**
- Modify: `.opencode/scripts/data_modules/cli_output.py`
- Modify: `requirements.txt` (add colorama)

- [ ] **Step 1: Add colorama dependency**

In `requirements.txt`, add (in alphabetical order near color related entries):
```
colorama>=0.4.6
```

- [ ] **Step 2: Rewrite cli_output.py**

Replace the content of `.opencode/scripts/data_modules/cli_output.py` with:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI output helpers for data_modules.

All CLI tools should emit output via these helpers.
Supports dual mode: text (human-readable with colors) and json (machine-readable).
"""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

import colorama
from colorama import Fore, Style

# Initialize colorama for cross-platform ANSI color support
colorama.init()

_OUTPUT_FORMAT = "text"  # "text" | "json"


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
            text += f" ({', '.join(warnings)})"
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
        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        # Header
        header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        _print_text(header_line)
        _print_text("  ".join("─" * w for w in col_widths))
        # Rows
        for row in rows:
            line = "  ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
            _print_text(line)


# Legacy aliases for backward compatibility
def print_json(payload: Dict[str, Any]) -> None:
    _print_json(payload)
```

- [ ] **Step 3: Verify module loads**

```bash
python -c "import sys; sys.path.insert(0, '.opencode/scripts'); from data_modules.cli_output import print_success, print_info, print_warning, print_error, print_table, set_output_format; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run full test suite**

```bash
python .opencode/scripts/run_all_tests.py 2>&1 | Select-Object -Last 5
```

Expected: 519 passed, 0 failed (unchanged).

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/data_modules/cli_output.py requirements.txt
git commit -m "feat: enhance cli_output.py with color support and text/json dual mode"
```

---

### Task 2: Migrate checkers_cli.py

**Files:**
- Modify: `.opencode/scripts/data_modules/checkers_cli.py`

- [ ] **Step 1: Replace direct print calls with cli_output**

In `checkers_cli.py`:

```python
# Replace all print() with cli_output functions

from .cli_output import print_success, print_error, print_info, print_table
```

Update `cmd_list` — replace the text display block (lines 711-729):
```python
    # OLD: direct print with manual formatting
    print(f"审查器列表 (共 {len(checkers)} 个):\n")
    for checker in checkers:
        ...
    
    # NEW: use print_table
    headers = ["id", "name", "category", "triggers"]
    rows = []
    for c in checkers:
        triggers = c.get("triggers", [])
        trigger_desc = "; ".join(
            str(t.get("expression") or t.get("keywords", "(条件)"))[:60]
            for t in triggers[:2] if isinstance(t, dict)
        ) if triggers else ""
        rows.append([c["id"], c["name"], c["category"], trigger_desc])
    print_table(headers, rows)
```

Update `cmd_validate` — replace error/warning print blocks with `print_error`/`print_warning`.
Update `cmd_create` — replace success/failure prints with `print_success`/`print_error`.
Update `cmd_schema` — replace with `print_success`.

- [ ] **Step 2: Verify CLI works**

```bash
python .opencode/scripts/webnovel.py checkers list
python .opencode/scripts/webnovel.py checkers validate
python .opencode/scripts/webnovel.py checkers schema consistency-checker
```

Expected: colored output in text mode.

- [ ] **Step 3: Run full test suite**

```bash
python .opencode/scripts/run_all_tests.py 2>&1 | Select-Object -Last 5
```

Expected: 519 passed, 0 failed.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/checkers_cli.py
git commit -m "refactor: migrate checkers_cli.py to use cli_output helpers"
```

---

### Task 3: Migrate observability_cli.py

**Files:**
- Modify: `.opencode/scripts/data_modules/observability_cli.py`

- [ ] **Step 1: Replace direct print calls**

In `observability_cli.py`, replace `print()` with:
```python
from .cli_output import print_success, print_error, print_info, print_table
```

- `print("无观测数据。")` → `print_info("无观测数据。")`
- `print("无项目目录...")` → `print_error("NO_PROJECT", "无项目目录...")`
- The token-report text block → `print_table()`
- The `format_perf_report` output is still printed via observability.py's own formatting

- [ ] **Step 2: Verify CLI works**

```bash
python .opencode/scripts/webnovel.py observability report
python .opencode/scripts/webnovel.py observability token-report
```

Expected: colored output.

- [ ] **Step 3: Run full test suite**

```bash
python .opencode/scripts/run_all_tests.py 2>&1 | Select-Object -Last 5
```

Expected: 519 passed, 0 failed.

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/observability_cli.py
git commit -m "refactor: migrate observability_cli.py to use cli_output helpers"
```

---

### Final Verification

- [ ] **End-to-end**

```bash
python .opencode/scripts/webnovel.py checkers list
python .opencode/scripts/webnovel.py checkers validate
python .opencode/scripts/run_all_tests.py
```
