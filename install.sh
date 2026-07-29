#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# install.sh - BTC Trading Bot Installation Script
# ============================================================
# Usage:  chmod +x install.sh && ./install.sh
#         sudo ./install.sh   (to also install systemd service)
# Safe to run multiple times (idempotent).
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
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[...] Python not found. Installing..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3 python3-venv python3-pip
        PYTHON_CMD="python3"
    elif command -v yum &>/dev/null; then
        sudo yum install -y -q python3 python3-venv python3-pip
        PYTHON_CMD="python3"
    elif command -v apk &>/dev/null; then
        apk add --no-cache python3 py3-pip
        PYTHON_CMD="python3"
    else
        echo "[FAIL] Package manager not supported."
        echo "       Install Python 3.12+ manually, then re-run this script."
        exit 1
    fi
    echo "[OK] Python installed: $($PYTHON_CMD --version)"
else
    echo "[OK] Python found: $($PYTHON_CMD --version)"
fi

# Verify Python version
PY_VER=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
PY_MAJOR=${PY_VER%.*}
PY_MINOR=${PY_VER#*.}
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "[FAIL] Python 3.10+ required (found $PY_VER)"
    exit 1
fi

# --- 2. Create virtual environment ---
if [ -d "$VENV_DIR" ]; then
    echo "[...] Virtual environment already exists."
else
    echo "[...] Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    echo "[OK] Virtual environment created"
fi

# --- 3. Upgrade pip ---
echo "[...] Upgrading pip..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip 2>/dev/null || true

# --- 4. Install Python dependencies ---
echo "[...] Installing Python dependencies..."
if "$VENV_DIR/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"; then
    echo "[OK] Dependencies installed"
else
    echo "[FAIL] pip install failed."
    echo "       Check requirements.txt and your internet connection."
    exit 1
fi

# --- 5. Create required directories ---
mkdir -p "$DATA_DIR" "$LOGS_DIR"
echo "[OK] Directories created:"
echo "      $DATA_DIR"
echo "      $LOGS_DIR"

# --- 6. Set file permissions ---
chmod +x "$REPO_DIR"/*.sh 2>/dev/null || true
chmod 644 "$REPO_DIR/.env.example" 2>/dev/null || true
echo "[OK] File permissions set"

# --- 7. Check .env ---
if [ -f "$REPO_DIR/.env" ]; then
    echo "[OK] .env configuration found"
else
    echo ""
    echo "[WARN] No .env file found."
    echo "       Create one by running:"
    echo ""
    echo "       cp .env.example .env"
    echo "       nano .env"
    echo ""
fi

# --- 8. Verify installation ---
echo "[...] Verifying Python imports..."
if "$VENV_DIR/bin/python" -c "import aiohttp, websockets, numpy, dotenv; print('OK')" 2>&1; then
    echo "[OK] Import verification passed"
else
    echo "[FAIL] Import verification failed."
    echo "       Try: $VENV_DIR/bin/pip install -r $REPO_DIR/requirements.txt"
    exit 1
fi

# --- 9. Install systemd service (if root) ---
if [ "$(id -u)" -eq 0 ] && [ -f "$REPO_DIR/trading-bot.service" ]; then
    echo "[...] Installing systemd service..."
    cp "$REPO_DIR/trading-bot.service" /etc/systemd/system/trading-bot.service
    chmod 644 /etc/systemd/system/trading-bot.service
    systemctl daemon-reload
    echo "[OK] systemd service installed"
    echo ""
    echo "  Enable auto-start:  sudo systemctl enable trading-bot"
    echo "  Start now:          sudo systemctl start trading-bot"
    echo "  Check status:       sudo systemctl status trading-bot"
elif [ "$(id -u)" -ne 0 ]; then
    echo ""
    echo "[INFO] Not running as root — skipping systemd installation."
    echo "       To install manually:"
    echo ""
    echo "       sudo cp trading-bot.service /etc/systemd/system/"
    echo "       sudo systemctl daemon-reload"
    echo "       sudo systemctl enable trading-bot"
    echo "       sudo systemctl start trading-bot"
    echo ""
fi

# --- 10. Run verification ---
echo "[...] Running verification..."
if [ -f "$REPO_DIR/verify_install.sh" ]; then
    "$REPO_DIR/verify_install.sh" || true
else
    echo "[WARN] verify_install.sh not found — skipping"
fi

echo ""
echo "============================================================"
echo "  INSTALLATION COMPLETE"
echo "============================================================"
echo ""
echo "  Next steps:"
echo ""
if [ ! -f "$REPO_DIR/.env" ]; then
    echo "  1. cp .env.example .env"
    echo "  2. nano .env           # Add your API keys"
    echo "  3. ./start.sh          # Start the bot"
    echo "  4. ./verify_install.sh # Confirm everything is ready"
else
    echo "  1. ./start.sh          # Start the bot"
    echo "  2. ./verify_install.sh # Confirm everything is ready"
    echo "  3. tail -f logs/application.log  # View live logs"
fi
echo ""
