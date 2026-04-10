#!/usr/bin/env python3
"""
Workflow state manager
- Track write/review task execution status
- Detect interruption points
- Provide recovery options
- Emit call traces for observability
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, Optional

from chapter_paths import default_chapter_draft_path, find_chapter_file
from project_locator import resolve_project_root
from runtime_compat import enable_windows_utf8_stdio, normalize_windows_path
from security_utils import atomic_write_json, create_secure_directory


logger = getLogger(__name__)


# UTF-8 output for Windows console (CLI run only, avoid pytest capture issues)
if sys.platform == "win32" and __name__ == "__main__" and not os.environ.get("PYTEST_CURRENT_TEST"):
    enable_windows_utf8_stdio(skip_in_pytest=True)


TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"

STEP_STATUS_STARTED = "started"
STEP_STATUS_RUNNING = "running"
STEP_STATUS_COMPLETED = "completed"
STEP_STATUS_FAILED = "failed"


def now_iso() -> str:
    return datetime.now().isoformat()


def find_project_root(override: Optional[Path] = None) -> Path:
    """Resolve project root (containing .webnovel/state.json).

    Args:
        override: If provided, use this path directly instead of auto-detecting.
    """
    if override is not None:
        # 允许传入“工作区根目录”，统一解析到真正的 book project_root（必须包含 .webnovel/state.json）
        return resolve_project_root(str(override))
    return resolve_project_root()


# Global variable to hold CLI-provided project root
_cli_project_root: Optional[Path] = None


def _get_active_project_root() -> Path:
    """Resolve workflow paths while兼容测试中无参 monkeypatch。"""
    if _cli_project_root is not None:
        return find_project_root(_cli_project_root)
    return find_project_root()


def get_workflow_state_path() -> Path:
    """Absolute path to workflow_state.json."""
    project_root = _get_active_project_root()
    return project_root / ".webnovel" / "workflow_state.json"


def get_call_trace_path() -> Path:
    project_root = _get_active_project_root()
    return project_root / ".webnovel" / "observability" / "call_trace.jsonl"


def append_call_trace(event: str, payload: Optional[Dict[str, Any]] = None):
    """Append workflow call trace event (best effort)."""
    payload = payload or {}
    trace_path = get_call_trace_path()
    create_secure_directory(str(trace_path.parent))
    row = {
        "timestamp": now_iso(),
        "event": event,
        "payload": payload,
    }
    with open(trace_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def safe_append_call_trace(event: str, payload: Optional[Dict[str, Any]] = None):
    try:
        append_call_trace(event, payload)
    except Exception as exc:
        logger.warning("failed to append call trace for event '%s': %s", event, exc)


def expected_step_owner(command: str, step_id: str) -> str:
    """Resolve expected caller owner by command + step id.

    Returns concise owner tags to align with
    `.claude/references/claude-code-call-matrix.md`.
    """
    if command == "webnovel-write":
        mapping = {
            "Step 1": "context-agent",
            "Step 1.5": "webnovel-write-skill",
            "Step 2A": "writer-draft",
            "Step 2B": "style-adapter",
            "Step 3": "review-agents",
            "Step 4": "polish-agent",
            "Step 5": "data-agent",
            "Step 6": "backup-agent",
        }
        return mapping.get(step_id, "webnovel-write-skill")

    if command == "webnovel-review":
        return "webnovel-review-skill"

    return "unknown"


def step_allowed_before(command: str, step_id: str, completed_steps: list[Dict[str, Any]]) -> bool:
    """Check simple ordering constraints by pending sequence."""
    sequence = get_pending_steps(command)
    if step_id not in sequence:
        return True

    expected_index = sequence.index(step_id)
    completed_ids = [str(item.get("id")) for item in completed_steps]
    required_before = sequence[:expected_index]
    return all(prev in completed_ids for prev in required_before)


def _new_task(command: str, args: Dict[str, Any]) -> Dict[str, Any]:
    started_at = now_iso()
    return {
        "command": command,
        "args": args,
        "started_at": started_at,
        "last_heartbeat": started_at,
        "status": TASK_STATUS_RUNNING,
        "current_step": None,
        "completed_steps": [],
        "failed_steps": [],
        "pending_steps": get_pending_steps(command),
        "retry_count": 0,
        "artifacts": {
            "chapter_file": {},
            "git_status": {},
            "state_json_modified": False,
            "entities_appeared": False,
            "review_completed": False,
        },
    }


def _finalize_current_step_as_failed(task: Dict[str, Any], reason: str):
    current_step = task.get("current_step")
    if not current_step:
        return
    if current_step.get("status") in {STEP_STATUS_COMPLETED, STEP_STATUS_FAILED}:
        return

    current_step = dict(current_step)
    current_step["status"] = STEP_STATUS_FAILED
    current_step["failed_at"] = now_iso()
    current_step["failure_reason"] = reason
    task.setdefault("failed_steps", []).append(current_step)
    task["current_step"] = None


def _mark_task_failed(state: Dict[str, Any], reason: str):
    task = state.get("current_task")
    if not task:
        return

    _finalize_current_step_as_failed(task, reason=reason)
    task["status"] = TASK_STATUS_FAILED
    task["failed_at"] = now_iso()
    task["failure_reason"] = reason


def start_task(command, args):
    """Start a new task."""
    state = load_state()
    current = state.get("current_task")

    if current and current.get("status") == TASK_STATUS_RUNNING:
        current["retry_count"] = int(current.get("retry_count", 0)) + 1
        current["last_heartbeat"] = now_iso()
        state["current_task"] = current
        save_state(state)
        safe_append_call_trace(
            "task_reentered",
            {
                "command": current.get("command"),
                "chapter": current.get("args", {}).get("chapter_num"),
                "retry_count": current["retry_count"],
            },
        )
        print(f"ℹ️ 任务已在运行，执行重入标记: {current.get('command')}")
        return

    state["current_task"] = _new_task(command, args)
    save_state(state)
    safe_append_call_trace("task_started", {"command": command, "args": args})
    print(f"✅ 任务已启动: {command} {json.dumps(args, ensure_ascii=False)}")


def start_step(step_id, step_name, progress_note=None):
    """Mark step started."""
    state = load_state()
    task = state.get("current_task")
    if not task:
        print("⚠️ 无活动任务，请先使用 start-task")
        return

    command = str(task.get("command") or "")
    if not step_allowed_before(command, step_id, task.get("completed_steps", [])):
        safe_append_call_trace(
            "step_order_violation",
            {
                "step_id": step_id,
                "command": command,
                "completed_steps": [row.get("id") for row in task.get("completed_steps", [])],
            },
        )

    owner = expected_step_owner(command, step_id)

    _finalize_current_step_as_failed(task, reason="step_replaced_before_completion")

    started_at = now_iso()
    task["current_step"] = {
        "id": step_id,
        "name": step_name,
        "status": STEP_STATUS_STARTED,
        "started_at": started_at,
        "running_at": started_at,
        "attempt": int(task.get("retry_count", 0)) + 1,
        "progress_note": progress_note,
    }
    task["current_step"]["status"] = STEP_STATUS_RUNNING
    task["status"] = TASK_STATUS_RUNNING
    task["last_heartbeat"] = now_iso()

    save_state(state)
    safe_append_call_trace(
        "step_started",
        {
            "step_id": step_id,
            "step_name": step_name,
            "command": task.get("command"),
            "chapter": task.get("args", {}).get("chapter_num"),
            "progress_note": progress_note,
            "expected_owner": owner,
        },
    )
    print(f"▶️ {step_id} 开始: {step_name}")


def complete_step(step_id, artifacts_json=None):
    """Mark step completed."""
    state = load_state()
    task = state.get("current_task")
    if not task or not task.get("current_step"):
        print("⚠️ 无活动 Step")
        return

    current_step = task["current_step"]
    if current_step.get("id") != step_id:
        print(f"⚠️ 当前 Step 为 {current_step.get('id')}，与 {step_id} 不一致，拒绝完成")
        safe_append_call_trace(
            "step_complete_rejected",
            {
                "requested_step_id": step_id,
                "active_step_id": current_step.get("id"),
                "command": task.get("command"),
            },
        )
        return

    current_step["status"] = STEP_STATUS_COMPLETED
    current_step["completed_at"] = now_iso()

    if artifacts_json:
        try:
            artifacts = json.loads(artifacts_json)
            current_step["artifacts"] = artifacts
            task["artifacts"].update(artifacts)
        except json.JSONDecodeError as exc:
            print(f"⚠️ Artifacts JSON 解析失败: {exc}")

    task["completed_steps"].append(current_step)
    task["current_step"] = None
    task["last_heartbeat"] = now_iso()

    save_state(state)
    safe_append_call_trace(
        "step_completed",
        {
            "step_id": step_id,
            "command": task.get("command"),
            "chapter": task.get("args", {}).get("chapter_num"),
        },
    )
    print(f"✅ {step_id} 完成")


def complete_task(final_artifacts_json=None):
    """Mark task completed."""
    state = load_state()
    task = state.get("current_task")
    if not task:
        print("⚠️ 无活动任务")
        return

    _finalize_current_step_as_failed(task, reason="task_completed_with_active_step")

    task["status"] = TASK_STATUS_COMPLETED
    task["completed_at"] = now_iso()

    if final_artifacts_json:
        try:
            final_artifacts = json.loads(final_artifacts_json)
            task["artifacts"].update(final_artifacts)
        except json.JSONDecodeError as exc:
            print(f"⚠️ Final artifacts JSON 解析失败: {exc}")

    state["last_stable_state"] = extract_stable_state(task)
    if "history" not in state:
        state["history"] = []
    state["history"].append(
        {
            "task_id": f"task_{len(state['history']) + 1:03d}",
            "command": task["command"],
            "chapter": task["args"].get("chapter_num"),
            "status": TASK_STATUS_COMPLETED,
            "completed_at": task["completed_at"],
        }
    )

    state["current_task"] = None
    save_state(state)
    safe_append_call_trace(
        "task_completed",
        {
            "command": task.get("command"),
            "chapter": task.get("args", {}).get("chapter_num"),
            "completed_steps": len(task.get("completed_steps", [])),
            "failed_steps": len(task.get("failed_steps", [])),
        },
    )
    print("🎀 任务完成")


def detect_interruption():
    """Detect interruption state."""
    state = load_state()
    if not state or "current_task" not in state or state["current_task"] is None:
        return None

    task = state["current_task"]
    if task.get("status") == TASK_STATUS_COMPLETED:
        return None

    last_heartbeat = datetime.fromisoformat(task["last_heartbeat"])
    elapsed = (datetime.now() - last_heartbeat).total_seconds()

    interrupt_info = {
        "command": task["command"],
        "args": task["args"],
        "task_status": task.get("status"),
        "current_step": task.get("current_step"),
        "completed_steps": task.get("completed_steps", []),
        "failed_steps": task.get("failed_steps", []),
        "elapsed_seconds": elapsed,
        "artifacts": task.get("artifacts", {}),
        "started_at": task.get("started_at"),
        "retry_count": int(task.get("retry_count", 0)),
    }

    safe_append_call_trace(
        "interruption_detected",
        {
            "command": task.get("command"),
            "chapter": task.get("args", {}).get("chapter_num"),
            "task_status": task.get("status"),
            "current_step": (task.get("current_step") or {}).get("id"),
            "elapsed_seconds": elapsed,
        },
    )
    return interrupt_info


def analyze_recovery_options(interrupt_info):
    """Analyze recovery options based on interruption point."""
    current_step = interrupt_info["current_step"]
    command = interrupt_info["command"]
    chapter_num = interrupt_info["args"].get("chapter_num", "?")

    if not current_step:
        return [
            {
                "option": "A",
                "label": "从头开始",
                "risk": "low",
                "description": "重新执行完整流程",
                "actions": [
                    "删除 workflow_state.json 当前任务",
                    f"执行 /{command} {chapter_num}",
                ],
            }
        ]

    step_id = current_step["id"]

    if step_id in {"Step 1", "Step 1.5"}:
        return [
            {
                "option": "A",
                "label": "从 Step 1 重新开始",
                "risk": "low",
                "description": "重新加载上下文",
                "actions": [
                    "清理中断状态",
                    f"执行 /{command} {chapter_num}",
                ],
            }
        ]

    if step_id in {"Step 2", "Step 2A", "Step 2B"}:
        project_root = find_project_root()
        existing_chapter = find_chapter_file(project_root, chapter_num)
        draft_path = None
        if existing_chapter:
            chapter_path = str(existing_chapter.relative_to(project_root))
        else:
            draft_path = default_chapter_draft_path(project_root, chapter_num)
            chapter_path = str(draft_path.relative_to(project_root))

        options = [
            {
                "option": "A",
                "label": "删除半成品，从 Step 1 重启",
                "risk": "low",
                "description": f"清理 {chapter_path}，重新生成章节",
                "actions": [
                    f"删除 {chapter_path}（如存在）",
                    "清理 Git 暂存区",
                    "清理中断状态",
                    f"执行 /{command} {chapter_num}",
                ],
            }
        ]

        candidate = existing_chapter or draft_path
        if candidate and candidate.exists():
            options.append(
                {
                    "option": "B",
                    "label": "回滚到上一章",
                    "risk": "medium",
                    "description": "丢弃当前章节进度",
                    "actions": [
                        f"git reset --hard ch{(chapter_num - 1):04d}",
                        "清理中断状态",
                        f"重新决定是否继续 Ch{chapter_num}",
                    ],
                }
            )
        return options

    if step_id == "Step 3":
        return [
            {
                "option": "A",
                "label": "重新执行审查",
                "risk": "medium",
                "description": "重新调用审查员并生成报告",
                "actions": ["重新执行审查", "生成审查报告", "继续 Step 4 润色"],
            },
            {
                "option": "B",
                "label": "跳过审查直接润色",
                "risk": "low",
                "description": "后续可用 /webnovel-review 补审",
                "actions": ["标记审查已跳过", "继续 Step 4 润色"],
            },
        ]

    if step_id == "Step 4":
        project_root = find_project_root()
        existing_chapter = find_chapter_file(project_root, chapter_num)
        draft_path = None
        if existing_chapter:
            chapter_path = str(existing_chapter.relative_to(project_root))
        else:
            draft_path = default_chapter_draft_path(project_root, chapter_num)
            chapter_path = str(draft_path.relative_to(project_root))

        return [
            {
                "option": "A",
                "label": "继续润色",
                "risk": "low",
                "description": f"继续润色 {chapter_path}，完成后进入 Step 5",
                "actions": [f"打开并继续润色 {chapter_path}", "保存文件", "继续 Step 5（Data Agent）"],
            },
            {
                "option": "B",
                "label": "删除润色稿，从 Step 2A 重写",
                "risk": "medium",
                "description": f"删除 {chapter_path} 并重新生成章节内容",
                "actions": [f"删除 {chapter_path}", "清理 Git 暂存区", "清理中断状态", f"执行 /{command} {chapter_num}"],
            },
        ]

    if step_id == "Step 5":
        return [
            {
                "option": "A",
                "label": "从 Step 5 重新开始",
                "risk": "low",
                "description": "重新运行 Data Agent（幂等）",
                "actions": ["重新调用 Data Agent", "继续 Step 6（Git 备份）"],
            }
        ]

    if step_id == "Step 6":
        return [
            {
                "option": "A",
                "label": "继续 Git 提交",
                "risk": "low",
                "description": "完成未完成的 Git commit + tag",
                "actions": ["检查 Git 暂存区", "重新执行 backup_manager.py", "继续 complete-task"],
            },
            {
                "option": "B",
                "label": "回滚 Git 改动",
                "risk": "medium",
                "description": "丢弃暂存区所有改动",
                "actions": ["git reset HEAD .", f"删除第{chapter_num}章文件", "清理中断状态"],
            },
        ]

    return [
        {
            "option": "A",
            "label": "从头开始",
            "risk": "low",
            "description": "重新执行完整流程",
            "actions": ["清理所有中断 artifacts", f"执行 /{command} {chapter_num}"],
        }
    ]


def _backup_chapter_for_cleanup(project_root: Path, chapter_num: int, chapter_path: Path) -> Path:
    """Backup chapter file before destructive cleanup."""
    backup_dir = project_root / ".webnovel" / "recovery_backups"
    create_secure_directory(str(backup_dir))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"ch{chapter_num:04d}-{chapter_path.name}.{timestamp}.bak"
    backup_path = backup_dir / backup_name
    shutil.copy2(chapter_path, backup_path)
    return backup_path


def cleanup_artifacts(chapter_num, *, confirm: bool = False):
    """Cleanup partial artifacts."""
    artifacts_cleaned = []
    planned_actions = []

    project_root = find_project_root()

    chapter_path = find_chapter_file(project_root, chapter_num)
    if chapter_path is None:
        draft_path = default_chapter_draft_path(project_root, chapter_num)
        if draft_path.exists():
            chapter_path = draft_path

    if chapter_path and chapter_path.exists():
        planned_actions.append(f"删除章节文件: {chapter_path.relative_to(project_root)}")

    planned_actions.append("重置 Git 暂存区: git reset HEAD .")

    if not confirm:
        preview_items = [f"[预览] {action}" for action in planned_actions]
        safe_append_call_trace(
            "artifacts_cleanup_preview",
            {
                "chapter": chapter_num,
                "planned_actions": planned_actions,
                "confirmed": False,
            },
        )
        print("⚠️ 检测到高风险清理操作，当前仅预览。若确认执行，请追加 --confirm。")
        return preview_items or ["[预览] 无可清理项"]

    if chapter_path and chapter_path.exists():
        try:
            backup_path = _backup_chapter_for_cleanup(project_root, chapter_num, chapter_path)
        except OSError as exc:
            error_msg = f"❌ 章节备份失败，已取消删除: {exc}"
            safe_append_call_trace(
                "artifacts_cleanup_backup_failed",
                {
                    "chapter": chapter_num,
                    "chapter_file": str(chapter_path),
                    "error": str(exc),
                },
            )
            return [error_msg]

        chapter_path.unlink()
        artifacts_cleaned.append(str(chapter_path.relative_to(project_root)))
        artifacts_cleaned.append(f"章节备份已保存: {backup_path.relative_to(project_root)}")

    result = subprocess.run(["git", "reset", "HEAD", "."], cwd=project_root, capture_output=True, text=True)
    if result.returncode == 0:
        artifacts_cleaned.append("Git 暂存区已清理（project）")
    else:
        git_error = (result.stderr or "").strip() or "unknown error"
        artifacts_cleaned.append(f"⚠️ Git 暂存区清理失败: {git_error}")

    safe_append_call_trace(
        "artifacts_cleaned",
        {
            "chapter": chapter_num,
            "items": artifacts_cleaned,
            "planned_actions": planned_actions,
            "confirmed": True,
            "git_reset_ok": result.returncode == 0,
        },
    )
    return artifacts_cleaned or ["无可清理项"]


def clear_current_task():
    """Clear interrupted current task."""
    state = load_state()
    task = state.get("current_task")
    if task:
        safe_append_call_trace(
            "task_cleared",
            {
                "command": task.get("command"),
                "chapter": task.get("args", {}).get("chapter_num"),
                "status": task.get("status"),
            },
        )
        state["current_task"] = None
        save_state(state)
        print("✅ 中断任务已清除")
    else:
        print("⚠️ 无中断任务")


def fail_current_task(reason: str = "manual_fail"):
    """Mark current task as failed and keep state for diagnostics."""
    state = load_state()
    task = state.get("current_task")
    if not task:
        print("⚠️ 无活动任务")
        return

    _mark_task_failed(state, reason=reason)
    save_state(state)
    safe_append_call_trace(
        "task_failed",
        {
            "command": task.get("command"),
            "chapter": task.get("args", {}).get("chapter_num"),
            "reason": reason,
        },
    )
    print(f"⚠️ 任务已标记失败: {reason}")


def load_state():
    """Load workflow state."""
    state_file = get_workflow_state_path()
    if not state_file.exists():
        return {"current_task": None, "last_stable_state": None, "history": []}
    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    state.setdefault("current_task", None)
    state.setdefault("last_stable_state", None)
    state.setdefault("history", [])
    if state.get("current_task"):
        state["current_task"].setdefault("failed_steps", [])
        state["current_task"].setdefault("retry_count", 0)
    return state


def save_state(state):
    """Save workflow state atomically."""
    state_file = get_workflow_state_path()
    create_secure_directory(str(state_file.parent))
    atomic_write_json(state_file, state, use_lock=True, backup=False)


def get_pending_steps(command):
    """Get command pending step list."""
    if command == "webnovel-write":
        # v2: Step 1 内置 Contract v2，不再单独记录 Step 1.5，避免产生 step_order_violation 噪声。
        return ["Step 1", "Step 2A", "Step 2B", "Step 3", "Step 4", "Step 5", "Step 6"]
    if command == "webnovel-review":
        return ["Step 1", "Step 2", "Step 3", "Step 4", "Step 5", "Step 6", "Step 7", "Step 8"]
    return []


def extract_stable_state(task):
    """Extract stable state snapshot."""
    return {
        "command": task["command"],
        "chapter_num": task["args"].get("chapter_num"),
        "completed_at": task.get("completed_at"),
        "artifacts": task.get("artifacts", {}),
    }


TASK_TYPE_BATCH = "batch"
TASK_TYPE_SINGLE = "single"


def start_batch_task(task_id: str, range_start: int, range_end: int, mode: str, metadata: Optional[Dict[str, Any]] = None):
    """Start a new batch writing task."""
    state = load_state()
    state.setdefault("batch_tasks", {})
    
    started_at = now_iso()
    state["batch_tasks"][task_id] = {
        "task_id": task_id,
        "range": {"start": range_start, "end": range_end},
        "mode": mode,
        "status": "running",
        "type": TASK_TYPE_BATCH,
        "started_at": started_at,
        "updated_at": started_at,
        "current_chapter": range_start,
        "completed_chapters": [],
        "failed_chapters": [],
        "chapter_results": {},
        "stop_reason": None,
        "metadata": metadata or {},
    }
    save_state(state)
    
    safe_append_call_trace(
        "batch_task_started",
        {
            "task_id": task_id,
            "range_start": range_start,
            "range_end": range_end,
            "mode": mode,
        },
    )
    print(f"✅ 批量任务已启动: {task_id} (第 {range_start}-{range_end} 章)")


def get_batch_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Get batch task by ID."""
    state = load_state()
    batch_tasks = state.get("batch_tasks", {})
    return batch_tasks.get(task_id)


