"""
项目元信息路由 —— 4 个只读 GET 端点。

从 app.py 迁移:
  GET /api/project/info          → state.json 只读投影
  GET /api/story-runtime/health  → 故事运行时健康报告
  GET /api/env-status            → embedding / rerank / vector DB 状态
  GET /api/env-status/probe      → 全面健康检查汇总
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..core.config import get_project_root, get_webnovel_dir
from ..schemas.project import (
    EnvStatus,
    HealthCheck,
    HealthProbeResponse,
    ProjectInfo,
    StoryRuntimeHealth,
)

router = APIRouter(prefix="/api")


# ── 辅助函数（从 app.py 迁移） ─────────────────────────────────────


def _load_state_payload(*, required: bool = False) -> dict:
    """读取 .webnovel/state.json 返回字典。"""
    state_path = get_webnovel_dir() / "state.json"
    if not state_path.is_file():
        if required:
            raise HTTPException(404, "state.json 不存在")
        return {}

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"state.json 读取失败: {exc}") from exc

    return payload if isinstance(payload, dict) else {}


def _build_story_runtime_health_report(project_root: Path) -> dict:
    """委托 data_modules 构建运行时健康报告。"""
    from data_modules.story_runtime_health import build_story_runtime_health

    return build_story_runtime_health(project_root)


# ── 端点 ──────────────────────────────────────────────────────────


@router.get("/project/info", response_model=ProjectInfo)
def project_info():
    """返回 state.json 完整内容（只读）。"""
    return _load_state_payload(required=True)


@router.get("/story-runtime/health", response_model=StoryRuntimeHealth)
def story_runtime_health():
    """返回故事运行时健康度。"""
    return _build_story_runtime_health_report(get_project_root())


@router.get("/env-status", response_model=EnvStatus)
def env_status():
    """返回环境状态（embed / rerank / vector DB）。"""
    from ..services.env import build_env_status

    return build_env_status(get_project_root())


@router.get("/env-status/probe", response_model=HealthProbeResponse)
def env_status_probe():
    """全面检查：环境状态 + 运行时健康，汇总为统一健康报告。"""
    from ..services.env import build_env_status

    status = build_env_status(get_project_root())
    runtime = _build_story_runtime_health_report(get_project_root())
    vector_db = status["vector_db"]
    checks = [
        HealthCheck(
            name="embed_api_key",
            ok=bool(status["embed"]["api_key_present"]),
            detail="已配置" if status["embed"]["api_key_present"] else "未配置",
        ),
        HealthCheck(
            name="rerank_api_key",
            ok=bool(status["rerank"]["api_key_present"]),
            detail="已配置" if status["rerank"]["api_key_present"] else "未配置",
        ),
        HealthCheck(
            name="vector_db",
            ok=bool(vector_db["exists"] and not vector_db["error"]),
            detail=vector_db["error"]
            or f"{vector_db['record_count']} records · {vector_db['size_bytes']} bytes",
        ),
        HealthCheck(
            name="story_runtime",
            ok=bool(runtime.get("mainline_ready")),
            detail=(
                f"chapter={runtime.get('chapter')} "
                f"status={runtime.get('latest_commit_status')} "
                f"fallback={','.join(runtime.get('fallback_sources') or []) or 'none'}"
            ),
        ),
    ]
    return HealthProbeResponse(
        ok=all(item.ok for item in checks),
        rag_mode=status["rag_mode"],
        checks=checks,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
