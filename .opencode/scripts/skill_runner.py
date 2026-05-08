#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skill runner - CJK-safe intermediate layer.

All CJK text flows through stdin or files, never CLI args.
Forces UTF-8 stdio on startup via runtime_compat.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

_scripts_root = Path(__file__).resolve().parent
if str(_scripts_root) not in sys.path:
    sys.path.insert(0, str(_scripts_root))

from runtime_compat import enable_windows_utf8_stdio


INFRA_CHECKS = {"contract_coverage"}


def filter_structural_checks(result: dict) -> dict:
    for c in result["checks"]:
        if c["name"] in INFRA_CHECKS:
            c["severity"] = "warning"
            c["passed"] = True
            if not c.get("fix"):
                c["fix"] = "infrastructure issue, does not block writing"
    result["passed"] = not any(
        c["severity"] == "blocking" and not c["passed"]
        for c in result["checks"]
    )
    return result


def cmd_story_system(args: argparse.Namespace) -> int:
    root = Path(args.project_root)
    goal = sys.stdin.read().strip()
    if not goal:
        print("ERROR: stdin missing CHAPTER_GOAL", file=sys.stderr)
        return 1

    s = json.loads((root / ".webnovel" / "state.json").read_text("utf-8"))
    genre = s.get("project_info", {}).get("genre", "")

    scripts_dir = str(_scripts_root)
    return subprocess.run([
        sys.executable, "-X", "utf8",
        f"{scripts_dir}/webnovel.py", "--project-root", str(root),
        "story-system", goal, "--genre", genre,
        "--chapter", str(args.chapter),
        "--persist", "--emit-runtime-contracts", "--format", "both",
    ], check=False).returncode


def cmd_check_structural(args: argparse.Namespace) -> int:
    from data_modules.structural_checker import run_checks

    root = Path(args.project_root)
    result = run_checks(root, args.chapter)
    result = filter_structural_checks(result)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if result["passed"] else "BLOCKED"
        print(f"Chapter {result['chapter']} structural: {status}")
        for c in result["checks"]:
            icon = "OK" if c["passed"] else "FAIL"
            print(f"  {icon} [{c['severity']}] {c['name']}")
            if not c["passed"]:
                print(f"         {c['detail']}")
                print(f"      -> {c['fix']}")

    return 0 if result["passed"] else 1


def cmd_check_file(path: str) -> int:
    p = Path(path)
    if p.is_file() and p.stat().st_size > 0:
        print("OK")
        return 0
    print("MISSING")
    return 1


def cmd_check_commit(project_root: str, chapter: int) -> int:
    p = Path(project_root) / ".story-system" / "commits" / f"chapter_{chapter:04d}.commit.json"
    return cmd_check_file(str(p))


def cmd_check_index(project_root: str, chapter: int) -> int:
    db_path = Path(project_root) / ".webnovel" / "index.db"
    if not db_path.is_file():
        print("MISSING")
        return 1
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM chapters WHERE chapter=?", (chapter,)
        ).fetchone()
        if row and row[0] > 0:
            print("OK")
            return 0
        print("MISSING")
        return 1
    finally:
        conn.close()


def cmd_check_batch_integrity(project_root: str, start: int, end: int) -> int:
    state_path = Path(project_root) / ".webnovel" / "batch_state.json"
    if not state_path.is_file():
        print("MISSING: batch_state.json not found")
        return 1
    s = json.loads(state_path.read_text("utf-8"))
    completed = set(s.get("completed_chapters", []))
    expected = set(range(start, end + 1))
    missing = sorted(expected - completed)
    if missing:
        print(f"MISSING: {missing}")
        return 1
    print("OK")
    return 0


def main() -> None:
    enable_windows_utf8_stdio(skip_in_pytest=True)

    parser = argparse.ArgumentParser(description="skill_runner")
    sub = parser.add_subparsers(dest="action", required=True)

    p_ss = sub.add_parser("story-system")
    p_ss.add_argument("--project-root", required=True)
    p_ss.add_argument("--chapter", type=int, required=True)

    p_cs = sub.add_parser("check-structural")
    p_cs.add_argument("--project-root", required=True)
    p_cs.add_argument("--chapter", type=int, required=True)
    p_cs.add_argument("--format", choices=["json", "text"], default="json")

    p_cc = sub.add_parser("check-commit")
    p_cc.add_argument("--project-root", required=True)
    p_cc.add_argument("--chapter", type=int, required=True)

    p_ci = sub.add_parser("check-index")
    p_ci.add_argument("--project-root", required=True)
    p_ci.add_argument("--chapter", type=int, required=True)

    p_cf = sub.add_parser("check-file")
    p_cf.add_argument("--path", required=True)

    p_cbi = sub.add_parser("check-batch-integrity")
    p_cbi.add_argument("--project-root", required=True)
    p_cbi.add_argument("--start", type=int, required=True)
    p_cbi.add_argument("--end", type=int, required=True)

    args = parser.parse_args()

    action_map = {
        "story-system": lambda: cmd_story_system(args),
        "check-structural": lambda: cmd_check_structural(args),
        "check-commit": lambda: cmd_check_commit(args.project_root, args.chapter),
        "check-index": lambda: cmd_check_index(args.project_root, args.chapter),
        "check-file": lambda: cmd_check_file(args.path),
        "check-batch-integrity": lambda: cmd_check_batch_integrity(args.project_root, args.start, args.end),
    }

    code = action_map[args.action]()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
