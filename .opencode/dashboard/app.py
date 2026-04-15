"""
Webnovel Dashboard - FastAPI 主应用

仅提供 GET 接口（严格只读）；所有文件读取经过 path_guard 防穿越校验。
"""

import asyncio
import hashlib
import json
import re
import sqlite3
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Body, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .path_guard import safe_resolve
from .watcher import FileWatcher

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
_project_root: Path | None = None
_watcher = FileWatcher()

STATIC_DIR = Path(__file__).parent / "frontend" / "dist"


def _get_project_root() -> Path:
    if _project_root is None:
        raise HTTPException(status_code=500, detail="项目根目录未配置")
    return _project_root


def _webnovel_dir() -> Path:
    return _get_project_root() / ".webnovel"


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------

def create_app(project_root: str | Path | None = None) -> FastAPI:
    global _project_root

    if project_root:
        _project_root = Path(project_root).resolve()

    @asynccontextmanager
    async def _lifespan(_: FastAPI):
        webnovel = _webnovel_dir()
        if webnovel.is_dir():
            _sync_chapters_from_source(_project_root)
            _watcher.start(webnovel, asyncio.get_running_loop())
        try:
            yield
        finally:
            _watcher.stop()

    app = FastAPI(title="Webnovel Dashboard", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # ===========================================================
    # API：项目元信息
    # ===========================================================

    @app.get("/api/project/info")
    def project_info():
        """返回 state.json 完整内容（只读）。"""
        state_path = _webnovel_dir() / "state.json"
        if not state_path.is_file():
            raise HTTPException(404, "state.json 不存在")
        return json.loads(state_path.read_text(encoding="utf-8"))

    # ===========================================================
    # API：小说发布
    # ===========================================================

    from .publish_bridge import (
        check_playwright,
        check_login_status,
        get_books,
        create_book,
        publish_chapters,
        get_task_status,
        get_remote_chapters,
    )

    @app.get("/api/publish/status")
    def api_publish_status():
        """检查发布环境状态（Playwright 可用性 + 登录状态）。"""
        pw = check_playwright()
        login = check_login_status()
        return {
            "playwright": pw,
            "login": login,
            "ready": pw["available"] and login["logged_in"],
        }

    @app.get("/api/publish/books")
    def api_publish_books():
        """获取已创建书籍列表。"""
        try:
            return get_books(_get_project_root())
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/publish/books")
    def api_publish_create_book(
        title: str,
        genre: str,
        synopsis: str,
        protagonist1: str = "",
        protagonist2: str = "",
    ):
        """创建新书。"""
        result = create_book(
            _get_project_root(), title, genre, synopsis, protagonist1, protagonist2
        )
        if result.get("success"):
            return result
        raise HTTPException(status_code=400, detail=result.get("error", "创建失败"))

    @app.get("/api/publish/books/{book_id}/remote-chapters")
    def api_remote_chapters(book_id: str):
        """获取番茄平台上的章节列表（已发布+草稿）。"""
        result = get_remote_chapters(_get_project_root(), book_id)
        if isinstance(result, dict) and "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result

    @app.post("/api/publish/chapters")
    def api_publish_chapters(
        book_id: str,
        range_spec: str = "all",
        publish_mode: str = "draft",
    ):
        """发布章节（创建后台任务）。"""
        task_id = publish_chapters(
            _get_project_root(), book_id, range_spec, publish_mode
        )
        return {"task_id": task_id, "status": "pending"}

    @app.get("/api/publish/task/{task_id}")
    def api_publish_task_status(task_id: str):
        """查询发布任务进度。"""
        status = get_task_status(task_id)
        if status is None:
            raise HTTPException(404, f"任务 {task_id} 不存在")
        return status

    @app.post("/api/publish/close")
    def api_close_publish_manager():
        """显式关闭浏览器，释放资源。"""
        return close_publish_manager()

    # ===========================================================
    # API：小说导出
    # ===========================================================
    from .export_bridge import (
        get_export_info,
        get_chapter_list,
        do_export,
        list_exports,
        _output_dir,
    )

    @app.get("/api/export/info")
    def api_export_info():
        """获取导出配置信息"""
        return get_export_info(_get_project_root())

    @app.get("/api/export/chapters")
    def api_export_chapters():
        """获取可用章节列表"""
        return get_chapter_list(_get_project_root())

    @app.post("/api/export/do")
    def api_do_export(
        format: str = Body(...),
        range_spec: str = Body("all"),
        author: str = Body(""),
        cover_path: Optional[str] = Body(None),
        style_path: Optional[str] = Body(None),
    ):
        """执行导出"""
        result = do_export(
            _get_project_root(), format, range_spec, author, cover_path, style_path
        )
        if not result.get("success"):
            raise HTTPException(400, detail=result.get("error"))
        return result

    @app.get("/api/export/files")
    def api_list_exports():
        """列出已导出的文件"""
        return list_exports(_get_project_root())

    @app.get("/api/export/download/{filename}")
    def api_download_export(filename: str):
        """下载导出的文件"""
        file_path = (_output_dir / filename).resolve()
        safe_resolve(file_path, _get_project_root())
        if not file_path.is_file():
            raise HTTPException(404, "文件不存在")
        return FileResponse(file_path)

    # ===========================================================
    # API：实体数据库（index.db 只读查询）
    # ===========================================================

    def _get_db() -> sqlite3.Connection:
        db_path = _webnovel_dir() / "index.db"
        if not db_path.is_file():
            raise HTTPException(404, "index.db 不存在")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _fetchall_safe(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
        """执行只读查询；若目标表不存在（旧库），返回空列表。"""
        try:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return []
            raise HTTPException(status_code=500, detail=f"数据库查询失败: {exc}") from exc

    @app.get("/api/entities")
    def list_entities(
        entity_type: Optional[str] = Query(None, alias="type"),
        include_archived: bool = False,
    ):
        """列出所有实体（可按类型过滤）。"""
        with closing(_get_db()) as conn:
            q = "SELECT * FROM entities"
            params: list = []
            clauses: list[str] = []
            if entity_type:
                clauses.append("type = ?")
                params.append(entity_type)
            if not include_archived:
                clauses.append("is_archived = 0")
            if clauses:
                q += " WHERE " + " AND ".join(clauses)
            q += " ORDER BY last_appearance DESC"
            rows = conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/entities/{entity_id}")
    def get_entity(entity_id: str):
        with closing(_get_db()) as conn:
            row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
            if not row:
                raise HTTPException(404, "实体不存在")
            return dict(row)

    @app.get("/api/relationships")
    def list_relationships(entity: Optional[str] = None, limit: int = 200):
        with closing(_get_db()) as conn:
            if entity:
                rows = conn.execute(
                    "SELECT * FROM relationships WHERE from_entity = ? OR to_entity = ? ORDER BY chapter DESC LIMIT ?",
                    (entity, entity, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM relationships ORDER BY chapter DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/relationships/graph")
    def relationships_graph():
        """返回聚合去重后的图谱数据（节点+边）。"""
        import json as _json
        with closing(_get_db()) as conn:
            # 获取所有关系
            rels = conn.execute(
                "SELECT * FROM relationships ORDER BY chapter ASC"
            ).fetchall()
            rels = [dict(r) for r in rels]

            # 获取所有实体
            ents = conn.execute(
                "SELECT * FROM entities WHERE is_archived = 0"
            ).fetchall()
            entity_map = {e["id"]: dict(e) for e in ents}

            type_colors = {
                "角色": "#4f8ff7", "地点": "#34d399", "星球": "#22d3ee",
                "神仙": "#f59e0b", "势力": "#8b5cf6", "招式": "#ef4444",
                "法宝": "#ec4899",
            }

            # 收集所有涉及的实体 ID
            related_ids = set()
            for r in rels:
                related_ids.add(r["from_entity"])
                related_ids.add(r["to_entity"])

            # 构建节点
            tier_sizes = {"S": 10, "A": 7, "B": 5, "C": 3}
            nodes = []
            for eid in related_ids:
                ent = entity_map.get(eid, {})
                tier = ent.get("tier", "D") or "D"
                nodes.append({
                    "id": eid,
                    "name": ent.get("canonical_name") or eid,
                    "type": ent.get("type") or "未知",
                    "tier": tier,
                    "val": tier_sizes.get(tier, 2),
                    "color": type_colors.get(ent.get("type"), "#5c6078"),
                    "desc": ent.get("desc") or "",
                    "first_appearance": ent.get("first_appearance", 0),
                    "last_appearance": ent.get("last_appearance", 0),
                    "is_protagonist": bool(ent.get("is_protagonist", False)),
                })

            # 构建聚合边（去重）
            link_map = {}
            for r in rels:
                key = f"{r['from_entity']}→{r['to_entity']}"
                if key not in link_map:
                    link_map[key] = {
                        "source": r["from_entity"],
                        "target": r["to_entity"],
                        "types": [],
                        "chapters": [],
                        "descriptions": [],
                    }
                if r["type"] not in link_map[key]["types"]:
                    link_map[key]["types"].append(r["type"])
                link_map[key]["chapters"].append(r["chapter"])
                if r.get("description"):
                    link_map[key]["descriptions"].append(r["description"])

            links = []
            for l in link_map.values():
                chapter_count = len(l["chapters"])
                links.append({
                    "source": l["source"],
                    "target": l["target"],
                    "types": l["types"],
                    "chapters": l["chapters"],
                    "descriptions": l["descriptions"],
                    "name": "、".join(l["types"]),
                    "strength": min(1.0, chapter_count / 5.0),
                    "width": 1 + len(l["types"]) * 0.5,
                    "first_chapter": min(l["chapters"]),
                    "last_chapter": max(l["chapters"]),
                })

            return {"nodes": nodes, "links": links}

    @app.get("/api/relationship-events")
    def list_relationship_events(
        entity: Optional[str] = None,
        from_chapter: Optional[int] = None,
        to_chapter: Optional[int] = None,
        limit: int = 200,
    ):
        with closing(_get_db()) as conn:
            q = "SELECT * FROM relationship_events"
            params: list = []
            clauses: list[str] = []
            if entity:
                clauses.append("(from_entity = ? OR to_entity = ?)")
                params.extend([entity, entity])
            if from_chapter is not None:
                clauses.append("chapter >= ?")
                params.append(from_chapter)
            if to_chapter is not None:
                clauses.append("chapter <= ?")
                params.append(to_chapter)
            if clauses:
                q += " WHERE " + " AND ".join(clauses)
            q += " ORDER BY chapter DESC, id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/chapters")
    def list_chapters():
        with closing(_get_db()) as conn:
            rows = conn.execute("SELECT * FROM chapters ORDER BY chapter ASC").fetchall()
            return [dict(r) for r in rows]

    @app.post("/api/sync-chapters")
    def sync_chapters():
        """手动触发章节索引同步（从正文文件补全缺失章节）。"""
        return _sync_chapters_from_source(_project_root)

    @app.get("/api/scenes")
    def list_scenes(chapter: Optional[int] = None, limit: int = 500):
        with closing(_get_db()) as conn:
            if chapter is not None:
                rows = conn.execute(
                    "SELECT * FROM scenes WHERE chapter = ? ORDER BY scene_index ASC", (chapter,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM scenes ORDER BY chapter ASC, scene_index ASC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/reading-power")
    def list_reading_power(limit: int = 50):
        with closing(_get_db()) as conn:
            rows = conn.execute(
                "SELECT * FROM chapter_reading_power ORDER BY chapter DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/review-metrics")
    def list_review_metrics(limit: int = 20):
        with closing(_get_db()) as conn:
            rows = conn.execute(
                "SELECT * FROM review_metrics ORDER BY end_chapter DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/state-changes")
    def list_state_changes(entity: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if entity:
                rows = conn.execute(
                    "SELECT * FROM state_changes WHERE entity_id = ? ORDER BY chapter DESC LIMIT ?",
                    (entity, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM state_changes ORDER BY chapter DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    @app.get("/api/aliases")
    def list_aliases(entity: Optional[str] = None):
        with closing(_get_db()) as conn:
            if entity:
                rows = conn.execute(
                    "SELECT * FROM aliases WHERE entity_id = ?", (entity,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM aliases").fetchall()
            return [dict(r) for r in rows]

    # ===========================================================
    # API：扩展表（v5.3+ / v5.4+）
    # ===========================================================

    @app.get("/api/overrides")
    def list_overrides(status: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if status:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM override_contracts WHERE status = ? ORDER BY chapter DESC LIMIT ?",
                    (status, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM override_contracts ORDER BY chapter DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/debts")
    def list_debts(status: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if status:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM chase_debt WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                    (status, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM chase_debt ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/debt-events")
    def list_debt_events(debt_id: Optional[int] = None, limit: int = 200):
        with closing(_get_db()) as conn:
            if debt_id is not None:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM debt_events WHERE debt_id = ? ORDER BY chapter DESC, id DESC LIMIT ?",
                    (debt_id, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM debt_events ORDER BY chapter DESC, id DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/invalid-facts")
    def list_invalid_facts(status: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if status:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM invalid_facts WHERE status = ? ORDER BY marked_at DESC LIMIT ?",
                    (status, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM invalid_facts ORDER BY marked_at DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/rag-queries")
    def list_rag_queries(query_type: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if query_type:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM rag_query_log WHERE query_type = ? ORDER BY created_at DESC LIMIT ?",
                    (query_type, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM rag_query_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/tool-stats")
    def list_tool_stats(tool_name: Optional[str] = None, limit: int = 200):
        with closing(_get_db()) as conn:
            if tool_name:
                return _fetchall_safe(
                    conn,
                    "SELECT * FROM tool_call_stats WHERE tool_name = ? ORDER BY created_at DESC LIMIT ?",
                    (tool_name, limit),
                )
            return _fetchall_safe(
                conn,
                "SELECT * FROM tool_call_stats ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )

    @app.get("/api/checklist-scores")
    def list_checklist_scores(limit: int = 100):
        with closing(_get_db()) as conn:
            return _fetchall_safe(
                conn,
                "SELECT * FROM writing_checklist_scores ORDER BY chapter DESC LIMIT ?",
                (limit,),
            )

    # ===========================================================
    # API：文档浏览（正文/大纲/设定集 —— 只读）
    # ===========================================================

    @app.get("/api/files/tree")
    def file_tree():
        """列出 正文/、大纲/、设定集/ 三个目录的树结构。"""
        root = _get_project_root()
        result = {}
        for folder_name in ("正文", "大纲", "设定集"):
            folder = root / folder_name
            if not folder.is_dir():
                result[folder_name] = []
                continue
            result[folder_name] = _walk_tree(folder, root)
        return result

    @app.get("/api/files/read")
    def file_read(path: str):
        """只读读取一个文件内容（限 正文/大纲/设定集 目录）。"""
        root = _get_project_root()
        resolved = safe_resolve(root, path)

        # 二次限制：只允许三大目录
        allowed_parents = [root / n for n in ("正文", "大纲", "设定集")]
        if not any(_is_child(resolved, p) for p in allowed_parents):
            raise HTTPException(403, "仅允许读取 正文/大纲/设定集 目录下的文件")

        if not resolved.is_file():
            raise HTTPException(404, "文件不存在")

        # 文本文件直接读；其他情况返回占位信息
        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = "[二进制文件，无法预览]"

        return {"path": path, "content": content}

    # ===========================================================
    # SSE：实时变更推送
    # ===========================================================

    @app.get("/api/events")
    async def sse():
        """Server-Sent Events 端点，推送 .webnovel/ 下的文件变更。"""
        q = _watcher.subscribe()

        async def _gen():
            try:
                while True:
                    msg = await q.get()
                    yield f"data: {msg}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                _watcher.unsubscribe(q)

        return StreamingResponse(_gen(), media_type="text/event-stream")

    # ===========================================================
    # 前端静态文件托管
    # ===========================================================

    if STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

        @app.get("/{full_path:path}")
        def serve_spa(full_path: str):
            """SPA fallback：任何非 /api 路径都返回 index.html。"""
            index = STATIC_DIR / "index.html"
            if index.is_file():
                return FileResponse(str(index))
            raise HTTPException(404, "前端尚未构建")
    else:
        @app.get("/")
        def no_frontend():
            return HTMLResponse(
                "<h2>Webnovel Dashboard API is running</h2>"
                "<p>前端尚未构建。请先在 <code>dashboard/frontend</code> 目录执行 <code>npm run build</code>。</p>"
                '<p>API 文档：<a href="/docs">/docs</a></p>'
            )

    return app


# ---------------------------------------------------------------------------
# 章节自动同步（Dashboard 启动时 / 手动触发）
# ---------------------------------------------------------------------------

def _sync_chapters_from_source(project_root: Path | None) -> dict:
    """扫描正文目录，补全 index.db 中缺失的章节记录。

    返回 {"added": N, "skipped": N, "total": N, "errors": [...]}
    """
    if project_root is None:
        return {"added": 0, "skipped": 0, "total": 0, "errors": ["项目根目录未配置"]}

    db_path = project_root / ".webnovel" / "index.db"
    if not db_path.is_file():
        return {"added": 0, "skipped": 0, "total": 0, "errors": ["index.db 不存在"]}

    # 查找正文目录
    zhengwen_dir = project_root / "正文"
    if not zhengwen_dir.is_dir():
        return {"added": 0, "skipped": 0, "total": 0, "errors": ["正文目录不存在"]}

    # 递归收集所有 第*.md 文件
    md_files = sorted(zhengwen_dir.rglob("第*.md"))
    if not md_files:
        return {"added": 0, "skipped": 0, "total": 0, "errors": ["未找到正文章节文件"]}

    # 读取已有章节号
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        existing = set(r[0] for r in cursor.execute("SELECT chapter FROM chapters").fetchall())
    except sqlite3.OperationalError:
        existing = set()

    added = 0
    skipped = 0
    errors = []

    for mf in md_files:
        m = re.match(r"第(\d+)章", mf.name)
        if not m:
            continue
        ch_num = int(m.group(1))

        if ch_num in existing:
            skipped += 1
            continue

        try:
            content = mf.read_text(encoding="utf-8")
        except Exception as e:
            errors.append(f"Ch{ch_num}: 读取失败 {e}")
            continue

        # 提取标题
        first_line = content.split("\n")[0]
        title_match = re.match(r"# 第\d+章 (.+)", first_line)
        title = title_match.group(1).strip() if title_match else ""

        # 计算中文字数
        lines = content.split("\n")
        text_lines = [l for l in lines if l.strip() and not l.strip().startswith("#")]
        word_count = sum(
            len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", line))
            for line in text_lines
        )

        # 提取前 500 字作为摘要
        body_start = content.find("\n\n", content.find("\n", content.find("\n") + 1) + 1)
        if body_start == -1:
            body_start = 0
        else:
            body_start += 2
        summary = content[body_start:body_start + 500].strip().replace("\n", " ")

        content_hash = hashlib.md5(
            f"{title}||{word_count}|{summary}|0".encode("utf-8")
        ).hexdigest()

        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO chapters
                (chapter, title, location, word_count, characters, summary, content_hash, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (ch_num, title, "", word_count, "[]", summary, content_hash),
            )
            added += 1
        except Exception as e:
            errors.append(f"Ch{ch_num}: 写入失败 {e}")

    conn.commit()
    total = cursor.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    conn.close()

    return {"added": added, "skipped": skipped, "total": total, "errors": errors}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _walk_tree(folder: Path, root: Path) -> list[dict]:
    items = []
    for child in sorted(folder.iterdir()):
        rel = str(child.relative_to(root)).replace("\\", "/")
        if child.is_dir():
            items.append({"name": child.name, "type": "dir", "path": rel, "children": _walk_tree(child, root)})
        else:
            items.append({"name": child.name, "type": "file", "path": rel, "size": child.stat().st_size})
    return items


def _is_child(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
