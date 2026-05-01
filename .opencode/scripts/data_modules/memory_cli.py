#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory CLI — query and manage memory/scratchpad data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import get_config, DataModulesConfig
from .memory.store import ScratchpadManager
from .cli_output import print_success, print_error, print_info, print_table


def cmd_stats(args: argparse.Namespace) -> int:
    config = _get_config(args.project_root)
    if config is None:
        return 1

    try:
        store = ScratchpadManager(config)
        stats = store.stats()
    except Exception as e:
        print_error("LOAD_FAILED", str(e))
        return 1

    if args.format == "json":
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        headers = ["维度", "值"]
        rows = [
            ["总条目", str(stats.get("total", 0))],
            ["活跃", str(stats.get("active", 0))],
            ["已过期", str(stats.get("outdated", 0))],
            ["矛盾", str(stats.get("contradicted", 0))],
            ["暂定", str(stats.get("tentative", 0))],
        ]
        print_table(headers, rows)
        print_info(f"存储路径: {stats.get('path', '')}")

    return 0


def cmd_query(args: argparse.Namespace) -> int:
    config = _get_config(args.project_root)
    if config is None:
        return 1

    try:
        store = ScratchpadManager(config)
        items = store.query(category=args.category, status=args.status)
    except Exception as e:
        print_error("QUERY_FAILED", str(e))
        return 1

    limited = items[: args.limit]

    if args.format == "json":
        payload = {"items": [item.to_dict() for item in limited], "count": len(limited)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        headers = ["id", "category", "subject", "value", "status", "chapter"]
        rows = []
        for item in limited:
            rows.append([
                item.id[:20],
                item.category,
                item.subject[:15],
                item.value[:20],
                item.status,
                str(item.source_chapter or ""),
            ])
        print_table(headers, rows)
        print_info(f"共 {len(items)} 条（显示前 {min(len(items), args.limit)} 条）")

    return 0


def cmd_conflicts(args: argparse.Namespace) -> int:
    config = _get_config(args.project_root)
    if config is None:
        return 1

    try:
        store = ScratchpadManager(config)
        conflicts = store.conflicts()
    except Exception as e:
        print_error("CONFLICT_FAILED", str(e))
        return 1

    if args.format == "json":
        print(json.dumps(conflicts, ensure_ascii=False, indent=2))
    else:
        if not conflicts:
            print_info("无冲突条目。")
            return 0
        print_table(
            ["category", "key", "active_items"],
            [
                [c.get("category", ""), str(c.get("key", "")), str(c.get("active_items", 0))]
                for c in conflicts
            ],
        )

    return 0


def _get_config(project_root: str | None) -> DataModulesConfig | None:
    try:
        if project_root:
            from project_locator import resolve_project_root
            resolved = resolve_project_root(project_root)
            return DataModulesConfig.from_project_root(resolved)
        return get_config()
    except Exception:
        print_error("NO_PROJECT", "无项目目录")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="记忆数据管理工具")
    parser.add_argument("--project-root", help="项目根目录（默认自动检测）")
    parser.add_argument("--format", "-f", choices=["text", "json"], default="text", help="输出格式")
    sub = parser.add_subparsers(dest="command", required=True)

    p_stats = sub.add_parser("stats", help="记忆数据统计")
    p_stats.set_defaults(func=cmd_stats)

    p_query = sub.add_parser("query", help="查询记忆条目")
    p_query.add_argument("--category", "-c", help="按类别过滤")
    p_query.add_argument("--status", "-s", help="按状态过滤 (active/outdated/contradicted/tentative)")
    p_query.add_argument("--limit", "-l", type=int, default=20, help="最大返回条数")
    p_query.set_defaults(func=cmd_query)

    p_conflicts = sub.add_parser("conflicts", help="查看冲突条目")
    p_conflicts.set_defaults(func=cmd_conflicts)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
