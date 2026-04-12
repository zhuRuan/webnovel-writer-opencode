"""
Publish Bridge — Dashboard 与现有发布系统之间的桥接层。

复用 publish_manager.py 中的 PublisherManager，将异步操作包装为
FastAPI 可调用的同步接口，并提供后台任务管理与进度跟踪。

浏览器登录流程简化：
- Dashboard 不直接控制浏览器
- 仅提供状态检测和 CLI 指引
- 用户通过 CLI 完成首次登录
"""

import asyncio
import atexit
import json
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

_pm_lock = threading.Lock()
_pm_loop: Optional[asyncio.AbstractEventLoop] = None
_pm_instance: Optional["PublisherManager"] = None
_pm_project_root: Optional[Path] = None
_pm_last_used: float = 0
_IDLE_TIMEOUT = 15 * 60  # 15分钟


def _run_async(coro):
    """线程安全的异步执行器，复用单个事件循环"""
    global _pm_loop
    with _pm_lock:
        if _pm_loop is None or _pm_loop.is_closed():
            _pm_loop = asyncio.new_event_loop()
    return _pm_loop.run_until_complete(coro)


def _close_pm_instance():
    """关闭并清理缓存的 PublisherManager 实例"""
    global _pm_instance, _pm_project_root
    if _pm_instance:
        try:
            _run_async(_pm_instance.close())
        except Exception:
            pass
        _pm_instance = None
        _pm_project_root = None


def _check_idle():
    """后台线程检查闲置并关闭浏览器"""
    while True:
        time.sleep(60)
        with _pm_lock:
            if _pm_instance and (time.time() - _pm_last_used) > _IDLE_TIMEOUT:
                _close_pm_instance()


threading.Thread(target=_check_idle, daemon=True).start()
atexit.register(_close_pm_instance)

# 确保 publisher 和 publish_manager 可被导入
_opencode_root = Path(__file__).resolve().parent.parent
_scripts_root = str(_opencode_root / "scripts")
_data_modules_root = str(_opencode_root / "scripts" / "data_modules")
for p in [_scripts_root, _data_modules_root]:
    if p not in sys.path:
        sys.path.insert(0, p)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class PublishTask:
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    total: int = 0
    message: str = ""
    logs: List[str] = field(default_factory=list)
    results: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "total": self.total,
            "message": self.message,
            "logs": self.logs[-50:],  # 最近 50 条日志
            "results": self.results,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskStore:
    """内存中的任务状态存储。"""

    def __init__(self):
        self._tasks: Dict[str, PublishTask] = {}

    def create(self, task_id: str, total: int = 0) -> PublishTask:
        task = PublishTask(task_id=task_id, total=total)
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> Optional[PublishTask]:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs):
        task = self._tasks.get(task_id)
        if task:
            for key, value in kwargs.items():
                setattr(task, key, value)
            task.updated_at = time.time()

    def add_log(self, task_id: str, message: str):
        task = self._tasks.get(task_id)
        if task:
            task.logs.append(message)
            task.updated_at = time.time()


_task_store = TaskStore()


def get_task_store() -> TaskStore:
    return _task_store


def _get_publish_manager(project_root: Path):
    """获取 PublisherManager 实例（单例模式）"""
    global _pm_instance, _pm_project_root, _pm_last_used
    
    from publish_manager import PublisherManager
    
    _pm_last_used = time.time()
    
    if _pm_instance is not None and _pm_project_root != project_root:
        _close_pm_instance()
    
    if _pm_instance is None:
        _pm_instance = PublisherManager(project_root)
        _pm_project_root = project_root
    
    return _pm_instance


def close_publish_manager() -> Dict[str, Any]:
    """显式关闭浏览器（供 API 调用）"""
    _close_pm_instance()
    return {"success": True}


def check_playwright() -> Dict[str, Any]:
    """检查 Playwright 是否可用。"""
    try:
        import playwright
        # playwright 包没有 __version__，尝试从已安装的包中获取
        try:
            from importlib.metadata import version
            ver = version("playwright")
        except Exception:
            ver = "unknown"
        return {"available": True, "version": ver}
    except ImportError:
        return {"available": False, "version": None}


