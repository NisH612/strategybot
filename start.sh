#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# start.sh - BTC Trading Bot Startup Script
# ============================================================
# Usage: ./start.sh
# Starts the bot in the background using nohup.
# ============================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
DATA_DIR="$REPO_DIR/data"
LOGS_DIR="$REPO_DIR/logs"
ENV_FILE="$REPO_DIR/.env"
PID_FILE="$REPO_DIR/bot.pid"

echo "============================================================"
echo "  BTC Trading Bot - Starting"
echo "============================================================"
echo ""

# --- 1. Check .env ---
if [ ! -f "$ENV_FILE" ]; then
    echo "[FAIL] .env file not found at: $ENV_FILE"
    echo ""
    echo "  Create one by running:"
    echo "    cp .env.example .env"
    echo "    nano .env"
    echo ""
    exit 1
fi
echo "[OK] .env found"

# --- 2. Validate .env has required vars ---
MISSING=""
for var in BINANCE_API_KEY BINANCE_SECRET DISCORD_TOKEN DISCORD_CHANNEL_ID; do
    VAL=$(grep -E "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d ' "'"'"'")
    if [ -z "$VAL" ]; then
        MISSING="$MISSING $var"
    fi
done
if [ -n "$MISSING" ]; then
    echo "[WARN] Missing environment variables:$MISSING"
    echo "       The bot may not function correctly."
    echo "       Edit .env to add them."
    echo ""
fi

# --- 3. Check virtual environment ---
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "[FAIL] Virtual environment not found at: $VENV_DIR"
    echo ""
    echo "  Run: ./install.sh"
    echo ""
    exit 1
fi
echo "[OK] Virtual environment found"

# --- 4. Create required directories ---
mkdir -p "$DATA_DIR" "$LOGS_DIR"
echo "[OK] Directories ready"

# --- 5. Check if already running ---
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[FAIL] Bot is already running (PID $OLD_PID)"
        echo ""
        echo "  Run: ./stop.sh"
        echo "  Or: ./restart.sh"
        echo ""
        exit 1
    fi
    rm -f "$PID_FILE"
fi

# --- 6. Change to project directory ---
cd "$REPO_DIR"

# --- 7. Start the bot ---
echo "[...] Starting bot..."
nohup "$VENV_DIR/bin/python" main.py >> "$LOGS_DIR/startup.log" 2>&1 &
BOT_PID=$!
echo "$BOT_PID" > "$PID_FILE"

# --- 8. Wait and verify ---
sleep 3
if kill -0 "$BOT_PID" 2>/dev/null; then
    echo "[OK] Bot started (PID $BOT_PID)"
    echo ""
    echo "  View logs:  tail -f logs/application.log"
    echo "  Stop bot:   ./stop.sh"
    echo "  Restart:    ./restart.sh"
    echo "  Status:     ./healthcheck.sh"
    echo ""
else
    echo "[FAIL] Bot failed to start"
    echo ""
    echo "  Check the startup log:"
    echo "    tail -n 30 logs/startup.log"
    echo "    tail -n 30 logs/error.log"
    echo ""
    rm -f "$PID_FILE"
    exit 1
fi
