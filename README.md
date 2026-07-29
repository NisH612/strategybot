# BTC Trading Bot

Automated Binance Futures trading bot with an EMA crossover strategy (10/25/250), market intelligence, confidence scoring, Discord notifications, and a REST API dashboard.

Designed for **24/7 unattended operation** on a Linux VPS or Docker container.

---

## Strategies

### Primary: EMA Crossover
- **EMA 10 / EMA 25 crossover** with **EMA 250** trend filter
- **Long**: EMA10 crosses above EMA25 + price above EMA250
- **Short**: EMA10 crosses below EMA25 + price below EMA250
- **SL/TP**: 2% each, managed as exchange stop-loss/take-profit orders
- **Trend flip exit**: position closes if price crosses EMA250 during a trade
- **1-hour timeframe** only
- **One position at a time**, 100% balance per trade

### Optional Filters
- **Confidence scoring** — weighted from OI, funding rate, Fear & Greed, news sentiment, liquidations, market trend (threshold: 70/100)
- **Risk management** — daily loss limit, consecutive loss limit, spread/volatility checks

---

## Quick Start (Bare Metal)

```bash
git clone https://github.com/NisH612/strategybot.git btc_trading_bot
cd btc_trading_bot
chmod +x *.sh
./install.sh
cp .env.example .env
nano .env
./start.sh
./verify_install.sh
```

---

## Wispbyte / Pterodactyl Deployment

### Option 1: Git Clone (Bare Metal)

Use the Wispbyte file manager or SSH to run:

```bash
git clone https://github.com/NisH612/strategybot.git btc_trading_bot
cd btc_trading_bot
chmod +x *.sh
./install.sh
cp .env.example .env
nano .env
./start.sh
```

### Option 2: Docker (Recommended for Pterodactyl)

```bash
# Build and run
docker compose up -d --build

# View logs
docker compose logs -f

# Stop
docker compose down
```

### Option 3: systemd (Auto-start on boot)

```bash
sudo cp trading-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl status trading-bot
```

---

## Configuration

Edit `.env` with your API keys and preferences:

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
| `MIN_CONFIDENCE` | No | `70` | Minimum confidence score (0–100) |
| `MAX_DAILY_LOSS` | No | `0` | Max daily loss (0 = unlimited) |
| `MAX_CONSECUTIVE_LOSSES` | No | `0` | Max consecutive losses (0 = unlimited) |
| `API_HOST` | No | `127.0.0.1` | REST API bind address |
| `API_PORT` | No | `8080` | REST API port |

All variables are documented with comments in `.env.example`.

---

## Management Scripts

| Script | Purpose |
|--------|---------|
| `install.sh` | Full installation (idempotent) |
| `start.sh` | Start bot in background |
| `stop.sh` | Graceful stop with escalation |
| `restart.sh` | Stop then start |
| `healthcheck.sh` | Runtime health check (PASS/FAIL) |
| `verify_install.sh` | Pre-startup verification |

---

## Viewing Logs

```bash
# All events
tail -f logs/application.log

# Errors only
tail -f logs/error.log

# Trade open/close events
tail -f logs/trades.log

# Startup logs
tail -f logs/startup.log

# Docker logs
docker compose logs -f

# systemd logs
journalctl -u trading-bot -f
```

Logs rotate automatically at midnight. Archives kept for 30 days (configurable via `LOG_BACKUP_COUNT`).

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

Access via SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 user@your-vps
```

---

## Updating

```bash
# Bare metal
cd btc_trading_bot
./stop.sh
git pull
./install.sh
./start.sh

# Docker
docker compose down
git pull
docker compose up -d --build

# systemd
sudo systemctl stop trading-bot
git pull
./install.sh
sudo systemctl start trading-bot
```

---

## Recovery

The bot automatically recovers from:
- Internet interruptions
- Binance API downtime
- Discord rate limits
- WebSocket disconnects
- Database locks
- Unexpected exceptions

On restart:
1. Validates configuration before connecting to external services
2. Loads the last open trade from SQLite
3. Verifies the position on Binance
4. Restores SL/TP orders if missing
5. Resumes Discord updates

---

## Switching to Live Trading

1. Edit `.env`:
   ```
   BINANCE_TESTNET=false
   ```
2. Ensure your Binance API key has futures trading permissions
3. Start with a small balance
4. Monitor closely during the first few trades

---

## Project Structure

```
├── Dockerfile                 # Container build
├── docker-compose.yml         # Docker deployment
├── main.py                    # Entry point
├── install.sh                 # Installation script
├── start.sh                   # Startup script
├── stop.sh                    # Stop script
├── restart.sh                 # Restart script
├── healthcheck.sh             # Runtime health check
├── verify_install.sh          # Pre-startup verification
├── trading-bot.service        # systemd unit file
├── bot.service                # Legacy systemd file
├── logrotate.conf             # Log rotation config
├── .env.example               # Configuration template
├── .gitattributes             # Git line-ending settings
├── requirements.txt           # Python dependencies
├── README.md                  # This file
├── LICENSE                    # MIT License
├── src/
│   ├── bot.py                 # Main orchestrator
│   ├── config/                # Settings from .env
│   ├── exchange/              # Binance Futures REST + WebSocket
│   ├── strategy/              # EMA crossover logic
│   ├── discord_bot/           # Discord embed notifications
│   ├── database/              # SQLite trade storage
│   ├── models/                # Data classes
│   ├── market_intelligence/   # OI, funding, Fear & Greed
│   ├── news/                  # News sentiment analysis
│   ├── confidence/            # Confidence scoring engine
│   ├── ml/                    # ML dataset preparation
│   ├── api/                   # REST API dashboard
│   ├── backtesting/           # Backtesting engine
│   ├── risk/                  # Risk management
│   └── utils/                 # Logger, helpers
├── data/                      # SQLite database
└── logs/                      # Log files
```

---

## Requirements

- Python 3.10+ (recommended 3.12+)
- Binance Futures account (testnet or live)
- Discord bot token
- Linux VPS (1GB RAM, 1 vCPU) or Docker
- Ubuntu 22.04+ / Debian 11+ / any Docker host

---

## Troubleshooting

### Clone hangs on Wispbyte/Pterodactyl
Ensure the panel has outbound internet access to GitHub. If the panel uses Docker, try the Dockerfile instead of git clone.

### "BINANCE_API_KEY is required"
Create `.env` from `.env.example` and fill in your API key.

### "API key has no permissions"
Enable Futures trading in your Binance API settings.

### Bot won't start
```bash
tail -f logs/application.log
tail -f logs/error.log
./verify_install.sh
```

### WebSocket keeps disconnecting
The bot reconnects automatically. Check your network:
```bash
ping -c 3 google.com
```

### "Address already in use"
Change `API_PORT` in `.env` to a different port.

### Database errors
The bot uses SQLite with safe WAL mode. If corrupted:
```bash
rm data/trades.db
```
(Trade history will be lost — the bot creates a fresh database.)

---

## License

MIT License. See `LICENSE` for details.
