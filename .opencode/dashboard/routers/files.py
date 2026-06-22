"""
文件浏览/编辑 API 路由。

从 app.py:1647-1850 迁移 4 个端点:
- GET  /api/files/tree      → 三大目录树结构
- GET  /api/files/read      → 只读文件内容（路径穿越防护）
- PUT  /api/files/write     → 写入文件 + SSE 推送
- POST /api/files/normalize → 内容感知同步（Markdown diff → index.db）

安全校验: safe_resolve（越界拦截） + _is_child（三级目录白名单）。
"""

from __future__ import annotations

import difflib
import json
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from dashboard.core.config import get_project_root
from dashboard.core.database import fetchall_safe, get_db
from dashboard.path_guard import safe_resolve
from dashboard.schemas.files import FileNormalizeRequest, FileReadQuery, FileWriteRequest
from dashboard.watcher import FileWatcher

router = APIRouter(prefix="/api/files", tags=["files"])

# FileWatcher 实例，由 create_app 通过 set_files_router_watcher() 注入
_watcher: FileWatcher | None = None


def set_files_router_watcher(w: FileWatcher) -> None:
    """由 create_app() 在包含路由前调用，注入全局 FileWatcher 实例。"""
    global _watcher
    _watcher = w


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _is_child(path: Path, parent: Path) -> bool:
    """检查 path 是否位于 parent 目录树下。"""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _walk_tree(folder: Path, root: Path) -> list[dict[str, Any]]:
    """递归遍历目录树，生成前端文件浏览器的节点列表。"""
    items: list[dict[str, Any]] = []
    for child in sorted(folder.iterdir()):
        if child.is_symlink():
            continue
        rel = str(child.relative_to(root)).replace("\\", "/")
        if child.is_dir():
            items.append({
                "name": child.name,
                "type": "dir",
                "path": rel,
                "children": _walk_tree(child, root),
            })
        else:
            if child.suffix == ".bak":
                continue  # 跳过备份文件
            items.append({
                "name": child.name,
                "type": "file",
                "path": rel,
                "size": child.stat().st_size,
            })
    return items


def _check_allowed_directory(resolved: Path, root: Path) -> None:
    """确保 resolved 位于 正文/大纲/设定集 三个目录之一，否则 403。"""
    allowed_parents = [root / n for n in ("正文", "大纲", "设定集")]
    if not any(_is_child(resolved, p) for p in allowed_parents):
        raise HTTPException(403, "仅允许操作 正文/大纲/设定集 目录下的文件")


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/tree")
def file_tree() -> dict[str, list[dict[str, Any]]]:
    """列出 正文/、大纲/、设定集/ 三个目录的树结构。"""
    root = get_project_root()
    result: dict[str, list[dict[str, Any]]] = {}
    for folder_name in ("正文", "大纲", "设定集"):
        folder = root / folder_name
        if not folder.is_dir():
            result[folder_name] = []
            continue
        result[folder_name] = _walk_tree(folder, root)
    return result


@router.get("/read")
def file_read(path: str = Query(..., min_length=1, description="文件相对路径")) -> dict[str, str]:
    """只读读取一个文件内容（限 正文/大纲/设定集 目录）。"""
    root = get_project_root()
    resolved = safe_resolve(root, path)

    _check_allowed_directory(resolved, root)

    if not resolved.is_file():
        raise HTTPException(404, "文件不存在")

    # 文本文件直接读；其他情况返回占位信息
    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = "[二进制文件，无法预览]"

    return {"path": path, "content": content}


