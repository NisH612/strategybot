#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# healthcheck.sh - BTC Trading Bot Health Check
# ============================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$REPO_DIR/bot.pid"
PASS=0
FAIL=0

check() {
    local name="$1"
    local result="$2"
    if [ "$result" = "PASS" ]; then
        echo "  [PASS] $name"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $name $3"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================================"
echo "  BTC Trading Bot - Health Check"
echo "============================================================"
echo ""

# --- 1. Process status ---
BOT_PID=""
if [ -f "$PID_FILE" ]; then
    BOT_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
fi
if [ -n "$BOT_PID" ] && kill -0 "$BOT_PID" 2>/dev/null; then
    check "Bot process" "PASS" "(PID $BOT_PID)"
elif BOT_PID=$(pgrep -f "python.*main.py" 2>/dev/null || true) && [ -n "$BOT_PID" ]; then
    check "Bot process" "PASS" "(PID $BOT_PID)"
else
    check "Bot process" "FAIL" "(not running)"
fi

# --- 2. Binance API connectivity ---
if [ -f "$REPO_DIR/.env" ] && command -v curl &>/dev/null; then
    TESTNET=$(grep -E "^BINANCE_TESTNET=" "$REPO_DIR/.env" | cut -d= -f2 | tr -d ' ')
    if [ "$TESTNET" = "false" ]; then
        BINANCE_URL="https://fapi.binance.com/fapi/v1/ping"
    else
        BINANCE_URL="https://testnet.binancefuture.com/fapi/v1/ping"
    fi
    if curl -sf "$BINANCE_URL" >/dev/null 2>&1; then
        check "Binance API" "PASS"
    else
        check "Binance API" "FAIL" "(cannot reach $BINANCE_URL)"
    fi
else
    check "Binance API" "FAIL" "(missing .env or curl)"
fi

# --- 3. Discord API connectivity ---
if command -v curl &>/dev/null; then
    if curl -sf "https://discord.com/api/v10/gateway" >/dev/null 2>&1; then
        check "Discord API" "PASS"
    else
        check "Discord API" "FAIL" "(cannot reach discord.com)"
    fi
else
    check "Discord API" "FAIL" "(curl not available)"
fi

# --- 4. Database ---
DB_FILE="$REPO_DIR/data/trades.db"
if [ -f "$DB_FILE" ]; then
    DB_SIZE=$(stat --format=%s "$DB_FILE" 2>/dev/null || stat -f%z "$DB_FILE" 2>/dev/null || echo "0")
    if [ "$DB_SIZE" -gt 0 ] 2>/dev/null; then
        check "Database" "PASS" "($DB_FILE, ${DB_SIZE} bytes)"
    else
        check "Database" "FAIL" "(empty database)"
    fi
else
    check "Database" "FAIL" "(not found - will be created on start)"
fi

# --- 5. WebSocket ---
# Check WebSocket via the exchange by looking at recent kline data
if [ -n "$BOT_PID" ] && kill -0 "$BOT_PID" 2>/dev/null; then
    if [ -f "$REPO_DIR/logs/application.log" ]; then
        # Check for recent WebSocket activity
        if tail -n 50 "$REPO_DIR/logs/application.log" | grep -q "candle\|ticker\|WebSocket\|connected"; then
            check "WebSocket" "PASS"
        else
            check "WebSocket" "WARN" "(no recent activity in logs)"
        fi
    else
        check "WebSocket" "WARN" "(no logs yet)"
    fi
else
    check "WebSocket" "FAIL" "(bot not running)"
fi

# --- 6. REST API ---
API_PORT=$(grep -E "^API_PORT=" "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d ' ' || echo "8080")
if command -v curl &>/dev/null; then
    if curl -sf "http://127.0.0.1:${API_PORT}/status" >/dev/null 2>&1; then
        check "REST API" "PASS" "(port $API_PORT)"
    else
        check "REST API" "FAIL" "(port $API_PORT not responding)"
    fi
else
    check "REST API" "FAIL" "(curl not available)"
fi

# --- 7. Memory ---
if [ -n "$BOT_PID" ] && kill -0 "$BOT_PID" 2>/dev/null; then
    MEM=$(ps -o rss= -p "$BOT_PID" 2>/dev/null || echo "0")
    MEM_MB=$((MEM / 1024))
    if [ "$MEM_MB" -lt 500 ]; then
        check "Memory" "PASS" "(${MEM_MB}MB RSS)"
    else
        check "Memory" "WARN" "(${MEM_MB}MB RSS - high usage)"
    fi
    CPU=$(ps -o %cpu= -p "$BOT_PID" 2>/dev/null || echo "0")
    if [ "$(echo "$CPU < 50" | bc 2>/dev/null || echo 0)" -eq 1 ]; then
        check "CPU" "PASS" "(${CPU}%)"
    else
        check "CPU" "WARN" "(${CPU}% - high usage)"
    fi
else
    check "Memory" "FAIL" "(bot not running)"
    check "CPU" "FAIL" "(bot not running)"
fi

# --- 8. Disk space ---
AVAIL=$(df -m "$REPO_DIR" 2>/dev/null | awk 'NR==2 {print $4}' || echo "0")
if [ "$AVAIL" -gt 1000 ] 2>/dev/null; then
    check "Disk space" "PASS" "(${AVAIL}MB available)"
elif [ "$AVAIL" -gt 100 ] 2>/dev/null; then
    check "Disk space" "WARN" "(only ${AVAIL}MB available)"
else
    check "Disk space" "FAIL" "(${AVAIL}MB available - critically low)"
fi

# --- 9. Log files ---
if [ -f "$REPO_DIR/logs/application.log" ]; then
    LOG_SIZE=$(stat --format=%s "$REPO_DIR/logs/application.log" 2>/dev/null || stat -f%z "$REPO_DIR/logs/application.log" 2>/dev/null || echo "0")
    LOG_HUMAN=$((LOG_SIZE / 1024))
    check "Log files" "PASS" "(${LOG_HUMAN}KB application.log)"
else
    check "Log files" "WARN" "(no logs yet)"
fi

echo ""
echo "============================================================"
if [ "$FAIL" -eq 0 ]; then
    echo "  RESULT: $PASS passed, 0 failed - ALL OK"
else
    echo "  RESULT: $PASS passed, $FAIL failed - issues detected"
fi
echo "============================================================"

# Exit with code based on failures
[ "$FAIL" -eq 0 ]