def list_batch_tasks(status: Optional[str] = None) -> list[Dict[str, Any]]:
    """List all batch tasks, optionally filtered by status."""
    state = load_state()
    batch_tasks = state.get("batch_tasks", {})
    tasks = list(batch_tasks.values())
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    return sorted(tasks, key=lambda x: x.get("started_at", ""), reverse=True)


def update_batch_progress(task_id: str, chapter: int, result: Dict[str, Any]):
    """Update batch task progress after a chapter completes."""
    state = load_state()
    batch_tasks = state.get("batch_tasks", {})
    
    if task_id not in batch_tasks:
        logger.warning(f"Batch task {task_id} not found")
        return
    
    task = batch_tasks[task_id]
    task["updated_at"] = now_iso()
    
    if result.get("status") == "success":
        task["completed_chapters"] = task.get("completed_chapters", [])
        if chapter not in task["completed_chapters"]:
            task["completed_chapters"].append(chapter)
        task["current_chapter"] = chapter + 1
    else:
        task["failed_chapters"] = task.get("failed_chapters", [])
        if chapter not in task["failed_chapters"]:
            task["failed_chapters"].append(chapter)
        task["chapter_results"][str(chapter)] = {
            "status": "failed",
            "error": result.get("error", "unknown"),
        }
        
        if result.get("stop_on_fail"):
            task["status"] = "stopped"
            task["stop_reason"] = f"chapter_{chapter}_failed"
    
    task["chapter_results"][str(chapter)] = task["chapter_results"].get(str(chapter), {})
    task["chapter_results"][str(chapter)].update({
        "status": result.get("status", "success"),
        "score": result.get("score"),
        "words": result.get("words", 0),
        "duration_seconds": result.get("duration_seconds", 0),
        "completed_at": now_iso(),
    })
    
    save_state(state)
    
    safe_append_call_trace(
        "batch_chapter_completed",
        {
            "task_id": task_id,
            "chapter": chapter,
            "status": result.get("status"),
            "score": result.get("score"),
        },
    )


