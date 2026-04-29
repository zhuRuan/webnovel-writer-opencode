# Observability Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add performance timing aggregation and CLI report command to the observability system.

**Architecture:** Three tasks. Task 1 adds read/stats/format functions to `observability.py`. Task 2 creates `observability_cli.py` with `main()`. Task 3 registers the command in `webnovel.py`.

**Tech Stack:** Python 3.10+, json, statistics (stdlib)

---

### Task 1: Add aggregation functions to observability.py

**Files:**
- Modify: `.opencode/scripts/data_modules/observability.py`

- [ ] **Step 1: Add imports at the top of observability.py**

After the existing imports (around line 13), add:
```python
import statistics
from collections import defaultdict
```

- [ ] **Step 2: Add read_perf_timings function**

Append after the existing `safe_append_perf_timing` function (end of file):

```python
def read_perf_timings(
    project_root: str | Path,
    tool_name: Optional[str] = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Read JSONL timing data. Newest first. Filter by tool_name if given."""
    root = Path(project_root).resolve()
    log_path = root / ".webnovel" / "observability" / "data_agent_timing.jsonl"
    if not log_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if tool_name and entry.get("tool_name") != tool_name:
                    continue
                entries.append(entry)
    except OSError:
        return []
    entries.reverse()
    return entries[:limit]


def compute_stats(timings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group timings by tool_name, compute per-tool aggregate stats."""
    by_tool: dict[str, list[dict]] = defaultdict(list)
    for t in timings:
        by_tool[t.get("tool_name", "unknown")].append(t)

    result: dict[str, dict[str, Any]] = {}
    for tool, entries in by_tool.items():
        elapsed = [e["elapsed_ms"] for e in entries if "elapsed_ms" in e]
        errors = [e for e in entries if not e.get("success", True)]
        sorted_elapsed = sorted(elapsed) if elapsed else []

        def _percentile(data: list[int], p: float) -> int:
            if not data:
                return 0
            k = (len(data) - 1) * (p / 100)
            f = int(k)
            c = min(f + 1, len(data) - 1)
            d = k - f
            return int(data[f] + d * (data[c] - data[f]))

        result[tool] = {
            "count": len(entries),
            "avg_ms": int(statistics.mean(elapsed)) if elapsed else 0,
            "min_ms": min(elapsed) if elapsed else 0,
            "max_ms": max(elapsed) if elapsed else 0,
            "p50_ms": _percentile(sorted_elapsed, 50),
            "p95_ms": _percentile(sorted_elapsed, 95),
            "p99_ms": _percentile(sorted_elapsed, 99),
            "error_count": len(errors),
            "error_rate": round(len(errors) / len(entries), 3) if entries else 0.0,
            "last_run": entries[0].get("timestamp", "") if entries else "",
        }
    return result


def format_perf_report(stats: dict[str, dict], fmt: str = "text") -> str:
    """Format stats as text table or JSON."""
    if fmt == "json":
        return json.dumps(stats, ensure_ascii=False, indent=2)

    if not stats:
        return "无观测数据。"

    lines = ["工具统计:"]
    for tool, s in stats.items():
        line = (
            f"  {tool:<40s} "
            f"count={s['count']:>4d}  "
            f"avg={s['avg_ms']:>5d}ms  "
            f"p95={s['p95_ms']:>5d}ms  "
            f"errors={s['error_count']}"
        )
        if s.get("last_run"):
            line += f"  last={s['last_run'][:19]}"
        lines.append(line)
    return "\n".join(lines)
```

- [ ] **Step 3: Verify functions load without error**

```bash
python -c "from data_modules.observability import read_perf_timings, compute_stats, format_perf_report; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add .opencode/scripts/data_modules/observability.py
git commit -m "feat: add read_perf_timings, compute_stats, format_perf_report to observability"
```

---

### Task 2: Create observability_cli.py

**Files:**
- Create: `.opencode/scripts/data_modules/observability_cli.py`

- [ ] **Step 1: Write the file**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Observability CLI — report performance timing stats.
"""

import argparse
import json
import sys

from .config import get_config
from .observability import read_perf_timings, compute_stats, format_perf_report


def cmd_report(args: argparse.Namespace) -> int:
    """Generate performance report."""
    config = get_config()
    project_root = args.project_root or str(config.project_root)

    timings = read_perf_timings(
        project_root,
        tool_name=args.tool,
        limit=args.last,
    )

    if not timings:
        print("无观测数据。请先运行一些上下文构建或状态保存操作。")
        return 0

    stats = compute_stats(timings)
    print(format_perf_report(stats, fmt=args.format))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="观测数据报告工具")
    parser.add_argument("--project-root", help="项目根目录（默认自动检测）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="生成性能报告")
    p_report.add_argument("--tool", "-t", help="过滤指定 tool_name")
    p_report.add_argument("--last", "-n", type=int, default=1000, help="最近 N 条记录（默认 1000）")
    p_report.add_argument("--format", "-f", choices=["text", "json"], default="text", help="输出格式")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the module loads**

```bash
python -c "from data_modules.observability_cli import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .opencode/scripts/data_modules/observability_cli.py
git commit -m "feat: add observability_cli with report command"
```

---

### Task 3: Register COMMAND_REGISTRY entry in webnovel.py

**Files:**
- Modify: `.opencode/scripts/data_modules/webnovel.py`

- [ ] **Step 1: Add registry entry**

After the existing `checkers` entry (around line 49), add:
```python
    "observability": {"type": "data_module", "target": "observability_cli", "needs_root": True},
```

- [ ] **Step 2: Add argparse sub-parser**

After the checkers sub-parser block (around line 372), add:
```python
    # observability 命令
    p_obs = sub.add_parser("observability", help="观测数据报告")
    p_obs.add_argument("args", nargs=argparse.REMAINDER)
```

- [ ] **Step 3: Verify CLI works**

```bash
python .opencode/scripts/webnovel.py observability report
```

Expected: prints "无观测数据。" or shows stats if timing data exists.

```bash
python .opencode/scripts/webnovel.py observability report --format json
```

Expected: valid JSON output.

- [ ] **Step 4: Run full test suite**

```bash
python .opencode/scripts/run_all_tests.py 2>&1 | Select-Object -Last 5
```

Expected: 493 passed, 12 failed (unchanged).

- [ ] **Step 5: Commit**

```bash
git add .opencode/scripts/data_modules/webnovel.py
git commit -m "feat: register observability command in COMMAND_REGISTRY"
```

---

### Final Verification

- [ ] **End-to-end test**

```bash
# Generate some timing data
python .opencode/scripts/webnovel.py observability report --format text
```

Expected: Output shows tool stats or "无观测数据" message.
