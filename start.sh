#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# start.sh - BTC Trading Bot Startup Script
# ============================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
DATA_DIR="$REPO_DIR/data"
LOGS_DIR="$REPO_DIR/logs"
ENV_FILE="$REPO_DIR/.env"

echo "============================================================"
echo "  BTC Trading Bot - Starting"
echo "============================================================"

# --- 1. Check .env ---
if [ ! -f "$ENV_FILE" ]; then
    echo "[FAIL] No .env file found."
    echo "       Run: cp .env.example .env"
    echo "       Then edit .env with your API keys."
    exit 1
fi
echo "[OK] .env found"

# --- 2. Check virtual environment ---
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "[FAIL] Virtual environment not found."
    echo "       Run: ./install.sh"
    exit 1
fi
echo "[OK] Virtual environment found"

# --- 3. Check directories ---
mkdir -p "$DATA_DIR" "$LOGS_DIR"
echo "[OK] Directories ready"

# --- 4. Check if already running ---
PID_FILE="$REPO_DIR/bot.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[FAIL] Bot is already running (PID $OLD_PID)"
        echo "       Run: ./stop.sh"
        exit 1
    fi
    rm -f "$PID_FILE"
fi

# --- 5. Start the bot ---
echo "[...] Starting bot..."
cd "$REPO_DIR"
nohup "$VENV_DIR/bin/python" main.py >> "$LOGS_DIR/startup.log" 2>&1 &
BOT_PID=$!
echo "$BOT_PID" > "$PID_FILE"

# --- 6. Wait and verify ---
sleep 3
if kill -0 "$BOT_PID" 2>/dev/null; then
    echo "[OK] Bot started (PID $BOT_PID)"
    echo ""
    echo "  View logs:  tail -f logs/application.log"
    echo "  Stop bot:   ./stop.sh"
    echo "  Status:     ./healthcheck.sh"
else
    echo "[FAIL] Bot failed to start"
    echo "       Check logs: tail -n 20 logs/startup.log"
    rm -f "$PID_FILE"
    exit 1
fi