def check_login_status() -> Dict[str, Any]:
    """检查番茄小说登录状态。"""
    from publisher.auth import (
        check_auth_state,
        get_default_auth_state_path,
    )
    auth_path = get_default_auth_state_path()
    is_logged_in = check_auth_state(auth_path)
    return {
        "logged_in": is_logged_in,
        "auth_state_path": str(auth_path),
        "cli_command": "python .opencode/scripts/webnovel.py publish setup-browser",
    }


def get_books(project_root: Path) -> List[Dict[str, Any]]:
    """获取已创建书籍列表。"""
    pm = _get_publish_manager(project_root)
    books = _run_async(pm.list_books())
    return books


def create_book(
    project_root: Path,
    title: str,
    genre: str,
    synopsis: str,
    protagonist1: str = "",
    protagonist2: str = "",
) -> Dict[str, Any]:
    """创建新书。"""
    pm = _get_publish_manager(project_root)
    try:
        book_id = _run_async(
            pm.create_book(title, genre, synopsis, protagonist1, protagonist2)
        )
        return {"success": True, "book_id": book_id, "title": title}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_remote_chapters(project_root: Path, book_id: str) -> List[Dict[str, Any]]:
    """获取番茄平台上的章节列表（已发布+草稿）。"""
    pm = _get_publish_manager(project_root)
    
    async def _fetch():
        client = await pm._ensure_client()
        published = await client.get_chapter_list(book_id)
        try:
            drafts = await client.get_draft_list(book_id)
        except Exception:
            drafts = []
        
        seen_ids = set()
        merged = []
        for ch in published + drafts:
            item_id = ch.get("item_id", "")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                merged.append(ch)
            elif not item_id:
                merged.append(ch)
        return merged
    
    try:
        return _run_async(_fetch())
    except Exception as e:
        return {"error": str(e)}


def publish_chapters(
    project_root: Path,
    book_id: str,
    range_spec: str = "all",
    publish_mode: str = "draft",
) -> str:
    """创建后台发布任务，返回 task_id。"""
    task_id = str(uuid.uuid4())[:8]
    task = _task_store.create(task_id)
    task.status = TaskStatus.RUNNING
    task.message = "正在初始化发布任务…"

    def _run():
        pm = _get_publish_manager(project_root)
        try:
            _task_store.add_log(task_id, "正在加载章节…")
            chapters = pm.load_chapters(range_spec)
            task.total = len(chapters)
            _task_store.add_log(task_id, f"找到 {len(chapters)} 个章节")

            if not chapters:
                _task_store.update(task_id, status=TaskStatus.FAILED, message="没有可发布的章节")
                return

            _task_store.add_log(task_id, "正在连接番茄小说…")
            _task_store.update(task_id, message="正在连接番茄小说…")

            async def _upload():
                client = await pm._ensure_client()
                results = await client.publish_chapters(
                    book_id=book_id,
                    chapters=chapters,
                    publish_mode=publish_mode,
                )
                return results

            results = _run_async(_upload())

            success_count = sum(1 for r in results if r.get("success"))
            fail_count = len(results) - success_count

            task.results = results
            task.progress = task.total
            task.status = TaskStatus.SUCCESS if fail_count == 0 else TaskStatus.FAILED
            task.message = f"发布完成：成功 {success_count}，失败 {fail_count}"
            _task_store.add_log(task_id, task.message)

            for r in results:
                status = "OK" if r.get("success") else "FAIL"
                _task_store.add_log(task_id, f"  [{status}] {r.get('message', '')}")

        except Exception as e:
            _task_store.update(task_id, status=TaskStatus.FAILED, message=f"发布失败: {e}")
            _task_store.add_log(task_id, f"ERROR: {e}")

    threading.Thread(target=_run, daemon=True).start()

    return task_id


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """查询发布任务进度。"""
    task = _task_store.get(task_id)
    if task:
        return task.to_dict()
    return None
