#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# restart.sh - BTC Trading Bot Restart Script
# ============================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo "  BTC Trading Bot - Restarting"
echo "============================================================"

"$REPO_DIR/stop.sh"
sleep 2
"$REPO_DIR/start.sh"
