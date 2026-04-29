#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查器 CLI 命令

从 checkers_manager.py 拆分出来的 CLI 入口。
"""

import argparse
import json
import sys

from .checkers_manager import CheckersManager
from .cli_output import print_success, print_error, print_warning, print_info, print_table
from .exceptions import ConfigError


def cmd_list(args: argparse.Namespace) -> int:
    """列出审查器命令"""
    manager = CheckersManager()

    try:
        checkers = manager.list_checkers(
            mode=args.mode,
            category=args.category,
            enabled_only=not args.all,
            format=args.format,
        )
    except ConfigError as e:
        print_error("CONFIG_ERROR", str(e))
        return 1

    if args.format == "json":
        print(json.dumps(checkers, ensure_ascii=False, indent=2))
    else:
        headers = ["状态", "类别", "审查器", "触发条件"]
        rows = []
        for checker in checkers:
            enabled = "✓" if checker["enabled"] else "✗"
            category = "[核心]" if checker["category"] == "core" else "[条件]"
            triggers = checker.get("triggers", [])
            trigger_desc = ""
            if triggers:
                parts = []
                for t in triggers[:2]:
                    if isinstance(t, dict):
                        expr = t.get("expression") or t.get("keywords", "(条件)")
                        if isinstance(expr, list):
                            expr = ", ".join(expr[:2])
                        parts.append(str(expr))
                    else:
                        parts.append(str(t))
                trigger_desc = "; ".join(parts)
            rows.append([enabled, category, f"{checker['id']}: {checker['name']}", trigger_desc])
        print_table(headers, rows)

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """验证配置命令"""
    manager = CheckersManager()

    result = manager.validate()

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["valid"]:
            print_success(message="配置验证通过")
        else:
            print_error("VALIDATE_FAIL", "配置验证失败")

        if result["errors"]:
            for error in result["errors"]:
                print_error("CONFIG_ERROR", error)

        if result["warnings"]:
            for warning in result["warnings"]:
                print_warning(warning)

        print_info(f"审查器: {result.get('checker_count', 0)}个, 模式: {result.get('mode_count', 0)}个")

    return 0 if result["valid"] else 1


def cmd_create(args: argparse.Namespace) -> int:
    """创建审查器命令"""
    manager = CheckersManager()

    triggers = args.triggers.split(",") if args.triggers else []

    result = manager.create_checker(
        checker_id=args.id,
        name=args.name,
        category=args.category,
        description=args.description or "",
        triggers=triggers,
    )

    if result["success"]:
        print_success(message=f"审查器创建成功: {args.id}")
    else:
        print_error("CREATE_FAILED", result.get('error', '未知错误'))
        return 1

    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    """获取 Schema 命令"""
    manager = CheckersManager()

    schema = manager.get_schema_for_checker(args.checker)
    if schema:
        print(json.dumps(schema, ensure_ascii=False, indent=2))
    else:
        print_error("NOT_FOUND", f"未找到审查器 {args.checker} 的 Schema")
        return 1

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="审查器配置管理工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出审查器")
    p_list.add_argument("--mode", "-m", choices=["standard", "minimal", "full", "unified_review"], help="审查模式")
    p_list.add_argument("--category", "-c", choices=["core", "conditional"], help="类别")
    p_list.add_argument("--all", "-a", action="store_true", help="显示所有（包括禁用的）")
    p_list.add_argument("--format", "-f", choices=["text", "json"], default="text", help="输出格式")
    p_list.set_defaults(func=cmd_list)

    p_validate = sub.add_parser("validate", help="验证配置")
    p_validate.add_argument("--format", "-f", choices=["text", "json"], default="text", help="输出格式")
    p_validate.set_defaults(func=cmd_validate)

    p_create = sub.add_parser("create", help="创建新审查器")
    p_create.add_argument("--id", "-i", required=True, help="审查器 ID")
    p_create.add_argument("--name", "-n", required=True, help="审查器名称")
    p_create.add_argument("--category", choices=["core", "conditional"], default="core", help="类别")
    p_create.add_argument("--description", "-d", default="", help="描述")
    p_create.add_argument("--triggers", "-t", default="", help="触发条件（逗号分隔）")
    p_create.set_defaults(func=cmd_create)

    p_schema = sub.add_parser("schema", help="获取审查器 Schema")
    p_schema.add_argument("checker", help="审查器 ID")
    p_schema.set_defaults(func=cmd_schema)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
