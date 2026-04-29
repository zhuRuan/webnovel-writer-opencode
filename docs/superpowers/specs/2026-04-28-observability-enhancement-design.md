# Observability Enhancement — Design Spec

Date: 2026-04-28  
Status: approved  
Scope: Add aggregation functions and CLI report command for performance timing data  

## Overview

Enhance the observability system to aggregate and report performance timing data. Currently the system writes raw JSONL traces but has no way to analyze them. Add aggregation methods to `observability.py` and a CLI command `observability report`.

## Change 1: Add aggregation functions to observability.py

**File:** `.opencode/scripts/data_modules/observability.py`

Add two new functions:

```python
def read_perf_timings(
    project_root: str | Path,
    tool_name: Optional[str] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Read JSONL timing data, return list of dicts (newest first).
    If tool_name is given, filter to that tool only.
    """
```

```python
def compute_stats(timings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Group timings by tool_name, compute per-tool stats:
    - count
    - avg_ms
    - min_ms / max_ms
    - p50, p95, p99 (percentiles)
    - error_count / error_rate
    - last_run (ISO timestamp of most recent entry)
    """
```

**Design note:** `compute_stats` is a pure function — no I/O, operates on the list returned by `read_perf_timings`. This makes it testable and reusable.

The report format function:

```python
def format_perf_report(stats: Dict[str, Dict], format: str = "text") -> str:
    """Format stats dict as text table or JSON string."""
```

## Change 2: Create observability_cli.py

**File:** Create `.opencode/scripts/data_modules/observability_cli.py`

CLI command: `python webnovel.py observability report [--tool NAME] [--last N] [--format text|json]`

- `--tool` — filter to a specific tool_name (e.g., `context_manager.build_context`)
- `--last N` — limit to most recent N entries (default: 1000)
- `--format` — `text` (default) or `json`

Structure follows the `checkers_cli.py` pattern: imports from `observability.py`, has `main()` function.

## Change 3: Register COMMAND_REGISTRY entry

**File:** `.opencode/scripts/data_modules/webnovel.py`

Add entry:
```python
"observability": {"type": "data_module", "target": "observability_cli", "needs_root": True},
```

Also add argparse sub-parser for `observability` with `report` sub-command.

## Non-Goals

- No real-time streaming or dashboard integration
- No Token tracking (separate iteration)
- No cache hit rate tracking (separate iteration)
- No changes to existing `safe_append_perf_timing` callers

## Verification

```bash
# Generate some timing data by running context operations
python .opencode/scripts/webnovel.py observability report --format text
python .opencode/scripts/webnovel.py observability report --tool context_manager.build_context --last 10 --format json
python -m pytest .opencode/scripts/data_modules/tests/test_observability.py -v  # if test exists
```
