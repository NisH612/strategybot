from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from src.config import Settings
from src.database import Database, DB_DIR
from src.models import MarketSnapshot
from src.strategy import EmaCrossoverStrategy, ema
from src.utils.logger import logger


@dataclass
class BacktestResult:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    start_balance: float = 0.0
    end_balance: float = 0.0
    trades: list[dict] = field(default_factory=list)


class Backtester:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or Settings()
        self.strategy = EmaCrossoverStrategy(
            fast_period=self.settings.ema_fast,
            slow_period=self.settings.ema_slow,
            trend_period=self.settings.ema_trend,
            sl_pct=self.settings.sl_pct,
            tp_pct=self.settings.tp_pct,
        )

    def run_on_candles(
        self,
        closes: list[float],
        oi_history: Optional[list[float]] = None,
        funding_history: Optional[list[float]] = None,
        fg_history: Optional[list[float]] = None,
        sentiment_history: Optional[list[float]] = None,
        use_confidence_filter: bool = False,
    ) -> BacktestResult:
        if len(closes) < self.settings.ema_trend + 10:
            logger.error("Not enough candles: need %d, got %d",
                          self.settings.ema_trend + 10, len(closes))
            return BacktestResult()

        balance = self.settings.start_balance
        peak_balance = balance
        max_dd = 0.0
        trades: list[dict] = []
        position = None
        entry_bar = 0

        for i in range(self.settings.ema_trend + 5, len(closes)):
            window = closes[:i + 1]
            signal = self.strategy.calculate(window)

            if position is None:
                entry = signal.get("entry_long") or signal.get("entry_short")
                if entry is None:
                    continue
                direction = "LONG" if signal["entry_long"] else "SHORT"
                sl = self.strategy.sl_price(entry, direction)
                tp = self.strategy.tp_price(entry, direction)
                position = {"direction": direction, "entry": entry, "sl": sl, "tp": tp}
                entry_bar = i
            else:
                high = closes[i]
                low = closes[i]
                exit_reason = None
                exit_price = None

                if position["direction"] == "LONG":
                    if low <= position["sl"]:
                        exit_reason = "STOP_LOSS"
                        exit_price = position["sl"]
                    elif high >= position["tp"]:
                        exit_reason = "TAKE_PROFIT"
                        exit_price = position["tp"]
                else:
                    if high >= position["sl"]:
                        exit_reason = "STOP_LOSS"
                        exit_price = position["sl"]
                    elif low <= position["tp"]:
                        exit_reason = "TAKE_PROFIT"
                        exit_price = position["tp"]

                if exit_reason is None:
                    exit_signal = False
                    if position["direction"] == "LONG" and signal.get("exit_long"):
                        exit_signal = True
                    elif position["direction"] == "SHORT" and signal.get("exit_short"):
                        exit_signal = True
                    if exit_signal:
                        exit_reason = "TREND_EXIT"
                        exit_price = closes[i]

                if exit_reason:
                    entry_px = position["entry"]
                    if position["direction"] == "LONG":
                        pnl_pct = (exit_price - entry_px) / entry_px * 100
                        pnl = balance * (pnl_pct / 100)
                    else:
                        pnl_pct = (entry_px - exit_price) / entry_px * 100
                        pnl = balance * (pnl_pct / 100)

                    balance += pnl
                    peak_balance = max(peak_balance, balance)
                    dd = (peak_balance - balance) / peak_balance * 100
                    max_dd = max(max_dd, dd)

                    trade = {
                        "bar": i,
                        "direction": position["direction"],
                        "entry": entry_px,
                        "exit": exit_price,
                        "pnl_pct": pnl_pct,
                        "pnl": pnl,
                        "reason": exit_reason,
                    }
                    trades.append(trade)
                    position = None

        return self._compute_results(trades, self.settings.start_balance, balance)

    def run_from_db(
        self,
        db: Database,
        use_confidence_filter: bool = False,
    ) -> BacktestResult:
        data = db.get_market_data(limit=10000)
        if len(data) < 10:
            logger.error("Not enough market data in DB for backtest")
            return BacktestResult()
        closes = [s.price for s in sorted(data, key=lambda x: x.timestamp)]
        oi = [s.open_interest for s in data]
        funding = [s.funding_rate for s in data]
        fg = [s.fear_greed_value for s in data]
        sentiment = [s.sentiment_score for s in data]
        return self.run_on_candles(
            closes=closes,
            oi_history=oi,
            funding_history=funding,
            fg_history=fg,
            sentiment_history=sentiment,
            use_confidence_filter=use_confidence_filter,
        )

    def _compute_results(
        self,
        trades: list[dict],
        start_balance: float,
        end_balance: float,
    ) -> BacktestResult:
        total = len(trades)
        if total == 0:
            return BacktestResult(start_balance=start_balance, end_balance=end_balance)

        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        n_wins = len(wins)
        n_losses = len(losses)
        win_rate = n_wins / total * 100 if total > 0 else 0.0

        gross_profit = sum(t["pnl"] for t in wins) if wins else 0.0
        gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        returns = [t["pnl_pct"] / 100 for t in trades]
        avg_return = np.mean(returns) if returns else 0.0
        std_return = np.std(returns) if len(returns) > 1 else 1.0
        sharpe = (avg_return / std_return) * np.sqrt(365) if std_return > 0 else 0.0

        avg_win = gross_profit / n_wins if n_wins > 0 else 0.0
        avg_loss = gross_loss / n_losses if n_losses > 0 else 0.0
        expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

        peak = start_balance
        max_dd = 0.0
        bal = start_balance
        for t in trades:
            bal += t["pnl"]
            peak = max(peak, bal)
            dd = (peak - bal) / peak * 100
            max_dd = max(max_dd, dd)

        result = BacktestResult(
            total_trades=total,
            wins=n_wins,
            losses=n_losses,
            win_rate=win_rate,
            total_pnl=end_balance - start_balance,
            profit_factor=profit_factor,
            max_drawdown_pct=max_dd,
            sharpe=sharpe,
            expectancy=expectancy,
            avg_win=avg_win,
            avg_loss=avg_loss,
            start_balance=start_balance,
            end_balance=end_balance,
            trades=trades,
        )

        logger.info(
            "Backtest: %d trades | WR=%.1f%% | PF=%.2f | DD=%.1f%% | Sharpe=%.2f | $%.0f→$%.0f",
            result.total_trades, result.win_rate, result.profit_factor,
            result.max_drawdown_pct, result.sharpe,
            result.start_balance, result.end_balance,
        )
        return result

    def export_report(self, result: BacktestResult, path: Optional[Path] = None) -> Path:
        if path is None:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            path = DB_DIR / f"backtest_{ts}.html"
        html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>Backtest Report</title>
