import asyncio
from datetime import datetime
from typing import Optional

import aiohttp

from src.models import NewsItem
from src.utils.logger import logger

HIGH_IMPACT_KEYWORDS = [
    "etf", "sec", "fed", "binance", "coinbase", "hack", "exploit",
    "regulation", "ban", "crackdown", "approval", "rejection",
    "crash", "rally", "all-time high", "ath", "halving",
    "interest rate", "inflation", "cpi", "war", "sanction",
]

BULLISH_KEYWORDS = [
    "approve", "bull", "rally", "surge", "gain", "green", "positive",
    "adoption", "institutional", "partnership", "upgrade", "breakthrough",
    "all-time high", "ath", "inflow", "buy", "accumulation",
]

BEARISH_KEYWORDS = [
    "ban", "crash", "dump", "hack", "exploit", "loss", "red", "negative",
    "fraud", "scam", "crackdown", "regulation", "fear", "panic",
    "sell-off", "liquidation", "outflow", "decline", "recession",
]


class SentimentAnalyzer:
    def analyze_text(self, text: str) -> float:
        text_lower = text.lower()
        score = 0.0
        for kw in BULLISH_KEYWORDS:
            if kw in text_lower:
                score += 10.0
        for kw in BEARISH_KEYWORDS:
            if kw in text_lower:
                score -= 10.0
        score = max(-100, min(100, score))
        return score

    def classify_severity(self, text: str) -> str:
        text_lower = text.lower()
        high = ["hack", "exploit", "ban", "crash", "sec", "fed"]
        for kw in high:
            if kw in text_lower:
                return "HIGH"
        return "MEDIUM" if any(kw in text_lower for kw in HIGH_IMPACT_KEYWORDS) else "LOW"

    def extract_topics(self, text: str) -> list[str]:
        topics = []
        text_lower = text.lower()
        topic_map = {
            "REGULATION": ["sec", "regulation", "ban", "crackdown", "legal"],
            "EXCHANGE": ["binance", "coinbase", "kraken", "exchange"],
            "MACRO": ["fed", "interest rate", "inflation", "cpi", "recession"],
            "ADOPTION": ["institutional", "adoption", "partnership", "etf"],
            "SECURITY": ["hack", "exploit", "breach", "security"],
            "MARKET": ["crash", "rally", "bull", "bear", "dump", "pump"],
        }
        for topic, kws in topic_map.items():
            if any(kw in text_lower for kw in kws):
                topics.append(topic)
        return topics


class NewsMonitor:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.analyzer = SentimentAnalyzer()
        self.recent_news: list[NewsItem] = []
        self.aggregate_sentiment: float = 0.0

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("News monitor started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._fetch_cryptopanic()
                self._update_sentiment()
            except Exception as exc:
                logger.debug("News poll error: %s", exc)
            await asyncio.sleep(600)

    async def _fetch_cryptopanic(self) -> None:
        try:
            url = "https://cryptopanic.com/api/v1/posts/"
            params = {
                "auth_token": "",  # Free tier works without token for basic
                "currencies": "BTC",
                "kind": "news",
                "limit": 10,
            }
            async with self._session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for post in data.get("results", []):
                        title = post.get("title", "")
                        if not title:
                            continue
                        dup = any(n.headline == title for n in self.recent_news)
                        if dup:
                            continue
                        item = NewsItem(
                            headline=title,
                            source="CryptoPanic",
                            url=post.get("url", ""),
                            timestamp=datetime.utcnow(),
                            sentiment=self.analyzer.analyze_text(title),
                            severity=self.analyzer.classify_severity(title),
                            topics=self.analyzer.extract_topics(title),
                        )
                        self.recent_news.insert(0, item)
                    self.recent_news = self.recent_news[:50]
        except Exception as exc:
            logger.debug("CryptoPanic fetch error: %s", exc)

    def _update_sentiment(self) -> None:
        if not self.recent_news:
            self.aggregate_sentiment = 0.0
            return
        scores = [n.sentiment for n in self.recent_news[:10]]
        self.aggregate_sentiment = sum(scores) / len(scores)
