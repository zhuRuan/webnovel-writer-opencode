#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared observability helpers for data modules.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from logger import get_logger
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


logger = get_logger(__name__)


def safe_log_tool_call(
    tool_logger,
    *,
    tool_name: str,
    success: bool,
    retry_count: int = 0,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    chapter: Optional[int] = None,
) -> None:
    try:
        tool_logger.log_tool_call(
            tool_name,
            success,
            retry_count=retry_count,
            error_code=error_code,
            error_message=error_message,
            chapter=chapter,
        )
    except Exception as exc:
        logger.warning(
            "failed to log tool call %s: %s",
            tool_name,
            exc,
        )


def safe_append_perf_timing(
    project_root: str | Path,
    *,
    tool_name: str,
    success: bool,
    elapsed_ms: int,
    chapter: Optional[int] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append timing trace for profiling long-running data-agent pipeline steps.

    Output path:
    - {project_root}/.webnovel/observability/data_agent_timing.jsonl
    """
    try:
        root = Path(project_root).resolve()
        obs_dir = root / ".webnovel" / "observability"
        obs_dir.mkdir(parents=True, exist_ok=True)
        log_path = obs_dir / "data_agent_timing.jsonl"

        payload: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "success": bool(success),
            "elapsed_ms": int(max(0, elapsed_ms)),
        }
        if chapter is not None:
            payload["chapter"] = int(chapter)
        if error_code:
            payload["error_code"] = error_code
        if error_message:
            payload["error_message"] = error_message
        if meta:
            payload["meta"] = meta

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("failed to append perf timing for %s: %s", tool_name, exc)


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
