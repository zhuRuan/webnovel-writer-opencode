#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI output helpers for data_modules.

All CLI tools should emit JSON payloads via these helpers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ErrorPayload:
    code: str
    message: str
    suggestion: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


def build_success(data: Any = None, message: str = "ok", warnings: Optional[list] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": "success",
        "message": message,
    }
    if data is not None:
        payload["data"] = data
    if warnings:
        payload["warnings"] = warnings
    return payload


def build_error(
    code: str,
    message: str,
    suggestion: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    error: Dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if suggestion:
        error["suggestion"] = suggestion
    if details:
        error["details"] = details
    return {
        "status": "error",
        "error": error,
    }


def print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def print_success(data: Any = None, message: str = "ok", warnings: Optional[list] = None) -> None:
    print_json(build_success(data=data, message=message, warnings=warnings))


def print_error(
    code: str,
    message: str,
    suggestion: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    print_json(build_error(code=code, message=message, suggestion=suggestion, details=details))


def print_foreshadowing_warning(overdue_list: list, mode: str = "log") -> None:
    """打印伏笔警告（供写作前调用）

    Args:
        overdue_list: 超期伏笔列表
        mode: 警告模式 "log" | "pause" | "ask"
    """
    if not overdue_list:
        return

    print("\n" + "=" * 50)
    print("⚠️  [伏笔提醒] 发现超期未回收伏笔")
    print("=" * 50)

    for fs in overdue_list:
        content = fs.get("content", "")
        planted = fs.get("planted_chapter", 0)
        elapsed = fs.get("elapsed_chapters", 0)
        urgency = fs.get("urgency", 0)
        tier = fs.get("tier", "支线")
        print(f"  • [{tier}] \"{content}\" (第{planted}章埋设，已逾期{elapsed}章, urgency={urgency})")

    print("-" * 50)

    if mode == "ask":
        print("是否继续生成？(y/n): ", end="")
        # 交互模式由调用方处理
    elif mode == "pause":
        print("已暂停生成。按回车继续...")
        input()
    else:
        print("提示：可使用 `webnovel query foreshadowing` 查看详情")
        print()


def format_foreshadowing_alert(overdue_list: list) -> Dict[str, Any]:
    """格式化伏笔警告为 JSON 结构（供 API 调用）"""
    if not overdue_list:
        return {"has_overdue": False, "count": 0, "items": []}

    return {
        "has_overdue": True,
        "count": len(overdue_list),
        "items": [
            {
                "content": fs.get("content"),
                "tier": fs.get("tier"),
                "planted_chapter": fs.get("planted_chapter"),
                "elapsed_chapters": fs.get("elapsed_chapters"),
                "urgency": fs.get("urgency"),
            }
            for fs in overdue_list
        ],
    }
