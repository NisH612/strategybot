import asyncio
import json
from typing import Any, Optional

from aiohttp import web

from src.utils.logger import logger


class DashboardAPI:
    def __init__(self, bot, host: str = "127.0.0.1", port: int = 8080) -> None:
        self.bot = bot
        self.host = host
        self.port = port
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self._app.router.add_get("/status", self._handle_status)
        self._app.router.add_get("/account", self._handle_account)
        self._app.router.add_get("/open-position", self._handle_open_position)
        self._app.router.add_get("/trades", self._handle_trades)
        self._app.router.add_get("/market", self._handle_market)
        self._app.router.add_get("/confidence", self._handle_confidence)
        self._app.router.add_get("/history", self._handle_history)

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info("Dashboard API running on http://%s:%d", self.host, self.port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    def _json(self, data: Any) -> web.Response:
        return web.json_response(data, dumps=lambda o: json.dumps(o, default=str))

    async def _handle_status(self, _: web.Request) -> web.Response:
        return self._json({
            "running": self.bot._running,
            "active_trade": self.bot._active_trade is not None,
            "current_price": self.bot._current_price,
            "candles": len(self.bot._closes),
            "uptime": str(self.bot._start_time) if hasattr(self.bot, "_start_time") else None,
        })

    async def _handle_account(self, _: web.Request) -> web.Response:
        try:
            bal = await self.bot.exchange.get_balance()
            return self._json({"balance_usdt": bal})
        except Exception as exc:
            return self._json({"error": str(exc)})

    async def _handle_open_position(self, _: web.Request) -> web.Response:
        trade = self.bot._active_trade
        if not trade:
            return self._json({"position": None})
        return self._json({
            "trade_id": trade.trade_id,
            "direction": trade.direction,
            "entry_price": trade.entry_price,
            "stop_loss": trade.stop_loss,
            "take_profit": trade.take_profit,
            "position_size": trade.position_size,
            "pnl": trade.pnl,
            "pnl_pct": trade.pnl_pct,
            "duration": trade.duration,
            "confidence": trade.confidence_score,
        })

    async def _handle_trades(self, request: web.Request) -> web.Response:
        limit = int(request.query.get("limit", "20"))
        trades = self.bot.db.get_all_trades()[:limit]
        return self._json([
            {
                "trade_id": t.trade_id,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
                "reason": t.reason,
                "status": t.status,
                "confidence": t.confidence_score,
            }
            for t in trades
        ])

    async def _handle_market(self, _: web.Request) -> web.Response:
        mi = getattr(self.bot, "market_intel", None)
        if not mi:
            return self._json({"error": "Market intelligence not available"})
        return self._json({
            "open_interest": mi.open_interest,
            "oi_change_1h": mi.oi_change_1h,
            "oi_change_4h": mi.oi_change_4h,
            "oi_change_24h": mi.oi_change_24h,
            "oi_trend": mi.oi_trend,
            "funding_rate": mi.funding_rate,
            "funding_trend": mi.funding_trend,
            "long_short_ratio": mi.long_short_ratio,
            "long_liquidations": mi.long_liquidations,
            "short_liquidations": mi.short_liquidations,
            "fear_greed_value": mi.fear_greed_value,
            "fear_greed_class": mi.fear_greed_class,
            "btc_dominance": mi.btc_dominance,
        })

    async def _handle_confidence(self, _: web.Request) -> web.Response:
        decisions = self.bot.db.get_recent_decisions(limit=10)
        return self._json([
            {
                "direction": d.direction,
                "confidence": d.confidence,
                "ema": d.ema_check,
                "funding": d.funding_check,
                "oi": d.oi_check,
                "news": d.news_check,
                "fear_greed": d.fear_greed,
                "liquidation_risk": d.liquidation_risk,
                "market_trend": d.market_trend,
                "approved": d.approved,
            }
            for d in decisions
        ])

    async def _handle_history(self, _: web.Request) -> web.Response:
        data = self.bot.db.get_market_data(limit=200)
        return self._json([
            {
                "timestamp": s.timestamp,
                "price": s.price,
                "open_interest": s.open_interest,
                "funding_rate": s.funding_rate,
                "fear_greed": s.fear_greed_value,
                "btc_dominance": s.btc_dominance,
                "sentiment": s.sentiment_score,
            }
            for s in data
        ])
