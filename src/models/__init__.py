from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

Direction = Literal["LONG", "SHORT"]
Reason = Literal["TAKE_PROFIT", "STOP_LOSS", "TREND_EXIT", "MANUAL"]
Status = Literal["OPEN", "CLOSED"]


@dataclass
class Trade:
    trade_id: str = ""
    pair: str = ""
    direction: Direction = "LONG"
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    balance_before: float = 0.0
    balance_after: Optional[float] = None
    stop_loss: float = 0.0
    take_profit: float = 0.0
    reason: Optional[Reason] = None
    status: Status = "OPEN"
    discord_message_id: Optional[int] = None
    position_size: float = 0.0
    quantity: float = 0.0
    sl_order_id: Optional[int] = None
    tp_order_id: Optional[int] = None
    confidence_score: Optional[float] = None
    confidence_report: Optional[str] = None

    @property
    def duration(self) -> Optional[str]:
        if not self.entry_time:
            return None
        end = self.exit_time or datetime.utcnow()
        delta = end - self.entry_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        return f"{hours}h {minutes}m"


@dataclass
class MarketSnapshot:
    timestamp: datetime = field(default_factory=datetime.utcnow)
    price: float = 0.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    ema_trend: float = 0.0
    volume: float = 0.0
    open_interest: float = 0.0
    oi_change_1h: float = 0.0
    oi_change_4h: float = 0.0
    oi_change_24h: float = 0.0
    oi_trend: str = "NEUTRAL"
    funding_rate: float = 0.0
    funding_trend: str = "NEUTRAL"
    long_short_ratio: float = 0.0
    long_liquidations: float = 0.0
    short_liquidations: float = 0.0
    total_liquidations: float = 0.0
    fear_greed_value: float = 50.0
    fear_greed_class: str = "NEUTRAL"
    btc_dominance: float = 0.0
    sentiment_score: float = 0.0
    trade_signal: Optional[str] = None
    trade_taken: bool = False
    trade_result: Optional[str] = None
    trade_pnl: Optional[float] = None


@dataclass
class NewsItem:
    headline: str = ""
    source: str = ""
    url: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sentiment: float = 0.0
    severity: str = "LOW"
    topics: list[str] = field(default_factory=list)


@dataclass
class DecisionReport:
    trade_id: str = ""
    direction: str = ""
    confidence: float = 0.0
    ema_check: str = ""
    funding_check: str = ""
    oi_check: str = ""
    news_check: str = ""
    fear_greed: str = ""
    liquidation_risk: str = ""
    market_trend: str = ""
    details: str = ""
    approved: bool = False
