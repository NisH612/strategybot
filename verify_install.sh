#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# verify_install.sh - Deployment Verification Script
# ============================================================
# Run after install.sh to confirm everything is ready.
# Returns PASS/FAIL for each check.
# ============================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0
WARN=0

check() {
    local name="$1"
    local result="$2"
    local msg="${3:-}"
    case "$result" in
        PASS) echo "  [PASS] $name"; PASS=$((PASS + 1)) ;;
        WARN) echo "  [WARN] $name $msg"; WARN=$((WARN + 1)) ;;
        FAIL) echo "  [FAIL] $name $msg"; FAIL=$((FAIL + 1)) ;;
    esac
}

echo "============================================================"
echo "  BTC Trading Bot - Installation Verification"
echo "============================================================"
echo ""

# --- 1. Python ---
if command -v python3 &>/dev/null; then
    PV=$(python3 --version 2>&1)
    check "Python3" "PASS" "($PV)"
else
    check "Python3" "FAIL" "(not found)"
fi

# --- 2. Virtual environment ---
VENV_DIR="$REPO_DIR/.venv"
if [ -f "$VENV_DIR/bin/python" ]; then
    check "Virtual environment" "PASS"
else
    check "Virtual environment" "FAIL" "(run ./install.sh)"
fi

# --- 3. Dependencies ---
if [ -f "$VENV_DIR/bin/python" ]; then
    if "$VENV_DIR/bin/python" -c "import aiohttp, websockets, numpy, dotenv" 2>/dev/null; then
        check "Dependencies" "PASS"
    else
        check "Dependencies" "FAIL" "(run ./install.sh)"
    fi
else
    check "Dependencies" "FAIL" "(venv missing)"
fi

# --- 4. requirements.txt ---
if [ -f "$REPO_DIR/requirements.txt" ]; then
    check "requirements.txt" "PASS"
else
    check "requirements.txt" "FAIL" "(missing)"
fi

# --- 5. main.py ---
if [ -f "$REPO_DIR/main.py" ]; then
    check "main.py" "PASS"
else
    check "main.py" "FAIL" "(missing)"
fi

# --- 6. .env file ---
if [ -f "$REPO_DIR/.env" ]; then
    check ".env file" "PASS"
    # Check required variables
    MISSING=""
    for var in BINANCE_API_KEY BINANCE_SECRET DISCORD_TOKEN DISCORD_CHANNEL_ID; do
        VAL=$(grep -E "^${var}=" "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d ' "'"'"'")
        if [ -z "$VAL" ]; then
            MISSING="$MISSING $var"
        fi
    done
    if [ -n "$MISSING" ]; then
        check "Env variables" "WARN" "(missing:$MISSING)"
    else
        check "Env variables" "PASS"
    fi
else
    check ".env file" "FAIL" "(copy .env.example to .env)"
fi

# --- 7. .env.example ---
if [ -f "$REPO_DIR/.env.example" ]; then
    check ".env.example" "PASS"
else
    check ".env.example" "FAIL" "(missing)"
fi

# --- 8. Database directory ---
DATA_DIR="$REPO_DIR/data"
if [ -d "$DATA_DIR" ]; then
    check "Data directory" "PASS"
else
    check "Data directory" "WARN" "(will be created on first start)"
fi

# --- 9. Logs directory ---
LOGS_DIR="$REPO_DIR/logs"
if [ -d "$LOGS_DIR" ]; then
    check "Logs directory" "PASS"
else
    check "Logs directory" "WARN" "(will be created on first start)"
fi

# --- 10. Shell scripts ---
ALL_EXEC=1
for script in install.sh start.sh stop.sh restart.sh healthcheck.sh verify_install.sh; do
    if [ -f "$REPO_DIR/$script" ]; then
        if [ -x "$REPO_DIR/$script" ]; then
            :  # ok
        else
            ALL_EXEC=0
        fi
    else
        check "$script" "FAIL" "(missing)"
        ALL_EXEC=0
    fi
done
if [ "$ALL_EXEC" -eq 1 ]; then
    check "Shell scripts" "PASS"
else
    check "Shell scripts" "WARN" "(run: chmod +x *.sh)"
fi

# --- 11. .gitignore ---
if [ -f "$REPO_DIR/.gitignore" ]; then
    check ".gitignore" "PASS"
else
    check ".gitignore" "WARN" "(missing - not critical)"
fi

# --- 12. LICENSE ---
if [ -f "$REPO_DIR/LICENSE" ]; then
    check "LICENSE" "PASS"
else
    check "LICENSE" "WARN" "(missing)"
fi

# --- 13. systemd service ---
if [ -f "$REPO_DIR/trading-bot.service" ]; then
    check "systemd service" "PASS"
else
    check "systemd service" "WARN" "(missing - not critical for Docker)"
fi

# --- 14. Dockerfile ---
if [ -f "$REPO_DIR/Dockerfile" ]; then
    check "Dockerfile" "PASS"
else
    check "Dockerfile" "WARN" "(missing - not critical for bare metal)"
fi

# --- 15. Git repository ---
if [ -d "$REPO_DIR/.git" ]; then
    BRANCH=$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    check "Git repository" "PASS" "(branch: $BRANCH)"
else
    check "Git repository" "WARN" "(not a git repo)"
fi

# --- 16. Binance connectivity ---
if command -v curl &>/dev/null; then
    if curl -sf "https://testnet.binancefuture.com/fapi/v1/ping" >/dev/null 2>&1 || curl -sf "https://fapi.binance.com/fapi/v1/ping" >/dev/null 2>&1; then
        check "Binance API" "PASS"
    else
        check "Binance API" "WARN" "(no connectivity - check firewall)"
    fi
else
    check "Binance API" "WARN" "(curl not available)"
fi

# --- 17. Discord connectivity ---
if command -v curl &>/dev/null; then
    if curl -sf "https://discord.com/api/v10/gateway" >/dev/null 2>&1; then
        check "Discord API" "PASS"
    else
        check "Discord API" "WARN" "(no connectivity - check firewall)"
    fi
else
    check "Discord API" "WARN" "(curl not available)"
fi

# --- Summary ---
echo ""
echo "============================================================"
echo "  RESULTS: $PASS passed, $WARN warnings, $FAIL failures"
echo "============================================================"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo "  Fix the failures above before starting the bot."
    echo "  Run: ./install.sh"
    exit 1
elif [ "$WARN" -gt 0 ]; then
    echo "  All critical checks passed. Review warnings above."
    echo "  Run: ./start.sh"
    exit 0
else
    echo "  All checks passed. Ready to deploy!"
    echo "  Run: ./start.sh"
    exit 0
fi
