"""
Webnovel Dashboard - FastAPI 主应用

仅提供 GET 接口（严格只读）；所有文件读取经过 path_guard 防穿越校验。
"""

import asyncio
import gc
import json
import logging
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .routers.files import router as files_router, set_files_router_watcher
from .routers.review import router as review_router
from .routers.extended import router as extended_router
from .watcher import FileWatcher

# ── Ensure scripts directory is on sys.path before DAO imports ──
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[1] / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from data_modules.dao import get_dao  # noqa: E402
from data_modules.dao.entity_dao import EntityDAO  # noqa: E402
from data_modules.dao.character_event_dao import CharacterEventDAO  # noqa: E402
from data_modules.dao.knowledge_dao import KnowledgeDAO  # noqa: E402
from data_modules.dao.faction_dao import FactionDAO  # noqa: E402
from data_modules.dao.relationship_dao import RelationshipDAO  # noqa: E402
from data_modules.dao.memory_dao import MemoryDAO  # noqa: E402
from data_modules.dao.state_dao import StateDAO  # noqa: E402
from data_modules.dao.director_dao import DirectorDAO  # noqa: E402
from data_modules.dao.chapter_dao import ChapterDAO  # noqa: E402
from data_modules.dao.process_dao import ProcessDAO  # noqa: E402
from data_modules.dao.style_collector_dao import StyleCollectorDAO  # noqa: E402

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
_project_root: Path | None = None
_watcher = FileWatcher()

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
STATIC_DIR = Path(__file__).parent / "frontend" / "dist"

_ACTION_RATE_LIMIT: dict[str, float] = {}  # action → last invoke timestamp

_collection_tasks: dict[str, asyncio.Task] = {}
_vacuum_lock: asyncio.Lock | None = None  # Initialized in lifespan


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


async def _analyze_chapters(chapters: list[dict], task_id: str,
                             dao: StyleCollectorDAO, db_path: str,
                             dispatch_callback: Callable | None = None):
    """Async generator yielding individual chapter analysis results as they complete.

    Uses asyncio.as_completed() within each batch so results are yielded
    incrementally instead of accumulating all in memory. Peak memory for
    analysis results is bounded by batch_size (50), not total chapters.
    """
    import os as _os
    from .services.style_analyzer import analyze_chapter_text
    concurrency = int(_os.environ.get("STYLE_ANALYSIS_CONCURRENCY", "3"))
    batch_size = 50  # 每批最多 50 章，避免内存爆炸
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    total = len(chapters)
    completed = 0

    async def _analyze_one(ci: int, ch: dict) -> dict | None:
        nonlocal completed
        async with semaphore:
            try:
                # Load content from DB instead of ch['content']
                ch_id = ch.get('id')
                if ch_id:
                    rows = dao._fetch("SELECT content FROM collected_chapters WHERE id=?", (ch_id,))
                    text = rows[0]['content'] if rows else ""
                else:
                    text = ch.get('content', '')  # fallback for online search path
                if not text:
                    async with lock:
                        completed += 1
                    return None
                result = await analyze_chapter_text(text)
                async with lock:
                    completed += 1
                    dao.update_progress(task_id, 'analyzing',
                        f'分析 {ch["work_title"]} 第{ch["chapter_num"]}章 ({completed}/{total})', 2, 5)
                    if dispatch_callback is not None:
                        await dispatch_callback("analyzing",
                            f'分析 {ch["work_title"]} 第{ch["chapter_num"]}章 ({completed}/{total})')
                    if not result:
                        logger.warning(f"章节分析返回空结果: {ch.get('work_title','')} 第{ch.get('chapter_num','?')}章 (id={ch_id})")
                    if result:
                        if ch_id:
                            dao.update_chapter_status(ch_id, 'analyzed')
                        return {
                            'author': ch['author'],
                            'work_title': ch['work_title'],
                            'chapter_num': ch['chapter_num'],
                            'chapter_title': ch.get('chapter_title', ''),
                            **result,
                        }
                return None
            except Exception:
                async with lock:
                    completed += 1
                return None

    # 分批处理：每批 batch_size 章，批内并发 3，批间串行
    # 使用 asyncio.as_completed 增量 yield 结果，不再积累到 analyses 列表
    for batch_start in range(0, total, batch_size):
        batch = chapters[batch_start:batch_start + batch_size]
        batch_tasks = [_analyze_one(batch_start + ci, ch) for ci, ch in enumerate(batch)]
        for coro in asyncio.as_completed(batch_tasks):
            result = await coro
            if result:
                yield result


async def _check_ollama_health() -> bool:
    try:
        cfg = DataModulesConfig.from_project_root(_get_project_root())
        ollama_host = cfg.ollama_host
    except Exception:
        import os
        ollama_host = os.environ.get("OLLAMA_HOST", "http://192.168.160.1:11434")
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "--max-time", "5",
            f"{ollama_host}/api/tags",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=6)
        data = json.loads(stdout.decode("utf-8", errors="replace"))
        return "models" in data and len(data.get("models", [])) > 0
    except Exception:
        return False


async def _generate_style_summary(author: str, analyses: list[dict],
                                   dao: StyleCollectorDAO, db_path: str):
    from .services.style_summarizer import (
        summarize_by_dimension, generate_author_summary, save_summaries_to_db,
        cluster_techniques,
    )
    from data_modules.dao.director_dao import DirectorDAO
    import json as _json
    if not analyses:
        return

    # Detect format: new (has "techniques" key) vs old (dimension keys)
    first = analyses[0] if analyses else {}
    is_new_format = "techniques" in first

    if is_new_format:
        # ── New technique extraction format ──
        # Cluster by category → sub_category → technique name
        clustered = cluster_techniques(analyses)
        if not clustered:
            return
        for cat_group in clustered:
            cat_group["author"] = author
            cat_group["chapter_range"] = f"全{len(analyses)}章"
        # Save to style_summaries only (no director_style writes for technique format)
        save_summaries_to_db(clustered, db_path)
        return

    # ── Old dimension format (backward compatible) ──
    # 每 10 章聚合一次
    batch_size = 10
    all_dimension_summaries = []
    director_dao = get_dao(DirectorDAO, db_path)
    for i in range(0, len(analyses), batch_size):
        batch = analyses[i:i + batch_size]
        start_ch = i + 1
        end_ch = min(i + batch_size, len(analyses))
        chapter_range = f"第{start_ch}-{end_ch}章"
        dims = summarize_by_dimension(batch)
        for d in dims:
            d["author"] = author
            d["chapter_range"] = chapter_range
        all_dimension_summaries.extend(dims)
        save_summaries_to_db(dims, db_path)
        # 每批 10 章单独写入 director_style（分段粒度，支持增量更新与回退）
        batch_summary = generate_author_summary(author, dims)
        rules_text = _json.dumps(batch_summary, ensure_ascii=False, indent=2)
        director_dao.upsert_style({
            "name": author,
            "category": f"综合文风_{start_ch}-{end_ch}章",
            "description": f"{author} 的文风总结（{chapter_range}）",
            "rules": rules_text,
            "priority": 5,
            "is_active": 1,
        })
    # 作家级别全量总结 → director_style（全章聚合版）
    author_summary = generate_author_summary(author, all_dimension_summaries)
    rules_text = _json.dumps(author_summary, ensure_ascii=False, indent=2)
    director_dao.upsert_style({
        "name": author,
        "category": "综合文风",
        "description": f"{author} 的文风采集总结（全 {len(analyses)} 章）",
        "rules": rules_text,
        "priority": 5,
        "is_active": 1,
    })


async def _summarize_chapter_style(
    chapter: int,
    project_root_str: str,
    sse_callback: Callable | None = None,
) -> dict:
    """Summarize a single chapter's writing style.

    Resolves the chapter file via CLI, reads content, calls
    style_analyzer.analyze_chapter_text(), saves results to
    style_summaries table, and returns a summary dict.

    Returns:
        dict with keys: chapter, techniques_count, summary_id,
        db_path, author, title, error (None on success).
    """
    project_root = Path(project_root_str)

    # Step 1: Resolve chapter file directly (no subprocess)
    text_dir = project_root / "正文"
    if not text_dir.is_dir():
        return {"chapter": chapter, "techniques_count": 0, "summary_id": None,
                "error": f"Chapter file not found: 正文目录不存在 {text_dir}"}
    import re
    chapter_file = None
    pattern = re.compile(rf"第0*{chapter}章")
    for f in sorted(text_dir.iterdir()):
        if f.is_file() and pattern.search(f.name):
            chapter_file = f
            break
    if not chapter_file or not chapter_file.exists():
        return _empty_chapter_result(chapter, f"Chapter file not found for chapter {chapter}")

    chapter_path = chapter_file

    # Step 2: Read content
    text = chapter_path.read_text(encoding="utf-8")

    # Step 3: Analyze style (async Ollama call)
    from .services.style_analyzer import analyze_chapter_text
    analysis = await analyze_chapter_text(text)

    if not analysis:
        return _empty_chapter_result(chapter, "empty_analysis")

    # Step 4: Source metadata
    state_path = project_root / ".webnovel" / "state.json"
    master_path = project_root / ".story-system" / "MASTER_SETTING.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        title = state.get("project_info", {}).get("title", f"第{chapter}章")
    except Exception:
        title = f"第{chapter}章"

    author = "未知作者"
    try:
        master = json.loads(master_path.read_text(encoding="utf-8"))
        author = master.get("author", "未知作者")
    except Exception:
        pass

    if not author or author == "未知作者":
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("project_info", {}).get("author"):
                author = state["project_info"]["author"]
        except Exception:
            pass

    # Step 5: Process result and save to DB
    from .services.style_summarizer import cluster_techniques, save_summaries_to_db

    db_path = project_root / ".webnovel" / "index.db"
    saved_ids: list[int] = []

    if isinstance(analysis, dict) and "techniques" in analysis:
        # New technique extraction format
        clustered = cluster_techniques([analysis])
        if clustered:
            for cat_group in clustered:
                cat_group["author"] = author
                cat_group["work_title"] = title
                cat_group["chapter_range"] = f"第{chapter}章"
            saved_ids = save_summaries_to_db(clustered, str(db_path))
        return {
            "chapter": chapter,
            "techniques_count": len(analysis.get("techniques", [])),
            "summary_id": saved_ids[0] if saved_ids else None,
            "db_path": str(db_path),
            "author": author,
            "title": title,
            "error": None,
        }

    if isinstance(analysis, dict):
        # Old 9-dimension format
        from .services.style_summarizer import summarize_by_dimension
        dims = summarize_by_dimension([analysis])
        for d in dims:
            d["author"] = author
            d["chapter_range"] = f"第{chapter}章"
        if dims:
            saved_ids = save_summaries_to_db(dims, str(db_path))
        return {
            "chapter": chapter,
            "techniques_count": 0,
            "summary_id": saved_ids[0] if saved_ids else None,
            "db_path": str(db_path),
            "author": author,
            "title": title,
            "error": None,
        }

    return _empty_chapter_result(chapter, "unknown_format", db_path=str(db_path))


def _empty_chapter_result(
    chapter: int,
    error: str,
    db_path: str = "",
) -> dict:
    """Return a uniform error dict for chapter style summarization failures."""
    return {
        "chapter": chapter,
        "techniques_count": 0,
        "summary_id": None,
        "db_path": db_path,
        "author": "",
        "title": "",
        "error": error,
    }


# ---------------------------------------------------------------------------
# ── 数据库维护助手 ─────────────────────────────────────────
def _do_incremental_vacuum(db_path: str, pages: int = 500) -> None:
    """Execute PRAGMA incremental_vacuum(N) on a dedicated connection."""
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA incremental_vacuum({pages})")
    finally:
        conn.close()


# 应用工厂
# ---------------------------------------------------------------------------

