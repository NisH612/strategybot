#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# stop.sh - BTC Trading Bot Stop Script
# ============================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$REPO_DIR/bot.pid"

echo "============================================================"
echo "  BTC Trading Bot - Stopping"
echo "============================================================"

if [ ! -f "$PID_FILE" ]; then
    echo "[WARN] No PID file found. Bot may not be running."
    # Try to find by process name
    BOT_PID=$(pgrep -f "python.*main.py" 2>/dev/null || true)
    if [ -n "$BOT_PID" ]; then
        echo "[...] Found bot process (PID $BOT_PID)"
        echo "[...] Sending SIGINT (graceful shutdown)..."
        kill -SIGINT "$BOT_PID" 2>/dev/null || true
        sleep 2
        if kill -0 "$BOT_PID" 2>/dev/null; then
            echo "[...] Waiting for process to exit..."
            sleep 5
            kill -0 "$BOT_PID" 2>/dev/null && kill -SIGTERM "$BOT_PID" 2>/dev/null || true
            sleep 2
        fi
        echo "[OK] Bot stopped"
    else
        echo "[OK] No bot process found"
    fi
    exit 0
fi

BOT_PID=$(cat "$PID_FILE")
if [ -z "$BOT_PID" ]; then
    echo "[WARN] PID file is empty"
    rm -f "$PID_FILE"
    exit 0
fi

if ! kill -0 "$BOT_PID" 2>/dev/null; then
    echo "[WARN] Bot process (PID $BOT_PID) is not running"
    rm -f "$PID_FILE"
    exit 0
fi

echo "[...] Sending SIGINT (graceful shutdown) to PID $BOT_PID..."
kill -SIGINT "$BOT_PID" 2>/dev/null || true

# Wait up to 15 seconds for graceful shutdown
echo "[...] Waiting for graceful shutdown..."
for i in $(seq 1 15); do
    if ! kill -0 "$BOT_PID" 2>/dev/null; then
        echo "[OK] Bot stopped"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# Force kill if still alive
echo "[WARN] Graceful shutdown timed out. Sending SIGTERM..."
kill -SIGTERM "$BOT_PID" 2>/dev/null || true
sleep 2
if kill -0 "$BOT_PID" 2>/dev/null; then
    echo "[WARN] Sending SIGKILL..."
    kill -SIGKILL "$BOT_PID" 2>/dev/null || true
fi

echo "[OK] Bot stopped"
rm -f "$PID_FILE"
