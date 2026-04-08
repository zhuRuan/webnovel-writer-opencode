#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webnovel 统一入口（面向 skills / agents 的稳定 CLI）

设计目标：
- 只有一个入口命令，避免到处拼 `python -m data_modules.xxx ...` 导致参数位置/引号/路径炸裂。
- 自动解析正确的 book project_root（包含 `.webnovel/state.json` 的目录）。
- 所有写入类命令在解析到 project_root 后，统一前置 `--project-root` 传给具体模块。

典型用法（推荐，不依赖 PYTHONPATH / 不要求 cd）：
  python "<SCRIPTS_DIR>/webnovel.py" preflight
  python "<SCRIPTS_DIR>/webnovel.py" where
  python "<SCRIPTS_DIR>/webnovel.py" use D:\\wk\\xiaoshuo\\凡人资本论
  python "<SCRIPTS_DIR>/webnovel.py" --project-root D:\\wk\\xiaoshuo index stats
  python "<SCRIPTS_DIR>/webnovel.py" --project-root D:\\wk\\xiaoshuo state process-chapter --chapter 100 --data @payload.json
  python "<SCRIPTS_DIR>/webnovel.py" --project-root D:\\wk\\xiaoshuo extract-context --chapter 100 --format json

也支持（不推荐，容易踩 PYTHONPATH/cd/参数顺序坑）：
  python -m data_modules.webnovel where
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from runtime_compat import normalize_windows_path
from project_locator import resolve_project_root, write_current_project_pointer, update_global_registry_current_project
from logger import get_logger, setup_logging


def _scripts_dir() -> Path:
    # data_modules/webnovel.py -> data_modules -> scripts
    return Path(__file__).resolve().parent.parent


def _resolve_root(explicit_project_root: Optional[str]) -> Path:
    # 允许显式传入工作区根目录或书项目根目录
    raw = explicit_project_root
    if raw:
        return resolve_project_root(raw)
    return resolve_project_root()


