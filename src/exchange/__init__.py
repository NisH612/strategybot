import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

import aiohttp
import websockets

from src.config import Settings
from src.utils.logger import logger
from src.utils import retry_async


class BinanceError(Exception):
    def __init__(self, code: int, msg: str) -> None:
        self.code = code
        self.msg = msg
        super().__init__(f"[{code}] {msg}")


class BinanceClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False
        self._on_kline: Optional[Callable] = None
        self._on_ticker: Optional[Callable] = None
        self._listen_key: Optional[str] = None
        self._listen_key_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # HTTP session
    # ------------------------------------------------------------------
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _sign(self, params: dict) -> dict:
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(
            self.settings.binance_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    async def _request(
        self,
        method: str,
        path: str,
        signed: bool = False,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
    ) -> Any:
        params = params or {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            self._sign(params)

        url = f"{self.settings.rest_url}{path}"
        headers = {"X-MBX-APIKEY": self.settings.binance_api_key}

        session = await self._get_session()
        async with session.request(
            method, url, params=params, json=data, headers=headers, timeout=10
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                try:
                    err = json.loads(body)
                    code = err.get("code", resp.status)
                    msg = err.get("msg", body)
                except Exception:
                    code = resp.status
                    msg = body
                raise BinanceError(code, msg)
            return json.loads(body) if body else {}

    async def _signed_request(
        self, method: str, path: str, params: Optional[dict] = None
    ) -> Any:
        return await retry_async(
            lambda: self._request(method, path, signed=True, params=params),
            attempts=3,
            base_delay=1.0,
            exc_check=(BinanceError, aiohttp.ClientError),
        )

    # ------------------------------------------------------------------
    # Public REST
    # ------------------------------------------------------------------
    async def get_klines(
        self, symbol: str, interval: str, limit: int = 500
    ) -> list[dict]:
        data = await self._request(
            "GET",
            "/fapi/v1/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            },
        )
        result = []
        for k in data:
            result.append({
                "open_time": datetime.fromtimestamp(k[0] / 1000),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": datetime.fromtimestamp(k[6] / 1000),
            })
        return result

    async def get_exchange_info(self) -> dict:
        return await self._request("GET", "/fapi/v1/exchangeInfo")

    async def get_symbol_info(self, symbol: str) -> Optional[dict]:
        info = await self.get_exchange_info()
        for s in info.get("symbols", []):
            if s["symbol"] == symbol:
                return s
        return None

    # ------------------------------------------------------------------
    # Account REST (signed)
    # ------------------------------------------------------------------
    async def get_account(self) -> dict:
        return await self._signed_request("GET", "/fapi/v1/account")

    async def get_balance(self, asset: str = "USDT") -> float:
        account = await self.get_account()
        for bal in account.get("assets", []):
            if bal["asset"] == asset:
                return float(bal["walletBalance"])
        return 0.0

    async def get_position(self, symbol: str) -> Optional[dict]:
        account = await self.get_account()
        for pos in account.get("positions", []):
            if pos["symbol"] == symbol:
                amt = float(pos.get("positionAmt", "0"))
                if abs(amt) > 0:
                    return pos
        return None

    async def get_symbol_filters(self, symbol: str) -> dict:
        info = await self.get_symbol_info(symbol)
        result = {}
        for f in (info or {}).get("filters", []):
            ft = f["filterType"]
            if ft in ("LOT_SIZE", "MIN_NOTIONAL", "PRICE_FILTER"):
                result[ft] = f
        return result

    # ------------------------------------------------------------------
    # Orders (signed)
    # ------------------------------------------------------------------
    async def create_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reduce_only: bool = False,
    ) -> dict:
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return await self._signed_request("POST", "/fapi/v1/order", params=params)

    async def create_stop_loss(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
    ) -> dict:
        params = {
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "quantity": quantity,
            "stopPrice": stop_price,
            "reduceOnly": "true",
        }
        return await self._signed_request("POST", "/fapi/v1/order", params=params)

    async def create_take_profit(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
    ) -> dict:
        params = {
            "symbol": symbol,
            "side": side,
            "type": "TAKE_PROFIT_MARKET",
            "quantity": quantity,
            "stopPrice": stop_price,
            "reduceOnly": "true",
        }
        return await self._signed_request("POST", "/fapi/v1/order", params=params)

    async def cancel_order(self, symbol: str, order_id: int) -> dict:
        return await self._signed_request(
            "DELETE",
            "/fapi/v1/order",
            params={"symbol": symbol, "orderId": order_id},
        )

    async def cancel_all_orders(self, symbol: str) -> list:
        return await self._signed_request(
            "DELETE",
            "/fapi/v1/allOpenOrders",
            params={"symbol": symbol},
        )

    async def get_open_orders(self, symbol: str) -> list:
        return await self._signed_request(
            "GET",
            "/fapi/v1/openOrders",
            params={"symbol": symbol},
        )

    async def get_order(self, symbol: str, order_id: int) -> dict:
        return await self._signed_request(
            "GET",
            "/fapi/v1/order",
            params={"symbol": symbol, "orderId": order_id},
        )

    # ------------------------------------------------------------------
    # Listen key (user data stream)
    # ------------------------------------------------------------------
    async def create_listen_key(self) -> str:
        data = await self._request("POST", "/fapi/v1/listenKey")
        key: str = data.get("listenKey", "")
        return key

    async def keepalive_listen_key(self) -> None:
        if self._listen_key:
            try:
                await self._request(
                    "PUT",
                    "/fapi/v1/listenKey",
                    params={"listenKey": self._listen_key},
                )
            except Exception as exc:
                logger.warning("Listen key keepalive failed: %s", exc)

    async def _keepalive_loop(self) -> None:
        while self._running:
            await asyncio.sleep(1800)
            try:
                await self.keepalive_listen_key()
            except Exception as exc:
                logger.error("Listen key keepalive error: %s", exc)

    # ------------------------------------------------------------------
    # WebSocket public streams
    # ------------------------------------------------------------------
    async def _ws_connect(
        self, stream_name: str, handler: Callable
    ) -> None:
        uri = f"{self.settings.wss_url}/{stream_name}"
        logger.info("Connecting WebSocket: %s", uri)
        async for ws in websockets.connect(
            uri, ping_interval=20, ping_timeout=10, close_timeout=5
        ):
            try:
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        await handler(msg)
                    except Exception as exc:
                        logger.exception("WS handler error: %s", exc)
            except websockets.ConnectionClosed:
                logger.warning("WebSocket disconnected, reconnecting...")
                await asyncio.sleep(2)

    async def _handle_kline(self, msg: dict) -> None:
        if self._on_kline:
            await self._on_kline(msg)

    async def _handle_ticker(self, msg: dict) -> None:
        if self._on_ticker:
            await self._on_ticker(msg)

    async def _handle_user_data(self, msg: dict) -> None:
        pass  # reserved for account/order updates

    async def start_kline_stream(
        self, symbol: str, interval: str, callback: Callable
    ) -> None:
        self._on_kline = callback
        stream = f"{symbol.lower()}@kline_{interval}"
        asyncio.create_task(self._ws_connect(stream, self._handle_kline))

    async def start_ticker_stream(
        self, symbol: str, callback: Callable
    ) -> None:
        self._on_ticker = callback
        stream = f"{symbol.lower()}@ticker"
        asyncio.create_task(self._ws_connect(stream, self._handle_ticker))

    async def start_user_data_stream(self) -> None:
        self._listen_key = await self.create_listen_key()
        asyncio.create_task(self._ws_connect(
            self._listen_key, self._handle_user_data
        ))
        self._listen_key_task = asyncio.create_task(self._keepalive_loop())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def get_lot_step(self, symbol: str) -> float:
        filters = await self.get_symbol_filters(symbol)
        ls = filters.get("LOT_SIZE", {})
        return float(ls.get("stepSize", "0.001"))

    async def quantity_for_balance(
        self, symbol: str, balance: float, price: float
    ) -> float:
        step = await self.get_lot_step(symbol)
        qty = (balance / price) * 0.99
        return float(
            (Decimal(str(qty)) / Decimal(str(step))).to_integral_value() * Decimal(str(step))
        )

    async def get_mark_price(self, symbol: str) -> float:
        data = await self._request(
            "GET", "/fapi/v1/premiumIndex", params={"symbol": symbol}
        )
        return float(data.get("markPrice", 0))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        self._running = True
        logger.info(
            "Binance client started (testnet=%s)", self.settings.testnet
        )

    async def stop(self) -> None:
        self._running = False
        if self._listen_key_task:
            self._listen_key_task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("Binance client stopped")
