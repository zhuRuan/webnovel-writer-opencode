"""
Webnovel Dashboard - FastAPI 主应用

仅提供 GET 接口（严格只读）；所有文件读取经过 path_guard 防穿越校验。
"""

import asyncio
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
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

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
STATIC_DIR = Path(__file__).parent / "frontend" / "dist"

_ACTION_RATE_LIMIT: dict[str, float] = {}  # action → last invoke timestamp


def _get_project_root() -> Path:
    if _project_root is None:
        raise HTTPException(status_code=500, detail="项目根目录未配置")
    return _project_root


def _webnovel_dir() -> Path:
    return _get_project_root() / ".webnovel"


def _story_system_dir() -> Path:
    return _get_project_root() / ".story-system"


def _build_story_runtime_health_report(project_root: Path) -> dict:
    from data_modules.story_runtime_health import build_story_runtime_health

    return build_story_runtime_health(project_root)


def _ensure_scripts_dir_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    scripts_entry = str(scripts_dir)
    if scripts_entry not in sys.path:
        sys.path.append(scripts_entry)


def _load_state_payload(*, required: bool = False) -> dict:
    state_path = _webnovel_dir() / "state.json"
    if not state_path.is_file():
        if required:
            raise HTTPException(404, "state.json 不存在")
        return {}

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"state.json 读取失败: {exc}") from exc

    return payload if isinstance(payload, dict) else {}


def _parse_json_value(raw: object, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _resolve_volume_for_chapter(state: dict, chapter: int) -> int | None:
    progress = state.get("progress") if isinstance(state, dict) else {}
    if not isinstance(progress, dict):
        return None
    volumes_planned = progress.get("volumes_planned")
    if not isinstance(volumes_planned, list):
        return None

    best: tuple[int, int] | None = None
    for item in volumes_planned:
        if not isinstance(item, dict):
            continue
        volume = item.get("volume")
        if not isinstance(volume, int) or volume <= 0:
            continue
        chapter_range = str(item.get("chapters_range") or "").strip()
        if "-" not in chapter_range:
            continue
        left, _, right = chapter_range.partition("-")
        try:
            start = int(left.strip())
            end = int(right.strip())
        except ValueError:
            continue
        if start <= 0 or end <= 0 or start > end:
            continue
        if start <= chapter <= end:
            candidate = (start, volume)
            if best is None or candidate[0] > best[0] or (
                candidate[0] == best[0] and candidate[1] < best[1]
            ):
                best = candidate
    return best[1] if best else None


def _build_strand_map(state: dict) -> dict[int, str]:
    tracker = state.get("strand_tracker") if isinstance(state, dict) else {}
    history = tracker.get("history") if isinstance(tracker, dict) else []
    if not isinstance(history, list):
        return {}

    strand_map: dict[int, str] = {}
    for index, entry in enumerate(history, start=1):
        if not isinstance(entry, dict):
            continue
        chapter_value = entry.get("chapter", index)
        try:
            chapter = int(chapter_value)
        except (TypeError, ValueError):
            chapter = index
        strand = str(entry.get("strand") or entry.get("dominant") or "").strip().lower()
        if chapter > 0 and strand and chapter not in strand_map:
            strand_map[chapter] = strand
    return strand_map


def _extract_story_chapter(path: Path) -> int:
    stem = path.stem
    if "_" not in stem:
        return 0
    _, _, tail = stem.partition("_")
    try:
        return int(tail.split(".")[0])
    except ValueError:
        return 0


def _inspect_vector_db(project_root: Path) -> dict:
    from data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(project_root)
    vector_db = cfg.vector_db
    exists = vector_db.is_file()
    size_bytes = vector_db.stat().st_size if exists else 0
    record_count = 0
    error = ""

    if exists and size_bytes > 0:
        try:
            with sqlite3.connect(str(vector_db)) as conn:
                cursor = conn.cursor()
                table_exists = cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'vectors'"
                ).fetchone()
                if table_exists:
                    row = cursor.execute("SELECT COUNT(*) FROM vectors").fetchone()
                    record_count = int(row[0] or 0) if row else 0
        except sqlite3.Error as exc:
            error = str(exc)

    return {
        "path": str(vector_db),
        "exists": exists,
        "size_bytes": size_bytes,
        "record_count": record_count,
        "error": error,
    }


