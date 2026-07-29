import os
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes")


REQUIRED = {
    "BINANCE_API_KEY": "Binance Futures API key",
    "BINANCE_SECRET": "Binance Futures API secret",
    "DISCORD_TOKEN": "Discord bot token",
    "DISCORD_CHANNEL_ID": "Discord channel ID for notifications",
}

OPTIONAL = {
    "BINANCE_TESTNET": "true",
    "SYMBOL": "BTCUSDT",
    "TIMEFRAME": "1h",
    "START_BALANCE": "100",
    "MIN_CONFIDENCE": "70",
    "MAX_DAILY_LOSS": "0",
    "MAX_CONSECUTIVE_LOSSES": "0",
    "MAX_SPREAD": "0.1",
    "MAX_VOLATILITY": "5.0",
    "API_HOST": "127.0.0.1",
    "API_PORT": "8080",
    "LOG_BACKUP_COUNT": "30",
    "LOG_LEVEL": "INFO",
}


@dataclass(frozen=True)
class Settings:
    binance_api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
    binance_secret: str = field(default_factory=lambda: os.getenv("BINANCE_SECRET", ""))
    testnet: bool = field(default_factory=lambda: _bool(os.getenv("BINANCE_TESTNET"), True))

    symbol: str = field(default_factory=lambda: os.getenv("SYMBOL", "BTCUSDT").upper())
    timeframe: str = field(default_factory=lambda: os.getenv("TIMEFRAME", "1h"))

    start_balance: float = field(default_factory=lambda: float(os.getenv("START_BALANCE", "100")))

    discord_token: str = field(default_factory=lambda: os.getenv("DISCORD_TOKEN", ""))
    discord_channel_id: int = field(
        default_factory=lambda: int(os.getenv("DISCORD_CHANNEL_ID", "0"))
    )

    min_confidence: int = field(default_factory=lambda: int(os.getenv("MIN_CONFIDENCE", "70")))
    max_daily_loss: float = field(default_factory=lambda: float(os.getenv("MAX_DAILY_LOSS", "0")))
    max_consecutive_losses: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONSECUTIVE_LOSSES", "0"))
    )
    max_spread_pct: float = field(default_factory=lambda: float(os.getenv("MAX_SPREAD", "0.1")))
    max_volatility_pct: float = field(
        default_factory=lambda: float(os.getenv("MAX_VOLATILITY", "5.0"))
    )

    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8080")))

    @property
    def rest_url(self) -> str:
        if self.testnet:
            return "https://testnet.binancefuture.com"
        return "https://fapi.binance.com"

    @property
    def wss_url(self) -> str:
        if self.testnet:
            return "wss://stream.testnet.binancefuture.com/ws"
        return "wss://fstream.binance.com/ws"

    @property
    def listen_key_url(self) -> str:
        return f"{self.rest_url}/fapi/v1/listenKey"

    @property
    def ema_fast(self) -> int:
        return 10

    @property
    def ema_slow(self) -> int:
        return 25

    @property
    def ema_trend(self) -> int:
        return 250

    @property
    def sl_pct(self) -> float:
        return 2.0

    @property
    def tp_pct(self) -> float:
        return 2.0

    @property
    def discord_update_interval(self) -> int:
        return 30

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.binance_api_key:
            errors.append("BINANCE_API_KEY is required – set it in .env")
        if not self.binance_secret:
            errors.append("BINANCE_SECRET is required – set it in .env")
        if self.timeframe != "1h":
            errors.append(
                f"TIMEFRAME={self.timeframe} – only '1h' has been tested. "
                f"Proceed with caution."
            )
        if not self.discord_token:
            errors.append("DISCORD_TOKEN is required – set it in .env")
        if not self.discord_channel_id:
            errors.append("DISCORD_CHANNEL_ID is required – set it in .env")
        if self.start_balance <= 0:
            errors.append("START_BALANCE must be positive")
        return errors


def validate_or_exit() -> Settings:
    missing = [k for k, desc in REQUIRED.items() if not os.getenv(k)]
    if missing:
        print("=" * 60, file=sys.stderr)
        print("  CONFIGURATION ERROR", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("", file=sys.stderr)
        for key in missing:
            desc = REQUIRED[key]
            print(f"  {key}  ({desc})", file=sys.stderr)
        print("", file=sys.stderr)
        print("  Create a .env file from .env.example and fill in all values.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    settings = Settings()
    errors = settings.validate()
    if errors:
        print("=" * 60, file=sys.stderr)
        print("  CONFIGURATION ERRORS", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  Fix the issues above and restart.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    return settings
