import asyncio
import signal
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp

from src.api import DashboardAPI
from src.config import Settings
from src.confidence import ConfidenceEngine
from src.database import Database
from src.discord_bot import DiscordNotifier
from src.exchange import BinanceClient
from src.market_intelligence import MarketIntelligence
from src.ml import MLDataPreparer
from src.models import MarketSnapshot, Trade, Direction, Reason, DecisionReport
from src.news import NewsMonitor
from src.risk import RiskManager
from src.strategy import EmaCrossoverStrategy, ema
from src.utils import generate_id
from src.utils.logger import logger


class TradingBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.exchange = BinanceClient(settings)
        self.strategy = EmaCrossoverStrategy(
            fast_period=settings.ema_fast,
            slow_period=settings.ema_slow,
            trend_period=settings.ema_trend,
            sl_pct=settings.sl_pct,
            tp_pct=settings.tp_pct,
        )
        self.discord = DiscordNotifier(settings)
        self.db = Database()
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._active_trade: Optional[Trade] = None
        self._closes: list[float] = []
        self._current_price: float = 0.0
        self._update_task: Optional[asyncio.Task] = None
        self._snapshot_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        logger.info("=" * 60)
        logger.info("BOT STARTING")
        logger.info("=" * 60)
        logger.info("Symbol: %s | Timeframe: %s | Testnet: %s",
                     self.settings.symbol, self.settings.timeframe,
                     self.settings.testnet)

        self.db.connect()
        self._session = aiohttp.ClientSession()
        await self.exchange.start()

        if self.settings.timeframe != "1h":
            logger.warning("TIMEFRAME=%s – only 1h has been tested!",
                           self.settings.timeframe)

        errors = self.settings.validate()
        for err in errors:
            logger.warning("Config: %s", err)

        self._running = True

        # Extended modules
        self.market_intel = MarketIntelligence(self.settings, self._session)
        self.news_monitor = NewsMonitor(self._session)
        self.confidence_engine = ConfidenceEngine(self.settings, self.market_intel, self.news_monitor)
        self.risk_manager = RiskManager(self.settings, self.db)
        self.ml_preparer = MLDataPreparer(self.db)
        self.api = DashboardAPI(self)
        await asyncio.gather(
            self.market_intel.start(),
            self.news_monitor.start(),
            self.api.start(),
            return_exceptions=True,
        )

        # Load historical candles for EMA warmup
        await self._load_historical()

        # Check for active trade (recovery)
        await self._recover_active_trade()

        # Start WebSocket streams
        await self.exchange.start_kline_stream(
            self.settings.symbol,
            self.settings.timeframe,
            self._on_kline,
        )
        await self.exchange.start_ticker_stream(
            self.settings.symbol,
            self._on_ticker,
        )

        # Periodic snapshot task
        self._snapshot_task = asyncio.create_task(self._snapshot_loop())

        # Signal handling
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                pass  # Windows

        logger.info("Bot running – awaiting candles...")

    async def stop(self) -> None:
        logger.info("Shutting down...")
        self._running = False
        if self._update_task:
            self._update_task.cancel()
        if self._snapshot_task:
            self._snapshot_task.cancel()
        await self.market_intel.stop()
        await self.news_monitor.stop()
        await self.api.stop()
        if self._session and not self._session.closed:
            await self._session.close()
        await self.exchange.stop()
        self.db.close()
        await self.discord.close()
        logger.info("Bot stopped")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    async def _load_historical(self) -> None:
        needed = self.settings.ema_trend + 100
        try:
            klines = await self.exchange.get_klines(
                self.settings.symbol,
                self.settings.timeframe,
                limit=needed,
            )
            self._closes = [k["close"] for k in klines]
            logger.info("Loaded %d historical candles", len(self._closes))
        except Exception as exc:
            logger.error("Failed to load historical data: %s", exc)
            self._closes = []

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------
    async def _recover_active_trade(self) -> None:
        trade = self.db.get_open_trade()
        if trade is None:
            logger.info("No active trade to recover")
            return

        logger.info(
            "Recovering active trade: %s %s entry=$%.2f",
            trade.direction, trade.trade_id, trade.entry_price,
        )

        # Verify position still open on exchange
        pos = await self.exchange.get_position(self.settings.symbol)
        if pos is None:
            logger.warning("Position not found on exchange – marking trade as CLOSED")
            trade.status = "CLOSED"
            trade.reason = "MANUAL"
            self.db.save_trade(trade)
            self._active_trade = None
            return

        amt = float(pos.get("positionAmt", "0"))
        if abs(amt) == 0:
            logger.warning("Zero position on exchange – closing trade")
            trade.status = "CLOSED"
            trade.reason = "MANUAL"
            self.db.save_trade(trade)
            self._active_trade = None
            return

        self._active_trade = trade
        logger.info("Trade recovered successfully")

        # Restore SL/TP orders if missing
        await self._ensure_sl_tp_orders(trade)

        # Resume Discord updates
        self._update_task = asyncio.create_task(self._update_loop())

    async def _ensure_sl_tp_orders(self, trade: Trade) -> None:
        try:
            open_orders = await self.exchange.get_open_orders(self.settings.symbol)
            has_sl = any(o.get("orderId") == trade.sl_order_id for o in open_orders)
            has_tp = any(o.get("orderId") == trade.tp_order_id for o in open_orders)

            if not has_sl:
                logger.info("Recreating SL order")
                sl_side = "SELL" if trade.direction == "LONG" else "BUY"
                sl_resp = await self.exchange.create_stop_loss(
                    self.settings.symbol, sl_side,
                    trade.quantity, trade.stop_loss,
                )
                trade.sl_order_id = sl_resp.get("orderId")
                self.db.save_trade(trade)

            if not has_tp:
                logger.info("Recreating TP order")
                tp_side = "SELL" if trade.direction == "LONG" else "BUY"
                tp_resp = await self.exchange.create_take_profit(
                    self.settings.symbol, tp_side,
                    trade.quantity, trade.take_profit,
                )
                trade.tp_order_id = tp_resp.get("orderId")
                self.db.save_trade(trade)
        except Exception as exc:
            logger.error("Failed to restore SL/TP orders: %s", exc)

    # ------------------------------------------------------------------
    # WebSocket handlers
    # ------------------------------------------------------------------
    async def _on_ticker(self, msg: dict) -> None:
        try:
            self._current_price = float(msg.get("c", 0))
        except (TypeError, ValueError, KeyError):
            pass

    async def _on_kline(self, msg: dict) -> None:
        try:
            k = msg.get("k", {})
            is_closed = k.get("x", False)
            if not is_closed:
                return

            close_price = float(k.get("c", 0))
            logger.debug("Candle closed at %.2f", close_price)

            self._closes.append(close_price)
            if len(self._closes) > self.settings.ema_trend + 100:
                self._closes = self._closes[-(self.settings.ema_trend + 100):]

            if len(self._closes) < self.settings.ema_trend + 5:
                logger.debug("Warming up – need %d candles, have %d",
                             self.settings.ema_trend + 5, len(self._closes))
                return

            await self._evaluate()
        except Exception as exc:
            logger.exception("Kline handler error: %s", exc)

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------
    async def _evaluate(self) -> None:
        signal = self.strategy.calculate(self._closes)

        if self._active_trade is None:
            await self._check_entry(signal)
        else:
            await self._check_exit(signal)

    async def _check_entry(self, signal: dict) -> None:
        entry_price = signal.get("entry_long") or signal.get("entry_short")
        if entry_price is None:
            return

        direction = "LONG" if signal["entry_long"] else "SHORT"
        logger.info("Entry signal: %s at %.2f", direction, entry_price)

        # Confidence check
        ema_signal = bool(signal.get("entry_long") or signal.get("entry_short"))
        report: DecisionReport = self.confidence_engine.score(direction, ema_signal)

        if not report.approved:
            logger.info("Trade REJECTED by confidence engine (%.1f%% < %d%%)",
                         report.confidence, self.settings.min_confidence)
            return

        # Risk check
        if not await self.risk_manager.check():
            logger.info("Trade REJECTED by risk manager")
            return

        # Get balance
        balance = await self.exchange.get_balance("USDT")
        logger.info("Account balance: $%.2f", balance)

        if balance < 5:
            logger.warning("Balance too low to trade ($%.2f)", balance)
            return

        # Calculate quantity
        qty = await self.exchange.quantity_for_balance(
            self.settings.symbol, balance, entry_price
        )
        if qty <= 0:
            logger.error("Invalid quantity: %.8f", qty)
            return

        # Create market order
        side = "BUY" if direction == "LONG" else "SELL"
        try:
            order = await self.exchange.create_market_order(
                self.settings.symbol, side, qty
            )
            filled_qty = float(order.get("executedQty", qty))
            avg_price = float(order.get("avgPrice", entry_price))
            logger.info("Order filled: %s @ %.2f qty=%.4f", side, avg_price, filled_qty)
        except Exception as exc:
            logger.error("Order failed: %s", exc)
            return

        # Build trade record
        sl_price = self.strategy.sl_price(avg_price, direction)
        tp_price = self.strategy.tp_price(avg_price, direction)
        pos_size = avg_price * filled_qty

        trade = Trade(
            trade_id=generate_id(),
            pair=self.settings.symbol,
            direction=direction,
            entry_price=avg_price,
            entry_time=datetime.utcnow(),
            balance_before=balance,
            stop_loss=sl_price,
            take_profit=tp_price,
            status="OPEN",
            position_size=pos_size,
            quantity=filled_qty,
            confidence_score=report.confidence,
            confidence_report=f"EMA={report.ema_check} OI={report.oi_check} Funding={report.funding_check} News={report.news_check} FG={report.fear_greed} Liq={report.liquidation_risk} Trend={report.market_trend}",
        )

        # Save decision report
        report.trade_id = trade.trade_id
        self.db.save_decision(report)

        # Place SL/TP orders
        sl_side = "SELL" if direction == "LONG" else "BUY"
        tp_side = "SELL" if direction == "LONG" else "BUY"
        try:
            sl_resp = await self.exchange.create_stop_loss(
                self.settings.symbol, sl_side, filled_qty, sl_price
            )
            trade.sl_order_id = sl_resp.get("orderId")
            tp_resp = await self.exchange.create_take_profit(
                self.settings.symbol, tp_side, filled_qty, tp_price
            )
            trade.tp_order_id = tp_resp.get("orderId")
        except Exception as exc:
            logger.error("SL/TP placement failed: %s", exc)

        # Discord notification (with intel)
        self.discord.set_intel(self.market_intel, report, self.news_monitor.aggregate_sentiment)
        try:
            msg_id = await self.discord.send_trade_open(trade)
            trade.discord_message_id = msg_id
        except Exception as exc:
            logger.error("Discord notification failed: %s", exc)

        self.db.save_trade(trade)
        self._active_trade = trade

        # Start update loop
        self._update_task = asyncio.create_task(self._update_loop())

    async def _check_exit(self, signal: dict) -> None:
        assert self._active_trade

        # First check if SL/TP already closed the position on exchange
        if await self._check_position_closed():
            return

        exit_needed = False
        reason: Optional[Reason] = None

        if self._active_trade.direction == "LONG":
            if signal.get("exit_long"):
                exit_needed = True
                reason = "TREND_EXIT"
        else:
            if signal.get("exit_short"):
                exit_needed = True
                reason = "TREND_EXIT"

        if not exit_needed:
            return

        logger.info(
            "Exit signal: %s reason=%s",
            self._active_trade.trade_id, reason,
        )

        await self._close_trade(reason or "TREND_EXIT")

    async def _check_position_closed(self) -> bool:
        assert self._active_trade
        try:
            pos = await self.exchange.get_position(self.settings.symbol)
            amt = float(pos.get("positionAmt", "0")) if pos else 0
            expected = self._active_trade.quantity
            if self._active_trade.direction == "SHORT":
                expected = -expected
            if abs(amt) < 0.0001:
                reason = self._detect_close_reason()
                logger.info("Position closed externally (SL/TP) - reason=%s", reason)
                await self._close_trade(reason)
                return True
        except Exception as exc:
            logger.error("Position check failed: %s", exc)
        return False

    def _detect_close_reason(self) -> Reason:
        if not self._active_trade or not self._current_price:
            return "STOP_LOSS"
        trade = self._active_trade
        if trade.direction == "LONG":
            if self._current_price <= trade.stop_loss:
                return "STOP_LOSS"
            if self._current_price >= trade.take_profit:
                return "TAKE_PROFIT"
        else:
            if self._current_price >= trade.stop_loss:
                return "STOP_LOSS"
            if self._current_price <= trade.take_profit:
                return "TAKE_PROFIT"
        return "STOP_LOSS"

    async def _close_trade(self, reason: Reason) -> None:
        trade = self._active_trade
        if trade is None:
            return

        # Cancel SL/TP orders
        try:
            await self.exchange.cancel_all_orders(self.settings.symbol)
        except Exception as exc:
            logger.warning("Cancel orders error: %s", exc)

        # Close position if still open on exchange
        exit_price = self._current_price
        pos_open = False
        try:
            pos = await self.exchange.get_position(self.settings.symbol)
            amt = float(pos.get("positionAmt", "0")) if pos else 0
            pos_open = abs(amt) > 0.0001
        except Exception:
            pass

        if pos_open:
            side = "SELL" if trade.direction == "LONG" else "BUY"
            try:
                close_order = await self.exchange.create_market_order(
                    self.settings.symbol, side, trade.quantity, reduce_only=True
                )
                exit_price = float(close_order.get("avgPrice", self._current_price))
            except Exception as exc:
                logger.error("Close order failed: %s", exc)
        else:
            logger.info("Position already closed on exchange")

        trade.exit_price = exit_price
        trade.exit_time = datetime.utcnow()
        trade.reason = reason
        trade.status = "CLOSED"

        # Calculate PnL
        if trade.direction == "LONG":
            trade.pnl = trade.position_size * ((exit_price - trade.entry_price) / trade.entry_price)
            trade.pnl_pct = (exit_price - trade.entry_price) / trade.entry_price * 100
        else:
            trade.pnl = trade.position_size * ((trade.entry_price - exit_price) / trade.entry_price)
            trade.pnl_pct = (trade.entry_price - exit_price) / trade.entry_price * 100

        trade.balance_after = trade.balance_before + (trade.pnl or 0)

        logger.info(
            "Trade closed: %s %s pnl=%.2f (%.2f%%) reason=%s",
            trade.direction, trade.trade_id, trade.pnl or 0,
            trade.pnl_pct or 0, reason,
        )

        # Update Discord
        try:
            await self.discord.send_trade_close(trade)
        except Exception as exc:
            logger.error("Discord close notification failed: %s", exc)

        self.db.save_trade(trade)
        self._active_trade = None
        self.risk_manager.reset_daily()

        if self._update_task:
            self._update_task.cancel()
            self._update_task = None

    # ------------------------------------------------------------------
    # Discord update loop
    # ------------------------------------------------------------------
    async def _update_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.settings.discord_update_interval)
            try:
                if self._active_trade is None:
                    break
                if self._current_price > 0:
                    self.discord.set_intel(self.market_intel, None, self.news_monitor.aggregate_sentiment)
                    await self.discord.send_trade_update(
                        self._active_trade, self._current_price
                    )
                await self._check_position_closed()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Discord update error: %s", exc)

    # ------------------------------------------------------------------
    # Periodic market data snapshots
    # ------------------------------------------------------------------
    async def _snapshot_loop(self) -> None:
        while self._running:
            await asyncio.sleep(300)
            try:
                await self._save_snapshot()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Snapshot error: %s", exc)

    async def _save_snapshot(self) -> None:
        if not self._current_price:
            return
        ema_fast = ema(self._closes, self.settings.ema_fast)[-1] if len(self._closes) >= self.settings.ema_fast else 0
        ema_slow = ema(self._closes, self.settings.ema_slow)[-1] if len(self._closes) >= self.settings.ema_slow else 0
        ema_trend = ema(self._closes, self.settings.ema_trend)[-1] if len(self._closes) >= self.settings.ema_trend else 0
        trade_result = None if not self._active_trade else ("WIN" if (self._active_trade.pnl or 0) > 0 else "LOSS")
        snap = MarketSnapshot(
            price=self._current_price,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            ema_trend=ema_trend,
            open_interest=self.market_intel.open_interest,
            oi_change_1h=self.market_intel.oi_change_1h,
            oi_change_4h=self.market_intel.oi_change_4h,
            oi_change_24h=self.market_intel.oi_change_24h,
            oi_trend=self.market_intel.oi_trend,
            funding_rate=self.market_intel.funding_rate,
            funding_trend=self.market_intel.funding_trend,
            long_short_ratio=self.market_intel.long_short_ratio,
            long_liquidations=self.market_intel.long_liquidations,
            short_liquidations=self.market_intel.short_liquidations,
            total_liquidations=self.market_intel.total_liquidations,
            fear_greed_value=self.market_intel.fear_greed_value,
            fear_greed_class=self.market_intel.fear_greed_class,
            btc_dominance=self.market_intel.btc_dominance,
            sentiment_score=self.news_monitor.aggregate_sentiment,
            trade_taken=self._active_trade is not None,
            trade_result=trade_result,
            trade_pnl=self._active_trade.pnl if self._active_trade else None,
        )
        self.db.save_market_snapshot(snap)


async def main() -> None:
    settings = Settings()
    bot = TradingBot(settings)
    try:
        await bot.start()
        while bot._running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
