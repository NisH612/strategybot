#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# install.sh - BTC Trading Bot Installation Script
# ============================================================
# Run: chmod +x install.sh && ./install.sh
# Re-runnable: safe to run multiple times.
# ============================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
DATA_DIR="$REPO_DIR/data"
LOGS_DIR="$REPO_DIR/logs"

echo "============================================================"
echo "  BTC Trading Bot - Installation"
echo "============================================================"
echo ""

# --- 1. Check Python ---
if ! command -v python3 &>/dev/null; then
    echo "[...] Python3 not found. Installing..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3 python3-venv python3-pip
    elif command -v yum &>/dev/null; then
        sudo yum install -y -q python3 python3-venv python3-pip
    else
        echo "[FAIL] Package manager not supported. Install Python 3.12+ manually."
        exit 1
    fi
    echo "[OK] Python3 installed: $(python3 --version)"
else
    echo "[OK] Python3 found: $(python3 --version)"
fi

# --- 2. Create virtual environment ---
if [ -d "$VENV_DIR" ]; then
    echo "[...] Virtual environment already exists, skipping."
else
    echo "[...] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "[OK] Virtual environment created at $VENV_DIR"
fi

# --- 3. Install Python dependencies ---
echo "[...] Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"
echo "[OK] Dependencies installed"

# --- 4. Create required directories ---
mkdir -p "$DATA_DIR" "$LOGS_DIR"
echo "[OK] Directories ready"
echo "      $DATA_DIR"
echo "      $LOGS_DIR"

# --- 5. Set permissions ---
chmod 755 "$REPO_DIR"/*.sh 2>/dev/null || true
chmod 644 "$REPO_DIR/.env.example" 2>/dev/null || true
echo "[OK] Permissions set"

# --- 6. Verify .env exists ---
if [ -f "$REPO_DIR/.env" ]; then
    echo "[OK] .env file found"
else
    echo "[WARN] No .env file found."
    echo "       Run: cp .env.example .env"
    echo "       Then edit .env with your API keys."
fi

# --- 7. Verify installation ---
echo "[...] Verifying installation..."
"$VENV_DIR/bin/python" -c "import aiohttp, websockets, numpy, dotenv; print('All imports OK')" 2>&1 || {
    echo "[FAIL] Import verification failed. Check requirements."
    exit 1
}
echo "[OK] Import verification passed"

# --- 8. Install systemd service (if root) ---
if [ "$(id -u)" -eq 0 ] && [ -f "$REPO_DIR/trading-bot.service" ]; then
    echo "[...] Installing systemd service..."
    cp "$REPO_DIR/trading-bot.service" /etc/systemd/system/trading-bot.service
    chmod 644 /etc/systemd/system/trading-bot.service
    systemctl daemon-reload
    echo "[OK] systemd service installed"
    echo "      Run: sudo systemctl enable trading-bot"
    echo "      Run: sudo systemctl start trading-bot"
elif [ "$(id -u)" -ne 0 ]; then
    echo "[INFO] Not running as root. Skip systemd installation."
    echo "       To install service manually:"
    echo "       sudo cp trading-bot.service /etc/systemd/system/"
    echo "       sudo systemctl daemon-reload"
fi

echo ""
echo "============================================================"
echo "  INSTALLATION COMPLETE"
echo "============================================================"
echo ""
echo "  Next steps:"
echo "    1. cp .env.example .env"
echo "    2. nano .env          # Add your API keys"
echo "    3. ./start.sh         # Start the bot"
echo "    4. ./healthcheck.sh   # Verify everything is running"
echo ""