def _strip_project_root_args(argv: list[str]) -> list[str]:
    """
    下游工具统一由本入口注入 `--project-root`，避免重复传参导致 argparse 报错/歧义。
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--project-root":
            i += 2
            continue
        if tok.startswith("--project-root="):
            i += 1
            continue
        out.append(tok)
        i += 1
    return out


def _run_data_module(module: str, argv: list[str]) -> int:
    """
    Import `data_modules.<module>` and call its main(), while isolating sys.argv.
    """
    mod = importlib.import_module(f"data_modules.{module}")
    main = getattr(mod, "main", None)
    if not callable(main):
        raise RuntimeError(f"data_modules.{module} 缺少可调用的 main()")

    old_argv = sys.argv
    try:
        sys.argv = [f"data_modules.{module}"] + argv
        try:
            main()
            return 0
        except SystemExit as e:
            return int(e.code or 0)
    finally:
        sys.argv = old_argv


def _run_script(script_name: str, argv: list[str]) -> int:
    """
    Run a script under `.claude/scripts/` via a subprocess.

    用途：兼容没有 main() 的脚本（例如 workflow_manager.py）。
    """
    script_path = _scripts_dir() / script_name
    if not script_path.is_file():
        raise FileNotFoundError(f"未找到脚本: {script_path}")
    proc = subprocess.run([sys.executable, str(script_path), *argv])
    return int(proc.returncode or 0)


def cmd_where(args: argparse.Namespace) -> int:
    root = _resolve_root(args.project_root)
    print(str(root))
    return 0


def _build_preflight_report(explicit_project_root: Optional[str]) -> dict:
    scripts_dir = _scripts_dir().resolve()
    plugin_root = scripts_dir.parent
    skill_root = plugin_root / "skills" / "webnovel-write"
    entry_script = scripts_dir / "webnovel.py"
    extract_script = scripts_dir / "extract_chapter_context.py"

    checks: list[dict[str, object]] = [
        {"name": "scripts_dir", "ok": scripts_dir.is_dir(), "path": str(scripts_dir)},
        {"name": "entry_script", "ok": entry_script.is_file(), "path": str(entry_script)},
        {"name": "extract_context_script", "ok": extract_script.is_file(), "path": str(extract_script)},
        {"name": "skill_root", "ok": skill_root.is_dir(), "path": str(skill_root)},
    ]

    project_root = ""
    project_root_error = ""
    try:
        resolved_root = _resolve_root(explicit_project_root)
        project_root = str(resolved_root)
        checks.append({"name": "project_root", "ok": True, "path": project_root})
    except Exception as exc:
        project_root_error = str(exc)
        checks.append({"name": "project_root", "ok": False, "path": explicit_project_root or "", "error": project_root_error})

    return {
        "ok": all(bool(item["ok"]) for item in checks),
        "project_root": project_root,
        "scripts_dir": str(scripts_dir),
        "skill_root": str(skill_root),
        "checks": checks,
        "project_root_error": project_root_error,
    }


def cmd_preflight(args: argparse.Namespace) -> int:
    report = _build_preflight_report(args.project_root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["checks"]:
            status = "OK" if item["ok"] else "ERROR"
            path = item.get("path") or ""
            print(f"{status} {item['name']}: {path}")
            if item.get("error"):
                print(f"  detail: {item['error']}")
    return 0 if report["ok"] else 1


def cmd_use(args: argparse.Namespace) -> int:
    project_root = normalize_windows_path(args.project_root).expanduser()
    try:
        project_root = project_root.resolve()
    except Exception:
        project_root = project_root

    workspace_root: Optional[Path] = None
    if args.workspace_root:
        workspace_root = normalize_windows_path(args.workspace_root).expanduser()
        try:
            workspace_root = workspace_root.resolve()
        except Exception:
            workspace_root = workspace_root

    # 1) 写入工作区指针（若工作区内存在 `.claude/`）
    pointer_file = write_current_project_pointer(project_root, workspace_root=workspace_root)
    if pointer_file is not None:
        print(f"workspace pointer: {pointer_file}")
    else:
        print("workspace pointer: (skipped)")

    # 2) 写入用户级 registry（保证全局安装/空上下文可恢复）
    reg_path = update_global_registry_current_project(workspace_root=workspace_root, project_root=project_root)
    if reg_path is not None:
        print(f"global registry: {reg_path}")
    else:
        print("global registry: (skipped)")

    return 0


def main() -> None:
    setup_logging()
    logger = get_logger(__name__)
    parser = argparse.ArgumentParser(description="webnovel unified CLI")
    parser.add_argument("--project-root", help="书项目根目录或工作区根目录（可选，默认自动检测）")

    sub = parser.add_subparsers(dest="tool", required=True)

    p_where = sub.add_parser("where", help="打印解析出的 project_root")
    p_where.set_defaults(func=cmd_where)

    p_preflight = sub.add_parser("preflight", help="校验统一 CLI 运行环境与 project_root")
    p_preflight.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_preflight.set_defaults(func=cmd_preflight)

    p_use = sub.add_parser("use", help="绑定当前工作区使用的书项目（写入指针/registry）")
    p_use.add_argument("project_root", help="书项目根目录（必须包含 .webnovel/state.json）")
    p_use.add_argument("--workspace-root", help="工作区根目录（可选；默认由运行环境推断）")
    p_use.set_defaults(func=cmd_use)

    # Pass-through to data modules
    p_index = sub.add_parser("index", help="转发到 index_manager")
    p_index.add_argument("args", nargs=argparse.REMAINDER)

    p_state = sub.add_parser("state", help="转发到 state_manager")
    p_state.add_argument("args", nargs=argparse.REMAINDER)

    p_rag = sub.add_parser("rag", help="转发到 rag_adapter")
    p_rag.add_argument("args", nargs=argparse.REMAINDER)

    p_style = sub.add_parser("style", help="转发到 style_sampler")
    p_style.add_argument("args", nargs=argparse.REMAINDER)

    p_entity = sub.add_parser("entity", help="转发到 entity_linker")
    p_entity.add_argument("args", nargs=argparse.REMAINDER)

    p_context = sub.add_parser("context", help="转发到 context_manager")
    p_context.add_argument("args", nargs=argparse.REMAINDER)

    p_migrate = sub.add_parser("migrate", help="转发到 migrate_state_to_sqlite")
    p_migrate.add_argument("args", nargs=argparse.REMAINDER)

    # checkers 子命令（审查器配置管理）
    p_checkers = sub.add_parser("checkers", help="审查器配置管理")
    p_checkers.add_argument("args", nargs=argparse.REMAINDER)

    # Pass-through to scripts
    p_workflow = sub.add_parser("workflow", help="转发到 workflow_manager.py")
    p_workflow.add_argument("args", nargs=argparse.REMAINDER)

    p_status = sub.add_parser("status", help="转发到 status_reporter.py")
    p_status.add_argument("args", nargs=argparse.REMAINDER)

    p_update_state = sub.add_parser("update-state", help="转发到 update_state.py")
    p_update_state.add_argument("args", nargs=argparse.REMAINDER)

    p_backup = sub.add_parser("backup", help="转发到 backup_manager.py")
    p_backup.add_argument("args", nargs=argparse.REMAINDER)

    p_archive = sub.add_parser("archive", help="转发到 archive_manager.py")
    p_archive.add_argument("args", nargs=argparse.REMAINDER)

    p_init = sub.add_parser("init", help="转发到 init_project.py（初始化项目）")
    p_init.add_argument("args", nargs=argparse.REMAINDER)

    p_extract_context = sub.add_parser("extract-context", help="转发到 extract_chapter_context.py")
    p_extract_context.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_extract_context.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")

    # export 命令（正文导出）
    p_export = sub.add_parser("export", help="正文导出工具")
    p_export.add_argument("args", nargs=argparse.REMAINDER)

    # publish 命令（番茄小说发布）
    p_publish = sub.add_parser("publish", help="番茄小说发布工具")
    p_publish.add_argument("args", nargs=argparse.REMAINDER)

    # dashboard 命令（可视化面板）
    p_dashboard = sub.add_parser("dashboard", help="启动可视化小说管理面板（只读 Web Dashboard）")
    p_dashboard.add_argument("--host", default="127.0.0.1", help="监听地址")
    p_dashboard.add_argument("--port", type=int, default=8765, help="监听端口")
    p_dashboard.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")

    # rule 命令（世界规则管理）
    p_rule = sub.add_parser("rule", help="世界规则管理")
    p_rule.add_argument("args", nargs=argparse.REMAINDER)

    # character 命令（角色状态管理）
    p_character = sub.add_parser("character", help="角色状态管理")
    p_character.add_argument("args", nargs=argparse.REMAINDER)

    # plot 命令（情节图谱管理）
    p_plot = sub.add_parser("plot", help="情节图谱与因果链管理")
    p_plot.add_argument("args", nargs=argparse.REMAINDER)

    # 兼容：允许 `--project-root` 出现在任意位置（减少 agents/skills 拼命令的出错率）
    from .cli_args import normalize_global_project_root

    argv = normalize_global_project_root(sys.argv[1:])
    args = parser.parse_args(argv)

    # where/use 直接执行
    if hasattr(args, "func"):
        code = int(args.func(args) or 0)
        raise SystemExit(code)

    tool = args.tool
    rest = list(getattr(args, "args", []) or [])
    # argparse.REMAINDER 可能以 `--` 开头占位，这里去掉
    if rest[:1] == ["--"]:
        rest = rest[1:]
    rest = _strip_project_root_args(rest)

    # init 是创建项目，不应该依赖/注入已存在 project_root
    if tool == "init":
        raise SystemExit(_run_script("init_project.py", rest))

    # checkers 是审查器配置管理，不需要 project_root
    if tool == "checkers":
        raise SystemExit(_run_data_module("checkers_manager", rest))

    # publish 命令中，setup-browser 不需要 project_root，其他命令需要
    if tool == "publish":
        if rest and rest[0] == "setup-browser":
            raise SystemExit(_run_script("publish_manager.py", rest))
        # 其他 publish 子命令需要 project_root

    # 其余工具：统一解析 project_root 后前置给下游
    project_root = _resolve_root(args.project_root)
    forward_args = ["--project-root", str(project_root)]

    if tool == "index":
        raise SystemExit(_run_data_module("index_manager", [*forward_args, *rest]))
    if tool == "state":
        raise SystemExit(_run_data_module("state_manager", [*forward_args, *rest]))
    if tool == "rag":
        raise SystemExit(_run_data_module("rag_adapter", [*forward_args, *rest]))
    if tool == "style":
        raise SystemExit(_run_data_module("style_sampler", [*forward_args, *rest]))
    if tool == "entity":
        raise SystemExit(_run_data_module("entity_linker", [*forward_args, *rest]))
    if tool == "context":
        raise SystemExit(_run_data_module("context_manager", [*forward_args, *rest]))
    if tool == "migrate":
        raise SystemExit(_run_data_module("migrate_state_to_sqlite", [*forward_args, *rest]))
    if tool == "checkers":
        raise SystemExit(_run_data_module("checkers_manager", rest))

    if tool == "workflow":
        raise SystemExit(_run_script("workflow_manager.py", [*forward_args, *rest]))
    if tool == "status":
        raise SystemExit(_run_script("status_reporter.py", [*forward_args, *rest]))
    if tool == "update-state":
        raise SystemExit(_run_script("update_state.py", [*forward_args, *rest]))
    if tool == "backup":
        raise SystemExit(_run_script("backup_manager.py", [*forward_args, *rest]))
    if tool == "archive":
        raise SystemExit(_run_script("archive_manager.py", [*forward_args, *rest]))
    if tool == "extract-context":
        return_args = [*forward_args, "--chapter", str(args.chapter), "--format", str(args.format)]
        raise SystemExit(_run_script("extract_chapter_context.py", return_args))

    if tool == "export":
        raise SystemExit(_run_script("export_manager.py", [*forward_args, *rest]))

    if tool == "publish":
        raise SystemExit(_run_script("publish_manager.py", [*forward_args, *rest]))

    # rule 命令（世界规则管理）
    if tool == "rule":
        from .cli_output import print_foreshadowing_warning
        from .state_manager import StateManager
        from .config import get_config

        config = get_config(project_root=str(project_root))
        state_manager = StateManager(config)

        # 解析 rule 子命令
        if not rest:
            print("用法: webnovel rule list|get <key>|set <key> <value>")
            raise SystemExit(0)

        subcmd = rest[0]
        if subcmd == "list":
            world_rules = state_manager.get_world_rules()
            if not world_rules:
                print("世界规则为空")
                raise SystemExit(0)
            import json
            print(json.dumps(world_rules, ensure_ascii=False, indent=2))
            raise SystemExit(0)
        elif subcmd == "get":
            if len(rest) < 2:
                print("用法: webnovel rule get <key>")
                raise SystemExit(1)
            key = rest[1]
            value = state_manager.get_world_rule(key)
            print(value or f"未找到规则: {key}")
            raise SystemExit(0)
        elif subcmd == "set":
            if len(rest) < 3:
                print("用法: webnovel rule set <key> <value>")
                raise SystemExit(1)
            key = rest[1]
            value = " ".join(rest[2:])
            state_manager.set_world_rule(key, value)
            print(f"已设置: {key} = {value}")
            raise SystemExit(0)
        elif subcmd == "foreshadowing-warn":
            # 手动触发伏笔警告（供调试）
            current_chapter = state_manager.get_current_chapter()
            threshold = config.foreshadowing_stale_threshold
            overdue = state_manager.get_overdue_foreshadowing(current_chapter, threshold)
            mode = config.foreshadowing_warning_mode
            print_foreshadowing_warning(overdue, mode)
            raise SystemExit(0)
        elif subcmd == "check":
            if len(rest) < 2:
                print("用法: webnovel rule check --chapter <章节号>")
                raise SystemExit(1)
            if rest[1] != "--chapter" or len(rest) < 3:
                print("用法: webnovel rule check --chapter <章节号>")
                raise SystemExit(1)
            chapter = int(rest[2])
            from .chapter_paths import find_chapter_file
            chapter_file = find_chapter_file(project_root, chapter)
            if not chapter_file or not chapter_file.exists():
                print(f"章节文件不存在: 第{chapter}章")
                raise SystemExit(1)
            chapter_text = chapter_file.read_text(encoding="utf-8")
            from .rule_checker_utils import check_chapter_rules
            result = check_chapter_rules(chapter_text, str(project_root))
            import json
            if result["overall_pass"]:
                print("✅ 规则检查通过，未发现问题。")
            else:
                print("❌ 发现以下问题：")
                for issue in result["issues"]:
                    print(f"  - [{issue['severity']}] {issue['detail']}")
                if result["warnings"]:
                    print("\n⚠️ 以下为警告：")
                    for warn in result["warnings"]:
                        print(f"  - {warn['detail']}")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0)

        elif subcmd == "usage-report":
            chapters = 10
            threshold = 0
            args_iter = iter(rest[1:])
            for arg in args_iter:
                if arg == "--chapters" or arg == "-n":
                    try:
                        chapters = int(next(args_iter))
                    except StopIteration:
                        pass
                elif arg == "--threshold" or arg == "-t":
                    try:
                        threshold = int(next(args_iter))
                    except StopIteration:
                        pass

            from .chapter_paths import find_chapter_file
            max_chapter = 0
            for f in project_root.glob("第*章.md"):
                import re
                m = re.search(r"(\d+)", f.stem)
                if m:
                    max_chapter = max(max_chapter, int(m.group(1)))
            if not max_chapter:
                for f in project_root.glob("chapter_*.md"):
                    import re
                    m = re.search(r"(\d+)", f.stem)
                    if m:
                        max_chapter = max(max_chapter, int(m.group(1)))

            if max_chapter == 0:
                print("❌ 未找到章节文件")
                raise SystemExit(1)

            start = max(1, max_chapter - chapters + 1)
            end = max_chapter
            print(f"📊 扫描第 {start} 章 至 第 {end} 章...")

            usage = state_manager.scan_rule_usage(start, end)
            unused = []
            used = []

            for key, data in sorted(usage.items()):
                count = data["count"]
                chs = data["chapters"]
                if count <= threshold:
                    unused.append((key, count, chs))
                else:
                    used.append((key, count, chs))

            print("\n📈 世界规则使用报告")
            print(f"扫描范围: 第 {start} 章 ~ 第 {end} 章（共 {chapters} 章）\n")

            if used:
                print("✅ 已使用的规则:")
                for key, count, chs in used:
                    chs_str = ", ".join(str(c) for c in chs) if chs else "无"
                    print(f"  • {key}: 出现 {count} 次 (章节: {chs_str})")
            else:
                print("ℹ️ 暂无使用的规则")

            if unused:
                print("\n⚠️ 以下规则使用较少或未使用:")
                for key, count, chs in unused:
                    chs_str = ", ".join(str(c) for c in chs) if chs else "无"
                    print(f"  • {key}: 出现 {count} 次 (章节: {chs_str})")
                print(f"\n（共 {len(unused)} 条规则需要关注）")
            raise SystemExit(0)

        else:
            print(f"未知子命令: {subcmd}")
            print("可用: list, get <key>, set <key> <value>, foreshadowing-warn, check --chapter <N>, usage-report")
            raise SystemExit(1)

    # character 命令（角色状态管理）
    if tool == "character":
        from .state_manager import StateManager
        from .config import get_config

        config = get_config(project_root=str(project_root))
        sm = StateManager(config)

        if not rest:
            chars = sm.list_characters_with_dynamic_state()
            import json
            print(json.dumps(chars, ensure_ascii=False, indent=2))
            raise SystemExit(0)

        subcmd = rest[0]
        if subcmd == "set-state":
            if len(rest) < 4:
                print("用法: webnovel character set-state <角色ID> <属性名> <值>")
                raise SystemExit(1)
            entity_id = rest[1]
            key = rest[2]
            value = " ".join(rest[3:])
            sm.update_character_dynamic_state(entity_id, {key: value})
            print(f"已更新 {entity_id}.{key} = {value}")
            raise SystemExit(0)
        elif subcmd == "get-state":
            if len(rest) < 2:
                print("用法: webnovel character get-state <角色ID>")
                raise SystemExit(1)
            entity_id = rest[1]
            state = sm.get_character_dynamic_state(entity_id)
            import json
            print(json.dumps(state, ensure_ascii=False, indent=2))
            raise SystemExit(0)
        elif subcmd == "list":
            chars = sm.list_characters_with_dynamic_state()
            import json
            print(json.dumps(chars, ensure_ascii=False, indent=2))
            raise SystemExit(0)
        else:
            print(f"未知子命令: {subcmd}")
            print("可用: set-state, get-state, list")
            raise SystemExit(1)

    # plot 命令（情节图谱管理）
    if tool == "plot":
        from .state_manager import StateManager
        from .chapter_paths import find_chapter_file
        import re

        config = get_config(project_root=str(project_root))
        sm = StateManager(config)

        if not rest:
            print("用法: webnovel plot list|add|extract|check --help")
            raise SystemExit(0)

        subcmd = rest[0]
        if subcmd == "list":
            chapter_filter = None
            actor_filter = None
            args_iter = iter(rest[1:])
            for arg in args_iter:
                if arg == "--chapter" or arg == "-c":
                    chapter_filter = int(next(args_iter))
                elif arg == "--actor" or arg == "-a":
                    actor_filter = next(args_iter)
            events = sm.get_plot_events(chapter=chapter_filter, actor=actor_filter)
            if not events:
                print("暂无事件记录。")
                raise SystemExit(0)
            for e in events:
                print(f"[{e.get('chapter', '?')}] {e['name']} (ID: {e['id']})")
                if e.get("description"):
                    print(f"    描述: {e['description']}")
                if e.get("actors"):
                    print(f"    参与者: {', '.join(e['actors'])}")
                if e.get("preconditions"):
                    print(f"    前置: {', '.join(e['preconditions'])}")
                print()
            raise SystemExit(0)

        elif subcmd == "add":
            if len(rest) < 4 or rest[1] != "--name" or rest[3] != "--chapter":
                print("用法: webnovel plot add --name <名称> --chapter <N> [--description <描述>] [--actors <角色1,角色2>] [--preconditions <事件1,事件2>]")
                raise SystemExit(1)
            name = rest[2]
            chapter = int(rest[4])
            event_data = {"name": name, "chapter": chapter, "description": "", "actors": [], "preconditions": []}
            args_iter = iter(rest[5:])
            try:
                for arg in args_iter:
                    if arg == "--description" or arg == "-d":
                        event_data["description"] = next(args_iter)
                    elif arg == "--actors" or arg == "-a":
                        actors_str = next(args_iter)
                        event_data["actors"] = [a.strip() for a in actors_str.split(",") if a.strip()]
                    elif arg == "--preconditions" or arg == "-p":
                        pre_str = next(args_iter)
                        event_data["preconditions"] = [p.strip() for p in pre_str.split(",") if p.strip()]
            except StopIteration:
                pass
            event_id = sm.add_plot_event(event_data)
            print(f"✅ 事件已添加: {name} (ID: {event_id})")
            raise SystemExit(0)

        elif subcmd == "delete":
            if len(rest) < 2:
                print("用法: webnovel plot delete <事件ID>")
                raise SystemExit(1)
            event_id = rest[1]
            if sm.delete_plot_event(event_id):
                print(f"✅ 事件 {event_id} 已删除")
            else:
                print(f"❌ 未找到事件 {event_id}")
            raise SystemExit(0)

        elif subcmd == "check":
            if len(rest) < 2 or rest[1] != "--chapter":
                print("用法: webnovel plot check --chapter <N>")
                raise SystemExit(1)
            chapter = int(rest[2])
            chapter_file = find_chapter_file(project_root, chapter)
            if not chapter_file or not chapter_file.exists():
                print(f"❌ 章节文件不存在: 第{chapter}章")
                raise SystemExit(1)
            chapter_text = chapter_file.read_text(encoding="utf-8")
            all_events = sm.get_plot_events()
            mentioned = [e for e in all_events if e["name"] in chapter_text]
            issues = []
            for e in mentioned:
                event_chapter = e.get("chapter", 0)
                if event_chapter > chapter:
                    issues.append({
                        "type": "TEMPORAL_CONFLICT",
                        "detail": f"事件「{e['name']}」在第{event_chapter}章才发生，但当前第{chapter}章已提及",
                        "severity": "high"
                    })
            causal_patterns = [
                r"因为(.*?)，所以(.*?)[。；]",
                r"由于(.*?)，(.*?)[。；]",
            ]
            for pattern in causal_patterns:
                matches = re.findall(pattern, chapter_text)
                for cause, effect in matches:
                    for e in all_events:
                        if e["name"] in cause:
                            if e.get("chapter", 999) > chapter:
                                issues.append({
                                    "type": "PREREQUISITE_MISSING",
                                    "detail": f"文中写道「{cause.strip()}」导致「{effect.strip()}」，但事件「{e['name']}」在第{e.get('chapter', '?')}章才发生",
                                    "severity": "high"
                                })
            if not issues:
                print(f"✅ 第{chapter}章因果一致性检查通过")
            else:
                print(f"❌ 第{chapter}章发现因果问题:")
                for issue in issues:
                    print(f"  - [{issue['severity'].upper()}] {issue['detail']}")
            raise SystemExit(0)

        elif subcmd == "extract":
            if len(rest) < 2 or rest[1] != "--chapter":
                print("用法: webnovel plot extract --chapter <N>")
                raise SystemExit(1)
            chapter = int(rest[2])
            chapter_file = find_chapter_file(project_root, chapter)
            if not chapter_file or not chapter_file.exists():
                print(f"❌ 章节文件不存在: 第{chapter}章")
                raise SystemExit(1)

            print(f"🤖 正在分析第{chapter}章...")
            chapter_text = chapter_file.read_text(encoding="utf-8")

            import json
            from .llm_utils import call_agent

            try:
                response = call_agent("extract_events", chapter_text[:8000])
                json_match = re.search(r'\[[\s\S]*\]', response)
                if not json_match:
                    print("❌ LLM 返回结果中未找到有效 JSON")
                    print(f"原始响应: {response[:500]}")
                    raise SystemExit(1)
                events = json.loads(json_match.group())
            except FileNotFoundError:
                print("❌ 提取提示词模板不存在: agents/extract_events.md")
                raise SystemExit(1)
            except Exception as e:
                print(f"❌ LLM 调用失败: {e}")
                raise SystemExit(1)

            if not events:
                print("ℹ️ 未提取到关键事件")
                raise SystemExit(0)

            print(f"\n📌 提取到 {len(events)} 个候选事件:\n")
            for i, ev in enumerate(events, 1):
                name = ev.get("name", "未命名")
                desc = ev.get("description", "")
                actors = ev.get("actors", [])
                precons = ev.get("preconditions", [])
                print(f"{i}. 【{name}】")
                if desc:
                    print(f"   描述: {desc}")
                if actors:
                    print(f"   参与者: {', '.join(actors)}")
                if precons:
                    print(f"   前置事件: {', '.join(precons)}")
                print()

            print("输入 'y' 添加所有事件，'n' 取消，或输入编号选择性添加（如 1,3）: ", end="")
            answer = input().strip().lower()

            if answer == "n" or answer == "no":
                print("已取消添加")
                raise SystemExit(0)

            selected = []
            if answer == "y" or answer == "yes":
                selected = events
            else:
                for part in answer.split(","):
                    try:
                        idx = int(part.strip()) - 1
                        if 0 <= idx < len(events):
                            selected.append(events[idx])
                    except ValueError:
                        pass

            if not selected:
                print("未选择任何事件")
                raise SystemExit(0)

            for ev in selected:
                ev["chapter"] = chapter
                sm.add_plot_event(ev)
            print(f"✅ 已添加 {len(selected)} 个事件到情节图谱")
            raise SystemExit(0)

        else:
            print(f"未知子命令: {subcmd}")
            print("可用: list, add, delete, extract, check")
            raise SystemExit(1)

    # dashboard 是交互式长驻服务，作为后台子进程启动，避免 agent 超时
    if tool == "dashboard":
        import os
        import subprocess
        import time
        import webbrowser
        import socket

        # 确保 .opencode 在 PYTHONPATH 中，使 import dashboard 生效
        # __file__ 在 data_modules/webnovel.py，所以 parent.parent.parent 才是 .opencode 目录
        opencode_dir = str(Path(__file__).resolve().parent.parent.parent)
        scripts_dir = str(Path(__file__).resolve().parent.parent)
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{opencode_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"

        # 启动后台进程
        cmd = [
            sys.executable, "-m", "dashboard.server",
            "--project-root", str(project_root),
            "--host", args.host,
            "--port", str(args.port),
        ]
        if args.no_browser:
            cmd.append("--no-browser")

        # 日志文件路径（放在 .opencode 目录下）
        log_file = Path(opencode_dir) / "dashboard.log"

        # Windows 下使用 CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS 确保子进程独立运行
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

        with open(log_file, "w", encoding="utf-8") as log_f:
            proc = subprocess.Popen(
                cmd,
                env=env,
                cwd=opencode_dir,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )

        # 等待服务就绪（通过检测端口监听状态）
        url = f"http://{args.host}:{args.port}"
        ready = False
        for i in range(40):
            time.sleep(0.3)
            # 先检查进程是否还活着
            if proc.poll() is not None:
                # 进程已退出，打印日志内容
                print(f"Dashboard 启动失败（进程已退出，退出码: {proc.returncode}）", file=sys.stderr)
                print(f"日志文件: {log_file}", file=sys.stderr)
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        print(f.read(), file=sys.stderr)
                except Exception:
                    pass
                return 1
            # 再检查端口是否监听
            try:
                with socket.create_connection((args.host, args.port), timeout=0.5):
                    ready = True
                    break
            except (ConnectionRefusedError, OSError):
                continue

        if not ready:
            print(f"Dashboard 启动超时（等待 {40*0.3:.0f} 秒后仍未就绪）", file=sys.stderr)
            print(f"日志文件: {log_file}", file=sys.stderr)
            proc.terminate()
            return 1

        print(f"Dashboard 启动: {url}")
        print(f"API 文档: {url}/docs")
        print(f"进程 PID: {proc.pid}")
        print(f"日志文件: {log_file}")

        if not args.no_browser:
            webbrowser.open(url)

        return 0

    raise SystemExit(2)


if __name__ == "__main__":
    main()
