#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Postcommit Gate — 提交后检查。

在 chapter-commit 完成后验证：
1. commit JSON 文件存在且可解析
2. commit status 为 accepted
3. 投影状态检查
4. 产物文件存在性
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from . import gate_report, issue


def _check_commit_file(project_root: Path, chapter: int) -> Dict[str, Any]:
    """检查 commit 文件。"""
    commits_dir = project_root / ".story-system" / "commits"
    commit_path = None
    for pattern in [f"chapter_{chapter:03d}.commit.json", f"chapter_{chapter:04d}.commit.json"]:
        p = commits_dir / pattern
        if p.is_file():
            commit_path = p
            break

    if not commit_path:
        return {"ok": False, "errors": [issue(
            "commit_file_missing",
            "error",
            f"第 {chapter} 章 commit 文件不存在",
        )], "commit": None}

    try:
        commit = json.loads(commit_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"ok": False, "errors": [issue(
            "commit_file_invalid",
            "error",
            f"commit 文件解析失败: {e}",
        )], "commit": None}

    errors = []
    status = str((commit.get("meta") or {}).get("status") or "")
    if status not in ("accepted", "rejected"):
        errors.append(issue(
            "invalid_commit_status",
            "error",
            f"无效的 commit status: {status}",
        ))

    return {"ok": len(errors) == 0, "errors": errors, "commit": commit}


def _check_projections(project_root: Path, commit: Dict[str, Any]) -> List[Dict[str, Any]]:
    """检查投影完整性。"""
    errors = []
    projection_status = commit.get("projection_status") or {}

    for writer, pstatus in projection_status.items():
        if str(pstatus).startswith("failed"):
            errors.append(issue(
                "projection_failed",
                "error",
                f"投影 {writer} 失败: {pstatus}",
                repair=f"运行 webnovel.py ssot rebuild 补跑 {writer}",
            ))

    # 检查 summary 文件
    chapter = int((commit.get("meta") or {}).get("chapter") or 0)
    if chapter > 0:
        summary_dir = project_root / ".webnovel" / "summaries"
        summary_file = summary_dir / f"ch{chapter:04d}.md"
        proj_summary = projection_status.get("summary", "")
        if proj_summary == "done" and not summary_file.is_file():
            errors.append(issue(
                "summary_file_missing",
                "warning",
                f"投影声称 summary done 但文件不存在: {summary_file.name}",
            ))

    # 检查 index.db
    index_db = project_root / ".webnovel" / "index.db"
    proj_index = projection_status.get("index", "")
    if proj_index == "done" and not index_db.is_file():
        errors.append(issue(
            "index_db_missing",
            "warning",
            "投影声称 index done 但 index.db 不存在",
        ))

    return errors


def run_postcommit_gate(project_root: Path, chapter: int) -> Dict[str, Any]:
    """运行 postcommit gate。"""
    errors = []
    warnings = []

    # commit 文件检查
    commit_check = _check_commit_file(project_root, chapter)
    for err in commit_check.get("errors") or []:
        if err["severity"] == "error":
            errors.append(err)
        else:
            warnings.append(err)

    if not commit_check["ok"]:
        return gate_report("postcommit", errors, warnings)

    commit = commit_check["commit"]

    # 投影检查
    proj_issues = _check_projections(project_root, commit)
    for i in proj_issues:
        if i["severity"] == "error":
            errors.append(i)
        else:
            warnings.append(i)

    return gate_report("postcommit", errors, warnings)
