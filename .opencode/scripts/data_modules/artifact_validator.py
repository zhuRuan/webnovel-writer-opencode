#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Artifact Validator — 提交前产物完整性验证。

验证 chapter-commit 流程中的 4 个 JSON 产物：
- review_result
- fulfillment_result
- disambiguation_result
- extraction_result

每个产物经过两层检查：
1. Schema 验证（Pydantic 模型）
2. 策略检查（领域规则）
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .chapter_commit_schema import (
    DisambiguationResult,
    ExtractionResult,
    FulfillmentResult,
    ReviewResult,
)
from .commit_artifacts import extraction_list

logger = logging.getLogger(__name__)

# 产物名称 → Pydantic 模型映射
ARTIFACT_SCHEMAS = {
    "review_result": ReviewResult,
    "fulfillment_result": FulfillmentResult,
    "disambiguation_result": DisambiguationResult,
    "extraction_result": ExtractionResult,
}

# 产物文件名映射
ARTIFACT_FILES = {
    "review_result": "review_results.json",
    "fulfillment_result": "fulfillment_result.json",
    "disambiguation_result": "disambiguation_result.json",
    "extraction_result": "extraction_result.json",
}


def _issue(code: str, severity: str, message: str, **extra: Any) -> Dict[str, Any]:
    """标准化错误/警告对象。"""
    issue = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    issue.update(extra)
    return issue


def _policy_issues(artifact_name: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """领域策略检查 — 超越 schema 验证的业务规则。"""
    issues = []

    if artifact_name == "review_result":
        blocking = 0
        for item in payload.get("issues") or []:
            if isinstance(item, dict) and item.get("blocking"):
                blocking += 1
        if blocking > 0:
            issues.append(_issue(
                "review_blocking",
                "error",
                f"审查结果包含 {blocking} 个 blocking issue",
                blocking_count=blocking,
            ))

    elif artifact_name == "fulfillment_result":
        missed = payload.get("missed_nodes") or []
        cbn = [n for n in missed if isinstance(n, dict) and str(n.get("type", "")).upper() == "CBN"]
        if cbn:
            issues.append(_issue(
                "missed_cbn",
                "error",
                f"遗漏 {len(cbn)} 个 CBN（核心情节点）",
                missed_cbn=cbn,
            ))

    elif artifact_name == "disambiguation_result":
        pending = payload.get("pending") or []
        if pending:
            issues.append(_issue(
                "disambiguation_pending",
                "error",
                f"仍有 {len(pending)} 个待消歧项",
                pending_count=len(pending),
            ))

    elif artifact_name == "extraction_result":
        events = extraction_list(payload, "accepted_events")
        if not events:
            issues.append(_issue(
                "no_events",
                "warning",
                "未提取到任何事件",
            ))

    return issues


def validate_artifact_payload(artifact_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """验证单个产物的 schema + 策略。"""
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    # Schema 验证
    schema_cls = ARTIFACT_SCHEMAS.get(artifact_name)
    if schema_cls:
        try:
            schema_cls.model_validate(payload)
        except Exception as e:
            errors.append(_issue(
                "schema_validation",
                "error",
                f"{artifact_name} schema 验证失败: {e}",
            ))
    else:
        warnings.append(_issue(
            "unknown_artifact",
            "warning",
            f"未知产物类型: {artifact_name}",
        ))

    # 策略检查
    for issue in _policy_issues(artifact_name, payload):
        if issue["severity"] == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    return {
        "artifact": artifact_name,
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_artifact_file(artifact_name: str, path: Path) -> Dict[str, Any]:
    """从文件读取并验证单个产物。"""
    if not path.is_file():
        return {
            "artifact": artifact_name,
            "ok": False,
            "errors": [_issue("file_missing", "error", f"文件不存在: {path.name}")],
            "warnings": [],
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {
            "artifact": artifact_name,
            "ok": False,
            "errors": [_issue("file_read_error", "error", f"文件读取/解析失败: {e}")],
            "warnings": [],
        }

    return validate_artifact_payload(artifact_name, payload)


def validate_commit_artifact_files(project_root: Path, chapter: int) -> Dict[str, Any]:
    """验证所有 4 个 commit 产物。"""
    tmp_dir = project_root / ".webnovel" / "tmp"
    results = {}

    for artifact_name, filename in ARTIFACT_FILES.items():
        path = tmp_dir / filename
        results[artifact_name] = validate_artifact_file(artifact_name, path)

    # 合并报告
    all_errors = []
    all_warnings = []
    for name, result in results.items():
        all_errors.extend(result.get("errors") or [])
        all_warnings.extend(result.get("warnings") or [])

    return {
        "ok": len(all_errors) == 0,
        "artifacts": results,
        "errors": all_errors,
        "warnings": all_warnings,
        "error_count": len(all_errors),
        "warning_count": len(all_warnings),
    }


def validate_chapter_commit(project_root: Path, chapter: int) -> Dict[str, Any]:
    """验证已持久化的 chapter commit JSON。"""
    # 查找 commit 文件
    commits_dir = project_root / ".story-system" / "commits"
    commit_path = None
    for pattern in [f"chapter_{chapter:03d}.commit.json", f"chapter_{chapter:04d}.commit.json"]:
        p = commits_dir / pattern
        if p.is_file():
            commit_path = p
            break

    if not commit_path:
        return {
            "ok": False,
            "errors": [_issue("commit_missing", "error", f"第 {chapter} 章 commit 文件不存在")],
            "warnings": [],
        }

    try:
        commit = json.loads(commit_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {
            "ok": False,
            "errors": [_issue("commit_read_error", "error", f"commit 文件解析失败: {e}")],
            "warnings": [],
        }

    errors = []
    warnings = []

    # 检查 commit status
    status = str((commit.get("meta") or {}).get("status") or "")
    if status not in ("accepted", "rejected"):
        errors.append(_issue("invalid_status", "error", f"无效的 commit status: {status}"))

    # 检查投影状态
    projection_status = commit.get("projection_status") or {}
    for writer, pstatus in projection_status.items():
        if str(pstatus).startswith("failed"):
            errors.append(_issue(
                "projection_failed",
                "error",
                f"投影 {writer} 失败: {pstatus}",
                writer=writer,
                status=pstatus,
            ))

    return {
        "ok": len(errors) == 0,
        "commit_path": str(commit_path),
        "status": status,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    """CLI 入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="验证 chapter-commit 产物")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    report = validate_commit_artifact_files(project_root, args.chapter)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "✅ 通过" if report["ok"] else "❌ 失败"
        print(f"产物验证: {status}")
        print(f"  错误: {report['error_count']}")
        print(f"  警告: {report['warning_count']}")
        for err in report["errors"]:
            print(f"  ❌ [{err['code']}] {err['message']}")
        for warn in report["warnings"]:
            print(f"  ⚠️ [{warn['code']}] {warn['message']}")

    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
