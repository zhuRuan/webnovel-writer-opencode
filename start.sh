#!/bin/bash
# Webnovel Dashboard — 一键启动前后端
# Usage: bash start.sh

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================"
echo " Webnovel Dashboard — 启动中..."
echo "========================================"

# 1. 启动后端 (FastAPI, port 8765)
echo "[backend] 启动 FastAPI 服务 → http://127.0.0.1:8765"
cd "$ROOT_DIR"
python3 -m .opencode.dashboard &
BACKEND_PID=$!
echo "[backend] PID=$BACKEND_PID"

# 等待后端就绪
echo "[backend] 等待后端就绪..."
for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:8765/ > /dev/null 2>&1; then
    echo "[backend] 就绪！"
    break
  fi
  sleep 1
done

# 2. 启动前端 (React + Vite)
echo "[frontend] 启动 Vite 开发服务器 → http://127.0.0.1:5173"
cd "$ROOT_DIR/.opencode/dashboard/frontend"
npx vite --host 0.0.0.0 &
FRONTEND_PID=$!
echo "[frontend] PID=$FRONTEND_PID"

echo ""
echo "========================================"
echo " 启动完成！"
echo " 后端: http://127.0.0.1:8765"
echo " 前端: http://127.0.0.1:5173"
echo "========================================"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 捕获退出信号，清理子进程
cleanup() {
  echo ""
  echo "正在停止所有服务..."
  kill $BACKEND_PID 2>/dev/null
  kill $FRONTEND_PID 2>/dev/null
  wait 2>/dev/null
  echo "已停止。"
}
trap cleanup EXIT INT TERM

# 等待任一子进程退出
wait