def complete_batch_task(task_id: str, summary: Optional[Dict[str, Any]] = None):
    """Mark batch task as completed."""
    state = load_state()
    batch_tasks = state.get("batch_tasks", {})
    
    if task_id not in batch_tasks:
        logger.warning(f"Batch task {task_id} not found")
        return
    
    task = batch_tasks[task_id]
    task["status"] = "completed"
    task["updated_at"] = now_iso()
    
    if summary:
        task["summary"] = summary
    
    save_state(state)
    
    safe_append_call_trace(
        "batch_task_completed",
        {
            "task_id": task_id,
            "completed_chapters": task.get("completed_chapters", []),
            "failed_chapters": task.get("failed_chapters", []),
        },
    )
    print(f"✅ 批量任务已完成: {task_id}")


def fail_batch_task(task_id: str, reason: str):
    """Mark batch task as failed."""
    state = load_state()
    batch_tasks = state.get("batch_tasks", {})
    
    if task_id not in batch_tasks:
        logger.warning(f"Batch task {task_id} not found")
        return
    
    task = batch_tasks[task_id]
    task["status"] = "failed"
    task["stop_reason"] = reason
    task["updated_at"] = now_iso()
    
    save_state(state)
    
    safe_append_call_trace(
        "batch_task_failed",
        {
            "task_id": task_id,
            "reason": reason,
        },
    )
    print(f"⚠️ 批量任务已标记失败: {task_id} - {reason}")


