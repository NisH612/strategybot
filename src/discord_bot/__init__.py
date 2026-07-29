from datetime import datetime
from typing import Optional

import aiohttp

from src.config import Settings
from src.models import Trade, MarketSnapshot, DecisionReport
from src.utils.logger import logger


class DiscordNotifier:
    def __init__(self, settings: Settings) -> None:
        self.token = settings.discord_token
        self.channel_id = settings.discord_channel_id
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _color(self, trade: Trade) -> int:
        return 0x00FF00 if trade.direction == "LONG" else 0xFF0000

    def _timestamp(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    def _intel_fields(self) -> list[dict]:
        fields = []
        if self._intel:
            fields.append({"name": "OI 1h", "value": f"{self._intel.oi_change_1h:+.1f}% ({self._intel.oi_trend})", "inline": True})
            fields.append({"name": "Funding", "value": f"{self._intel.funding_rate:.4f}% ({self._intel.funding_trend})", "inline": True})
            fields.append({"name": "F&G", "value": f"{self._intel.fear_greed_value:.0f} ({self._intel.fear_greed_class})", "inline": True})
            fields.append({"name": "Dom", "value": f"{self._intel.btc_dominance:.1f}%", "inline": True})
            fields.append({"name": "L/S", "value": f"{self._intel.long_short_ratio:.2f}", "inline": True})
            fields.append({"name": "Liq", "value": f"L:{self._intel.long_liquidations:.0f} S:{self._intel.short_liquidations:.0f}", "inline": True})
        if self._sentiment is not None:
            emoji = "🟢" if self._sentiment > 10 else ("🔴" if self._sentiment < -10 else "⚪")
            fields.append({"name": "Sentiment", "value": f"{emoji} {self._sentiment:+.0f}", "inline": True})
        if self._decision:
            fields.append({"name": "Confidence", "value": f"{self._decision.confidence:.0f}% {'✅' if self._decision.approved else '❌'}", "inline": False})
        return fields

    def _build_open_embed(self, trade: Trade) -> dict:
        fields = [
            {"name": "Pair", "value": trade.pair, "inline": True},
            {"name": "Direction", "value": trade.direction, "inline": True},
            {"name": "Entry", "value": f"${trade.entry_price:,.2f}", "inline": True},
            {"name": "SL", "value": f"${trade.stop_loss:,.2f}", "inline": True},
            {"name": "TP", "value": f"${trade.take_profit:,.2f}", "inline": True},
            {"name": "Size", "value": f"${trade.position_size:,.2f}", "inline": True},
            {"name": "Balance", "value": f"${trade.balance_before:,.2f}", "inline": True},
        ]
        fields += self._intel_fields()
        fields.append({"name": "Time", "value": trade.entry_time.strftime("%Y-%m-%d %H:%M:%S UTC") if trade.entry_time else "N/A", "inline": False})
        return {
            "title": "Trade Opened",
            "color": self._color(trade),
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def _build_update_embed(self, trade: Trade, current_price: float) -> dict:
        pnl = trade.position_size * ((current_price - trade.entry_price) / trade.entry_price) if trade.direction == "LONG" else trade.position_size * ((trade.entry_price - current_price) / trade.entry_price)
        pnl_pct = ((current_price - trade.entry_price) / trade.entry_price * 100) if trade.direction == "LONG" else ((trade.entry_price - current_price) / trade.entry_price * 100)
        balance = trade.balance_before + pnl
        fields = [
            {"name": "Pair", "value": trade.pair, "inline": True},
            {"name": "Dir", "value": trade.direction, "inline": True},
            {"name": "Entry", "value": f"${trade.entry_price:,.2f}", "inline": True},
            {"name": "Price", "value": f"${current_price:,.2f}", "inline": True},
            {"name": "PnL", "value": f"{pnl:+.2f} ({pnl_pct:+.2f}%)", "inline": False},
            {"name": "Dur", "value": trade.duration or "N/A", "inline": True},
            {"name": "SL", "value": f"${trade.stop_loss:,.2f}", "inline": True},
            {"name": "TP", "value": f"${trade.take_profit:,.2f}", "inline": True},
            {"name": "Balance", "value": f"${balance:,.2f}", "inline": True},
        ]
        fields += self._intel_fields()
        return {
            "title": "Trade Opened",
            "color": self._color(trade),
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def _build_close_embed(self, trade: Trade) -> dict:
        arrow = "🟢" if (trade.pnl or 0) >= 0 else "🔴"
        fields = [
            {"name": "Pair", "value": trade.pair, "inline": True},
            {"name": "Direction", "value": trade.direction, "inline": True},
            {"name": "Entry", "value": f"${trade.entry_price:,.2f}", "inline": True},
            {"name": "Exit", "value": f"${trade.exit_price:,.2f}" if trade.exit_price else "N/A", "inline": True},
            {"name": "SL", "value": f"${trade.stop_loss:,.2f}", "inline": True},
            {"name": "TP", "value": f"${trade.take_profit:,.2f}", "inline": True},
            {"name": f"PnL {arrow}", "value": f"{trade.pnl:+.2f} ({trade.pnl_pct:+.2f}%)" if trade.pnl_pct else "N/A", "inline": False},
            {"name": "Balance", "value": f"${trade.balance_after:,.2f}" if trade.balance_after else "N/A", "inline": True},
        ]
        if trade.confidence_score is not None:
            fields.append({"name": "Confidence", "value": f"{trade.confidence_score:.0f}%", "inline": True})
        fields.append({"name": "Dur", "value": trade.duration or "N/A", "inline": True})
        fields.append({"name": "Reason", "value": trade.reason or "N/A", "inline": True})
        return {
            "title": "Trade Closed",
            "color": 0x808080,
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def set_intel(self, intel=None, decision=None, sentiment: float | None = None) -> None:
        self._intel = intel
        self._decision = decision
        self._sentiment = sentiment

    async def send_message(self, embed: dict) -> Optional[int]:
        session = await self._get_session()
        url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
        }
        payload = {"embeds": [embed]}
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                logger.error("Discord send failed [%s]: %s", resp.status, text)
                return None
            data = await resp.json()
            msg_id: int = data["id"]
            return msg_id

    async def edit_message(self, message_id: int, embed: dict) -> bool:
        session = await self._get_session()
        url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages/{message_id}"
        headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
        }
        payload = {"embeds": [embed]}
        async with session.patch(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error("Discord edit failed [%s]: %s", resp.status, text)
                return False
            return True

    async def send_trade_open(self, trade: Trade) -> Optional[int]:
        embed = self._build_open_embed(trade)
        msg_id = await self.send_message(embed)
        if msg_id:
            logger.info(
                "Discord trade-open sent (msg_id=%s)", msg_id
            )
        return msg_id

    async def send_trade_update(self, trade: Trade, current_price: float) -> bool:
        if not trade.discord_message_id:
            return False
        embed = self._build_update_embed(trade, current_price)
        return await self.edit_message(trade.discord_message_id, embed)

    async def send_trade_close(self, trade: Trade) -> bool:
        if not trade.discord_message_id:
            return False
        embed = self._build_close_embed(trade)
        return await self.edit_message(trade.discord_message_id, embed)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
