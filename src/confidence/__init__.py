from src.config import Settings
from src.market_intelligence import MarketIntelligence
from src.news import NewsMonitor
from src.models import DecisionReport
from src.utils.logger import logger


class ConfidenceEngine:
    def __init__(
        self,
        settings: Settings,
        market_intel: MarketIntelligence,
        news_monitor: NewsMonitor,
    ) -> None:
        self.settings = settings
        self.mi = market_intel
        self.news = news_monitor

    def score(self, direction: str, ema_signal: bool) -> DecisionReport:
        report = DecisionReport(direction=direction)

        if not ema_signal:
            report.confidence = 0.0
            report.ema_check = "FAIL"
            report.approved = False
            return report

        report.ema_check = "PASS"
        weights = {
            "ema": 40,
            "oi": 15,
            "funding": 10,
            "fear_greed": 10,
            "news": 10,
            "liquidations": 10,
            "market_trend": 5,
        }

        score = weights["ema"]

        # Open Interest
        oi_score = self._score_oi(direction)
        report.oi_check = "PASS" if oi_score > 0 else ("FAIL" if oi_score < 0 else "NEUTRAL")
        score += oi_score * weights["oi"] / 100

        # Funding
        fund_score = self._score_funding()
        report.funding_check = "PASS" if fund_score > 0 else ("FAIL" if fund_score < 0 else "NEUTRAL")
        score += fund_score * weights["funding"] / 100

        # Fear & Greed
        fg_score = self._score_fear_greed()
        report.fear_greed = self._fg_label()
        score += fg_score * weights["fear_greed"] / 100

        # News sentiment
        news_score = self._score_news()
        report.news_check = "PASS" if news_score > 0 else ("FAIL" if news_score < 0 else "NEUTRAL")
        score += news_score * weights["news"] / 100

        # Liquidations
        liq_score = self._score_liquidations(direction)
        report.liquidation_risk = "LOW" if liq_score > 0 else ("HIGH" if liq_score < 0 else "MEDIUM")
        score += liq_score * weights["liquidations"] / 100

        # Market trend (BTC dominance)
        trend_score = self._score_market_trend()
        report.market_trend = "BULLISH" if trend_score > 0 else ("BEARISH" if trend_score < 0 else "NEUTRAL")
        score += trend_score * weights["market_trend"] / 100

        report.confidence = max(0, min(100, score))
        report.approved = report.confidence >= self.settings.min_confidence

        logger.info(
            "Confidence: %.1f%% | EMA=%s OI=%s Funding=%s News=%s FG=%s Liq=%s Trend=%s | %s",
            report.confidence, report.ema_check, report.oi_check,
            report.funding_check, report.news_check, report.fear_greed,
            report.liquidation_risk, report.market_trend,
            "APPROVED" if report.approved else "REJECTED",
        )

        return report

    def _score_oi(self, direction: str) -> float:
        trend = self.mi.oi_trend
        change = self.mi.oi_change_1h
        if direction == "LONG":
            if trend == "INCREASING" and change > 5:
                return 1.0
            elif trend == "INCREASING":
                return 0.5
            elif trend == "DECREASING":
                return -0.5
            return 0.0
        else:
            if trend == "DECREASING" and change < -5:
                return 1.0
            elif trend == "DECREASING":
                return 0.5
            elif trend == "INCREASING":
                return -0.5
            return 0.0

    def _score_funding(self) -> float:
        trend = self.mi.funding_trend
        rate = self.mi.funding_rate
        if trend == "BULLISH" and rate > 0.005:
            return 1.0
        elif trend == "BULLISH":
            return 0.5
        elif trend == "BEARISH" and rate < -0.005:
            return -1.0
        elif trend == "BEARISH":
            return -0.5
        return 0.0

    def _score_fear_greed(self) -> float:
        v = self.mi.fear_greed_value
        if v <= 20:
            return 1.0
        elif v <= 40:
            return 0.5
        elif v <= 60:
            return 0.0
        elif v <= 80:
            return -0.5
        return -1.0

    def _fg_label(self) -> str:
        v = self.mi.fear_greed_value
        if v <= 20:
            return "EXTREME FEAR"
        elif v <= 40:
            return "FEAR"
        elif v <= 60:
            return "NEUTRAL"
        elif v <= 80:
            return "GREED"
        return "EXTREME GREED"

    def _score_news(self) -> float:
        s = self.news.aggregate_sentiment
        if s > 30:
            return 1.0
        elif s > 10:
            return 0.5
        elif s < -30:
            return -1.0
        elif s < -10:
            return -0.5
        return 0.0

    def _score_liquidations(self, direction: str) -> float:
        total = self.mi.total_liquidations
        if total == 0:
            return 0.0
        if direction == "LONG":
            ratio = self.mi.short_liquidations / total if total > 0 else 0.5
        else:
            ratio = self.mi.long_liquidations / total if total > 0 else 0.5
        if ratio > 0.7:
            return 1.0
        elif ratio > 0.55:
            return 0.5
        elif ratio < 0.3:
            return -1.0
        elif ratio < 0.45:
            return -0.5
        return 0.0

    def _score_market_trend(self) -> float:
        if not self.mi._dom_history or len(self.mi._dom_history) < 2:
            return 0.0
        recent = self.mi._dom_history[-5:] if len(self.mi._dom_history) >= 5 else self.mi._dom_history
        change = recent[-1] - recent[0]
        if change < -0.5:
            return 1.0
        elif change < -0.2:
            return 0.5
        elif change > 0.5:
            return -1.0
        elif change > 0.2:
            return -0.5
        return 0.0