@router.put("/write")
def file_write(request: FileWriteRequest) -> dict[str, Any]:
    """写入文件内容（限 正文/大纲/设定集 目录）。"""
    path = request.path
    content = request.content

    root = get_project_root()
    resolved = safe_resolve(root, path)

    _check_allowed_directory(resolved, root)

    if not resolved.is_file():
        raise HTTPException(404, "文件不存在")

    # 备份原文件
    backup = resolved.with_suffix(resolved.suffix + ".bak")
    try:
        backup.write_text(resolved.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass  # 备份失败不阻断写入

    # 写入新内容
    resolved.write_text(content, encoding="utf-8")

    # 写入成功后删除备份
    try:
        if backup.exists():
            backup.unlink()
    except Exception:
        pass

    # 触发 SSE 通知
    if _watcher is not None:
        try:
            _watcher._dispatch(json.dumps({
                "type": "file-saved",
                "path": path,
                "ts": time.time(),
            }))
        except Exception:
            pass

    return {"ok": True, "path": path, "size": len(content)}


@router.post("/normalize")
def normalize_file(data: FileNormalizeRequest) -> dict[str, Any]:
    """内容感知同步 - 解析编辑后的 Markdown 变更，更新 index.db。"""
    path = data.path

    root = get_project_root()
    resolved = safe_resolve(root, path)

    _check_allowed_directory(resolved, root)

    if not resolved.is_file():
        raise HTTPException(404, "文件不存在")

    if resolved.suffix != ".md":
        return {"ok": True, "changes": [], "warning": "非 Markdown 文件，跳过处理"}

    try:
        new_content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"ok": True, "changes": [], "warning": "文件编码不是 UTF-8"}

    backup = resolved.with_suffix(resolved.suffix + ".bak")
    if not backup.is_file():
        return {"ok": True, "changes": [], "warning": "no backup found"}

    changes: list[dict[str, Any]] = []
    warning: str | None = None
    try:
        old_content = backup.read_text(encoding="utf-8")
        diff = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile="old", tofile="new", lineterm="",
        ))
        if not diff:
            backup.unlink()
            return {"ok": True, "changes": [], "warning": "文件内容未变化"}

        known_entities: dict[str, str] = {}
        try:
            with closing(get_db()) as conn:
                rows = fetchall_safe(conn, "SELECT id, canonical_name FROM entities WHERE is_archived = 0")
                for r in rows:
                    eid = r.get("id")
                    name = r.get("canonical_name")
                    if eid and name and len(name) >= 2:
                        known_entities[eid] = name
        except HTTPException:
            pass

        for entity_id, name in known_entities.items():
            in_old = name in old_content
            in_new = name in new_content
            if in_old != in_new:
                changes.append({
                    "entity_id": entity_id,
                    "field": "desc",
                    "old_value": f"referenced={in_old}",
                    "new_value": f"referenced={in_new}",
                    "action": "added" if in_new else "removed",
                    "entity_name": name,
                })

        relationship_keywords = {
            "同盟": "盟友", "敌对": "敌对", "合作": "合作",
            "师徒": "师徒", "联盟": "联盟", "暗恋": "暗恋",
            "恋爱": "恋爱", "朋友": "朋友", "主仆": "主仆",
        }
        rel_changes: list[dict[str, Any]] = []
        for keyword, rel_type in relationship_keywords.items():
            in_old = keyword in old_content
            in_new = keyword in new_content
            if in_old != in_new:
                rel_changes.append({
                    "keyword": keyword, "rel_type": rel_type,
                    "old_present": in_old, "new_present": in_new,
                })
        if rel_changes:
            changes.append({
                "entity_id": "__relationships__",
                "field": "keywords",
                "old_value": json.dumps([r for r in rel_changes if r["old_present"]]),
                "new_value": json.dumps([r for r in rel_changes if r["new_present"]]),
                "action": "relationship_keywords_changed",
                "details": rel_changes,
            })

        entity_changes = [c for c in changes if c.get("entity_id") != "__relationships__"]
        if entity_changes:
            try:
                with closing(get_db()) as conn:
                    for ch in entity_changes:
                        eid = ch.get("entity_id")
                        new_ref = ch.get("new_value", "")
                        conn.execute(
                            "UPDATE entities SET desc = COALESCE(desc, '') || ? WHERE id = ?",
                            (f"\n[normalize] 章节文件引用: {new_ref}", eid),
                        )
                    conn.commit()
            except HTTPException:
                warning = "实体表更新失败（index.db 不可用）"
            except Exception as exc:
                warning = f"实体表更新异常: {exc}"
    except Exception as exc:
        warning = f"解析异常: {exc}"

    # 清理备份
    try:
        if backup.exists():
            backup.unlink()
    except Exception:
        pass

    result: dict[str, Any] = {"ok": True, "changes": changes}
    if warning:
        result["warning"] = warning
    return result
