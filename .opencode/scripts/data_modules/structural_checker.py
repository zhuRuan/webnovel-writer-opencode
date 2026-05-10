#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def run_checks(project_root: Path, chapter: int) -> dict[str, Any]:
    checks = []
    state = _load_state(project_root)

    checks.append(_check_strand_balance(state, chapter))
    checks.append(_check_entity_freshness(state, chapter))
    checks.append(_check_memory_bloat(project_root))
    checks.append(_check_debt_burden(state, project_root, chapter))
    checks.append(_check_contract_coverage(project_root, chapter))

    passed = not any(c["severity"] == "blocking" and not c["passed"] for c in checks)
    return {"chapter": chapter, "passed": passed, "checks": checks}


def _load_state(project_root: Path) -> dict:
    state_file = project_root / ".webnovel" / "state.json"
    if state_file.is_file():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {}


def _check_strand_balance(state: dict, chapter: int) -> dict:
    tracker = state.get("strand_tracker") or {}
    history = tracker.get("history") or []
    result = {
        "name": "strand_balance",
        "passed": True,
        "severity": "blocking",
        "detail": "",
        "fix": "",
    }

    if not history:
        return result

    # count consecutive same dominant
    last = history[-1].get("dominant", "")
    consecutive = 0
    for entry in reversed(history):
        if entry.get("dominant") == last:
            consecutive += 1
        else:
            break
    if last == "quest" and consecutive > 5:
        result["passed"] = False
        result["detail"] = f"quest 连续主导 {consecutive} 章（上限 5 章）"
        result["fix"] = "切换到 Fire（感情线）或 Constellation（世界观线）"
        return result

    # constellation check
    last_const = _safe_int(tracker.get("last_constellation_chapter"))
    if last_const == 0 and chapter > 8:
        result["passed"] = False
        result["detail"] = f"constellation 从未激活（当前第{chapter}章），最高容忍 8 章"
        result["fix"] = "本章或下一章必须安排世界观展开：新势力/新地点/设定揭示/身世线索"
    elif last_const > 0:
        gap = chapter - last_const
        if gap > 8:
            result["passed"] = False
            result["detail"] = f"constellation 已 {gap} 章未出现（上限 8 章）"
            result["fix"] = "安排世界观展示内容"

    return result


def _check_entity_freshness(state: dict, chapter: int) -> dict:
    result = {
        "name": "entity_freshness",
        "passed": True,
        "severity": "blocking",
        "detail": "",
        "fix": "",
    }
    protag = state.get("protagonist_state") or {}
    location = protag.get("location") or {}
    last_chapter = _safe_int(location.get("last_chapter"))
    if last_chapter <= 0:
        return result

    gap = chapter - last_chapter
    if gap >= 5:
        result["passed"] = False
        result["detail"] = f"主角位置 {gap} 章未更新（最后: 第{last_chapter}章）"
        result["fix"] = "data-agent 需输出 location.current state_delta（即使位置未变）"
    return result


def _check_memory_bloat(project_root: Path) -> dict:
    result = {
        "name": "memory_bloat",
        "passed": True,
        "severity": "warning",
        "detail": "",
        "fix": "",
    }
    mem_file = project_root / ".webnovel" / "memory_scratchpad.json"
    if not mem_file.is_file():
        return result

    try:
        data = json.loads(mem_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return result

    # Support both flat list (legacy) and dict-of-buckets format
    if isinstance(data, dict):
        entries = []
        for v in data.values():
            if isinstance(v, list):
                entries.extend(v)
    elif isinstance(data, list):
        entries = data
    else:
        return result

    if not entries:
        return result

    outdated = sum(1 for e in entries if isinstance(e, dict) and e.get("status") == "outdated")
    ratio = outdated / len(entries)
    if ratio > 0.30:
        result["passed"] = False
        result["detail"] = f"记忆过期率 {ratio:.1%}（{outdated}/{len(entries)}），超过 30% 阈值"
        result["fix"] = "运行 memory-compact 清理过期条目"
    return result


def _check_debt_burden(state: dict, project_root=None, chapter=0):
    result = {
        "name": "debt_burden",
        "passed": True,
        "severity": "warning",
        "detail": "",
        "fix": "",
    }
    # Prefer index.db if available
    if project_root:
        db_path = Path(project_root) / ".webnovel" / "index.db"
        if db_path.is_file():
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            try:
                total = conn.execute(
                    "SELECT COUNT(*) FROM chase_debt WHERE status='active'"
                ).fetchone()[0]
                overdue = conn.execute(
                    "SELECT COUNT(*) FROM chase_debt WHERE status='active' AND due_chapter < ?",
                    (chapter,)
                ).fetchone()[0]
                if total > 5:
                    result["passed"] = False
                    result["detail"] = f"active debts {total} (threshold 5), {overdue} overdue"
                    result["fix"] = "resolve overdue foreshadowing in upcoming chapters"
                elif overdue > 0:
                    result["passed"] = False
                    result["detail"] = f"{overdue} debts overdue"
                    result["fix"] = "check overdue foreshadowing, repay in upcoming chapters"
                return result
            finally:
                conn.close()
    # Fallback: read from state.json
    foreshadowing = (state.get("plot_threads") or {}).get("foreshadowing") or []
    unresolved = [f for f in foreshadowing if f.get("status") == "未回收"]
    if len(unresolved) > 5:
        result["passed"] = False
        result["detail"] = f"unresolved foreshadowing {len(unresolved)} (threshold 5)"
        result["fix"] = "resolve or mark abandoned for overdue foreshadowing"
    return result


def _check_contract_coverage(project_root: Path, chapter: int) -> dict:
    result = {
        "name": "contract_coverage",
        "passed": True,
        "severity": "blocking",
        "detail": "",
        "fix": "",
    }
    contract = project_root / ".story-system" / "chapters" / f"chapter_{chapter:03d}.json"
    if not contract.is_file():
        result["passed"] = False
        result["detail"] = f"缺少 chapter_{chapter:03d}.json 合同"
        result["fix"] = "运行 story-system 生成本章合同"
    return result


def _safe_int(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="结构自检（写前阻断）")
    parser.add_argument("--project-root", required=True, help="项目根目录")
    parser.add_argument("--chapter", type=int, required=True, help="目标章节号")
    parser.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    result = run_checks(project_root, args.chapter)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "全部通过" if result["passed"] else "存在阻断问题"
        print(f"第{result['chapter']}章 结构自检: {status}")
        for c in result["checks"]:
            icon = "PASS" if c["passed"] else "FAIL"
            print(f"  {icon} [{c['severity']}] {c['name']}")
            if not c["passed"]:
                print(f"         {c['detail']}")
                print(f"      -> {c['fix']}")

    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
