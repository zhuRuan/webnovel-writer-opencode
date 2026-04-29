#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Observability CLI — report performance timing stats.
"""

import argparse
import sys

from .cli_output import print_success, print_error, print_info, print_table
from .config import get_config
from .observability import read_perf_timings, compute_stats, format_perf_report


def cmd_report(args: argparse.Namespace) -> int:
    """Generate performance report."""
    from pathlib import Path
    try:
        config = get_config(Path(args.project_root) if args.project_root else None)
        project_root = str(config.project_root)
    except Exception:
        print_error("NO_PROJECT", "无项目目录，无法读取观测数据。")
        return 1

    timings = read_perf_timings(
        project_root,
        tool_name=args.tool,
        limit=args.last,
    )

    if not timings:
        print_info("无观测数据。请先运行一些上下文构建或状态保存操作。")
        return 0

    stats = compute_stats(timings)
    print(format_perf_report(stats, fmt=args.format))
    return 0


def cmd_token_report(args: argparse.Namespace) -> int:
    """Show per-chapter token consumption."""
    from pathlib import Path
    try:
        config = get_config(Path(args.project_root) if args.project_root else None)
        project_root = str(config.project_root)
    except Exception:
        print_error("NO_PROJECT", "无项目目录，无法读取观测数据。")
        return 1

    timings = read_perf_timings(
        project_root,
        tool_name="context_manager.build_context",
        limit=args.last,
    )

    if not timings:
        print_info("无上下文构建记录。")
        return 0

    chapters: dict[int, int] = {}
    for t in timings:
        meta = t.get("meta", {})
        ch = meta.get("chapter")
        tokens = meta.get("estimated_tokens")
        if ch is not None and tokens is not None:
            if ch not in chapters:
                chapters[ch] = tokens

    if not chapters:
        print_info("无 Token 估算数据（需要更新后的 ContextManager 生成的数据）。")
        return 0

    if args.format == "json":
        import json as _json
        print(_json.dumps(chapters, ensure_ascii=False, indent=2))
    else:
        headers = ["章节", "Tokens"]
        rows = [[f"第{ch}章", str(t)] for ch, t in sorted(chapters.items())]
        total = sum(chapters.values())
        avg = total // len(chapters)
        print_table(headers, rows)
        print_info(f"总计: {total} tokens  平均: {avg} tokens/章")

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

    p_token = sub.add_parser("token-report", help="查看 Token 消耗报告")
    p_token.add_argument("--last", "-n", type=int, default=1000, help="最近 N 条记录")
    p_token.add_argument("--format", "-f", choices=["text", "json"], default="text", help="输出格式")
    p_token.set_defaults(func=cmd_token_report)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
