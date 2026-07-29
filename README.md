# BTC Trading Bot

Automated Binance Futures trading bot with an EMA crossover strategy (10/25/250), market intelligence, confidence scoring, Discord notifications, and a REST API dashboard.

Designed for **24/7 unattended operation** on a Linux VPS (Wispbyte or any Ubuntu/Debian server).

---

## Strategy

- **EMA 10 / EMA 25 crossover** with **EMA 250** trend filter
- **Long**: EMA10 crosses above EMA25 + price above EMA250
- **Short**: EMA10 crosses below EMA25 + price below EMA250
- **SL/TP**: 2% each, managed as exchange stop-loss/take-profit orders
- **Trend flip exit**: position closes if price crosses EMA250 during a trade
- **1-hour timeframe** only
- **One position at a time**, 100% balance per trade

### Optional Filters (configurable)

- **Confidence scoring** — weighted from OI, funding rate, Fear & Greed, news sentiment, liquidations, market trend (threshold: 70/100)
- **Risk management** — daily loss limit, consecutive loss limit, spread/volatility checks

---

## Quick Deploy (Wispbyte / Fresh Ubuntu VPS)

```bash
# 1. Clone
git clone <repository-url> btc_trading_bot
cd btc_trading_bot

# 2. Install
chmod +x *.sh
./install.sh

# 3. Configure
cp .env.example .env
nano .env                # Fill in API keys, tokens

# 4. Start
./start.sh

# 5. Verify
./healthcheck.sh

# 6. Enable auto-start on boot
sudo cp trading-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
```

---

## Manual Setup

### Prerequisites

- Python 3.12+
- Binance Futures account (testnet or live)
- Discord application with bot token
- Linux VPS (recommended: 1GB RAM, 1 vCPU)

### Installation

```bash
git clone <repository-url> btc_trading_bot
cd btc_trading_bot

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

mkdir -p data logs
cp .env.example .env
```

### Configuration

Edit `.env` with your API keys and preferences. All variables are documented in `.env.example`.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BINANCE_API_KEY` | Yes | — | Binance Futures API key |
| `BINANCE_SECRET` | Yes | — | Binance Futures API secret |
| `BINANCE_TESTNET` | No | `true` | Use testnet (`true`) or live (`false`) |
| `SYMBOL` | No | `BTCUSDT` | Trading pair |
| `TIMEFRAME` | No | `1h` | Chart timeframe (only 1h tested) |
| `START_BALANCE` | No | `100` | Virtual balance for position sizing |
| `DISCORD_TOKEN` | Yes | — | Discord bot token |
| `DISCORD_CHANNEL_ID` | Yes | — | Discord channel ID |
| `MIN_CONFIDENCE` | No | `70` | Minimum confidence score (0-100) |
| `MAX_DAILY_LOSS` | No | `0` | Max daily loss (0 = unlimited) |
| `MAX_CONSECUTIVE_LOSSES` | No | `0` | Max consecutive losses (0 = unlimited) |
| `API_HOST` | No | `127.0.0.1` | REST API bind address |
| `API_PORT` | No | `8080` | REST API port |

---

## Running

### Using start/stop scripts

```bash
./start.sh       # Start in background
./stop.sh        # Graceful stop
./restart.sh     # Restart
./healthcheck.sh # Check everything
```

### Using systemd (recommended for production)

```bash
sudo cp trading-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trading-bot    # Auto-start on boot
sudo systemctl start trading-bot     # Start now
sudo systemctl status trading-bot    # Check status
sudo journalctl -u trading-bot -f    # Follow logs
```

---

## Viewing Logs

```bash
# Application log (all events)
tail -f logs/application.log

# Error log (only errors)
tail -f logs/error.log

# Trades log (trade open/close events)
tail -f logs/trades.log

# systemd logs (if using systemd)
journalctl -u trading-bot -f
```

Logs are rotated automatically at midnight. Archives are kept for 30 days (configurable via `LOG_BACKUP_COUNT`).

---

## REST API Dashboard

The dashboard runs on `http://127.0.0.1:8080` by default.