def create_app(project_root: str | Path | None = None) -> FastAPI:
    global _project_root

    if project_root:
        if _project_root is not None:
            import warnings
            warnings.warn(f"Dashboard project_root 被覆盖: {_project_root} → {project_root}", stacklevel=2)
        _project_root = Path(project_root).resolve()
        # 同步到 core.config 以便 services/db.py 使用
        from .core.config import init_project_root
        init_project_root(_project_root)

    _ensure_scripts_dir_on_path()

    @asynccontextmanager
    async def _lifespan(_: FastAPI):
        global _vacuum_lock
        if _project_root is None:
            yield
            return

        _vacuum_lock = asyncio.Lock()

        webnovel = _webnovel_dir()
        story_system = _story_system_dir()

        # 确保关键目录存在
        runtime_dir = webnovel / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)

        # 确保名家采集相关表已创建
        db_path = webnovel / "index.db"
        if db_path.is_file():
            try:
                conn = sqlite3.connect(str(db_path), timeout=5)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS collected_chapters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        author TEXT NOT NULL,
                        work_title TEXT NOT NULL,
                        chapter_num INTEGER NOT NULL,
                        chapter_title TEXT,
                        content TEXT NOT NULL,
                        source_url TEXT,
                        word_count INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'raw',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_cc_author ON collected_chapters(author);
                    CREATE TABLE IF NOT EXISTS style_summaries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        author TEXT NOT NULL,
                        work_title TEXT,
                        summary_title TEXT NOT NULL,
                        category TEXT NOT NULL,
                        content TEXT NOT NULL,
                        examples TEXT DEFAULT '[]',
                        keywords TEXT DEFAULT '[]',
                        quality_score REAL DEFAULT 0,
                        chapter_range TEXT,
                        model_used TEXT DEFAULT 'qwen3.5_9B_Q4',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS collection_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        author TEXT NOT NULL,
                        task_id TEXT NOT NULL UNIQUE,
                        status TEXT DEFAULT 'pending',
                        progress TEXT DEFAULT '{}',
                        steps_json TEXT DEFAULT '[]',
                        start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        end_time TIMESTAMP,
                        chapters_collected INTEGER DEFAULT 0,
                        summaries_generated INTEGER DEFAULT 0,
                        error_message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_cr_author ON collection_reports(author);
                """)
                conn.close()
            except Exception:
                pass

        if webnovel.is_dir() or story_system.is_dir():
            _watcher.start(
                watch_webnovel_dir=webnovel if webnovel.is_dir() else None,
                watch_story_system_dir=story_system if story_system.is_dir() else None,
                loop=asyncio.get_running_loop(),
            )

        # 启动时清理僵尸任务（服务重启后残留的 running 状态且无对应 asyncio task）
        if db_path.is_file():
            try:
                dao = get_dao(StyleCollectorDAO, db_path)
                stale = dao._fetch(
                    "SELECT task_id FROM collection_reports WHERE status NOT IN ('done','failed','cancelled','stale')"
                )
                cleaned = 0
                for r in stale:
                    if r["task_id"] not in _collection_tasks:
                        dao._execute(
                            "UPDATE collection_reports SET status='stale', error_message='服务重启，任务丢失' WHERE task_id=?",
                            (r["task_id"],)
                        )
                        cleaned += 1
                if cleaned:
                    logging.getLogger(__name__).info(f"清理了 {cleaned} 个僵尸采集任务")
            except Exception:
                pass

        # Seed writing techniques if table is empty
        try:
            seed_dao = DirectorDAO(str(db_path))
            seed_dao.seed_techniques()
        except Exception:
            pass

        # Sync 裁决规则.csv → anti_patterns.json（仅在文件不存在时）
        try:
            anti_path = _get_project_root() / ".story-system" / "anti_patterns.json"
            if not anti_path.is_file():
                sync_script = SCRIPTS_DIR / "sync_anti_patterns.py"
                if sync_script.is_file():
                    subprocess.run(
                        [sys.executable, str(sync_script), "--project-root", str(_get_project_root())],
                        capture_output=True, timeout=10,
                    )
        except Exception:
            pass

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

        async def _vacuum_scheduler():
            """Periodically run incremental VACUUM and expire old style summaries."""
            while True:
                try:
                    await asyncio.sleep(21600)  # 6 hours
                    db_path_val = _webnovel_dir() / "index.db"
                    if not db_path_val.is_file():
                        continue
                    async with _vacuum_lock:
                        await asyncio.to_thread(_do_incremental_vacuum, str(db_path_val))
                        # TTL cleanup: delete style_summaries older than 90 days
                        try:
                            dao = get_dao(StyleCollectorDAO, db_path_val)
                            deleted = dao.cleanup_expired_summaries()
                            if deleted:
                                logging.getLogger(__name__).info(
                                    "清理了 %d 条过期文风总结(>90天)", deleted
                                )
                        except Exception:
                            pass
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass

        poll_task = asyncio.create_task(_polling_loop())
        vacuum_task = asyncio.create_task(_vacuum_scheduler())

        # Dispatch SSE event on server startup for frontend auto-reload
        async def _startup_event():
            await asyncio.sleep(2)
            _watcher._dispatch(json.dumps({
                "type": "server-restart",
                "ts": time.time(),
            }))

        startup_task = asyncio.create_task(_startup_event())

        try:
            yield
        finally:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
            vacuum_task.cancel()
            try:
                await vacuum_task
            except asyncio.CancelledError:
                pass
            startup_task.cancel()
            try:
                await startup_task
            except asyncio.CancelledError:
                pass
            for _tid, _task in list(_collection_tasks.items()):
                _task.cancel()
                try:
                    await _task
                except asyncio.CancelledError:
                    pass
            _collection_tasks.clear()
            _watcher.stop()

    app = FastAPI(title="Webnovel Dashboard", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    set_files_router_watcher(_watcher)
    app.include_router(files_router)

    from .routers.chapters import router as chapters_router
    from .routers.contracts import router as contracts_router
    from .routers.entities import router as entities_router
    from .routers.extended import router as extended_router
    from .routers.review import router as review_router

    app.include_router(contracts_router)
    app.include_router(entities_router)
    app.include_router(review_router)
    app.include_router(chapters_router)
    app.include_router(extended_router)

    # ===========================================================
    # API：项目元信息
    # ===========================================================

    @app.get("/api/project/info")
    def project_info():
        """返回 state.json 完整内容（只读）。"""
        return _load_state_payload(required=True)

    @app.get("/api/projects")
    def list_projects():
        """列出所有可用的书项目。"""
        from .core.config import ProjectRegistry
        return {"projects": ProjectRegistry.list_projects(), "current": str(_get_project_root())}

    @app.post("/api/projects/switch")
    def switch_project(data: dict):
        """切换到指定项目。"""
        path_str = (data.get("path") or data.get("project_path") or "").strip()
        if not path_str:
            raise HTTPException(400, "缺少 path 参数")
        target = Path(path_str).resolve()
        if not target.is_dir():
            raise HTTPException(404, f"目录不存在: {target}")
        if not (target / ".webnovel" / "state.json").is_file():
            raise HTTPException(404, f"不是有效的书项目: {target}")
        from .core.config import switch_project_root
        switch_project_root(target)
        global _project_root
        _project_root = target
        # 重启 watcher 以监听新项目
        webnovel = target / ".webnovel"
        story_system = target / ".story-system"
        _watcher.stop()
        if webnovel.is_dir() or story_system.is_dir():
            _watcher.start(
                watch_webnovel_dir=webnovel if webnovel.is_dir() else None,
                watch_story_system_dir=story_system if story_system.is_dir() else None,
                loop=asyncio.get_running_loop(),
            )
        # 推送 SSE 通知前端刷新
        try:
            _watcher._dispatch(json.dumps({"type": "project-switched", "path": str(target), "ts": time.time()}))
        except Exception:
            pass
        return {"ok": True, "current": str(target)}

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
        conn.execute("PRAGMA mmap_size = 1073741824")
        conn.execute("PRAGMA cache_size = -64000")
        conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
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

    def _get_db_path() -> str:
        return str(_get_project_root() / ".webnovel" / "index.db")

    def _load_chapter_memories(chapter: int, dao) -> int:
        project_root = _get_project_root()
        commit_path = project_root / '.story-system' / 'commits' / f'chapter_{int(chapter):03d}.commit.json'
        if not commit_path.exists():
            return 0
        commit_data = json.loads(commit_path.read_text(encoding='utf-8'))
        extraction = commit_data.get('extraction_result', {})
        raw_facts = extraction.get('raw_facts', '') or ''
        known_entities = extraction.get('known_entities', {})
        if not raw_facts or not known_entities:
            return 0
        from data_modules.observer_settler import ObserverSettlerModule
        memories = ObserverSettlerModule._extract_character_memories(raw_facts, known_entities, chapter)
        created = 0
        for mem in memories:
            try:
                dao.create_memory(mem)
                created += 1
            except Exception:
                pass
        return created

    def _ensure_character_events_table():
        with closing(_get_db()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS character_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK(event_type IN ('need_to_do','want_to_do','planned','promise','prerequisite')),
                    description TEXT NOT NULL,
                    source_chapter INTEGER NOT NULL,
                    target_chapter INTEGER,
                    prerequisites TEXT DEFAULT '[]',
                    trigger_condition TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','in_progress','resolved','abandoned')),
                    resolved_chapter INTEGER,
                    urgency INTEGER DEFAULT 5 CHECK(urgency BETWEEN 1 AND 10),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ce_actor ON character_events(actor_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ce_status ON character_events(status)")
            conn.commit()



    # ===========================================================
    # API：角色事件
    # ===========================================================

    @app.get("/api/character-events")
    def list_character_events(
        actor_id: Optional[str] = Query(None, description="Filter by actor entity ID"),
        status: Optional[str] = Query(None, description="Filter by status: pending, in_progress, resolved, abandoned"),
        overdue: bool = Query(False, description="Return only overdue events"),
        current_chapter: int = Query(0, description="Current chapter for overdue calculation"),
    ):
        dao = get_dao(CharacterEventDAO, _get_db_path())
        return dao.list_events(
            actor_id=actor_id,
            status=status,
            overdue=overdue,
            current_chapter=current_chapter,
        )

    @app.post("/api/character-events", status_code=201)
    def create_character_event(data: dict):
        actor_id = (data.get("actor_id") or "").strip()
        event_type = (data.get("event_type") or "").strip()
        description = (data.get("description") or "").strip()
        source_chapter = data.get("source_chapter")

        if not actor_id or not event_type or not description or source_chapter is None:
            raise HTTPException(status_code=400, detail="actor_id, event_type, description, source_chapter 为必填字段")

        valid_types = ("need_to_do", "want_to_do", "planned", "promise", "prerequisite")
        if event_type not in valid_types:
            raise HTTPException(status_code=422, detail=f"event_type 必须为以下之一: {', '.join(valid_types)}")

        _ensure_character_events_table()
        dao = get_dao(CharacterEventDAO, _get_db_path())
        try:
            return dao.create_event(data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.put("/api/character-events/{event_id}")
    def update_character_event(event_id: int, data: dict):
        dao = get_dao(CharacterEventDAO, _get_db_path())

        if "status" in data and data["status"] is not None:
            valid_statuses = ("pending", "in_progress", "resolved", "abandoned")
            if data["status"] not in valid_statuses:
                raise HTTPException(status_code=422, detail=f"status 必须为以下之一: {', '.join(valid_statuses)}")

        allowed = {'status', 'urgency', 'description', 'target_chapter'}
        if not any(data.get(k) is not None for k in allowed):
            raise HTTPException(status_code=400, detail="未提供任何可更新字段")

        result = dao.update_event(event_id, data)
        if result is None:
            raise HTTPException(status_code=404, detail="事件不存在")
        return result

    @app.delete("/api/character-events/{event_id}")
    def delete_character_event(event_id: int):
        dao = get_dao(CharacterEventDAO, _get_db_path())
        if not dao.delete_event(event_id):
            raise HTTPException(status_code=404, detail="事件不存在")
        return {"ok": True, "deleted_id": event_id}

    @app.patch("/api/character-events/{event_id}/resolve")
    def resolve_character_event(event_id: int, chapter: int = Query(None, description="结算章节号，不传则自动取当前最新章")):
        resolved_chapter = chapter
        if resolved_chapter is None:
            with closing(_get_db()) as conn:
                chapters = _fetchall_safe(conn, "SELECT MAX(chapter) AS max_ch FROM chapters")
            resolved_chapter = chapters[0]["max_ch"] if chapters and chapters[0].get("max_ch") is not None else 0

        dao = get_dao(CharacterEventDAO, _get_db_path())
        result = dao.resolve_event(event_id, resolved_chapter)
        if result is None:
            raise HTTPException(status_code=404, detail="事件不存在")
        return result

    # ===========================================================
    # API：角色记忆
    # ===========================================================

    @app.get("/api/memories")
    def list_memories(
        actor_id: str = Query(...),
        memory_type: Optional[str] = Query(None),
        tag: Optional[str] = Query(None),
        limit: int = Query(50),
        offset: int = Query(0),
    ):
        dao = get_dao(MemoryDAO, _get_db_path())
        return dao.list_memories(
            actor_id=actor_id,
            memory_type=memory_type,
            tag=tag,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/memories/rag")
    def rag_search_memories(
        actor_id: str = Query(...),
        query: str = Query(...),
        k: int = Query(10),
    ):
        dao = get_dao(MemoryDAO, _get_db_path())
        return {"memories": dao.rag_search(actor_id=actor_id, query_text=query, k=k)}

    @app.get("/api/memories/{memory_id}")
    def get_memory(memory_id: int):
        dao = get_dao(MemoryDAO, _get_db_path())
        result = dao.get_memory(memory_id)
        if not result:
            raise HTTPException(404, "记忆不存在")
        return result

    @app.post("/api/memories", status_code=201)
    def create_memory(data: dict):
        required = ["actor_id", "memory_type", "content", "source_chapter"]
        for f in required:
            if f not in data:
                raise HTTPException(400, f"缺少必填字段: {f}")
        if data["memory_type"] not in ("episodic", "semantic", "relational", "decision"):
            raise HTTPException(422, "memory_type 必须为 episodic/semantic/relational/decision")
        dao = get_dao(MemoryDAO, _get_db_path())
        return dao.create_memory(data)

    @app.delete("/api/memories/{memory_id}")
    def delete_memory(memory_id: int):
        dao = get_dao(MemoryDAO, _get_db_path())
        if not dao.delete_memory(memory_id):
            raise HTTPException(404, "记忆不存在")
        return {"ok": True}

    @app.post("/api/memories/decay")
    def decay_memories(
        current_chapter: int = Query(...),
    ):
        dao = get_dao(MemoryDAO, _get_db_path())
        return dao.decay_memories(current_chapter=current_chapter)

    @app.post("/api/memories/load-from-chapter")
    def load_memories_from_chapter(chapter: int = Query(...)):
        project_root = _get_project_root()
        commit_path = project_root / '.story-system' / 'commits' / f'chapter_{int(chapter):03d}.commit.json'
        if not commit_path.exists():
            raise HTTPException(404, f"第{chapter}章的 commit 文件不存在")

        commit_data = json.loads(commit_path.read_text(encoding='utf-8'))
        extraction = commit_data.get('extraction_result', {})
        raw_facts = extraction.get('raw_facts', '') or ''
        known_entities = extraction.get('known_entities', {})

        if not raw_facts or not known_entities:
            raise HTTPException(400, "extraction_result 中无 raw_facts 或 known_entities")

        from data_modules.observer_settler import ObserverSettlerModule
        memories = ObserverSettlerModule._extract_character_memories(raw_facts, known_entities, chapter)
        dao = get_dao(MemoryDAO, _get_db_path())
        created = 0
        for mem in memories:
            try:
                dao.create_memory(mem)
                created += 1
            except Exception:
                pass
        return {"ok": True, "created": created, "chapter": chapter}

    @app.post("/api/memories/batch")
    def batch_load_memories(from_chapter: int = Query(1), to_chapter: int = Query(...)):
        dao = get_dao(MemoryDAO, _get_db_path())
        total = 0
        for ch in range(from_chapter, to_chapter + 1):
            total += _load_chapter_memories(ch, dao)
        return {"ok": True, "total_created": total, "chapters": f"{from_chapter}-{to_chapter}"}

    # ===========================================================
    # API：角色状态
    # ===========================================================

    @app.get("/api/state/{actor_id}")
    def get_character_state(actor_id: str):
        dao = get_dao(StateDAO, _get_db_path())
        result = dao.get_state(actor_id)
        if not result:
            raise HTTPException(404, "角色状态不存在")
        return result

    @app.put("/api/state/{actor_id}")
    def upsert_character_state(actor_id: str, data: dict):
        if "chapter" not in data:
            raise HTTPException(400, "缺少必填字段: chapter")
        dao = get_dao(StateDAO, _get_db_path())
        return dao.upsert_state(actor_id=actor_id, data=data)

    @app.get("/api/state/{actor_id}/history")
    def get_state_history(
        actor_id: str,
        change_type: Optional[str] = Query(None),
        limit: int = Query(20),
    ):
        dao = get_dao(StateDAO, _get_db_path())
        return dao.get_state_history(actor_id=actor_id, change_type=change_type, limit=limit)

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

    @app.get("/api/process/stats")
    def get_process_stats():
        dao = get_dao(ProcessDAO, _get_db_path())
        return dao.get_global_stats()

    @app.get("/api/process/actor/{actor_id}/behavior")
    def get_actor_behavior(actor_id: str):
        dao = get_dao(ProcessDAO, _get_db_path())
        return dao.get_actor_behavior(actor_id)

    @app.get("/api/foreshadowing/reminders")
    def foreshadowing_reminders(threshold: int = Query(5, ge=1, le=20)):
        """返回活跃伏笔提醒（从 state.json plot_threads.foreshadowing 读取）。

        优先显示即将到期的（有 target_chapter/due_chapter 且在当前章节 + threshold 范围内），
        其次显示未回收但无目标章的活跃伏笔。
        """
        state = _load_state_payload()
        current_chapter = int((state.get("progress") or {}).get("current_chapter") or 0)
        items = (state.get("plot_threads") or {}).get("foreshadowing") or []
        if not isinstance(items, list):
            items = []
        due_soon = []
        active_no_deadline = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").strip()
            if status in ("已回收", "已完成", "已解决", "resolved", "done", "closed"):
                continue
            content = str(item.get("content") or item.get("description") or "未命名伏笔")
            due = _to_int(item.get("due_chapter") or item.get("target_chapter") or 0)
            planted = _to_int(item.get("planted_chapter") or item.get("source_chapter") or 0)
            entry = {
                "id": f"fs-{i}",
                "content": content,
                "target_chapter": due if due > 0 else None,
                "planted_chapter": planted,
                "status": status or "active",
                "tier": str(item.get("tier") or ""),
            }
            if due > 0 and current_chapter <= due <= current_chapter + threshold:
                due_soon.append(entry)
            elif due <= 0:
                active_no_deadline.append(entry)
        # 即将到期的排前面，无目标章的排后面
        due_soon.sort(key=lambda r: r["target_chapter"] or 9999)
        active_no_deadline.sort(key=lambda r: r.get("planted_chapter", 0))
        reminders = due_soon + active_no_deadline
        return {"reminders": reminders, "current_chapter": current_chapter, "total": len(items)}


    def _to_int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

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
                    event_name = "message"
                    try:
                        d = json.loads(msg)
                        if isinstance(d, dict) and "type" in d:
                            event_name = d["type"]
                    except Exception:
                        pass
                    yield f"event: {event_name}\ndata: {msg}\n\n"
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

    # 关键 section 列表（被排除时应告警，可通过 dashboard_config.json 覆盖）
    _DEFAULT_CRITICAL_SECTIONS = {"core", "scene", "story_contract", "user_prompts"}

    def _get_critical_sections() -> set:
        """每次调用重新读取配置，支持运行时修改。"""
        config_path = _get_project_root() / ".webnovel" / "dashboard_config.json"
        if config_path.is_file():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(cfg.get("critical_sections"), list):
                    return set(cfg["critical_sections"])
            except (OSError, json.JSONDecodeError):
                pass
        return _DEFAULT_CRITICAL_SECTIONS

    @app.get("/api/context/health/{chapter}")
    def context_health(chapter: int):
        """返回指定章的上下文健康度报告。"""
        runtime_dir = _webnovel_dir() / "runtime"
        trace_file = runtime_dir / f"chapter-{chapter:03d}.trace.json"
        context_file = runtime_dir / f"chapter-{chapter:03d}.context.json"

        if not trace_file.is_file():
            raise HTTPException(404, "trace 文件不存在")

        trace = json.loads(trace_file.read_text(encoding="utf-8"))
        sections = trace.get("sections", {})
        included = sections.get("included", [])
        excluded = sections.get("excluded", [])

        # 从 context.json 估算 token 数（粗略：len/2，中文偏低约 30%）
        total_tokens = 0
        section_tokens = {}
        if context_file.is_file():
            try:
                ctx = json.loads(context_file.read_text(encoding="utf-8"))
                for name, content in ctx.items():
                    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                    tokens = len(text) // 2
                    section_tokens[name] = tokens
                    total_tokens += tokens
            except (OSError, json.JSONDecodeError):
                pass

        critical_excluded = [s for s in excluded if s in _get_critical_sections()]
        health_score = 100 - len(critical_excluded) * 20

        return {
            "chapter": chapter,
            "stage": trace.get("stage", "unknown"),
            "template": trace.get("template", "default"),
            "included": included,
            "excluded": excluded,
            "critical_excluded": critical_excluded,
            "section_tokens": section_tokens,
            "total_tokens": total_tokens,
            "health_score": max(0, health_score),
            "weights_used": trace.get("weights_used", {}),
            "ranker_enabled": trace.get("ranker", {}).get("enabled", False),
        }

    @app.get("/api/context/history")
    def context_history(limit: int = Query(20, ge=1, le=100)):
        """返回最近 N 章的上下文健康度趋势。"""
        runtime_dir = _webnovel_dir() / "runtime"
        if not runtime_dir.is_dir():
            return {"items": []}

        items = []
        for trace_file in sorted(runtime_dir.glob("chapter-*.trace.json"), reverse=True)[:limit]:
            try:
                trace = json.loads(trace_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            sections = trace.get("sections", {})
            excluded = sections.get("excluded", [])
            critical_excluded = [s for s in excluded if s in _get_critical_sections()]
            items.append({
                "chapter": trace.get("chapter", 0),
                "stage": trace.get("stage", "unknown"),
                "template": trace.get("template", "default"),
                "included_count": len(sections.get("included", [])),
                "excluded_count": len(excluded),
                "critical_excluded_count": len(critical_excluded),
            })
        return {"items": list(reversed(items))}

    # ===========================================================
    # API：质量预警
    # ===========================================================

    def _get_recent_review_scores(project_root: Path, n: int = 5) -> list[dict]:
        db_path = project_root / ".webnovel" / "index.db"
        if not db_path.is_file():
            return []
        try:
            with closing(sqlite3.connect(str(db_path), timeout=5)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT end_chapter, overall_score FROM review_metrics ORDER BY end_chapter DESC LIMIT ?",
                    (n,),
                ).fetchall()
                return [{"chapter": r["end_chapter"], "score": r["overall_score"]} for r in rows]
        except sqlite3.Error:
            return []

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
        try:
            with closing(sqlite3.connect(str(db_path), timeout=5)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT cd.id, cd.debt_type, cd.due_chapter, cd.source_chapter, de.note
                       FROM chase_debt cd
                       LEFT JOIN debt_events de ON de.debt_id = cd.id AND de.event_type = 'created'
                       WHERE cd.status IN ('active', 'overdue') AND cd.due_chapter < ?""",
                    (current_chapter,),
                ).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error:
            return []

    def _get_long_absent_characters(project_root: Path, current_chapter: int, threshold: int = 20) -> list[dict]:
        db_path = project_root / ".webnovel" / "index.db"
        if not db_path.is_file():
            return []
        try:
            with closing(sqlite3.connect(str(db_path), timeout=5)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT id, canonical_name, last_appearance FROM entities WHERE is_archived = 0 AND (? - last_appearance) > ?",
                    (current_chapter, threshold),
                ).fetchall()
                return [{"id": r["id"], "name": r["canonical_name"],
                         "absent_chapters": current_chapter - int(r["last_appearance"] or 0)} for r in rows]
        except sqlite3.Error:
            return []

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
            detail = d.get("note") or d.get("debt_type", "")
            alerts.append({"type": "debt_overdue", "severity": "critical",
                           "detail": detail, "due_chapter": d.get("due_chapter", 0)})

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
    # API：Theater 角色知识库
    # ===========================================================

    @app.get("/api/theater/knowledge")
    def get_theater_knowledge(actor_id: str | None = None):
        """获取角色的公共知识库（二进制确定知道/不知道）。"""
        project_root = _get_project_root()
        theater_dir = project_root / "theater"
        if not theater_dir.is_dir():
            return {"actors": [], "domain_tree": None}

        try:
            from data_modules.theater.actor_manager import list_actors, get_common_knowledge, load_domain_tree  # noqa: E402
        except ModuleNotFoundError:
            # theater 模块尚未实现，返回空数据优雅降级
            return {"actors": [], "domain_tree": None}

        domain_tree = load_domain_tree(project_root)
        actors = list_actors(project_root)

        # 从 index.db entities 表加载实体数据（串联角色图鉴）
        entity_map: dict[str, dict] = {}
        try:
            with closing(_get_db()) as conn:
                rows = _fetchall_safe(conn, "SELECT * FROM entities", ())
            for row in rows:
                eid = row.get("id", "")
                if eid:
                    entity_map[eid] = row
        except Exception:
            pass

        result = {"domain_tree": domain_tree, "actors": []}
        for actor in actors:
            aid = actor["actor_id"]
            if actor_id and aid != actor_id:
                continue
            entry = {
                "actor_id": aid,
                "name": actor.get("name", aid),
                "tier": actor.get("tier", "extra"),
                "intro_chapter": actor.get("intro_chapter", 0),
            }

            # 附加实体数据
            entity = entity_map.get(aid)
            if entity:
                entry["entity"] = {
                    "type": entity.get("type", ""),
                    "first_appearance": entity.get("first_appearance", 0),
                    "last_appearance": entity.get("last_appearance", 0),
                    "is_protagonist": entity.get("is_protagonist", 0),
                    "desc": entity.get("desc", ""),
                }
                cj = entity.get("current_json", "{}")
                try:
                    entry["entity"]["traits"] = json.loads(cj).get("traits", [])
                except (json.JSONDecodeError, TypeError):
                    entry["entity"]["traits"] = []

            try:
                knowledge = get_common_knowledge(project_root, aid)
                entry["retrieval_base"] = knowledge.get("retrieval_base", 0.5)
                entry["known_domains"] = knowledge.get("known_domains", {})
                entry["total_known"] = len(entry["known_domains"])
            except Exception:
                entry["known_domains"] = {}
                entry["retrieval_base"] = 0
                entry["total_known"] = 0
            result["actors"].append(entry)

        result["actors"].sort(key=lambda a: a.get("total_known", 0), reverse=True)
        return result

    @app.get("/api/skills/catalog")
    def get_skills_catalog():
        """公共技能目录——所有技能分类和熟练度标准。"""
        project_root = _get_project_root()
        try:
            from data_modules.theater.actor_manager import get_skills_catalog as load_catalog
            return load_catalog(project_root)
        except ModuleNotFoundError:
            raise HTTPException(503, "theater 模块未安装")

    @app.get("/api/skills/actor/{actor_id}")
    def get_actor_skills(actor_id: str):
        """指定角色的技能列表（含熟练度等级和中文标签）。"""
        project_root = _get_project_root()
        try:
            from data_modules.theater.actor_manager import get_actor_skills as load_actor_skills
            return load_actor_skills(project_root, actor_id)
        except ModuleNotFoundError:
            raise HTTPException(503, "theater 模块未安装")

    @app.get("/api/skills/actor/{actor_id}/rag")
    def get_actor_rag(actor_id: str, q: str = "", top_k: int = 5):
        """角色 RAG 检索：从历史章节找相关内容。"""
        project_root = _get_project_root()
        try:
            from data_modules.theater.actor_manager import actor_rag_search
            return actor_rag_search(project_root, actor_id, query=q, top_k=min(top_k, 10))
        except ModuleNotFoundError:
            raise HTTPException(503, "theater 模块未安装")

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

    @app.delete("/api/style/anti-patterns")
    def delete_anti_pattern(text: str = Query(..., min_length=1)):
        """按文本内容删除反模式（带文件锁防并发）。"""
        text = text.strip()
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

    # ── DB-backed anti-patterns (replaces JSON file reader) ──

    @app.get("/api/anti-patterns")
    def get_anti_patterns_db():
        dao = get_dao(DirectorDAO, _get_db_path())
        return dao.list_anti_patterns()

    @app.post("/api/anti-patterns")
    def add_anti_pattern_db(data: dict):
        dao = get_dao(DirectorDAO, _get_db_path())
        text = data.get("text", "").strip()
        if not text:
            raise HTTPException(400, "text 不能为空")
        return dao.add_anti_pattern(
            text,
            data.get("source", ""),
            data.get("category", "禁写"),
            data.get("genre", ""),
        )

    @app.delete("/api/anti-patterns/{pattern_id}")
    def delete_anti_pattern_db(pattern_id: int):
        dao = get_dao(DirectorDAO, _get_db_path())
        return dao.delete_anti_pattern(pattern_id)

    # ===========================================================
    # API：文风约束只读数据
    # ===========================================================

    @app.get("/api/style/chapters")
    def list_chapter_contracts():
        """列出所有章级合同摘要。"""
        chapters_dir = _get_project_root() / ".story-system" / "chapters"
        if not chapters_dir.is_dir():
            return {"chapters": []}

        result = []
        for f in sorted(chapters_dir.glob("chapter_*.json"), key=lambda p: int(re.search(r"(\d+)", p.name).group(1)) if re.search(r"(\d+)", p.name) else 0):
            m = re.search(r"chapter_(\d+)\.json$", f.name)
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

    @app.get("/api/style/prompts")
    def get_prompts():
        """读取设定集/prompts/ 下的所有 .md 文件。"""
        prompts_dir = _get_project_root() / "设定集" / "prompts"
        if not prompts_dir.is_dir():
            return {"prompts": []}
        result = []
        for f in sorted(prompts_dir.glob("*.md")):
            try:
                content = f.read_text(encoding="utf-8").strip()
                result.append({"name": f.stem, "filename": f.name, "content": content})
            except Exception:
                result.append({"name": f.stem, "filename": f.name, "content": "", "error": "读取失败"})
        return {"prompts": result}

    @app.post("/api/style/prompts")
    def create_prompt(request: dict):
        """创建新的提示词文件。"""
        name = (request.get("name") or "").strip()
        content = (request.get("content") or "").strip()
        if not name:
            raise HTTPException(400, "name 不能为空")
        if not content:
            raise HTTPException(400, "content 不能为空")
        # 文件名安全检查：先 strip 再检查路径穿越
        safe_name = name.strip()
        if not safe_name:
            raise HTTPException(400, "文件名不能为空")
        if "/" in safe_name or "\\" in safe_name or safe_name == "..":
            raise HTTPException(400, "文件名包含非法字符")
        if re.search(r'[:*?"<>|]', safe_name):
            raise HTTPException(400, "文件名包含 Windows 保留字符: :*?\"<>|")

        prompts_dir = _get_project_root() / "设定集" / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        path = prompts_dir / f"{safe_name}.md"
        if path.is_file():
            raise HTTPException(409, f"文件已存在: {path.name}")

        path.write_text(content + "\n", encoding="utf-8")
        try:
            _watcher._dispatch(json.dumps({
                "type": "style-updated", "layer": "prompts", "ts": time.time(),
            }))
        except Exception:
            pass
        return {"ok": True, "filename": path.name}

    @app.put("/api/style/prompts/{filename}")
    def update_prompt(filename: str, request: dict):
        """更新提示词文件内容。"""
        content = (request.get("content") or "").strip()
        if not content:
            raise HTTPException(400, "content 不能为空")
        # 安全检查：先 strip 再检查路径穿越
        filename = filename.strip()
        if not filename:
            raise HTTPException(400, "非法文件名")
        if "/" in filename or "\\" in filename or filename == "..":
            raise HTTPException(400, "非法文件名")
        if re.search(r'[:*?"<>|]', filename):
            raise HTTPException(400, "文件名包含 Windows 保留字符")

        prompts_dir = _get_project_root() / "设定集" / "prompts"
        path = prompts_dir / filename
        if not path.is_file():
            raise HTTPException(404, f"文件不存在: {filename}")

        path.write_text(content + "\n", encoding="utf-8")
        try:
            _watcher._dispatch(json.dumps({
                "type": "style-updated", "layer": "prompts", "ts": time.time(),
            }))
        except Exception:
            pass
        return {"ok": True, "filename": filename}

    @app.delete("/api/style/prompts/{filename}")
    def delete_prompt(filename: str):
        """删除提示词文件。"""
        filename = filename.strip()
        if not filename:
            raise HTTPException(400, "非法文件名")
        if "/" in filename or "\\" in filename or filename == "..":
            raise HTTPException(400, "非法文件名")
        if re.search(r'[:*?"<>|]', filename):
            raise HTTPException(400, "文件名包含 Windows 保留字符")

        prompts_dir = _get_project_root() / "设定集" / "prompts"
        path = prompts_dir / filename
        if not path.is_file():
            raise HTTPException(404, f"文件不存在: {filename}")

        path.unlink()
        try:
            _watcher._dispatch(json.dumps({
                "type": "style-updated", "layer": "prompts", "ts": time.time(),
            }))
        except Exception:
            pass
        return {"ok": True, "deleted": filename}

    @app.get("/api/style/reviewer-checklist")
    def get_reviewer_checklist():
        """读取审查维度清单。"""
        checklist = [
            {"dimension": "设定一致性", "content": "角色状态/世界规则/物品属性是否与 state.json 一致", "format": "[设定]: pass 或 发现N个问题(简述)", "must_bash": True},
            {"dimension": "时间线", "content": "事件顺序/时间跨度是否合理", "format": "[时间线]: pass 或 发现N个问题(简述)", "must_bash": True},
            {"dimension": "叙事连贯", "content": "视角是否统一/场景切换是否有过渡", "format": "[连贯]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "角色一致性", "content": "对话风格/行为动机是否符合人设", "format": "[角色]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "逻辑", "content": "因果关系/行为后果是否合理", "format": "[逻辑]: pass 或 发现N个问题(简述)", "must_bash": False},
            {"dimension": "项目规则", "content": "破折号≤20、但≤6、不是X是Y≤1、句号≤70/千字、系统【】格式", "format": "[规则]: pass 或 发现N个问题(简述)", "must_bash": True},
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

    @app.get("/api/style/active")
    def get_active_style_constraints():
        """合并返回当前激活的全部风格约束——供 Agent 通过 webnovel-style skill 调用。"""
        dao = get_dao(DirectorDAO, _get_db_path())
        dao.seed_defaults()

        # 1. Active director styles (is_active=1)
        styles = dao.list_styles(active_only=True)

        # 2. Anti-patterns from anti_patterns.json
        anti_patterns = []
        ap_path = _anti_patterns_path()
        if ap_path.is_file():
            try:
                data = json.loads(ap_path.read_text(encoding="utf-8"))
                anti_patterns = data if isinstance(data, list) else []
            except Exception:
                pass

        # 3. Writing techniques grouped by primary category
        techniques = dao.list_by_primary_category()

        # 4. Reference entries grouped by source_csv
        ref_rows = dao._fetch(
            "SELECT source_csv, COUNT(*) as count FROM reference_entries GROUP BY source_csv ORDER BY source_csv"
        )
        reference_sections = {}
        for r in ref_rows:
            items = dao._fetch(
                "SELECT * FROM reference_entries WHERE source_csv=? ORDER BY name ASC LIMIT 10",
                (r["source_csv"],),
            )
            reference_sections[r["source_csv"]] = {
                "count": r["count"],
                "items": items,
            }

        return {
            "director_styles": styles,
            "anti_patterns": anti_patterns,
            "techniques": techniques,
            "reference_sections": reference_sections,
        }

    # ===========================================================
    # API：导演文风 & 写作技法（Director Style DB）
    # ===========================================================

    @app.get("/api/director/styles")
    def list_director_styles(category: str = Query(None), active_only: bool = Query(True)):
        dao = get_dao(DirectorDAO, _get_db_path())
        dao.seed_defaults()
        return dao.list_styles(category=category, active_only=active_only)

    @app.post("/api/director/styles")
    def upsert_director_style(data: dict):
        dao = get_dao(DirectorDAO, _get_db_path())
        return dao.upsert_style(data)

    @app.post("/api/director/styles/{style_id}/toggle")
    def toggle_director_style(style_id: int, data: dict = None):
        """切换或设置 director_style 条目的激活状态。body: { is_active: true/false }"""
        if data is None:
            data = {}
        dao = get_dao(DirectorDAO, _get_db_path())
        result = dao.toggle_style(style_id, data.get("is_active", None))
        if result is None:
            raise HTTPException(404, "文风规则不存在")
        return result

    @app.get("/api/director/styles/prompt")
    def get_style_prompt():
        dao = get_dao(DirectorDAO, _get_db_path())
        dao.seed_defaults()
        return {"prompt": dao.get_active_styles_prompt()}

    @app.get("/api/techniques")
    def list_techniques(category: str = Query(None), search: str = Query(None)):
        dao = get_dao(DirectorDAO, _get_db_path())
        dao.seed_techniques()
        if search:
            return dao.search_techniques(search, category)
        return dao.list_techniques(category=category)

    @app.post("/api/techniques/track")
    def track_technique(data: dict):
        dao = get_dao(DirectorDAO, _get_db_path())
        return dao.track_technique(
            data.get("chapter"),
            data.get("name"),
            data.get("category"),
            data.get("context", ""),
        )

    @app.post("/api/style/summarize-chapter")
    async def summarize_chapter_style_endpoint(data: dict):
        """分析单章文风并保存结果。

        Accepts ``{chapter: int}``, calls _summarize_chapter_style() asynchronously,
        dispatches SSE events (``style-summarize-progress``) through the file watcher
        with steps: started → analyzing → saving → error → done.
        """
        chapter = data.get("chapter")
        if not chapter or not isinstance(chapter, int) or chapter < 1:
            raise HTTPException(400, "Invalid chapter number")

        project_root = str(_get_project_root())

        # SSE start event
        try:
            _watcher._dispatch(json.dumps({
                "type": "style-summarize-progress",
                "chapter": chapter,
                "step": "started",
                "ts": time.time(),
            }))
        except Exception:
            pass

        # Build SSE callback for _summarize_chapter_style
        async def _sse_callback(step: str):
            try:
                _watcher._dispatch(json.dumps({
                    "type": "style-summarize-progress",
                    "chapter": chapter,
                    "step": step,
                    "ts": time.time(),
                }))
            except Exception:
                pass

        result = await _summarize_chapter_style(
            chapter=chapter,
            project_root_str=project_root,
            sse_callback=_sse_callback,
        )

        if result.get("error"):
            error = result["error"]
            # SSE error event
            try:
                _watcher._dispatch(json.dumps({
                    "type": "style-summarize-progress",
                    "chapter": chapter,
                    "step": "error",
                    "error": error,
                    "ts": time.time(),
                }))
            except Exception:
                pass

            if "Chapter file not found" in error or "Timeout" in error:
                raise HTTPException(404, error)
            if error == "empty_analysis":
                raise HTTPException(503, "Ollama unavailable or returned empty analysis")
            raise HTTPException(400, error)

        # SSE done event
        try:
            _watcher._dispatch(json.dumps({
                "type": "style-summarize-progress",
                "chapter": chapter,
                "step": "done",
                "summary_id": result.get("summary_id"),
                "ts": time.time(),
            }))
        except Exception:
            pass

        return result

    @app.post("/api/techniques")
    def create_technique(data: dict):
        """手动创建写作技法."""
        dao = get_dao(DirectorDAO, _get_db_path())
        dao.seed_techniques()
        try:
            return dao.create_technique(data)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.put("/api/techniques/{tech_id}")
    def update_technique(tech_id: int, data: dict):
        """更新写作技法."""
        dao = get_dao(DirectorDAO, _get_db_path())
        dao.seed_techniques()
        try:
            return dao.update_technique(tech_id, data)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/techniques/chapter/{chapter}")
    def get_chapter_techniques(chapter: int):
        dao = get_dao(DirectorDAO, _get_db_path())
        return dao.get_chapter_techniques(chapter)

    @app.post("/api/techniques/import")
    def import_techniques_from_csv():
        """从 CSV 导入写作技法"""
        dao = get_dao(DirectorDAO, _get_db_path())
        return dao.import_from_csv()

    @app.get("/api/techniques/categories")
    def list_technique_categories():
        """列出所有技法分类及每类数量"""
        dao = get_dao(DirectorDAO, _get_db_path())
        dao.seed_techniques()
        rows = dao._fetch(
            """SELECT category, COUNT(*) as count,
                      GROUP_CONCAT(sub_category) as sub_cats
               FROM writing_techniques
               GROUP BY category
               ORDER BY count DESC"""
        )
        return {"categories": [dict(r) for r in rows]}

    @app.get("/api/techniques/grouped")
    def list_techniques_grouped():
        """按 7 大主分类分组列出写作技法"""
        dao = get_dao(DirectorDAO, _get_db_path())
        dao.seed_techniques()
        return dao.list_by_primary_category()

    @app.get("/api/techniques/search")
    def search_techniques(
        q: str = Query(""),
        category: str = Query(""),
        skill: str = Query(""),
        genre: str = Query(""),
        source: str = Query(""),
        limit: int = Query(50, ge=1, le=50),
        offset: int = Query(0, ge=0),
    ):
        """搜索写作技法，支持分类/技能/题材过滤 + 关键词全文检索。
        当 source 参数指定非写作技法来源时，同步检索 reference_entries 表。"""
        dao = get_dao(DirectorDAO, _get_db_path())
        dao.seed_techniques()

        conditions = []
        params = []

        like = None
        if q:
            conditions.append("(name LIKE ? OR description LIKE ? OR keywords LIKE ? OR when_to_use LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like, like])
        if category:
            conditions.append("primary_category = ?")
            params.append(category)
        if skill:
            conditions.append("skill_tags LIKE ?")
            params.append(f"%{skill}%")
        if genre:
            conditions.append("applicable_genres LIKE ?")
            params.append(f"%{genre}%")

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM writing_techniques WHERE {where} ORDER BY name ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        results = dao._fetch(sql, tuple(params))

        if source and source != "写作技法":
            ref_conditions = []
            ref_params_list: list = []
            if q and like:
                ref_conditions.append("(name LIKE ? OR description LIKE ? OR keywords LIKE ?)")
                ref_params_list.extend([like, like, like])
            ref_conditions.append("source_csv = ?")
            ref_params_list.append(source)
            ref_where = " AND ".join(ref_conditions)
            ref_sql = f"SELECT * FROM reference_entries WHERE {ref_where} ORDER BY name ASC LIMIT ? OFFSET ?"
            ref_params_list.extend([limit, offset])
            ref_results = dao._fetch(ref_sql, tuple(ref_params_list))
            results.extend(ref_results)

        return results

    @app.post("/api/techniques")
    def create_technique(data: dict):
        """创建写作技法。POST body 字段对应 writing_techniques 表全部可写列。"""
        dao = get_dao(DirectorDAO, _get_db_path())
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "技法名称不能为空")
        primary = (data.get("primary_category") or data.get("category") or "情节").strip()
        category = dao._PRIMARY_CATEGORY_MAP.get(primary, primary)
        dao._execute(
            """INSERT INTO writing_techniques
               (name, category, primary_category, sub_category, description,
                when_to_use, applicable_genres, keywords, example, anti_pattern,
                model_instruction, detailed_description, level_name, difficulty, source_csv)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                category, primary,
                (data.get("sub_category") or "").strip(),
                (data.get("description") or "").strip(),
                (data.get("when_to_use") or "").strip(),
                (data.get("applicable_genres") or "").strip(),
                (data.get("keywords") or "").strip(),
                (data.get("example") or "").strip(),
                (data.get("anti_pattern") or "").strip(),
                (data.get("model_instruction") or "").strip(),
                (data.get("detailed_description") or "").strip(),
                (data.get("level_name") or "知识补充").strip(),
                int(data.get("difficulty", 5)),
                (data.get("source_csv") or "手动创建").strip(),
            )
        )
        rows = dao._fetch("SELECT * FROM writing_techniques ORDER BY id DESC LIMIT 1")
        return rows[0] if rows else {"ok": True}

    @app.put("/api/techniques/{tech_id}")
    def update_technique(tech_id: int, data: dict):
        """更新写作技法。PUT body 字段对应 writing_techniques 表可写列。"""
        dao = get_dao(DirectorDAO, _get_db_path())
        existing = dao._fetch("SELECT id FROM writing_techniques WHERE id=?", (tech_id,))
        if not existing:
            raise HTTPException(404, "技法不存在")
        allowed = {
            "name", "category", "primary_category", "sub_category", "description",
            "when_to_use", "applicable_genres", "keywords", "example", "anti_pattern",
            "model_instruction", "detailed_description", "level_name", "difficulty",
            "source_csv", "skill_tags",
        }
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            raise HTTPException(400, "没有可更新的字段")
        if "category" in updates:
            updates["primary_category"] = dao._PRIMARY_CATEGORY_MAP.get(
                updates["category"], updates["category"]
            )
        elif "primary_category" in updates:
            updates["category"] = updates["primary_category"]
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [tech_id]
        dao._execute(f"UPDATE writing_techniques SET {set_clause} WHERE id=?", tuple(values))
        rows = dao._fetch("SELECT * FROM writing_techniques WHERE id=?", (tech_id,))
        return rows[0] if rows else {"ok": True}

    @app.delete("/api/techniques/{tech_id}")
    def delete_technique_by_id(tech_id: int):
        """删除指定写作技法。"""
        dao = get_dao(DirectorDAO, _get_db_path())
        existing = dao._fetch("SELECT id FROM writing_techniques WHERE id=?", (tech_id,))
        if not existing:
            raise HTTPException(404, "技法不存在")
        dao._execute("DELETE FROM writing_techniques WHERE id=?", (tech_id,))
        return {"deleted": True, "id": tech_id}

    @app.get("/api/reference/search")
    def search_reference(
        source: str = Query(""),
        q: str = Query(""),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        dao = get_dao(DirectorDAO, _get_db_path())
        dao._ensure_tables()

        conditions = []
        params: list = []
        if source:
            conditions.append("source_csv = ?")
            params.append(source)
        if q:
            conditions.append("(name LIKE ? OR description LIKE ? OR keywords LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM reference_entries WHERE {where} ORDER BY name ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        return dao._fetch(sql, tuple(params))

    @app.get("/api/reference/sources")
    def list_reference_sources():
        dao = get_dao(DirectorDAO, _get_db_path())
        rows = dao._fetch(
            "SELECT source_csv, COUNT(*) as count FROM reference_entries GROUP BY source_csv ORDER BY source_csv"
        )
        return [{"source": r["source_csv"], "count": r["count"]} for r in rows]

    # ===========================================================
    # API：名家采集
    # ===========================================================

    @app.get("/api/collect/progress/{task_id}")
    def get_collection_progress(task_id: str):
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        reports = dao._fetch(
            "SELECT * FROM collection_reports WHERE task_id = ?", (task_id,)
        )
        if not reports:
            raise HTTPException(404, "任务不存在")
        return reports[0]

    @app.get("/api/collect/authors")
    def list_collected_authors():
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        authors_raw = dao.get_authors()
        works = []
        for author in authors_raw:
            chs = dao._fetch(
                """SELECT work_title, COUNT(*) as chapter_count,
                   MAX(created_at) as last_updated
                   FROM collected_chapters WHERE author=?
                   GROUP BY work_title ORDER BY last_updated DESC""",
                (author,)
            )
            total = sum(w['chapter_count'] for w in chs)
            works.append({
                "author": author,
                "total_chapters": total,
                "works": [{
                    "title": w['work_title'],
                    "chapters": w['chapter_count'],
                    "last_updated": w['last_updated'],
                } for w in chs],
                "can_reanalyze": total > 0,
            })
        return {"authors": works}

    @app.get("/api/collect/authors/{author}/styles")
    def get_author_styles(author: str):
        """返回作家的 style_summaries + director_style + 统计聚合结果"""
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        summaries = dao._fetch(
            "SELECT * FROM style_summaries WHERE author=? ORDER BY created_at DESC",
            (author,),
        )
        styles = dao._fetch(
            "SELECT * FROM director_style WHERE name=? ORDER BY created_at DESC",
            (author,),
        )
        chapters = dao._fetch(
            "SELECT COUNT(*) as cnt FROM collected_chapters WHERE author=?",
            (author,),
        )
        last = dao._fetch(
            "SELECT created_at FROM collected_chapters WHERE author=? ORDER BY created_at DESC LIMIT 1",
            (author,),
        )
        return {
            "author": author,
            "summaries": summaries or [],
            "style_rules": styles or [],
            "total_chapters": chapters[0]["cnt"] if chapters else 0,
            "total_summaries": len(summaries or []),
            "last_updated": last[0]["created_at"] if last else "",
        }

    @app.get("/api/collect/summaries")
    def get_style_summaries(
        author: str = Query(None),
        category: str = Query(None),
    ):
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        return {"summaries": dao.get_summaries(author=author, category=category)}

    @app.delete("/api/collect/summaries/{summary_id}")
    def delete_collected_summary(summary_id: int):
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        existing = dao._fetch(
            "SELECT id FROM style_summaries WHERE id = ?", (summary_id,)
        )
        if not existing:
            raise HTTPException(404, "摘要不存在")
        dao._execute("DELETE FROM style_summaries WHERE id = ?", (summary_id,))
        return {"deleted": True, "summary_id": summary_id}

    @app.post("/api/collect/summaries/{summary_id}/retry")
    async def retry_style_summary(summary_id: int):
        """Regenerate a style summary from peer analyses for the same author+dimension.
        Does NOT touch director_style."""
        from .services.style_summarizer import summarize_by_dimension, DIMENSION_MAP

        dao = get_dao(StyleCollectorDAO, _get_db_path())

        # 1. Load target summary to get author + dimension (category)
        target = dao._fetch(
            "SELECT * FROM style_summaries WHERE id = ?", (summary_id,)
        )
        if not target:
            raise HTTPException(404, "摘要不存在")
        target = target[0]
        author = target["author"]
        category = target["category"]  # Chinese display name, e.g. "句式风格"

        # 2. Map category → internal dimension key for summarize_by_dimension
        dim_key = None
        for key, info in DIMENSION_MAP.items():
            if info["display_name"] == category:
                dim_key = key
                break
        if not dim_key:
            raise HTTPException(400, f"未识别的文风维度: {category}")

        # 3. Load peer summaries (same author + category, excluding target)
        peer_rows = dao._fetch(
            "SELECT * FROM style_summaries WHERE author = ? AND category = ? AND id != ?",
            (author, category, summary_id),
        )
        if len(peer_rows) < 2:
            raise HTTPException(
                400,
                f"需要至少 2 条同维度摘要才能聚合，当前仅 {len(peer_rows)} 条",
            )

        # 4. Construct analysis dicts from peers (one per peer, only target dimension)
        analyses: list[dict] = []
        for row in peer_rows:
            score = row.get("quality_score")
            try:
                score = float(score) if score is not None else 0.0
            except (TypeError, ValueError):
                score = 0.0
            analyses.append({
                dim_key: {
                    "summary": row.get("content", "") or "",
                    "score": score,
                }
            })

        # 5. Call summarize_by_dimension to re-aggregate
        results = summarize_by_dimension(analyses)

        # 6. Find regenerated result for our dimension
        new_result = None
        for r in results:
            if r["dimension"] == dim_key:
                new_result = r
                break
        if not new_result:
            raise HTTPException(500, f"聚合失败: 未生成 {category} 的聚合结果")

        # 7. UPSERT: delete old row + insert regenerated row
        dao._execute("DELETE FROM style_summaries WHERE id = ?", (summary_id,))
        dao._execute(
            """INSERT INTO style_summaries
               (author, work_title, summary_title, category, content,
                examples, keywords, quality_score, chapter_range)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                target["author"],
                target.get("work_title", ""),
                f"{target['author']} - {category} (重新聚合)",
                category,
                new_result["summary"],
                target.get("examples", "[]") or "[]",
                target.get("keywords", "[]") or "[]",
                new_result["score"],
                target.get("chapter_range", ""),
            ),
        )

        return {
            "summary_id": summary_id,
            "author": author,
            "category": category,
            "dimension": dim_key,
            "peers_used": len(peer_rows),
            "regenerated": True,
        }

    async def _extract_technique_names_via_ollama(content: str) -> list[dict]:
        """Call Ollama to extract specific technique names from analysis content."""
        from .services.style_analyzer import OLLAMA_CHAT_URL, OLLAMA_MODEL

        TECH_NAME_PROMPT = """你是一位写作技法命名专家。请阅读以下文风分析内容，从中提取2-4个具体的写作技法。每个技法需要name（4-8字，精炼如"潜台词错位式对谈"）、description（50-120字）、keywords（3-5个用/分隔）。技法名不要重复维度标签。严格按JSON数组格式输出：[{"name": "技法名", "description": "描述", "keywords": "关键词/关键词"}]。分析内容：{content}"""

        prompt = TECH_NAME_PROMPT.format(content=content[:3000])
        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", OLLAMA_CHAT_URL,
                "-d", json.dumps({"model": OLLAMA_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False, "think": False}, ensure_ascii=False),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            data = json.loads(stdout.decode("utf-8", errors="replace"))
            response = data.get("message", {}).get("content", "")
            start = response.find("["); end = response.rfind("]")
            if start != -1 and end != -1: return json.loads(response[start:end+1])
            parsed = json.loads(response)
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception as e:
            raise Exception(f"技法名提取失败: {e}")

    def _build_technique_entry(
        tech: dict, s: dict, citation: str, raw_category: str, primary: str,
        content: str, chapter_range: str,
    ) -> dict:
        """Build a single technique entry dict from text extraction + summary metadata."""
        name = f"{tech['name']}（{chapter_range}）" if chapter_range else tech["name"]
        desc = tech.get("description", "")[:200]
        keywords = tech.get("keywords", "")

        # Process summary-level keywords as fallback
        keywords_raw = s.get("keywords", "") or ""
        if not keywords and keywords_raw:
            if isinstance(keywords_raw, str):
                try:
                    kw_list = json.loads(keywords_raw)
                    if isinstance(kw_list, list):
                        keywords = ", ".join(str(k) for k in kw_list)
                except (json.JSONDecodeError, TypeError):
                    keywords = str(keywords_raw)

        # Process examples
        examples_raw = s.get("examples", "") or ""
        example = examples_raw
        if examples_raw:
            try:
                ex_list = json.loads(examples_raw) if isinstance(examples_raw, str) else examples_raw
                if isinstance(ex_list, list) and ex_list:
                    example = "\n".join(
                        f"▶ ✅ {ex}" if not str(ex).startswith("▶") else str(ex)
                        for ex in ex_list
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        # Limit fallback text sizes to prevent massive API responses
        _when_fallback = tech.get("scenes", content[:200] if content else "")
        _detail_fallback = content[:1000] if content else ""

        return {
            "name": name,
            "raw_category": raw_category,
            "primary": primary,
            "sub_category": s.get("category", ""),
            "description": desc,
            "when_to_use": tech.get("when_to_use", _when_fallback),
            "example": example,
            "anti_pattern": tech.get("anti_pattern", ""),
            "source_csv": "名家技法",
            "applicable_genres": citation,
            "detailed_description": tech.get("detailed_description", _detail_fallback),
            "model_instruction": tech.get("model_instruction", ""),
            "keywords": keywords,
            "level_name": tech.get("level_name", "分析提取"),
            "difficulty": tech.get("difficulty", 5),
        }

    @app.post("/api/collect/summaries/{summary_id}/publish")
    async def publish_summary_to_techniques(summary_id: int):
        """将名家分析摘要发布到写作技法库。
        从分析内容中提取具体写作技法名，
        写入 writing_techniques 表（idempotent: name 冲突时 UPDATE）。"""
        try:
            return await _publish_summary_to_techniques_impl(summary_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"publish_summary_to_techniques failed for summary {summary_id}")
            raise HTTPException(500, str(e))

    async def _publish_summary_to_techniques_impl(summary_id: int):
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        summaries = dao._fetch("SELECT * FROM style_summaries WHERE id=?", (summary_id,))
        if not summaries:
            raise HTTPException(404, "摘要不存在")
        s = summaries[0]

        tech_dao = get_dao(DirectorDAO, _get_db_path())
        tech_dao._ensure_tables()

        # Build citation metadata
        citation_parts = []
        if s.get("author"):
            citation_parts.append(f"作者: {s['author']}")
        if s.get("work_title"):
            citation_parts.append(f"作品: {s['work_title']}")
        if s.get("chapter_range"):
            citation_parts.append(f"章节: {s['chapter_range']}")
        citation = "｜".join(citation_parts) if citation_parts else ""

        chapter_range = (s.get("chapter_range") or "").strip()

        # Map summary dimension to category
        _dim_cat = {
            '句式风格': ('文笔', '文笔'), '词汇质地': ('文笔', '文笔'),
            '修辞手法': ('文笔', '文笔'), '叙事视角': ('文笔', '文笔'),
            '对白风格': ('对话', '对话'), '情感张力': ('情感', '情感'),
            '描写偏好': ('场景', '场景'), '节奏控制': ('节奏', '节奏'),
            '人物刻画': ('人物', '人物'),
        }
        raw_category = s.get("category", "情节").strip()
        primary = raw_category
        title = (s.get("summary_title") or "").strip()
        for dim, (cat, prim) in _dim_cat.items():
            if dim in title:
                raw_category, primary = cat, prim
                break

        content = s.get("content", "") or ""
        if not content:
            raise HTTPException(400, "分析内容为空，无法提取技法")

        # Detect format: v2 JSON cluster or legacy markdown
        parsed_techniques = []
        if content.strip().startswith("{"):
            # ── v2 JSON format (from style_summarizer._format_category_summary) ──
            try:
                cluster = json.loads(content)
                if cluster.get("format") == "technique-cluster-v2":
                    for t in cluster.get("techniques", []):
                        parsed_techniques.append({
                            "name": t["name"],
                            "description": t.get("description", "")[:200],
                            "scenes": "、".join(t.get("applicable_scenes", [])),
                            "keywords": "/".join(t.get("sub_categories", [])),
                            "examples": t.get("examples", []),
                        })
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("JSON cluster parse failed, falling back to regex")
                parsed_techniques = []
        
        if not parsed_techniques:
            # ── Legacy markdown format (regex fallback) ──
            technique_blocks = re.split(r'\n(?=##\s)', content)
            for block in technique_blocks:
                name_match = re.search(r'##\s*(.+?)（出现', block)
                if not name_match:
                    continue
                name = name_match.group(1).strip()
                desc_match = re.search(r'说明：(.+?)(?:\n|$)', block)
                desc = desc_match.group(1).strip() if desc_match else ""
                keywords_str = s.get("keywords", "") or ""
                if isinstance(keywords_str, str) and keywords_str.startswith("["):
                    try:
                        kw_list = json.loads(keywords_str)
                        keywords_str = "/".join(kw_list[:6])
                    except Exception:
                        pass
                scenes_match = re.search(r'适用：(.+?)(?:\n|$)', block)
                scenes = scenes_match.group(1).strip() if scenes_match else ""
                parsed_techniques.append({
                    "name": name,
                    "description": desc[:200],
                    "scenes": scenes,
                    "keywords": keywords_str,
                })

        tech_names = parsed_techniques

        # Dedup helpers
        def _name_match(a, b):
            """Check if two technique names are exactly the same (ignoring chapter range suffix).
            Only merge techniques with EXACT same name (cleaned)."""
            a_clean = re.sub(r'[（(].*?[）)]', '', a).strip()
            b_clean = re.sub(r'[（(].*?[）)]', '', b).strip()
            return a_clean == b_clean

        def _merge_texts(old, new):
            """Merge two texts, keeping both if different."""
            if old == new or not new:
                return old
            if not old:
                return new
            return f"{old}\n\n{new}"

        existing = tech_dao._fetch(
            "SELECT id, name, description, example FROM writing_techniques WHERE source_csv='名家技法'",
            (),
        )

        published_techniques = []
        for tech in tech_names:
            entry = _build_technique_entry(
                tech, s, citation, raw_category, primary, content, chapter_range,
            )
            name = entry["name"]

            merged = False
            for ex in existing:
                if _name_match(ex['name'], name):
                    merged_desc = _merge_texts(ex['description'], entry["description"])
                    merged_example = _merge_texts(ex.get('example', ''), entry["example"])
                    tech_dao._execute(
                        "UPDATE writing_techniques SET description=?, example=?, applicable_genres=? WHERE id=?",
                        (merged_desc, merged_example, citation, ex['id']),
                    )
                    merged = True
                    break

            if not merged:
                tech_dao._execute(
                    """INSERT OR REPLACE INTO writing_techniques
                       (name, category, primary_category, sub_category, description,
                        when_to_use, example, anti_pattern, source_csv, applicable_genres,
                        detailed_description, model_instruction, keywords, level_name, difficulty)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        name,
                        entry["raw_category"],
                        entry["primary"],
                        entry["sub_category"],
                        entry["description"],
                        entry["when_to_use"],
                        entry["example"],
                        entry["anti_pattern"],
                        entry["source_csv"],
                        entry["applicable_genres"],
                        entry["detailed_description"],
                        entry["model_instruction"],
                        entry["keywords"],
                        entry["level_name"],
                        entry["difficulty"],
                    ),
                )

            published_techniques.append({"name": name, "merged": merged})

        return {
            "published": True,
            "summary_id": summary_id,
            "techniques": published_techniques,
        }

    @app.get("/api/collect/chapters")
    def get_collected_chapters(
        author: str = Query(None),
        work_title: str = Query(None),
    ):
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        return {"chapters": dao.get_chapters(author=author, work_title=work_title)}

    @app.post("/api/collect/authors/{author}/reanalyze")
    async def reanalyze_author_chapters(author: str, data: dict = None):
        """批量重新分析指定作家的章节。可选过滤: start, end, work_title"""
        if data is None:
            data = {}
        db_path = _get_db_path()
        dao = get_dao(StyleCollectorDAO, db_path)

        start = data.get("start", None)
        end = data.get("end", None)
        work_title = data.get("work_title", None)

        chapters = dao.get_chapters(author=author, work_title=work_title)
        if not chapters:
            raise HTTPException(404, f"作家 '{author}' 没有已采集的章节")

        # Filter by chapter range if specified
        if start is not None or end is not None:
            chapters = [
                ch for ch in chapters
                if (start is None or ch["chapter_num"] >= start) and
                   (end is None or ch["chapter_num"] <= end)
            ]

        if not chapters:
            raise HTTPException(400, "指定范围内没有章节")

        # Create analysis task
        task_id = dao.create_report(author)
        chapter_dicts = [{k: ch[k] for k in ch.keys()} for ch in chapters]
        _collection_tasks[task_id] = asyncio.create_task(
            _analyze_uploaded_book(author, chapter_dicts, task_id, db_path)
        )

        return {
            "task_id": task_id,
            "author": author,
            "work_title": work_title,
            "chapters": len(chapters),
            "range": f"{chapters[0]['chapter_num']}-{chapters[-1]['chapter_num']}" if chapters else "",
            "status": "analyzing",
        }

    @app.get("/api/collect/reports")
    def get_collection_reports(author: str = Query(None)):
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        return {"reports": dao.get_reports(author=author)}

    @app.delete("/api/collect/reports/{report_id}")
    def delete_collection_report(report_id: int):
        """删除采集报告（不删除关联的章节数据）。"""
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        existing = dao._fetch("SELECT id FROM collection_reports WHERE id=?", (report_id,))
        if not existing:
            raise HTTPException(404, "报告不存在")
        dao._execute("DELETE FROM collection_reports WHERE id=?", (report_id,))
        return {"deleted": True, "report_id": report_id}

    @app.delete("/api/collect/reports/batch/failed")
    def delete_failed_collection_reports():
        """批量删除所有 status='failed' 的采集报告。"""
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        reports = dao._fetch(
            "SELECT id FROM collection_reports WHERE status='failed'"
        )
        if not reports:
            return {"deleted": 0, "message": "没有失败的采集报告"}
        ids = [r["id"] for r in reports]
        placeholders = ",".join("?" * len(ids))
        dao._execute(
            f"DELETE FROM collection_reports WHERE id IN ({placeholders})",
            tuple(ids),
        )
        return {"deleted": len(ids), "report_ids": ids}

    @app.get("/api/collect/active")
    def get_active_collections():
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        return {"tasks": dao.get_active_tasks()}

    @app.post("/api/collect/tasks/{task_id}/cancel")
    async def cancel_collection(task_id: str):
        """取消正在运行的采集任务。同时取消 asyncio task 并标记 DB。"""
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        # 取消运行中的 asyncio task
        t = _collection_tasks.get(task_id)
        if t and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        _collection_tasks.pop(task_id, None)
        dao.fail_report(task_id, '用户取消')
        # 清空 activeTask 的 SSE 通知
        try:
            _watcher._dispatch(json.dumps({
                "type": "collection-progress",
                "data": {"task_id": task_id, "author": "", "status": "cancelled",
                         "progress": {"current": 0, "total": 0, "message": "任务已取消"}},
                "ts": time.time(),
            }))
        except Exception:
            pass
        return {"task_id": task_id, "status": "cancelled"}

    @app.post("/api/collect/tasks/{task_id}/retry")
    async def retry_collection(task_id: str):
        """重试失败或卡死的采集任务。"""
        db_path = _get_db_path()
        dao = get_dao(StyleCollectorDAO, db_path)
        reports = dao._fetch(
            "SELECT * FROM collection_reports WHERE task_id = ?", (task_id,)
        )
        if not reports:
            raise HTTPException(404, "任务不存在")
        report = reports[0]
        author = report["author"]

        # 检查是否同一作家的 running task 已存在
        existing = _collection_tasks.get(task_id)
        if existing and not existing.done():
            raise HTTPException(400, "该任务正在运行中")

        # 清理旧 asyncio task
        _collection_tasks.pop(task_id, None)

        # 判断重试路径：有已采集章节 → 直接分析，否则报错（在线搜索已停用）
        chapters = dao.get_chapters(author=author)
        if chapters:
            chapter_dicts = [{k: ch[k] for k in ch.keys()} for ch in chapters]
            new_task_id = dao.create_report(author)
            _collection_tasks[new_task_id] = asyncio.create_task(
                _analyze_uploaded_book(author, chapter_dicts, new_task_id, db_path)
            )
            return {"task_id": new_task_id, "author": author, "chapters": len(chapters), "status": "analyzing"}
        else:
            raise HTTPException(400, "该作家没有已采集的章节，请先通过上传文件进行分析。在线搜索功能已停用。")

    @app.post("/api/collect/tasks/cleanup-stale")
    def cleanup_stale_tasks():
        """清理无对应 asyncio task 的僵尸任务（服务重启后残留的 running 状态）。"""
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        active_reports = dao._fetch(
            "SELECT task_id, author FROM collection_reports WHERE status NOT IN ('done','failed','cancelled')"
        )
        cleaned = 0
        for r in active_reports:
            if r["task_id"] not in _collection_tasks:
                dao._execute(
                    "UPDATE collection_reports SET status='stale', error_message='服务重启，任务丢失' WHERE task_id=?",
                    (r["task_id"],)
                )
                cleaned += 1
        return {"cleaned": cleaned, "message": f"清理了 {cleaned} 个僵尸任务"} if cleaned else {"cleaned": 0}

    @app.post("/api/collect/chapters")
    def save_collected_chapter(data: dict):
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        cid = dao.insert_chapter(data)
        return {"id": cid, "ok": True}

    @app.put("/api/collect/chapters/{chapter_id}")
    def update_collected_chapter(chapter_id: int, data: dict):
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        allowed = {"chapter_title", "status", "author", "work_title"}
        update_data = {k: v for k, v in data.items() if k in allowed}
        if not update_data:
            raise HTTPException(400, "未提供可编辑字段")
        existing = dao._fetch("SELECT id FROM collected_chapters WHERE id=?", (chapter_id,))
        if not existing:
            raise HTTPException(404, "章节不存在")
        set_clause = ", ".join(f"{k} = ?" for k in update_data)
        values = list(update_data.values()) + [chapter_id]
        dao._execute(f"UPDATE collected_chapters SET {set_clause} WHERE id = ?", tuple(values))
        return {"id": chapter_id, **update_data}

    @app.delete("/api/collect/chapters/{chapter_id}")
    def delete_collected_chapter(chapter_id: int):
        """Delete a collected chapter and cascade to associated style_summaries.

        Does NOT touch director_style entries.
        """
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        # Check chapter exists
        existing = dao._fetch(
            "SELECT id, author, chapter_num FROM collected_chapters WHERE id=?",
            (chapter_id,),
        )
        if not existing:
            raise HTTPException(404, "章节不存在")
        ch = existing[0]
        # Compute batch range (10-chapter batches used by _generate_style_summary)
        batch_start = ((ch["chapter_num"] - 1) // 10) * 10 + 1
        chapter_range_pattern = f"第{batch_start}-%章"
        # Count summaries before deletion
        count_rows = dao._fetch(
            "SELECT COUNT(*) as cnt FROM style_summaries WHERE author=? AND chapter_range LIKE ?",
            (ch["author"], chapter_range_pattern),
        )
        summaries_deleted = count_rows[0]["cnt"] if count_rows else 0
        # Delete associated style_summaries
        dao._execute(
            "DELETE FROM style_summaries WHERE author=? AND chapter_range LIKE ?",
            (ch["author"], chapter_range_pattern),
        )
        # Delete the chapter
        dao._execute("DELETE FROM collected_chapters WHERE id=?", (chapter_id,))
        return {"deleted": True, "chapter_id": chapter_id, "summaries_deleted": summaries_deleted}

    @app.post("/api/collect/chapters/delete-batch")
    def delete_collected_chapters_batch(data: dict):
        """Delete ALL collected_chapters, style_summaries, and director_style entries
        for a given author at once."""
        author = (data.get("author") or "").strip()
        if not author:
            raise HTTPException(400, "请提供 author 参数")
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        # Count chapters for author
        ch = dao._fetch("SELECT COUNT(*) as cnt FROM collected_chapters WHERE author=?", (author,))
        chapters_deleted = ch[0]["cnt"] if ch else 0
        if chapters_deleted == 0:
            raise HTTPException(404, f"作家 '{author}' 没有已采集的章节")
        # Count summaries
        sm = dao._fetch("SELECT COUNT(*) as cnt FROM style_summaries WHERE author=?", (author,))
        summaries_deleted = sm[0]["cnt"] if sm else 0
        # Count director_style entries (name matches author)
        st = dao._fetch("SELECT COUNT(*) as cnt FROM director_style WHERE name=?", (author,))
        styles_deleted = st[0]["cnt"] if st else 0
        # Delete style_summaries
        dao._execute("DELETE FROM style_summaries WHERE author=?", (author,))
        # Delete collected_chapters
        dao._execute("DELETE FROM collected_chapters WHERE author=?", (author,))
        # Delete director_style entries for this author
        dao._execute("DELETE FROM director_style WHERE name=?", (author,))
        return {
            "deleted": True,
            "author": author,
            "chapters_deleted": chapters_deleted,
            "summaries_deleted": summaries_deleted,
            "styles_deleted": styles_deleted,
        }

    @app.delete("/api/collect/authors/{author}")
    def delete_author(author: str):
        """级联删除作家的所有采集数据: chapters → summaries → reports → director_style"""
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        # Count and delete collected_chapters
        ch = dao._fetch("SELECT COUNT(*) as cnt FROM collected_chapters WHERE author=?", (author,))
        chapters_deleted = ch[0]["cnt"] if ch else 0
        # Count and delete style_summaries
        sm = dao._fetch("SELECT COUNT(*) as cnt FROM style_summaries WHERE author=?", (author,))
        summaries_deleted = sm[0]["cnt"] if sm else 0
        # Count and delete collection_reports
        rp = dao._fetch("SELECT COUNT(*) as cnt FROM collection_reports WHERE author=?", (author,))
        reports_deleted = rp[0]["cnt"] if rp else 0
        # Count and delete director_style (name field stores author name)
        st = dao._fetch("SELECT COUNT(*) as cnt FROM director_style WHERE name=?", (author,))
        styles_deleted = st[0]["cnt"] if st else 0
        if chapters_deleted == 0 and summaries_deleted == 0 and reports_deleted == 0 and styles_deleted == 0:
            raise HTTPException(404, f"作家 '{author}' 没有已采集的数据")
        # Delete in cascade order
        dao._execute("DELETE FROM style_summaries WHERE author=?", (author,))
        dao._execute("DELETE FROM collection_reports WHERE author=?", (author,))
        dao._execute("DELETE FROM director_style WHERE name=?", (author,))
        dao._execute("DELETE FROM collected_chapters WHERE author=?", (author,))
        return {
            "author": author,
            "chapters_deleted": chapters_deleted,
            "summaries_deleted": summaries_deleted,
            "reports_deleted": reports_deleted,
            "styles_deleted": styles_deleted,
        }

    @app.post("/api/collect/chapters/{chapter_id}/retry")
    async def retry_chapter_analysis(chapter_id: int):
        """Re-analyze a single chapter. Loads content, runs 9-dimension analysis,
        upserts into style_summaries. Does NOT touch director_style."""
        from .services.style_analyzer import analyze_chapter_text, _CN_TO_EN

        db_path = _get_db_path()
        dao = get_dao(StyleCollectorDAO, db_path)

        # 1. Load chapter content and metadata
        content = dao.get_chapter_content(chapter_id)
        if not content:
            raise HTTPException(404, f"章节 {chapter_id} 无正文内容")

        rows = dao._fetch(
            "SELECT author, work_title, chapter_num, chapter_title "
            "FROM collected_chapters WHERE id=?",
            (chapter_id,),
        )
        if not rows:
            raise HTTPException(404, f"章节 {chapter_id} 不存在")

        ch = rows[0]
        author = ch["author"]
        work_title = ch["work_title"]
        chapter_num = ch["chapter_num"]
        chapter_title = ch.get("chapter_title", "")

        # 2. Run 9-dimension analysis
        result = await analyze_chapter_text(content)
        if not result:
            raise HTTPException(500, "文风分析返回空结果（Ollama 可能不可用）")

        # 3. Delete old summaries for this chapter (match by author + chapter_range)
        chapter_range = f"第{chapter_num}章"
        dao._execute(
            "DELETE FROM style_summaries WHERE author=? AND chapter_range=?",
            (author, chapter_range),
        )

        # 4. Insert new summaries (one row per dimension, includes quality_score)
        for cn_key, en_key in _CN_TO_EN.items():
            dim = result.get(en_key)
            if not isinstance(dim, dict):
                continue
            score = dim.get("score", 0)
            try:
                score = max(0.0, min(1.0, float(score)))
            except (TypeError, ValueError):
                score = 0.0
            dao._execute(
                """INSERT INTO style_summaries
                   (author, work_title, summary_title, category, content,
                    examples, keywords, quality_score, chapter_range)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    author,
                    work_title,
                    f"{author} - {cn_key} ({chapter_range})",
                    cn_key,
                    str(dim.get("summary", "")),
                    "[]",
                    "[]",
                    score,
                    chapter_range,
                ),
            )

        # 5. Update chapter status
        dao.update_chapter_status(chapter_id, "analyzed")

        return {
            "chapter_id": chapter_id,
            "author": author,
            "work_title": work_title,
            "chapter_num": chapter_num,
            "chapter_title": chapter_title,
            "analysis": result,
        }

    @app.post("/api/collect/reanalyze")
    async def reanalyze_collection(data: dict):
        author = data.get('author', '').strip()
        if not author:
            raise HTTPException(400, "请输入作家名称")
        db_path = _get_db_path()
        dao = get_dao(StyleCollectorDAO, db_path)
        chapters = dao.get_chapters(author=author)
        if not chapters:
            raise HTTPException(404, f"未找到作家 '{author}' 的已采集章节")
        task_id = dao.create_report(author)
        chapter_dicts = [
            {k: ch[k] for k in ch.keys()} for ch in chapters
        ]
        _collection_tasks[task_id] = asyncio.create_task(
            _analyze_uploaded_book(author, chapter_dicts, task_id, db_path)
        )
        return {"task_id": task_id, "author": author, "chapters": len(chapters), "status": "started"}

    @app.post("/api/collect/migrate")
    def migrate_authors_and_cleanup(dry_run: bool = Query(True)):
        db_path = _get_db_path()
        dao = get_dao(StyleCollectorDAO, db_path)
        import re as _re
        from .services.file_parser import extract_metadata
        result = {"author_fixes": [], "reports_cleaned": 0, "dry_run": dry_run}

        all_chapters = dao._fetch("SELECT id, author, work_title FROM collected_chapters")
        for ch in all_chapters:
            old_author, old_work = ch["author"], ch["work_title"]
            new_author, new_work = old_author, old_work
            m = _re.match(r"^(.+?)作者[：:]\s*(.+)$", old_author or "")
            if m:
                new_work = m.group(1).strip().strip("《》")
                new_author = m.group(2).strip()
            elif "（" in (old_author or "") or "《" in (old_author or ""):
                meta = extract_metadata(old_author + ".txt" if old_author else "")
                new_author = meta.get("author") or old_author
                new_work = meta.get("work_title") or old_work
            if new_author != old_author:
                result["author_fixes"].append({
                    "id": ch["id"], "old_author": old_author, "new_author": new_author,
                })
                if not dry_run:
                    dao._execute("UPDATE collected_chapters SET author=? WHERE id=?",
                                 (new_author, ch["id"]))
                    if new_work != old_work and new_work:
                        dao._execute("UPDATE collected_chapters SET work_title=? WHERE id=?",
                                     (new_work, ch["id"]))

        corrupt = dao._fetch(
            "SELECT id FROM collection_reports WHERE status='done' AND summaries_generated=0"
        )
        result["reports_to_clean"] = len(corrupt)
        if not dry_run and corrupt:
            ids = [r["id"] for r in corrupt]
            dao._execute(f"DELETE FROM collection_reports WHERE id IN ({','.join('?'*len(ids))})", tuple(ids))
            result["reports_cleaned"] = len(ids)

        return result

    @app.post("/api/collect/upload")
    async def upload_book_file(
        file: UploadFile = File(...),
        author: str = Form(""),
        work_title: str = Form(""),
    ):
        """上传整本小说文件（.txt / .md），自动分章并导入名家采集库。

        流程：
        1. 读取文件内容（UTF-8）
        2. 用 chapter_splitter 自动识别章节边界并切分
        3. 将章节写入 collected_chapters 表
        4. 返回 task_id，后台启动文风分析
        """
        # 校验文件类型
        filename = str(file.filename or "")
        if not filename.lower().endswith((".txt", ".md", ".text", ".markdown")):
            raise HTTPException(400, "仅支持 .txt / .md 文件")

        # 读取内容
        content_bytes = await file.read()
        if not content_bytes:
            raise HTTPException(400, "文件内容为空")
        try:
            text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content_bytes.decode("gbk")
            except UnicodeDecodeError:
                raise HTTPException(400, "文件编码不支持（仅支持 UTF-8 / GBK）")
        del content_bytes  # 释放原始字节，避免 bytes+str 双倍内存峰值

        if not text.strip():
            raise HTTPException(400, "文件内容为空")

        # 推导作者名和工作名：文件名 → 正文前几行 → 兜底
        from .services.file_parser import extract_metadata, extract_metadata_from_content
        meta = extract_metadata(filename)
        resolved_author = author.strip() or meta.get("author", "")
        resolved_work = work_title.strip() or meta.get("work_title", "")
        if not resolved_author or not resolved_work:
            content_meta = extract_metadata_from_content(text)
            resolved_author = resolved_author or content_meta.get("author", "")
            resolved_work = resolved_work or content_meta.get("work_title", "")
        resolved_author = resolved_author or filename.rsplit(".", 1)[0].strip()
        resolved_work = resolved_work or resolved_author

        # 提前创建采集任务以获取 task_id（用于 SSE 进度推送）
        dao = get_dao(StyleCollectorDAO, _get_db_path())
        task_id = dao.create_report(resolved_author)

        # SSE 进度推送 helper（上传/解析阶段也用同一个 task_id）
        def _upload_dispatch(status, msg, current=0, total=5):
            try:
                _watcher._dispatch(json.dumps({
                    "type": "collection-progress",
                    "data": {"task_id": task_id, "author": resolved_author, "status": status,
                             "progress": {"current": current, "total": total, "message": msg}},
                    "ts": time.time(),
                }))
            except Exception:
                pass

        _upload_dispatch("processing", f"读取完成，开始解析 {filename}", 1, 5)

        # 分章
        from .services.chapter_splitter import split_chapters
        segments = split_chapters(text)
        del text  # 立即释放原始全文，仅保留分章后的 segments 列表

        if not segments:
            raise HTTPException(400, "未能从文件中识别出章节，请检查文件格式")

        _upload_dispatch("splitting", f"已识别 {len(segments)} 个章节，正在保存到数据库...", 1, 5)

        # 写入数据库（逐章保存 + 记录 DB id 用于后续分析状态更新）
        saved_count = 0
        chapter_id_map = {}  # seg.chapter_num → db row id
        for si, seg in enumerate(segments):
            try:
                ch_id = dao.insert_chapter({
                    "author": resolved_author,
                    "work_title": resolved_work,
                    "chapter_num": seg.chapter_num,
                    "chapter_title": seg.title or f"第{seg.chapter_num}章",
                    "content": seg.content,
                    "source_url": f"upload://{filename}",
                    "word_count": len(seg.content),
                    "status": "raw",
                })
                saved_count += 1
                chapter_id_map[seg.chapter_num] = ch_id
                # 每 20 章推送一次保存进度
                if (si + 1) % 20 == 0:
                    _upload_dispatch("saving", f"已保存 {saved_count}/{len(segments)} 章...", 2, 5)
            except Exception:
                continue

        _upload_dispatch("saving", f"保存完成（{saved_count}/{len(segments)} 章），启动文风分析...", 2, 5)

        # 提取章节内容列表用于分析（携带 DB id 用于后续状态更新）
        chapters_for_analysis = [
            {
                "id": chapter_id_map.get(seg.chapter_num),
                "author": resolved_author,
                "work_title": resolved_work,
                "chapter_num": seg.chapter_num,
                "chapter_title": seg.title or f"第{seg.chapter_num}章",
                "source_url": f"upload://{filename}",
            }
            for seg in segments
        ]
        # 释放分章列表并强制 GC，避免内存膨胀
        detected_count = len(segments)
        del segments
        gc.collect()
        _collection_tasks[task_id] = asyncio.create_task(
            _analyze_uploaded_book(resolved_author, chapters_for_analysis, task_id, _get_db_path())
        )

        return {
            "task_id": task_id,
            "author": resolved_author,
            "work_title": resolved_work,
            "chapters_detected": detected_count,
            "chapters_saved": saved_count,
            "status": "analyzing",
        }

    async def _analyze_uploaded_book(author: str, chapters: list[dict], task_id: str, db_path: str):
        """后台分析上传的书籍章节（跳过搜索和下载阶段，直接分析）。"""
        dao = get_dao(StyleCollectorDAO, db_path)
        async def _dispatch(status, msg, current=2, total=5):
            try:
                _watcher._dispatch(json.dumps({
                    "type": "collection-progress",
                    "data": {"task_id": task_id, "author": author, "status": status,
                             "progress": {"current": current, "total": total, "message": msg}},
                    "ts": time.time(),
                }))
            except Exception:
                pass
        try:
            dao.update_progress(task_id, "analyzing", f"开始分析 {author} 的文风（共 {len(chapters)} 章）", 2, 5)
            await _dispatch("analyzing", f"开始分析文风（共 {len(chapters)} 章）", 2)
            if not await _check_ollama_health():
                dao.fail_report(task_id, 'Ollama 服务不可用，请确认已启动')
                await _dispatch("failed", "Ollama 服务不可用")
                return
            analyses: list[dict] = []
            async for result in _analyze_chapters(chapters, task_id, dao, db_path, _dispatch):
                analyses.append(result)

            dao.update_progress(task_id, "summarizing", "生成文风总结", 3, 5)
            await _dispatch("summarizing", "生成文风总结", 3)
            await _generate_style_summary(author, analyses, dao, db_path)

            dao.complete_report(task_id, len(chapters), len(analyses))
            await _dispatch("done", f"完成：{len(chapters)} 章，{len(analyses)} 条分析", 5, 5)
        except asyncio.CancelledError:
            dao.fail_report(task_id, "任务被取消")
            await _dispatch("failed", "任务被取消")
            raise
        except Exception as e:
            dao.fail_report(task_id, str(e)[:500])
            await _dispatch("failed", str(e)[:100])
        finally:
            _collection_tasks.pop(task_id, None)

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
    # API：数据库维护 - VACUUM
    # ===========================================================

    @app.post("/api/admin/vacuum")
    async def vacuum_database(full: bool = Query(True)):
        """Execute database VACUUM operation.

        - full=True (default): full VACUUM, rebuilds entire database. Slow (~minutes).
        - full=False: incremental vacuum, frees up to N pages from freelist. Fast.
        """
        global _vacuum_lock
        db_path = _webnovel_dir() / "index.db"
        if not db_path.is_file():
            raise HTTPException(404, "index.db 不存在")

        if _vacuum_lock is None or _vacuum_lock.locked():
            raise HTTPException(409, "VACUUM 正在执行中，请稍后再试")

        async with _vacuum_lock:
            pages_before = 0
            pages_after = 0

            def _run_vacuum():
                nonlocal pages_before, pages_after
                conn = sqlite3.connect(str(db_path), timeout=10)
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    pages_before = conn.execute("PRAGMA page_count").fetchone()[0]
                    if full:
                        conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
                        conn.execute("VACUUM")
                    else:
                        conn.execute("PRAGMA incremental_vacuum(500)")
                    pages_after = conn.execute("PRAGMA page_count").fetchone()[0]
                finally:
                    conn.close()

            try:
                await asyncio.to_thread(_run_vacuum)
            except Exception as exc:
                raise HTTPException(500, f"VACUUM 失败: {exc}") from exc

            return {
                "ok": True,
                "type": "full" if full else "incremental",
                "pages_before": pages_before,
                "pages_after": pages_after,
                "pages_freed": pages_before - pages_after,
            }

    # ===========================================================
    # API：批量操作
    # ===========================================================

    _BATCH_ACTIONS = {
        "write": {
            "cmd": ["orchestrate", "write"],
            "timeout": 300,
            "desc": "批量写入章节",
        },
        "delete": {
            "cmd": ["delete-chapters"],
            "timeout": 60,
            "desc": "批量删除章节",
        },
    }

    @app.post("/api/batch/{action}")
    async def batch_action(action: str, request: dict):
        """批量操作（write/delete），使用 async subprocess 避免阻塞。"""
        if action not in _BATCH_ACTIONS:
            raise HTTPException(403, f"不允许的批量操作: {action}")

        chapters = request.get("chapters")
        if not chapters:
            raise HTTPException(400, "chapters 不能为空")
        chapters = str(chapters).strip()
        if not re.match(r'^[\d,\-\s]+$', chapters):
            raise HTTPException(400, "chapters 格式无效，只允许数字、逗号、连字符")

        spec = _BATCH_ACTIONS[action]
        cmd = [
            sys.executable, "-X", "utf8",
            str(SCRIPTS_DIR / "webnovel.py"),
            "--project-root", str(_get_project_root()),
            *spec["cmd"], chapters,
        ]

        if action == "delete" and not request.get("confirm", False):
            cmd.append("--dry-run")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=spec["timeout"],
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            raise HTTPException(504, f"批量操作超时（{spec['timeout']}s）")

        result_stdout = stdout.decode("utf-8", errors="replace")
        result_stderr = stderr.decode("utf-8", errors="replace")
        result_code = proc.returncode or 0

        try:
            _watcher._dispatch(json.dumps({
                "type": "batch-done", "action": action,
                "code": result_code, "ts": time.time(),
            }))
        except Exception:
            pass

        return {
            "action": action,
            "desc": spec["desc"],
            "stdout": result_stdout,
            "stderr": result_stderr,
            "code": result_code,
            "dry_run": action == "delete" and not request.get("confirm", False),
        }

    # ===========================================================
    # 前端静态文件托管
    # ===========================================================

    if STATIC_DIR.is_dir() and (STATIC_DIR / "index.html").is_file():
        assets_dir = STATIC_DIR / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

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
            build_cmd = "cd .opencode/dashboard/frontend && npm install && npm run build"
            return HTMLResponse(
                "<h2>Webnovel Dashboard API is running</h2>"
                "<p>前端尚未构建。请先在 <code>dashboard/frontend</code> 目录执行：</p>"
                f"<pre><code>{build_cmd}</code></pre>"
                "<p>构建完成后刷新页面即可。API 文档：<a href='/docs'>/docs</a></p>")

    return app
