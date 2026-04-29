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