| Endpoint | Description |
|----------|-------------|
| `/status` | Bot status, uptime, candle count |
| `/account` | USDT balance |
| `/open-position` | Current trade details |
| `/trades` | Recent trade history |
| `/market` | Live OI, funding, Fear & Greed, dominance |
| `/confidence` | Recent decision reports |
| `/history` | Historical market snapshots |

To access from outside the VPS, use SSH port forwarding:

```bash
ssh -L 8080:127.0.0.1:8080 user@your-vps
```

Then open `http://127.0.0.1:8080` in your browser.

---

## Updating

```bash
cd btc_trading_bot
./stop.sh
git pull
./install.sh        # Re-install dependencies
sudo systemctl daemon-reload   # If service file changed
./start.sh
```

---

## Project Structure

```
├── main.py                  # Entry point
├── install.sh               # Installation script
├── start.sh                 # Startup script
├── stop.sh                  # Stop script
├── restart.sh               # Restart script
├── healthcheck.sh           # Health check script
├── trading-bot.service      # systemd unit file
├── logrotate.conf           # Log rotation config
├── .env.example             # Configuration template
├── requirements.txt         # Python dependencies
├── README.md                # This file
├── LICENSE                  # MIT License
├── src/
│   ├── bot.py               # Main orchestrator
│   ├── config/              # Settings from .env
│   ├── exchange/            # Binance Futures REST + WebSocket
│   ├── strategy/            # EMA crossover logic
│   ├── discord_bot/         # Discord embed notifications
│   ├── database/            # SQLite trade storage
│   ├── models/              # Data classes
│   ├── market_intelligence/ # OI, funding, Fear & Greed, dominance
│   ├── news/                # News sentiment analysis
│   ├── confidence/          # Confidence scoring engine
│   ├── ml/                  # ML dataset preparation
│   ├── api/                 # REST API dashboard
│   ├── backtesting/         # Backtesting engine
│   ├── risk/                # Risk management
│   └── utils/               # Logger, helpers
├── data/                    # SQLite database
├── logs/                    # Log files
└── tests/                   # Test directory
```

---

## Switching to Live Trading

1. Edit `.env`:
   ```
   BINANCE_TESTNET=false
   ```
2. Ensure your Binance API key has futures trading permissions enabled.
3. Start with a small balance and monitor closely.
4. Review confidence scores and backtesting results before going live.

---

## Troubleshooting

### "BINANCE_API_KEY is required"
- Create `.env` from `.env.example`
- Fill in your Binance API key

### "API key has no permissions"
- Enable Futures trading in Binance API settings
- Enable reading and trading permissions

### Bot won't start
- Check logs: `tail -f logs/application.log`
- Check config: ensure `.env` has all required fields
- Run: `./healthcheck.sh`

### WebSocket disconnects
- Handled automatically by the built-in reconnection logic.
- Check network connectivity: `ping -c 3 google.com`

### Discord rate limits
- Bot updates every 30 seconds, well within Discord's limits.

### "Address already in use" for API
- Another process is using port 8080. Change `API_PORT` in `.env`.

### Database errors
- The bot uses SQLite with WAL mode for safe concurrent access.
- If corrupted: `rm data/trades.db` (trades will be lost)

---

## Recovery

On restart, the bot automatically:

1. Validates configuration before connecting to external services.
2. Loads the last open trade from SQLite.
3. Verifies the position on Binance.
4. Restores SL/TP orders if missing from the exchange.
5. Resumes Discord updates.

---

## Requirements

- Python 3.12+
- Binance Futures account (testnet or live)
- Discord application with bot token
- Linux VPS (recommended: 1GB RAM, 1 vCPU)
- Operating system: Ubuntu 22.04+ / Debian 11+

---

## License

MIT License. See `LICENSE` for details.
