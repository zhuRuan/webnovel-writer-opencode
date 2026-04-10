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
    p_dashboard.add_argument("--force", action="store_true", help="强制重启（清理旧进程）")

    # write-batch 命令（批量写作）
    p_write_batch = sub.add_parser("write-batch", help="批量写作工具")
    p_write_batch.add_argument("args", nargs=argparse.REMAINDER)

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

    # write-batch 命令（批量写作）- 通过 Skill 执行
    if tool == "write-batch":
        import os
        skill_root = Path(__file__).resolve().parent.parent / "skills" / "webnovel-write-batch"
        skill_script = skill_root / "SKILL.md"
        if not skill_script.exists():
            logger.error(f"批量写作 skill 不存在: {skill_script}")
            raise SystemExit(1)
        logger.info(f"批量写作 skill 路径: {skill_script}")
        raise SystemExit(0)

    if tool == "export":
        raise SystemExit(_run_script("export_manager.py", [*forward_args, *rest]))

    if tool == "publish":
        raise SystemExit(_run_script("publish_manager.py", [*forward_args, *rest]))

    # dashboard 是交互式长驻服务，作为后台子进程启动，避免 agent 超时
    if tool == "dashboard":
        import os
        import subprocess
        import time
        import webbrowser
        import socket

        def _kill_port(port: int) -> None:
            """清理占用指定端口的进程（Windows）"""
            try:
                result = subprocess.run(
                    f'netstat -ano | findstr ":{port}"',
                    shell=True,
                    capture_output=True,
                    text=True,
                )
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 5 and parts[3] == "LISTENING":
                        pid = parts[-1].strip()
                        if pid and pid != "0":
                            try:
                                subprocess.run(
                                    f"taskkill /PID {pid} /F",
                                    shell=True,
                                    capture_output=True,
                                )
                                print(f"已终止旧进程 PID: {pid}")
                            except Exception:
                                pass
            except Exception:
                pass

        # 确保 .opencode 在 PYTHONPATH 中，使 import dashboard 生效
        # __file__ 在 data_modules/webnovel.py，所以 parent.parent.parent 才是 .opencode 目录
        opencode_dir = str(Path(__file__).resolve().parent.parent.parent)
        scripts_dir = str(Path(__file__).resolve().parent.parent)
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{opencode_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"

        # 清理端口占用
        _kill_port(args.port)

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