def get_batch_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """Get batch task progress summary."""
    task = get_batch_task(task_id)
    if not task:
        return None
    
    range_start = task.get("range", {}).get("start", 0)
    range_end = task.get("range", {}).get("end", 0)
    total = range_end - range_start + 1
    completed = len(task.get("completed_chapters", []))
    failed = len(task.get("failed_chapters", []))
    
    scores = [
        task["chapter_results"].get(str(ch), {}).get("score")
        for ch in task.get("completed_chapters", [])
        if task["chapter_results"].get(str(ch), {}).get("score") is not None
    ]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    return {
        "task_id": task_id,
        "range": task.get("range"),
        "total_chapters": total,
        "completed": completed,
        "failed": failed,
        "remaining": total - completed - failed,
        "progress_percent": (completed / total * 100) if total > 0 else 0,
        "current_chapter": task.get("current_chapter"),
        "avg_score": avg_score,
        "status": task.get("status"),
        "stop_reason": task.get("stop_reason"),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="工作流状态管理")
    parser.add_argument(
        "--project-root",
        dest="global_project_root",
        help="项目根目录（可选，默认自动检测）",
    )
    subparsers = parser.add_subparsers(dest="action", help="操作类型")

    def add_project_root_arg(subparser):
        """Allow --project-root after subcommand for compatibility."""
        subparser.add_argument("--project-root", help="项目根目录（可选，默认自动检测）")

    p_start_task = subparsers.add_parser("start-task", help="开始新任务")
    add_project_root_arg(p_start_task)
    p_start_task.add_argument("--command", required=True, help="命令名称")
    p_start_task.add_argument("--chapter", type=int, help="章节号")

    p_start_step = subparsers.add_parser("start-step", help="开始 Step")
    add_project_root_arg(p_start_step)
    p_start_step.add_argument("--step-id", required=True, help="Step ID")
    p_start_step.add_argument("--step-name", required=True, help="Step 名称")
    p_start_step.add_argument("--note", help="进度备注")

    p_complete_step = subparsers.add_parser("complete-step", help="完成 Step")
    add_project_root_arg(p_complete_step)
    p_complete_step.add_argument("--step-id", required=True, help="Step ID")
    p_complete_step.add_argument("--artifacts", help="Artifacts JSON")

    p_complete_task = subparsers.add_parser("complete-task", help="完成任务")
    add_project_root_arg(p_complete_task)
    p_complete_task.add_argument("--artifacts", help="Final artifacts JSON")

    p_fail_task = subparsers.add_parser("fail-task", help="标记任务失败")
    add_project_root_arg(p_fail_task)
    p_fail_task.add_argument("--reason", default="manual_fail", help="失败原因")

    p_detect = subparsers.add_parser("detect", help="检测中断")
    add_project_root_arg(p_detect)

    p_cleanup = subparsers.add_parser("cleanup", help="清理 artifacts")
    add_project_root_arg(p_cleanup)
    p_cleanup.add_argument("--chapter", type=int, required=True, help="章节号")
    p_cleanup.add_argument("--confirm", action="store_true", help="确认执行删除与 Git 重置（高风险）")

    p_clear = subparsers.add_parser("clear", help="清除中断任务")
    add_project_root_arg(p_clear)

    # Batch task subcommands
    p_start_batch = subparsers.add_parser("start-batch", help="开始批量任务")
    add_project_root_arg(p_start_batch)
    p_start_batch.add_argument("--task-id", required=True, help="批量任务ID")
    p_start_batch.add_argument("--range-start", type=int, required=True, help="起始章节")
    p_start_batch.add_argument("--range-end", type=int, required=True, help="结束章节")
    p_start_batch.add_argument("--mode", default="standard", help="审查级别")
    p_start_batch.add_argument("--review-level", default=None, help="审查级别（别名）")
    p_start_batch.add_argument("--stop-on-fail", action="store_true", help="失败时停止")
    p_start_batch.add_argument("--force", action="store_true", help="强制执行")

    p_update_batch = subparsers.add_parser("update-batch", help="更新批量任务进度")
    add_project_root_arg(p_update_batch)
    p_update_batch.add_argument("--task-id", required=True, help="批量任务ID")
    p_update_batch.add_argument("--chapter", type=int, required=True, help="章节号")
    p_update_batch.add_argument("--status", required=True, help="状态: success/failed")
    p_update_batch.add_argument("--score", type=float, help="审查分数")
    p_update_batch.add_argument("--words", type=int, default=0, help="字数")
    p_update_batch.add_argument("--duration-seconds", type=int, default=0, help="耗时（秒）")
    p_update_batch.add_argument("--error", help="错误信息")
    p_update_batch.add_argument("--stop-on-fail", action="store_true", help="是否停止")

    p_complete_batch = subparsers.add_parser("complete-batch", help="完成批量任务")
    add_project_root_arg(p_complete_batch)
    p_complete_batch.add_argument("--task-id", required=True, help="批量任务ID")

    p_fail_batch = subparsers.add_parser("fail-batch", help="标记批量任务失败")
    add_project_root_arg(p_fail_batch)
    p_fail_batch.add_argument("--task-id", required=True, help="批量任务ID")
    p_fail_batch.add_argument("--reason", required=True, help="失败原因")

    p_list_batch = subparsers.add_parser("list-batch", help="列出批量任务")
    add_project_root_arg(p_list_batch)
    p_list_batch.add_argument("--status", help="按状态筛选")

    p_progress_batch = subparsers.add_parser("progress-batch", help="查看批量任务进度")
    add_project_root_arg(p_progress_batch)
    p_progress_batch.add_argument("--task-id", required=True, help="批量任务ID")

    args = parser.parse_args()

    # Set global project root if provided (support both before/after subcommand).
    project_root_arg = getattr(args, "project_root", None) or getattr(args, "global_project_root", None)
    if project_root_arg:
        _cli_project_root = normalize_windows_path(project_root_arg)

    if args.action == "start-task":
        start_task(args.command, {"chapter_num": args.chapter})
    elif args.action == "start-step":
        start_step(args.step_id, args.step_name, args.note)
    elif args.action == "complete-step":
        complete_step(args.step_id, args.artifacts)
    elif args.action == "complete-task":
        complete_task(args.artifacts)
    elif args.action == "fail-task":
        fail_current_task(args.reason)
    elif args.action == "detect":
        interrupt = detect_interruption()
        if interrupt:
            print("\n🔶 检测到中断任务:")
            print(json.dumps(interrupt, ensure_ascii=False, indent=2))
            print("\n📕 恢复选项:")
            options = analyze_recovery_options(interrupt)
            print(json.dumps(options, ensure_ascii=False, indent=2))
        else:
            print("✅ 无中断任务")
    elif args.action == "cleanup":
        cleaned = cleanup_artifacts(args.chapter, confirm=args.confirm)
        if args.confirm:
            print(f"✅ 已清理: {', '.join(cleaned)}")
        else:
            for item in cleaned:
                print(item)
            print("⚠️ 以上为预览，未执行实际清理。")
    elif args.action == "clear":
        clear_current_task()
    elif args.action == "start-batch":
        mode = args.review_level or args.mode
        metadata = {
            "stop_on_fail": args.stop_on_fail,
            "force": args.force,
        }
        start_batch_task(args.task_id, args.range_start, args.range_end, mode, metadata)
    elif args.action == "update-batch":
        result = {
            "status": args.status,
            "score": args.score,
            "words": args.words,
            "duration_seconds": args.duration_seconds,
            "error": args.error,
            "stop_on_fail": args.stop_on_fail,
        }
        update_batch_progress(args.task_id, args.chapter, result)
    elif args.action == "complete-batch":
        complete_batch_task(args.task_id)
    elif args.action == "fail-batch":
        fail_batch_task(args.task_id, args.reason)
    elif args.action == "list-batch":
        tasks = list_batch_tasks(args.status)
        if tasks:
            for task in tasks:
                print(json.dumps(task, ensure_ascii=False, indent=2))
                print("---")
        else:
            print("未找到批量任务")
    elif args.action == "progress-batch":
        progress = get_batch_progress(args.task_id)
        if progress:
            print(json.dumps(progress, ensure_ascii=False, indent=2))
        else:
            print(f"未找到批量任务: {args.task_id}")
    else:
        parser.print_help()