<style>
  body {{ font-family: monospace; max-width: 800px; margin: 20px auto; padding: 10px; }}
  h1 {{ color: #333; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: right; }}
  th {{ background: #f5f5f5; }}
  .win {{ color: green; }} .loss {{ color: red; }}
</style></head><body>
<h1>Backtest Report</h1>
<p>Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total Trades</td><td>{result.total_trades}</td></tr>
<tr><td>Win Rate</td><td>{result.win_rate:.1f}%</td></tr>
<tr><td>Profit Factor</td><td>{result.profit_factor:.2f}</td></tr>
<tr><td>Max DD</td><td>{result.max_drawdown_pct:.1f}%</td></tr>
<tr><td>Sharpe</td><td>{result.sharpe:.2f}</td></tr>
<tr><td>Expectancy</td><td>${result.expectancy:.2f}</td></tr>
<tr><td>Avg Win</td><td>${result.avg_win:.2f}</td></tr>
<tr><td>Avg Loss</td><td>${result.avg_loss:.2f}</td></tr>
<tr><td>Start Balance</td><td>${result.start_balance:.2f}</td></tr>
<tr><td>End Balance</td><td>${result.end_balance:.2f}</td></tr>
<tr><td>Total PnL</td><td>{result.total_pnl:+.2f}</td></tr>
</table>
<h2>Trades</h2>
<table><tr><th>#</th><th>Dir</th><th>Entry</th><th>Exit</th><th>PnL%</th><th>Reason</th></tr>"""
        for i, t in enumerate(result.trades, 1):
            cls = "win" if t["pnl"] > 0 else "loss"
            html += f"<tr class='{cls}'><td>{i}</td><td>{t['direction']}</td>"
            html += f"<td>{t['entry']:.2f}</td><td>{t['exit']:.2f}</td>"
            html += f"<td>{t['pnl_pct']:+.2f}%</td><td>{t['reason']}</td></tr>"
        html += "</table></body></html>"
        path.write_text(html)
        logger.info("Backtest report: %s", path)
        return path
