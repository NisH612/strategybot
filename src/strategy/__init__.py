import numpy as np

from src.utils.logger import logger


def ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return [0.0] * len(values)
    result = [0.0] * len(values)
    multiplier = 2.0 / (period + 1)
    result[0] = values[0]
    for i in range(1, len(values)):
        result[i] = (values[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


class EmaCrossoverStrategy:
    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 25,
        trend_period: int = 250,
        sl_pct: float = 2.0,
        tp_pct: float = 2.0,
    ) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.trend_period = trend_period
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct

    def calculate(
        self, closes: list[float]
    ) -> dict:
        ema_fast = ema(closes, self.fast_period)
        ema_slow = ema(closes, self.slow_period)
        ema_trend = ema(closes, self.trend_period)

        last = len(closes) - 1
        prev = len(closes) - 2

        entry_long = None
        entry_short = None
        exit_long = False
        exit_short = False

        trend_long = closes[last] > ema_trend[last]
        trend_short = closes[last] < ema_trend[last]

        cross_above = (
            ema_fast[prev] <= ema_slow[prev] and ema_fast[last] > ema_slow[last]
        )
        cross_below = (
            ema_fast[prev] >= ema_slow[prev] and ema_fast[last] < ema_slow[last]
        )

        if cross_above and trend_long:
            entry_long = closes[last]
        elif cross_below and trend_short:
            entry_short = closes[last]

        if trend_short:
            exit_long = True
        if trend_long:
            exit_short = True

        return {
            "ema_fast": ema_fast[last],
            "ema_slow": ema_slow[last],
            "ema_trend": ema_trend[last],
            "entry_long": entry_long,
            "entry_short": entry_short,
            "exit_long": exit_long,
            "exit_short": exit_short,
            "close": closes[last],
        }

    def sl_price(self, entry: float, direction: str) -> float:
        if direction == "LONG":
            return entry * (1 - self.sl_pct / 100)
        return entry * (1 + self.sl_pct / 100)

    def tp_price(self, entry: float, direction: str) -> float:
        if direction == "LONG":
            return entry * (1 + self.tp_pct / 100)
        return entry * (1 - self.tp_pct / 100)
