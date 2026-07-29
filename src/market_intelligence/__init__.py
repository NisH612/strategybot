import asyncio
from datetime import datetime, timedelta
from typing import Optional

import aiohttp

from src.config import Settings
from src.utils.logger import logger


class MarketIntelligence:
    def __init__(self, settings: Settings, session: aiohttp.ClientSession) -> None:
        self.settings = settings
        self._session = session
        self._running = False

        self.open_interest: float = 0.0
        self.oi_change_1h: float = 0.0
        self.oi_change_4h: float = 0.0
        self.oi_change_24h: float = 0.0
        self.oi_trend: str = "NEUTRAL"

        self.funding_rate: float = 0.0
        self.funding_trend: str = "NEUTRAL"

        self.long_short_ratio: float = 0.0

        self.long_liquidations: float = 0.0
        self.short_liquidations: float = 0.0
        self.total_liquidations: float = 0.0

        self.fear_greed_value: float = 50.0
        self.fear_greed_class: str = "NEUTRAL"

        self.btc_dominance: float = 0.0

        self._oi_history: list[tuple[datetime, float]] = []
        self._funding_history: list[tuple[datetime, float]] = []
        self._dom_history: list[float] = []
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Market intelligence started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await asyncio.gather(
                    self._poll_open_interest(),
                    self._poll_funding(),
                    self._poll_long_short(),
                    self._poll_fear_greed(),
                    self._poll_dominance(),
                    return_exceptions=True,
                )
            except Exception as exc:
                logger.error("Market intelligence poll error: %s", exc)
            await asyncio.sleep(300)

    # ------------------------------------------------------------------
    # Open Interest
    # ------------------------------------------------------------------
    async def _poll_open_interest(self) -> None:
        try:
            url = f"{self.settings.rest_url}/fapi/v1/openInterest"
            params = {"symbol": self.settings.symbol}
            async with self._session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.open_interest = float(data.get("openInterest", 0))

            now = datetime.utcnow()
            self._oi_history.append((now, self.open_interest))
            cutoff = now - timedelta(hours=24)
            self._oi_history = [
                (t, v) for t, v in self._oi_history if t > cutoff
            ]

            if len(self._oi_history) >= 2:
                latest = self._oi_history[-1][1]
                self.oi_change_1h = self._oi_change_since(now - timedelta(hours=1), latest)
                self.oi_change_4h = self._oi_change_since(now - timedelta(hours=4), latest)
                self.oi_change_24h = self._oi_change_since(now - timedelta(hours=24), latest)

            if self.oi_change_1h > 2:
                self.oi_trend = "INCREASING"
            elif self.oi_change_1h < -2:
                self.oi_trend = "DECREASING"
            else:
                self.oi_trend = "NEUTRAL"
        except Exception as exc:
            logger.debug("OI poll error: %s", exc)

    def _oi_change_since(self, since: datetime, latest: float) -> float:
        for ts, val in reversed(self._oi_history):
            if ts <= since and val > 0:
                return (latest - val) / val * 100
        return 0.0

    # ------------------------------------------------------------------
    # Funding Rate
    # ------------------------------------------------------------------
    async def _poll_funding(self) -> None:
        try:
            url = f"{self.settings.rest_url}/fapi/v1/premiumIndex"
            params = {"symbol": self.settings.symbol}
            async with self._session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.funding_rate = float(data.get("lastFundingRate", 0))

            now = datetime.utcnow()
            self._funding_history.append((now, self.funding_rate))
            cutoff = now - timedelta(hours=24)
            self._funding_history = [
                (t, v) for t, v in self._funding_history if t > cutoff
            ]

            if len(self._funding_history) >= 3:
                recent = [v for _, v in self._funding_history[-3:]]
                avg = sum(recent) / len(recent)
                if avg > 0.0001:
                    self.funding_trend = "BULLISH"
                elif avg < -0.0001:
                    self.funding_trend = "BEARISH"
                else:
                    self.funding_trend = "NEUTRAL"
        except Exception as exc:
            logger.debug("Funding poll error: %s", exc)

    # ------------------------------------------------------------------
    # Long/Short Ratio
    # ------------------------------------------------------------------
    async def _poll_long_short(self) -> None:
        try:
            url = f"{self.settings.rest_url}/futures/data/globalLongShortAccountRatio"
            params = {"symbol": self.settings.symbol, "period": "1h", "limit": 1}
            headers = {"X-MBX-APIKEY": self.settings.binance_api_key}
            async with self._session.get(url, params=params, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        self.long_short_ratio = float(data[0].get("longShortRatio", 0))
        except Exception as exc:
            logger.debug("Long/short poll error: %s", exc)

    # ------------------------------------------------------------------
    # Liquidations (approximate from aggressive order flow)
    # ------------------------------------------------------------------
    async def update_liquidations(self, long_liq: float, short_liq: float) -> None:
        self.long_liquidations = long_liq
        self.short_liquidations = short_liq
        self.total_liquidations = long_liq + short_liq

    # ------------------------------------------------------------------
    # Fear & Greed
    # ------------------------------------------------------------------
    async def _poll_fear_greed(self) -> None:
        try:
            async with self._session.get(
                "https://api.alternative.me/fng/?limit=1", timeout=10
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    item = data.get("data", [{}])[0]
                    self.fear_greed_value = float(item.get("value", 50))
                    self.fear_greed_class = item.get("value_classification", "Neutral").upper()
        except Exception as exc:
            logger.debug("Fear & Greed poll error: %s", exc)

    # ------------------------------------------------------------------
    # BTC Dominance
    # ------------------------------------------------------------------
    async def _poll_dominance(self) -> None:
        try:
            async with self._session.get(
                "https://api.coingecko.com/api/v3/global", timeout=10
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    market_data = data.get("data", {})
                    self.btc_dominance = float(
                        market_data.get("market_cap_percentage", {}).get("btc", 0)
                    )
                    self._dom_history.append(self.btc_dominance)
                    if len(self._dom_history) > 100:
                        self._dom_history = self._dom_history[-100:]
        except Exception as exc:
            logger.debug("Dominance poll error: %s", exc)
