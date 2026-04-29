# CLI Output Enhancement — Design Spec

Date: 2026-04-29  
Status: approved  
Scope: Enhance cli_output.py with color support and text/json dual mode, migrate all CLI commands  

## Overview

Upgrade the CLI output system to support human-readable colored text output alongside the existing JSON format. Add cross-platform color support via colorama. Add new output helpers (print_warning, print_info, print_table). Migrate all CLI command modules to use the unified output format.

## Dependency

Add `colorama>=0.4.6` to `requirements.txt` for cross-platform ANSI color support on Windows/Linux/Mac.

## Change 1: Enhance cli_output.py

**File:** `.opencode/scripts/data_modules/cli_output.py`

Add a global format setting and color support:

```python
import colorama
from colorama import Fore, Style
```

On init, call `colorama.init()` for Windows compatibility.

### New output functions

```python
def set_output_format(fmt: str) -> None:
    """Set global output format: text | json"""

def print_info(message: str, *, format: Optional[str] = None) -> None:
    """ℹ️ Blue text in text mode, JSON in json mode."""

def print_warning(message: str, *, format: Optional[str] = None) -> None:
    """⚠️ Yellow text in text mode, JSON in json mode."""

def print_success(data=None, message="ok", *, format=None) -> None:
    """✅ Green text in text mode, existing JSON in json mode."""

def print_error(code, message, suggestion=None, *, format=None) -> None:
    """❌ Red text in text mode, existing JSON in json mode."""

def print_table(headers, rows, *, format=None) -> None:
    """Text table in text mode, JSON array in json mode."""
```

Color mapping:
- `print_info` → `Fore.CYAN + message`
- `print_warning` → `Fore.YELLOW + "⚠ " + message`
- `print_success` → `Fore.GREEN + "✓ " + message` (text) or existing JSON (json)
- `print_error` → `Fore.RED + "✗ " + code + ": " + message` (text) or existing JSON (json)
- `print_table` → padded columns with header underline (text) or JSON array (json)

The existing `build_success`/`build_error`/`print_json` remain unchanged for backward compatibility.

## Change 2: Migrate CLI command modules

**Primary targets (use direct print() today):**
- `checkers_cli.py` — cmd_list, cmd_validate, cmd_create, cmd_schema
- `observability_cli.py` — cmd_report, cmd_token_report

**Secondary targets (already use cli_output but not consistently):**
- `state_manager.py`, `rag_adapter.py`, `index_manager.py`, `entity_linker.py`, `context_manager.py`
  — These already call `print_success`/`print_error`, so they benefit automatically from the text mode upgrade.

**Migration rule:**
- All output to stdout → use `print_success`/`print_info`/`print_error`/`print_warning`/`print_table`
- Error messages to stderr → use `print_error`

## Change 3: Update requirements.txt

Add: `colorama>=0.4.6`

## Non-Goals

- No progress bars (can be added later with `tqdm` if needed)
- No terminal width auto-detection
- No `--format` flag added to commands that don't already have one (the global format is set by config/environment)
- No rich text markup or markdown rendering

## Verification

```bash
# Visual inspection of colored output
python .opencode/scripts/webnovel.py checkers list
python .opencode/scripts/webnovel.py observability report

# JSON mode still works (some commands use --format json)
python .opencode/scripts/webnovel.py checkers list --format json
python .opencode/scripts/webnovel.py observability report --format json

# Full test suite
python .opencode/scripts/run_all_tests.py
```
