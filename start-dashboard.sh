#!/bin/bash
# webnovel-writer Dashboard — 一键启动 (后端8765 + 前端同端口)
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
export WEBNOVEL_PROJECT_ROOT="$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/.opencode"
lsof -i :8765 -t 2>/dev/null | xargs kill 2>/dev/null
sleep 1
echo "启动 Dashboard: http://127.0.0.1:8765"
cd "$PROJECT_ROOT"
python3 -m dashboard.server --project-root "$PROJECT_ROOT" --port 8765 --kill-existing
