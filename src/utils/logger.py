import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


LOG_BACKUP_COUNT = _int_env("LOG_BACKUP_COUNT", 30)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def _handler(path: str, level: int, fmt: logging.Formatter) -> TimedRotatingFileHandler:
    h = TimedRotatingFileHandler(
        LOG_DIR / path,
        when="midnight",
        interval=1,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    h.setLevel(level)
    h.setFormatter(fmt)
    return h


def build_logger(name: str = "bot") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.addHandler(_handler("application.log", getattr(logging, LOG_LEVEL, logging.INFO), fmt))
    logger.addHandler(_handler("error.log", logging.ERROR, fmt))

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    return logger


def build_trades_logger() -> logging.Logger:
    logger = logging.getLogger("trades")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.addHandler(_handler("trades.log", logging.INFO, fmt))
    logger.propagate = False
    return logger


logger = build_logger()
trades_logger = build_trades_logger()
