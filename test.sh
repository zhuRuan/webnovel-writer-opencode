#!/usr/bin/env bash
#
# test.sh — Dashboard test environment setup
#
# Usage:
#   ./test.sh            Start dashboard and wait for readiness
#   ./test.sh --stop     Kill the running dashboard
#

set -e

PIDFILE="/tmp/dashboard-test.pid"
PORT=8765
HEALTH_URL="http://localhost:${PORT}/api/entities"
TIMEOUT=30

start() {
    echo "Starting dashboard on port ${PORT}..."

    # Start dashboard in background
    python -m .opencode.dashboard &
    DASH_PID=$!

    # Record PID
    echo "$DASH_PID" > "$PIDFILE"
    echo "Dashboard PID: $DASH_PID"

    # Poll health endpoint until ready
    echo "Waiting for dashboard to become ready..."
    ELAPSED=0
    while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
        if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
            echo "Dashboard ready on port ${PORT}"
            exit 0
        fi
        sleep 1
        ELAPSED=$((ELAPSED + 1))
    done

    echo "ERROR: Dashboard failed to start within ${TIMEOUT}s" >&2
    kill "$DASH_PID" 2>/dev/null || true
    rm -f "$PIDFILE"
    exit 1
}

stop() {
    if [ ! -f "$PIDFILE" ]; then
        echo "No dashboard PID file found at ${PIDFILE}" >&2
        exit 1
    fi

    DASH_PID=$(cat "$PIDFILE")
    echo "Stopping dashboard (PID: $DASH_PID)..."

    kill "$DASH_PID" 2>/dev/null || true
    rm -f "$PIDFILE"

    # Wait for port to be freed
    echo "Waiting for port ${PORT} to be released..."
    for i in $(seq 1 10); do
        if ! curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
            echo "Dashboard stopped, port ${PORT} released."
            exit 0
        fi
        sleep 1
    done

    echo "WARNING: Port ${PORT} still in use after 10s" >&2
    exit 1
}

case "${1:-}" in
    --stop)
        stop
        ;;
    *)
        start
        ;;
esac
