import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import Trade, Direction, Reason, Status, MarketSnapshot, NewsItem, DecisionReport
from src.utils.logger import logger

DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "trades.db"


class Database:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def _create_tables(self) -> None:
        assert self._conn
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id          TEXT PRIMARY KEY,
                pair              TEXT NOT NULL,
                direction         TEXT NOT NULL,
                entry_price       REAL NOT NULL,
                exit_price        REAL,
                entry_time        TEXT NOT NULL,
                exit_time         TEXT,
                pnl               REAL,
                pnl_pct           REAL,
                balance_before    REAL NOT NULL,
                balance_after     REAL,
                stop_loss         REAL NOT NULL,
                take_profit       REAL NOT NULL,
                reason            TEXT,
                status            TEXT NOT NULL DEFAULT 'OPEN',
                discord_message_id INTEGER,
                position_size     REAL NOT NULL DEFAULT 0,
                quantity          REAL NOT NULL DEFAULT 0,
                sl_order_id       INTEGER,
                tp_order_id       INTEGER,
                confidence_score  REAL,
                confidence_report TEXT
            );

            CREATE TABLE IF NOT EXISTS market_data (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp         TEXT NOT NULL,
                price             REAL NOT NULL,
                ema_fast          REAL,
                ema_slow          REAL,
                ema_trend         REAL,
                volume            REAL,
                open_interest     REAL,
                oi_change_1h      REAL,
                oi_change_4h      REAL,
                oi_change_24h     REAL,
                oi_trend          TEXT,
                funding_rate      REAL,
                funding_trend     TEXT,
                long_short_ratio  REAL,
                long_liquidations REAL,
                short_liquidations REAL,
                total_liquidations REAL,
                fear_greed_value  REAL,
                fear_greed_class  TEXT,
                btc_dominance     REAL,
                sentiment_score   REAL,
                trade_signal      TEXT,
                trade_taken       INTEGER DEFAULT 0,
                trade_result      TEXT,
                trade_pnl         REAL
            );

            CREATE TABLE IF NOT EXISTS decision_reports (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id          TEXT,
                timestamp         TEXT NOT NULL,
                direction         TEXT,
                confidence        REAL,
                ema_check         TEXT,
                funding_check     TEXT,
                oi_check          TEXT,
                news_check        TEXT,
                fear_greed        TEXT,
                liquidation_risk  TEXT,
                market_trend      TEXT,
                details           TEXT,
                approved          INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS news_cache (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                headline          TEXT NOT NULL,
                source            TEXT,
                url               TEXT,
                timestamp         TEXT NOT NULL,
                sentiment         REAL,
                severity          TEXT,
                topics            TEXT
            );
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------
    def save_trade(self, trade: Trade) -> None:
        assert self._conn
        self._conn.execute(
            """
            INSERT OR REPLACE INTO trades
                (trade_id, pair, direction, entry_price, exit_price,
                 entry_time, exit_time, pnl, pnl_pct,
                 balance_before, balance_after, stop_loss, take_profit,
                 reason, status, discord_message_id, position_size,
                 quantity, sl_order_id, tp_order_id,
                 confidence_score, confidence_report)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                trade.trade_id, trade.pair, trade.direction,
                trade.entry_price, trade.exit_price,
                trade.entry_time.isoformat() if trade.entry_time else None,
                trade.exit_time.isoformat() if trade.exit_time else None,
                trade.pnl, trade.pnl_pct,
                trade.balance_before, trade.balance_after,
                trade.stop_loss, trade.take_profit,
                trade.reason, trade.status,
                trade.discord_message_id, trade.position_size,
                trade.quantity, trade.sl_order_id, trade.tp_order_id,
                trade.confidence_score, trade.confidence_report,
            ),
        )
        self._conn.commit()

    def get_open_trade(self) -> Optional[Trade]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY entry_time DESC LIMIT 1"
        ).fetchone()
        return self._row_to_trade(row) if row else None

    def get_last_closed_trade(self) -> Optional[Trade]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_time DESC LIMIT 1"
        ).fetchone()
        return self._row_to_trade(row) if row else None

    def get_all_trades(self) -> list[Trade]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM trades ORDER BY entry_time DESC"
        ).fetchall()
        return [self._row_to_trade(r) for r in rows]

    def get_trades_since(self, since: datetime) -> list[Trade]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM trades WHERE entry_time >= ? ORDER BY entry_time",
            (since.isoformat(),),
        ).fetchall()
        return [self._row_to_trade(r) for r in rows]

    def get_consecutive_losses(self) -> int:
        assert self._conn
        rows = self._conn.execute(
            "SELECT pnl FROM trades WHERE status = 'CLOSED' ORDER BY exit_time DESC LIMIT 10"
        ).fetchall()
        count = 0
        for r in rows:
            p = r["pnl"]
            if p is not None and p < 0:
                count += 1
            else:
                break
        return count

    def get_daily_pnl(self) -> float:
        assert self._conn
        today = datetime.utcnow().strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM trades "
            "WHERE status = 'CLOSED' AND exit_time LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return row[0] if row else 0.0

    def _row_to_trade(self, row: sqlite3.Row) -> Trade:
        return Trade(
            trade_id=row["trade_id"],
            pair=row["pair"],
            direction=row["direction"],
            entry_price=row["entry_price"],
            exit_price=row["exit_price"],
            entry_time=datetime.fromisoformat(row["entry_time"])
            if row["entry_time"] else None,
            exit_time=datetime.fromisoformat(row["exit_time"])
            if row["exit_time"] else None,
            pnl=row["pnl"],
            pnl_pct=row["pnl_pct"],
            balance_before=row["balance_before"],
            balance_after=row["balance_after"],
            stop_loss=row["stop_loss"],
            take_profit=row["take_profit"],
            reason=row["reason"],
            status=row["status"],
            discord_message_id=row["discord_message_id"],
            position_size=row["position_size"],
            quantity=row["quantity"],
            sl_order_id=row["sl_order_id"],
            tp_order_id=row["tp_order_id"],
            confidence_score=row["confidence_score"],
            confidence_report=row["confidence_report"],
        )

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    def save_market_snapshot(self, snap: MarketSnapshot) -> None:
        assert self._conn
        self._conn.execute(
            """
            INSERT INTO market_data
                (timestamp, price, ema_fast, ema_slow, ema_trend, volume,
                 open_interest, oi_change_1h, oi_change_4h, oi_change_24h, oi_trend,
                 funding_rate, funding_trend, long_short_ratio,
                 long_liquidations, short_liquidations, total_liquidations,
                 fear_greed_value, fear_greed_class, btc_dominance,
                 sentiment_score, trade_signal, trade_taken, trade_result, trade_pnl)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                snap.timestamp.isoformat(), snap.price,
                snap.ema_fast, snap.ema_slow, snap.ema_trend, snap.volume,
                snap.open_interest, snap.oi_change_1h, snap.oi_change_4h,
                snap.oi_change_24h, snap.oi_trend,
                snap.funding_rate, snap.funding_trend, snap.long_short_ratio,
                snap.long_liquidations, snap.short_liquidations,
                snap.total_liquidations,
                snap.fear_greed_value, snap.fear_greed_class, snap.btc_dominance,
                snap.sentiment_score, snap.trade_signal,
                1 if snap.trade_taken else 0,
                snap.trade_result, snap.trade_pnl,
            ),
        )
        self._conn.commit()

    def get_market_data(
        self, limit: int = 100, offset: int = 0
    ) -> list[MarketSnapshot]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM market_data ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def _row_to_snapshot(self, row: sqlite3.Row) -> MarketSnapshot:
        return MarketSnapshot(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            price=row["price"],
            ema_fast=row["ema_fast"],
            ema_slow=row["ema_slow"],
            ema_trend=row["ema_trend"],
            volume=row["volume"],
            open_interest=row["open_interest"],
            oi_change_1h=row["oi_change_1h"],
            oi_change_4h=row["oi_change_4h"],
            oi_change_24h=row["oi_change_24h"],
            oi_trend=row["oi_trend"],
            funding_rate=row["funding_rate"],
            funding_trend=row["funding_trend"],
            long_short_ratio=row["long_short_ratio"],
            long_liquidations=row["long_liquidations"],
            short_liquidations=row["short_liquidations"],
            total_liquidations=row["total_liquidations"],
            fear_greed_value=row["fear_greed_value"],
            fear_greed_class=row["fear_greed_class"],
            btc_dominance=row["btc_dominance"],
            sentiment_score=row["sentiment_score"],
            trade_signal=row["trade_signal"],
            trade_taken=bool(row["trade_taken"]),
            trade_result=row["trade_result"],
            trade_pnl=row["trade_pnl"],
        )

    # ------------------------------------------------------------------
    # Decision reports
    # ------------------------------------------------------------------
    def save_decision(self, report: DecisionReport) -> None:
        assert self._conn
        self._conn.execute(
            """
            INSERT INTO decision_reports
                (trade_id, timestamp, direction, confidence,
                 ema_check, funding_check, oi_check, news_check,
                 fear_greed, liquidation_risk, market_trend,
                 details, approved)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                report.trade_id, datetime.utcnow().isoformat(),
                report.direction, report.confidence,
                report.ema_check, report.funding_check, report.oi_check,
                report.news_check, report.fear_greed, report.liquidation_risk,
                report.market_trend, report.details,
                1 if report.approved else 0,
            ),
        )
        self._conn.commit()

    def get_recent_decisions(self, limit: int = 20) -> list[DecisionReport]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM decision_reports ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_decision(r) for r in rows]

    def _row_to_decision(self, row: sqlite3.Row) -> DecisionReport:
        return DecisionReport(
            trade_id=row["trade_id"],
            direction=row["direction"],
            confidence=row["confidence"],
            ema_check=row["ema_check"],
            funding_check=row["funding_check"],
            oi_check=row["oi_check"],
            news_check=row["news_check"],
            fear_greed=row["fear_greed"],
            liquidation_risk=row["liquidation_risk"],
            market_trend=row["market_trend"],
            details=row["details"],
            approved=bool(row["approved"]),
        )

    # ------------------------------------------------------------------
    # News cache
    # ------------------------------------------------------------------
    def save_news(self, item: NewsItem) -> None:
        assert self._conn
        self._conn.execute(
            """
            INSERT INTO news_cache (headline, source, url, timestamp, sentiment, severity, topics)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                item.headline, item.source, item.url,
                item.timestamp.isoformat(), item.sentiment,
                item.severity, json.dumps(item.topics),
            ),
        )
        self._conn.commit()

    def get_recent_news(self, limit: int = 20) -> list[NewsItem]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM news_cache ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_news(r) for r in rows]

    def _row_to_news(self, row: sqlite3.Row) -> NewsItem:
        return NewsItem(
            headline=row["headline"],
            source=row["source"],
            url=row["url"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            sentiment=row["sentiment"],
            severity=row["severity"],
            topics=json.loads(row["topics"]) if row["topics"] else [],
        )

    # ------------------------------------------------------------------
    # ML dataset export
    # ------------------------------------------------------------------
    def export_market_data_csv(self, path: Path) -> None:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM market_data ORDER BY timestamp ASC"
        ).fetchall()
        if not rows:
            logger.warning("No market data to export")
            return
        cols = [d[0] for d in self._conn.execute("PRAGMA table_info(market_data)").fetchall()]
        import csv
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow([r[c] for c in cols])
        logger.info("Exported %d rows to %s", len(rows), path)
