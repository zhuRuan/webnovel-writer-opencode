#!/bin/bash
# Webnovel Dashboard — 一键重启前后端（先停旧，再启新）
# Atlas 调用: bash restart.sh
# 只启后端:  bash restart.sh --no-frontend

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── 固化项目环境（本机专用于此项目开发） ──
export PYTHONPATH="$ROOT_DIR/.opencode:$PYTHONPATH"
export WEBNOVEL_PROJECT_ROOT="$ROOT_DIR/特级"

# ── 停止旧进程 ──
fuser -k 8765/tcp 2>/dev/null && echo "[stop] 旧后端已停" || true
fuser -k 5173/tcp 2>/dev/null && echo "[stop] 旧前端已停" || true
sleep 2

# ── 后端 (FastAPI, port 8765) ──
echo "[backend] 启动 → http://127.0.0.1:8765"
cd "$ROOT_DIR/.opencode"
setsid python3 -m dashboard --project-root "$WEBNOVEL_PROJECT_ROOT" > /tmp/dashboard.log 2>&1 &
for i in $(seq 1 15); do
  curl -s http://127.0.0.1:8765/api/projects > /dev/null 2>&1 && break
  sleep 1
done
echo "[backend] 就绪"

# ── 前端 (Vite, port 5173) ──
if [ "${1:-}" != "--no-frontend" ]; then
  echo "[frontend] 启动 → http://127.0.0.1:5173"
  cd "$ROOT_DIR/.opencode/dashboard/frontend"
  nohup npx vite --host 0.0.0.0 --port 5173 > /tmp/vite.log 2>&1 &
  echo "[frontend] 已启动"
fi

echo "后端: http://127.0.0.1:8765"
[ "${1:-}" != "--no-frontend" ] && echo "前端: http://127.0.0.1:5173"