def _build_env_status(project_root: Path) -> dict:
    from data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(project_root)
    vector_info = _inspect_vector_db(project_root)

    embed_ready = bool(str(cfg.embed_api_key or "").strip())
    rerank_ready = bool(str(cfg.rerank_api_key or "").strip())
    vector_ready = bool(vector_info["exists"] and vector_info["size_bytes"] > 0)

    if vector_ready and embed_ready and rerank_ready:
        rag_mode = "full"
    elif vector_ready and embed_ready:
        rag_mode = "embed_only"
    else:
        rag_mode = "bm25_only"

    return {
        "embed": {
            "base_url": cfg.embed_base_url,
            "model": cfg.embed_model,
            "api_key_present": embed_ready,
        },
        "rerank": {
            "base_url": cfg.rerank_base_url,
            "model": cfg.rerank_model,
            "api_key_present": rerank_ready,
        },
        "vector_db": vector_info,
        "rag_mode": rag_mode,
    }


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------

def create_app(project_root: str | Path | None = None) -> FastAPI:
    global _project_root

    if project_root:
        if _project_root is not None:
            import warnings
            warnings.warn(f"Dashboard project_root 被覆盖: {_project_root} → {project_root}", stacklevel=2)
        _project_root = Path(project_root).resolve()

    _ensure_scripts_dir_on_path()

    @asynccontextmanager
    async def _lifespan(_: FastAPI):
        webnovel = _webnovel_dir()
        story_system = _story_system_dir()
        if webnovel.is_dir() or story_system.is_dir():
            _watcher.start(
                watch_webnovel_dir=webnovel if webnovel.is_dir() else None,
                watch_story_system_dir=story_system if story_system.is_dir() else None,
                loop=asyncio.get_running_loop(),
            )

        async def _polling_loop():
            """Periodically push workflow and debt status to SSE clients."""
            while True:
                try:
                    await asyncio.sleep(30)
                    if not _watcher._subscribers:
                        continue
                    try:
                        from data_modules.workflow_checkpoint import all_chapters_progress
                        wf = all_chapters_progress(_get_project_root())
                        _watcher._dispatch(json.dumps({"type": "workflow-status", "data": wf, "ts": time.time()}))
                    except Exception:
                        pass
                except asyncio.CancelledError:
                    break

        poll_task = asyncio.create_task(_polling_loop())
        try:
            yield
        finally:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
            _watcher.stop()

    app = FastAPI(title="Webnovel Dashboard", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # ===========================================================
    # API：项目元信息
    # ===========================================================

    @app.get("/api/project/info")
    def project_info():
        """返回 state.json 完整内容（只读）。"""
        return _load_state_payload(required=True)

    @app.get("/api/story-runtime/health")
    def story_runtime_health():
        return _build_story_runtime_health_report(_get_project_root())

    # ===========================================================
    # API：实体数据库（index.db 只读查询）
    # ===========================================================

    def _get_db() -> sqlite3.Connection:
        db_path = _webnovel_dir() / "index.db"
        if not db_path.is_file():
            raise HTTPException(404, "index.db 不存在")
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _fetchall_safe(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
        """执行只读查询；若目标表不存在（旧库），返回空列表。"""
        try:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower() or "no such column" in str(exc).lower():
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
            rows = _fetchall_safe(conn, q, tuple(params))
            return [dict(r) for r in rows]

    @app.get("/api/entities/{entity_id}")
    def get_entity(entity_id: str):
        with closing(_get_db()) as conn:
            rows = _fetchall_safe(conn, "SELECT * FROM entities WHERE id = ?", (entity_id,))
            if not rows:
                raise HTTPException(404, "实体不存在")
            return rows[0]

    @app.get("/api/relationships")
    def list_relationships(entity: Optional[str] = None, limit: int = 200):
        with closing(_get_db()) as conn:
            if entity:
                return _fetchall_safe(conn,
                    "SELECT * FROM relationships WHERE from_entity = ? OR to_entity = ? ORDER BY chapter DESC LIMIT ?",
                    (entity, entity, limit))
            return _fetchall_safe(conn,
                "SELECT * FROM relationships ORDER BY chapter DESC LIMIT ?", (limit,))

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
            return _fetchall_safe(conn, q, tuple(params))

    @app.get("/api/chapters")
    def list_chapters():
        with closing(_get_db()) as conn:
            rows = _fetchall_safe(conn, "SELECT * FROM chapters ORDER BY chapter ASC")
            return [{**r, "characters": _parse_json_value(r.get("characters"), [])} for r in rows]

    @app.get("/api/scenes")
    def list_scenes(chapter: Optional[int] = None, limit: int = 500):
        with closing(_get_db()) as conn:
            if chapter is not None:
                return _fetchall_safe(conn,
                    "SELECT * FROM scenes WHERE chapter = ? ORDER BY scene_index ASC", (chapter,))
            return _fetchall_safe(conn,
                "SELECT * FROM scenes ORDER BY chapter ASC, scene_index ASC LIMIT ?", (limit,))

    @app.get("/api/reading-power")
    def list_reading_power(limit: int = 50):
        with closing(_get_db()) as conn:
            return _fetchall_safe(conn,
                "SELECT * FROM chapter_reading_power ORDER BY chapter DESC LIMIT ?", (limit,))

    @app.get("/api/review-metrics")
    def list_review_metrics(limit: int = 20):
        with closing(_get_db()) as conn:
            rows = _fetchall_safe(conn,
                "SELECT * FROM review_metrics ORDER BY end_chapter DESC LIMIT ?", (limit,))
            return [{**r,
                "dimension_scores": _parse_json_value(r.get("dimension_scores"), {}),
                "severity_counts": _parse_json_value(r.get("severity_counts"), {}),
                "critical_issues": _parse_json_value(r.get("critical_issues"), [])}
                for r in rows]

    @app.get("/api/stats/chapter-trend")
    def chapter_trend(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        state = _load_state_payload()
        strand_map = _build_strand_map(state)

        with closing(_get_db()) as conn:
            total_rows = _fetchall_safe(conn, "SELECT COUNT(*) AS count FROM chapters")
            latest_rows = _fetchall_safe(conn, "SELECT MAX(chapter) AS chapter FROM chapters")
            rows = _fetchall_safe(
                conn,
                """
                WITH selected_chapters AS (
                    SELECT chapter, title, location, word_count, characters, summary
                    FROM chapters
                    ORDER BY chapter DESC
                    LIMIT ? OFFSET ?
                )
                SELECT
                    c.chapter,
                    c.title,
                    c.location,
                    c.word_count,
                    c.characters,
                    c.summary,
                    rp.hook_type,
                    rp.hook_strength,
                    rp.is_transition,
                    rp.override_count,
                    rp.debt_balance,
                    rm.overall_score AS review_score,
                    rm.severity_counts
                FROM selected_chapters c
                LEFT JOIN chapter_reading_power rp ON rp.chapter = c.chapter
                LEFT JOIN review_metrics rm ON rm.end_chapter = c.chapter
                ORDER BY c.chapter ASC
                """,
                (limit, offset),
            )

        hook_strength_value = {"weak": 1, "medium": 3, "strong": 5}
        items = []
        for row in rows:
            chapter = int(row.get("chapter") or 0)
            hook_strength = str(row.get("hook_strength") or "").strip().lower()
            items.append(
                {
                    "chapter": chapter,
                    "title": row.get("title") or "",
                    "location": row.get("location") or "",
                    "word_count": int(row.get("word_count") or 0),
                    "characters": _parse_json_value(row.get("characters"), []),
                    "summary": row.get("summary") or "",
                    "review_score": row.get("review_score"),
                    "review_severity_counts": _parse_json_value(row.get("severity_counts"), {}),
                    "hook_type": row.get("hook_type") or "",
                    "hook_strength": hook_strength,
                    "hook_strength_value": hook_strength_value.get(hook_strength, 0),
                    "is_transition": bool(row.get("is_transition")),
                    "override_count": int(row.get("override_count") or 0),
                    "debt_balance": float(row.get("debt_balance") or 0.0),
                    "strand": strand_map.get(chapter, ""),
                    "volume": _resolve_volume_for_chapter(state, chapter),
                }
            )

        return {
            "items": items,
            "total": int(total_rows[0]["count"] or 0) if total_rows else 0,
            "latest_chapter": int(latest_rows[0]["chapter"] or 0) if latest_rows else 0,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/commits")
    def list_commits(limit: int = Query(20, ge=1, le=200)):
        commits_dir = _story_system_dir() / "commits"
        if not commits_dir.is_dir():
            return {"items": [], "total": 0, "limit": limit}

        items = []
        for path in commits_dir.glob("chapter_*.commit.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            meta = payload.get("meta") if isinstance(payload, dict) else {}
            provenance = payload.get("provenance") if isinstance(payload, dict) else {}
            chapter = int((meta or {}).get("chapter") or _extract_story_chapter(path))
            items.append(
                {
                    "chapter": chapter,
                    "status": str((meta or {}).get("status") or "missing"),
                    "projection_status": payload.get("projection_status") or {},
                    "write_fact_role": str((provenance or {}).get("write_fact_role") or ""),
                    "contract_refs": payload.get("contract_refs") or {},
                    "path": path.name,
                    "updated_at": datetime.fromtimestamp(
                        path.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
            )

        items.sort(key=lambda item: item["chapter"], reverse=True)
        return {"items": items[:limit], "total": len(items), "limit": limit}

    @app.get("/api/contracts/summary")
    def contracts_summary():
        from data_modules.story_contracts import StoryContractPaths, read_json_if_exists

        project_root = _get_project_root()
        state = _load_state_payload()
        runtime = _build_story_runtime_health_report(project_root)
        chapter = int(runtime.get("chapter") or ((state.get("progress") or {}).get("current_chapter") or 0))
        current_volume = _resolve_volume_for_chapter(state, chapter) or int(
            ((state.get("progress") or {}).get("current_volume") or 1)
        )

        paths = StoryContractPaths.from_project_root(project_root)
        master_payload = read_json_if_exists(paths.master_json) or {}

        return {
            "chapter": chapter,
            "current_volume": current_volume,
            "master": {
                "exists": bool(master_payload),
                "primary_genre": str(((master_payload.get("route") or {}).get("primary_genre") or "")),
                "core_tone": str(
                    ((master_payload.get("master_constraints") or {}).get("core_tone") or "")
                ),
            },
            "counts": {
                "volumes": len(list(paths.volumes_dir.glob("volume_*.json"))) if paths.volumes_dir.is_dir() else 0,
                "chapters": len(list(paths.chapters_dir.glob("chapter_*.json"))) if paths.chapters_dir.is_dir() else 0,
                "reviews": len(list(paths.reviews_dir.glob("chapter_*.review.json"))) if paths.reviews_dir.is_dir() else 0,
                "commits": len(list(paths.commits_dir.glob("chapter_*.commit.json"))) if paths.commits_dir.is_dir() else 0,
            },
            "current_contracts": {
                "volume": paths.volume_json(current_volume).is_file(),
                "chapter": paths.chapter_json(chapter).is_file() if chapter > 0 else False,
                "review": paths.review_json(chapter).is_file() if chapter > 0 else False,
                "commit": paths.commit_json(chapter).is_file() if chapter > 0 else False,
            },
        }

    @app.get("/api/env-status")
    def env_status():
        return _build_env_status(_get_project_root())

    @app.get("/api/env-status/probe")
    def env_status_probe():
        status = _build_env_status(_get_project_root())
        runtime = _build_story_runtime_health_report(_get_project_root())
        vector_db = status["vector_db"]
        checks = [
            {
                "name": "embed_api_key",
                "ok": bool(status["embed"]["api_key_present"]),
                "detail": "已配置" if status["embed"]["api_key_present"] else "未配置",
            },
            {
                "name": "rerank_api_key",
                "ok": bool(status["rerank"]["api_key_present"]),
                "detail": "已配置" if status["rerank"]["api_key_present"] else "未配置",
            },
            {
                "name": "vector_db",
                "ok": bool(vector_db["exists"] and not vector_db["error"]),
                "detail": vector_db["error"]
                or f"{vector_db['record_count']} records · {vector_db['size_bytes']} bytes",
            },
            {
                "name": "story_runtime",
                "ok": bool(runtime.get("mainline_ready")),
                "detail": (
                    f"chapter={runtime.get('chapter')} "
                    f"status={runtime.get('latest_commit_status')} "
                    f"fallback={','.join(runtime.get('fallback_sources') or []) or 'none'}"
                ),
            },
        ]
        return {
            "ok": all(bool(item["ok"]) for item in checks),
            "rag_mode": status["rag_mode"],
            "checks": checks,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/state-changes")
    def list_state_changes(entity: Optional[str] = None, limit: int = 100):
        with closing(_get_db()) as conn:
            if entity:
                return _fetchall_safe(conn,
                    "SELECT * FROM state_changes WHERE entity_id = ? ORDER BY chapter DESC LIMIT ?",
                    (entity, limit))
            return _fetchall_safe(conn,
                "SELECT * FROM state_changes ORDER BY chapter DESC LIMIT ?", (limit,))

    @app.get("/api/aliases")
    def list_aliases(entity: Optional[str] = None):
        with closing(_get_db()) as conn:
            if entity:
                return _fetchall_safe(conn,
                    "SELECT * FROM aliases WHERE entity_id = ?", (entity,))
            return _fetchall_safe(conn, "SELECT * FROM aliases")

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

    @app.get("/api/story-events")
    def list_story_events(chapter: Optional[int] = None, limit: int = 200):
        with closing(_get_db()) as conn:
            if chapter is not None:
                rows = _fetchall_safe(
                    conn,
                    """
                    SELECT event_id, chapter, event_type, subject, payload_json, created_at
                    FROM story_events
                    WHERE chapter = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (chapter, limit),
                )
            else:
                rows = _fetchall_safe(
                    conn,
                    """
                    SELECT event_id, chapter, event_type, subject, payload_json, created_at
                    FROM story_events
                    ORDER BY chapter DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

        normalized = []
        for row in rows:
            payload = {}
            try:
                payload = json.loads(row.get("payload_json") or "{}")
            except json.JSONDecodeError:
                payload = {}
            normalized.append({**row, "payload": payload})
        return normalized

    @app.get("/api/story-events/health")
    def story_event_health():
        with closing(_get_db()) as conn:
            event_rows = _fetchall_safe(conn, "SELECT COUNT(*) AS count FROM story_events")
            proposal_rows = _fetchall_safe(
                conn,
                """
                SELECT COUNT(*) AS count
                FROM override_contracts
                WHERE record_type = 'amend_proposal' AND status = 'pending'
                """,
            )

        events_dir = _story_system_dir() / "events"
        file_count = len(list(events_dir.glob("chapter_*.events.json"))) if events_dir.is_dir() else 0
        return {
            "story_events": event_rows[0]["count"] if event_rows else 0,
            "pending_amend_proposals": proposal_rows[0]["count"] if proposal_rows else 0,
            "event_files": file_count,
        }

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
        """Server-Sent Events 端点，推送 .webnovel/.story-system 的文件变更。"""
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
    # API：写作进度与监控
    # ===========================================================

    @app.get("/api/workflow/status")
    def workflow_status():
        from data_modules.workflow_checkpoint import all_chapters_progress

        return all_chapters_progress(_get_project_root())

    @app.get("/api/context/budget/{chapter}")
    def context_budget(chapter: int):
        trace_file = _webnovel_dir() / "runtime" / f"chapter-{chapter:03d}.trace.json"
        if not trace_file.is_file():
            raise HTTPException(404, "trace 文件不存在")
        return json.loads(trace_file.read_text(encoding="utf-8"))

    # ===========================================================
    # API：质量预警
    # ===========================================================

    def _get_recent_review_scores(project_root: Path, n: int = 5) -> list[dict]:
        db_path = project_root / ".webnovel" / "index.db"
        if not db_path.is_file():
            return []
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT end_chapter, overall_score FROM review_metrics ORDER BY end_chapter DESC LIMIT ?",
                (n,),
            ).fetchall()
            return [{"chapter": r["end_chapter"], "score": r["overall_score"]} for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    @staticmethod
    def _is_declining(scores: list[dict], threshold: int = 3) -> bool:
        if len(scores) < threshold:
            return False
        recent = scores[:threshold]
        return all(
            recent[i]["score"] is not None and recent[i + 1]["score"] is not None
            and (recent[i]["score"] or 0) < (recent[i + 1]["score"] or 0)
            for i in range(len(recent) - 1)
        )

    def _get_overdue_debts(project_root: Path, current_chapter: int) -> list[dict]:
        db_path = project_root / ".webnovel" / "index.db"
        if not db_path.is_file():
            return []
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT id, note, due_chapter, source_chapter FROM chase_debt WHERE status = 'pending' AND due_chapter < ?",
                (current_chapter,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def _get_long_absent_characters(project_root: Path, current_chapter: int, threshold: int = 20) -> list[dict]:
        db_path = project_root / ".webnovel" / "index.db"
        if not db_path.is_file():
            return []
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT id, canonical_name, last_appearance FROM entities WHERE is_archived = 0 AND (? - last_appearance) > ?",
                (current_chapter, threshold),
            ).fetchall()
            return [{"id": r["id"], "name": r["canonical_name"],
                     "absent_chapters": current_chapter - int(r["last_appearance"] or 0)} for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    @app.get("/api/alerts")
    def get_alerts():
        state = _load_state_payload()
        progress = state.get("progress") if isinstance(state, dict) else {}
        current_chapter = int(progress.get("current_chapter") or 0)
        project_root = _get_project_root()
        alerts = []

        # Score decline
        recent = _get_recent_review_scores(project_root, 5)
        if _is_declining(recent, threshold=3):
            alerts.append({"type": "score_decline", "severity": "warning",
                           "detail": f"连续{len(recent)}章审查分下降", "chapters": recent})

        # Overdue debts
        overdue = _get_overdue_debts(project_root, current_chapter)
        for d in overdue:
            alerts.append({"type": "debt_overdue", "severity": "critical",
                           "detail": d.get("note", ""), "due_chapter": d.get("due_chapter", 0)})

        # Long-absent characters
        absent = _get_long_absent_characters(project_root, current_chapter)
        for c in absent:
            alerts.append({"type": "character_absent", "severity": "info",
                           "detail": f"{c['name']} 已 {c['absent_chapters']} 章未出场"})

        # Strand monotony
        strand_map = _build_strand_map(state)
        recent_chapters = sorted(strand_map.keys(), reverse=True)[:5]
        if len(recent_chapters) >= 5:
            recent_strands = [strand_map.get(ch, "") for ch in recent_chapters]
            if len(set(recent_strands)) == 1 and recent_strands[0]:
                alerts.append({"type": "strand_monotony", "severity": "info",
                               "detail": f"连续 5 章同一主线: {recent_strands[0]}"})

        # Sort by severity
        sev_order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda a: sev_order.get(a.get("severity", "info"), 2))

        return {"alerts": alerts, "updated_at": datetime.now(timezone.utc).isoformat()}

    # ===========================================================
    # API：文风约束编辑（读写）
    # ===========================================================

    def _master_setting_path() -> Path:
        return _get_project_root() / ".story-system" / "MASTER_SETTING.json"

    def _anti_patterns_path() -> Path:
        return _get_project_root() / ".story-system" / "anti_patterns.json"

    def _atomic_write_json(path: Path, data: Any) -> None:
        """原子写入 JSON 文件（带备份）。"""
        try:
            from security_utils import atomic_write_json as _aw
        except ImportError:
            from scripts.security_utils import atomic_write_json as _aw
        _aw(path, data, backup=True)

    def _locked_anti_patterns():
        """返回 anti_patterns.json 的文件锁上下文管理器。"""
        import filelock
        lock_path = _anti_patterns_path().with_suffix(".json.lock")
        return filelock.FileLock(str(lock_path), timeout=5)

    @app.get("/api/style/master-setting")
    def get_master_setting():
        """读取 MASTER_SETTING.json。"""
        path = _master_setting_path()
        if not path.is_file():
            raise HTTPException(404, "MASTER_SETTING.json 不存在")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.put("/api/style/master-setting")
    def update_master_setting(request: dict):
        """更新 master_constraints 字段。locked 字段不允许修改。"""
        path = _master_setting_path()
        if not path.is_file():
            raise HTTPException(404, "MASTER_SETTING.json 不存在")

        current = json.loads(path.read_text(encoding="utf-8"))
        constraints = request.get("master_constraints")
        if not isinstance(constraints, dict):
            raise HTTPException(400, "缺少 master_constraints 字段")

        # 检查 locked 字段
        locked = (current.get("override_policy") or {}).get("locked") or []
        for key in constraints:
            if f"master_constraints.{key}" in locked:
                raise HTTPException(403, f"字段 {key} 已锁定，不允许修改")

        current.setdefault("master_constraints", {}).update(constraints)
        _atomic_write_json(path, current)

        # 触发 SSE 通知
        try:
            _watcher._dispatch(json.dumps({
                "type": "style-updated", "layer": "master-setting", "ts": time.time(),
            }))
        except Exception:
            pass

        return {"ok": True, "master_constraints": current["master_constraints"]}

    @app.get("/api/style/anti-patterns")
    def get_anti_patterns():
        """读取 anti_patterns.json。"""
        path = _anti_patterns_path()
        if not path.is_file():
            return {"patterns": []}
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"patterns": data if isinstance(data, list) else []}

    @app.post("/api/style/anti-patterns")
    def add_anti_pattern(request: dict):
        """追加新反模式（带文件锁防并发）。"""
        text = (request.get("text") or "").strip()
        if not text:
            raise HTTPException(400, "text 不能为空")

        path = _anti_patterns_path()
        with _locked_anti_patterns():
            existing = []
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                existing = data if isinstance(data, list) else []

            # 去重
            seen = {str(item.get("text", "")).strip() for item in existing if isinstance(item, dict)}
            if text in seen:
                raise HTTPException(409, "该反模式已存在")

            entry = {
                "text": text,
                "source_table": "dashboard_manual",
                "source_id": f"manual_{int(time.time())}",
                "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            existing.append(entry)
            _atomic_write_json(path, existing)

        try:
            _watcher._dispatch(json.dumps({
                "type": "style-updated", "layer": "anti-patterns", "ts": time.time(),
            }))
        except Exception:
            pass

        return {"ok": True, "entry": entry, "total": len(existing)}

    @app.post("/api/style/anti-patterns/delete")
    def delete_anti_pattern(request: dict):
        """按文本内容删除反模式（带文件锁防并发）。"""
        text = (request.get("text") or "").strip()
        if not text:
            raise HTTPException(400, "text 不能为空")

        path = _anti_patterns_path()
        if not path.is_file():
            raise HTTPException(404, "anti_patterns.json 不存在")

        with _locked_anti_patterns():
            data = json.loads(path.read_text(encoding="utf-8"))
            existing = data if isinstance(data, list) else []
            new_list = [item for item in existing
                        if not (isinstance(item, dict) and str(item.get("text", "")).strip() == text)]
            if len(new_list) == len(existing):
                raise HTTPException(404, f"未找到反模式: {text}")
            _atomic_write_json(path, new_list)

        try:
            _watcher._dispatch(json.dumps({
                "type": "style-updated", "layer": "anti-patterns", "ts": time.time(),
            }))
        except Exception:
            pass

        return {"ok": True, "removed_text": text, "total": len(new_list)}

    # ===========================================================
    # API：文风约束只读数据
    # ===========================================================

    @app.get("/api/style/techniques")
    def get_techniques():
        """读取写作技法 CSV。"""
        # 从 dashboard 模块位置推导仓库根目录（.opencode/dashboard/app.py → .opencode/）
        opencode_dir = Path(__file__).resolve().parent.parent
        csv_path = opencode_dir / "references" / "csv" / "写作技法.csv"
        if not csv_path.is_file():
            for candidate in [
                _get_project_root() / ".opencode" / "references" / "csv" / "写作技法.csv",
                Path.cwd() / ".opencode" / "references" / "csv" / "写作技法.csv",
            ]:
                if candidate.is_file():
                    csv_path = candidate
                    break
        if not csv_path.is_file():
            return {"techniques": []}

        import csv as csv_mod
        techniques = []
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                techniques.append({
                    "id": row.get("编号", ""),
                    "category": row.get("分类", ""),
                    "name": row.get("技法名称", ""),
                    "summary": row.get("核心摘要", ""),
                    "instruction": row.get("大模型指令", ""),
                    "keywords": row.get("关键词", ""),
                    "pitfalls": row.get("毒点", ""),
                    "positive_example": row.get("正例", ""),
                    "negative_example": row.get("反例", ""),
                    "applicable_genre": row.get("适用题材", ""),
                    "scene": row.get("适用场景", ""),
                })
        return {"techniques": techniques}

    @app.get("/api/style/chapters")
    def list_chapter_contracts():
        """列出所有章级合同摘要。"""
        chapters_dir = _get_project_root() / ".story-system" / "chapters"
        if not chapters_dir.is_dir():
            return {"chapters": []}

        import re as re_mod
        result = []
        for f in sorted(chapters_dir.glob("chapter_*.json")):
            m = re_mod.search(r"chapter_(\d+)\.json$", f.name)
            if not m:
                continue
            ch_num = int(m.group(1))
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                directive = data.get("chapter_directive") or {}
                result.append({
                    "chapter": ch_num,
                    "goal": str(directive.get("goal", ""))[:100],
                    "time_anchor": directive.get("time_anchor", ""),
                    "strand": directive.get("strand", ""),
                    "hook_type": directive.get("hook_type", ""),
                    "hook_strength": directive.get("hook_strength", ""),
                })
            except Exception:
                result.append({"chapter": ch_num, "goal": "(读取失败)", "time_anchor": "", "strand": "", "hook_type": "", "hook_strength": ""})
        return {"chapters": result}

    @app.get("/api/style/chapters/{chapter}")
    def get_chapter_contract(chapter: int):
        """读取单章合同详情。"""
        chapters_dir = _get_project_root() / ".story-system" / "chapters"
        if not chapters_dir.is_dir():
            raise HTTPException(404, "章级合同目录不存在")

        # 尝试多种格式
        for pattern in [f"chapter_{chapter:03d}.json", f"chapter_{chapter:04d}.json", f"chapter_{chapter}.json"]:
            path = chapters_dir / pattern
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))

        raise HTTPException(404, f"第 {chapter} 章合同不存在")

    @app.get("/api/style/reviewer-checklist")
    def get_reviewer_checklist():
        """读取审查维度清单。"""
        checklist = [
            {"dimension": "设定一致性", "content": "角色状态/世界规则/物品属性是否与 state.json 一致", "format": "[设定]: pass 或 发现N个问题(简述)", "must_bash": True},
            {"dimension": "时间线", "content": "事件顺序/时间跨度是否合理", "format": "[时间线]: pass 或 发现N个问题(简述)", "must_bash": True},
            {"dimension": "叙事连贯", "content": "视角是否统一/场景切换是否有过渡", "format": "[连贯]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "角色一致性", "content": "对话风格/行为动机是否符合人设", "format": "[角色]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "逻辑", "content": "因果关系/行为后果是否合理", "format": "[逻辑]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "AI味-词汇", "content": "缓缓/淡淡/微微/眸中/瞳孔 密度", "format": "[AI味-词汇]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "AI味-句式", "content": "三段闭环/同构句/总结句/碎片句", "format": "[AI味-句式]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "AI味-叙事", "content": "匀速节奏/戏剧性反讽/安全着陆", "format": "[AI味-叙事]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "AI味-情感", "content": "标签化情绪/即时切换", "format": "[AI味-情感]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "AI味-对话", "content": "信息宣讲/书面语", "format": "[AI味-对话]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "项目规则", "content": "破折号≤20、但≤6、不是X是Y≤1、句号≤70/千字、系统【】格式", "format": "[规则]: pass 或 发现N个问题(简述)", "must_bash": True},
            {"dimension": "节奏", "content": "章首钩子/中段脉冲/章末锚点/段长变化", "format": "[节奏]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "毒点", "content": "降智推进/强行误会/圣母无代价/工具人配角/双标裁决", "format": "[毒点]: pass 或 发现N个问题(简述)", "must_bash": False},
        ]
        # 也返回 anti_patterns
        ap_path = _anti_patterns_path()
        anti_patterns = []
        if ap_path.is_file():
            try:
                data = json.loads(ap_path.read_text(encoding="utf-8"))
                anti_patterns = data if isinstance(data, list) else []
            except Exception:
                pass
        return {"checklist": checklist, "anti_patterns": anti_patterns}

    # ===========================================================
    # API：运维操作（安全写入口）
    # ===========================================================

    _ACTIONS = {
        "ssot-verify": ["ssot", "verify"],
        "ssot-rebuild": ["ssot", "rebuild"],
        "entity-clean": ["entity-clean", "--mark-invalid"],
    }

    @app.post("/api/actions/{action}")
    def run_action(action: str):
        """Execute a low-risk CLI action and return output."""
        if action not in _ACTIONS:
            raise HTTPException(403, f"不允许的操作: {action}")

        # Rate limit: 1 per second per action
        now = time.time()
        last = _ACTION_RATE_LIMIT.get(action, 0)
        if now - last < 1.0:
            raise HTTPException(429, "操作过于频繁，请稍后再试")
        _ACTION_RATE_LIMIT[action] = now

        cmd = [
            sys.executable, "-X", "utf8",
            str(SCRIPTS_DIR / "webnovel.py"),
            "--project-root", str(_get_project_root()),
            *_ACTIONS[action],
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, "操作超时（30s）")

        # Push SSE event to notify frontend
        try:
            _watcher._dispatch(json.dumps({
                "type": "action-done", "action": action,
                "code": result.returncode, "ts": time.time(),
            }))
        except Exception:
            pass

        return {
            "action": action,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "code": result.returncode,
        }

    # ===========================================================
    # 前端静态文件托管
    # ===========================================================

    if STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

        @app.get("/{full_path:path}")
        def serve_spa(full_path: str):
            """SPA fallback：任何非 /api 路径都返回 index.html。"""
            if full_path.startswith("api/"):
                raise HTTPException(404, "API 路径不存在")
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
# 辅助函数
# ---------------------------------------------------------------------------

def _walk_tree(folder: Path, root: Path) -> list[dict]:
    items = []
    for child in sorted(folder.iterdir()):
        if child.is_symlink():
            continue
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
