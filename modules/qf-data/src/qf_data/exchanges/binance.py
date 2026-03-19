"""
Binance 交易所客户端
支持REST API和WebSocket
API文档: https://binance-docs.github.io/apidocs/
"""
import asyncio
import json
import hmac
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, AsyncIterator, Dict, Any
import aiohttp
import websockets

from ..base import BaseDataSource
from ..types import KlineData, TickData, OrderBook, OrderBookLevel, SymbolInfo, Exchange, MarketType
from ..exceptions import DataSourceError, ConnectionError, AuthenticationError, RateLimitError


class BinanceClient(BaseDataSource):
    """Binance交易所客户端"""
    
    REST_BASE_URL = "https://api.binance.com"
    WS_BASE_URL = "wss://stream.binance.com:9443/ws"
    WS_STREAM_URL = "wss://stream.binance.com:9443/stream"
    
    # K线周期映射
    INTERVAL_MAP = {
        "1m": "1m",
        "3m": "3m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "8h": "8h",
        "12h": "12h",
        "1d": "1d",
        "3d": "3d",
        "1w": "1w",
        "1M": "1M",
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("Binance", config)
        self.api_key = self.config.get("api_key")
        self.api_secret = self.config.get("api_secret")
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connection = None
        self._ws_callbacks = {}
    
    def _generate_signature(self, query_string: str) -> str:
        """生成API签名"""
        if not self.api_secret:
            raise AuthenticationError("API Secret not configured")
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        return headers
    
    async def connect(self) -> None:
        """建立连接"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        self._connected = True
    
    async def disconnect(self) -> None:
        """断开连接"""
        if self.ws_connection:
            await self.ws_connection.close()
            self.ws_connection = None
        if self.session:
            await self.session.close()
            self.session = None
        self._connected = False
    
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        signed: bool = False
    ) -> Dict:
        """发送HTTP请求"""
        if not self.session:
            await self.connect()
        
        url = f"{self.REST_BASE_URL}{path}"
        headers = self._get_headers()
        params = params or {}
        
        if signed and self.api_secret:
            params["timestamp"] = int(datetime.now(timezone.utc).timestamp() * 1000)
            query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
            params["signature"] = self._generate_signature(query_string)
        
        try:
            async with self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params
            ) as response:
                if response.status == 429:
                    raise RateLimitError("Binance API rate limit exceeded")
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            raise ConnectionError(f"Binance connection error: {e}")
    
    async def get_kline(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[KlineData]:
        """获取K线数据
        
        Args:
            symbol: 交易对，如 "BTCUSDT"
            interval: K线周期
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回条数限制，最大1000
        """
        binance_interval = self.INTERVAL_MAP.get(interval, interval)
        params = {
            "symbol": symbol,
            "interval": binance_interval,
            "limit": min(limit, 1000),
        }
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)
        
        result = await self._request("GET", "/api/v3/klines", params=params)
        
        klines = []
        for item in result:
            # Binance返回格式:
            # [open_time, open, high, low, close, volume, close_time, quote_volume, trades, ...]
            klines.append(KlineData(
                timestamp=datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc),
                open=Decimal(str(item[1])),
                high=Decimal(str(item[2])),
                low=Decimal(str(item[3])),
                close=Decimal(str(item[4])),
                volume=Decimal(str(item[5])),
                quote_volume=Decimal(str(item[7])),
                trades=item[8],
                buy_volume=Decimal(str(item[9])),
                sell_volume=Decimal(str(item[5])) - Decimal(str(item[9])),
            ))
        
        return klines
    
    async def get_tick(self, symbol: str, limit: int = 100) -> List[TickData]:
        """获取最近成交数据"""
        params = {
            "symbol": symbol,
            "limit": min(limit, 1000),
        }
        result = await self._request("GET", "/api/v3/trades", params=params)
        
        ticks = []
        for item in result:
            ticks.append(TickData(
                timestamp=datetime.fromtimestamp(item["time"] / 1000, tz=timezone.utc),
                symbol=symbol,
                price=Decimal(str(item["price"])),
                volume=Decimal(str(item["qty"])),
                side="buy" if item.get("isBuyerMaker") == False else "sell",
            ))
        
        return sorted(ticks, key=lambda x: x.timestamp)
    
    async def get_orderbook(self, symbol: str, depth: int = 100) -> OrderBook:
        """获取订单簿"""
        # Binance允许的limit: 5, 10, 20, 50, 100, 500, 1000, 5000
        valid_limits = [5, 10, 20, 50, 100, 500, 1000, 5000]
        limit = min(valid_limits, key=lambda x: abs(x - depth) if x >= depth else float('inf'))
        
        params = {
            "symbol": symbol,
            "limit": limit,
        }
        result = await self._request("GET", "/api/v3/depth", params=params)
        
        bids = [
            OrderBookLevel(
                price=Decimal(str(b[0])),
                volume=Decimal(str(b[1]))
            )
            for b in result.get("bids", [])
        ]
        asks = [
            OrderBookLevel(
                price=Decimal(str(a[0])),
                volume=Decimal(str(a[1]))
            )
            for a in result.get("asks", [])
        ]
        
        return OrderBook(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            bids=bids,
            asks=asks,
        )
    
    async def get_symbols(self, market_type: Optional[MarketType] = None) -> List[SymbolInfo]:
        """获取交易对列表"""
        result = await self._request("GET", "/api/v3/exchangeInfo")
        
        symbols = []
        for item in result.get("symbols", []):
            if item.get("status") != "TRADING":
                continue
            
            # 计算精度
            price_precision = 0
            qty_precision = 0
            
            for filter_info in item.get("filters", []):
                if filter_info.get("filterType") == "PRICE_FILTER":
                    tick_size = filter_info.get("tickSize", "0.1")
                    price_precision = len(tick_size.split(".")[-1].rstrip("0")) if "." in tick_size else 0
                elif filter_info.get("filterType") == "LOT_SIZE":
                    step_size = filter_info.get("stepSize", "0.1")
                    qty_precision = len(step_size.split(".")[-1].rstrip("0")) if "." in step_size else 0
            
            symbols.append(SymbolInfo(
                symbol=item["symbol"],
                exchange=Exchange.BINANCE,
                market_type=MarketType.CRYPTO,
                base_asset=item.get("baseAsset"),
                quote_asset=item.get("quoteAsset"),
                price_precision=price_precision,
                quantity_precision=qty_precision,
            ))
        
        return symbols
    
    async def _ws_connect(self, streams: List[str]) -> None:
        """建立WebSocket连接（多流）"""
        stream_path = "/".join(streams)
        url = f"{self.WS_STREAM_URL}?streams={stream_path}"
        self.ws_connection = await websockets.connect(url)
        asyncio.create_task(self._ws_handler())
    
    async def _ws_handler(self) -> None:
        """WebSocket消息处理"""
        try:
            async for message in self.ws_connection:
                data = json.loads(message)
                stream = data.get("stream", "")
                payload = data.get("data", {})
                
                if stream in self._ws_callbacks:
                    await self._ws_callbacks[stream](payload)
        except websockets.exceptions.ConnectionClosed:
            pass
    
    async def _ws_subscribe(self, stream: str, callback) -> None:
        """订阅WebSocket流"""
        if not self.ws_connection:
            await self._ws_connect([stream])
        self._ws_callbacks[stream] = callback
    
    async def subscribe_kline(self, symbol: str, interval: str) -> AsyncIterator[KlineData]:
        """订阅K线数据流"""
        symbol_lower = symbol.lower()
        binance_interval = self.INTERVAL_MAP.get(interval, interval)
        stream = f"{symbol_lower}@kline_{binance_interval}"
        
        queue = asyncio.Queue()
        
        async def callback(data):
            k = data.get("k", {})
            if k.get("x"):  # 只返回完成的K线
                kline = KlineData(
                    timestamp=datetime.fromtimestamp(k["t"] / 1000, tz=timezone.utc),
                    open=Decimal(str(k["o"])),
                    high=Decimal(str(k["h"])),
                    low=Decimal(str(k["l"])),
                    close=Decimal(str(k["c"])),
                    volume=Decimal(str(k["v"])),
                    quote_volume=Decimal(str(k["q"])),
                    trades=k.get("n"),
                    buy_volume=Decimal(str(k["V"])),
                    sell_volume=Decimal(str(k["v"])) - Decimal(str(k["V"])),
                )
                await queue.put(kline)
        
        await self._ws_subscribe(stream, callback)
        
        while True:
            yield await queue.get()
    
    async def subscribe_tick(self, symbol: str) -> AsyncIterator[TickData]:
        """订阅成交数据流"""
        symbol_lower = symbol.lower()
        stream = f"{symbol_lower}@trade"
        
        queue = asyncio.Queue()
        
        async def callback(data):
            tick = TickData(
                timestamp=datetime.fromtimestamp(data["T"] / 1000, tz=timezone.utc),
                symbol=symbol,
                price=Decimal(str(data["p"])),
                volume=Decimal(str(data["q"])),
                side="buy" if not data.get("m") else "sell",
            )
            await queue.put(tick)
        
        await self._ws_subscribe(stream, callback)
        
        while True:
            yield await queue.get()
    
    async def subscribe_orderbook(self, symbol: str, depth: int = 20) -> AsyncIterator[OrderBook]:
        """订阅订单簿数据流"""
        symbol_lower = symbol.lower()
        # Binance支持 @depth 或 @depth5, @depth10, @depth20
        if depth in [5, 10, 20]:
            stream = f"{symbol_lower}@depth{depth}"
        else:
            stream = f"{symbol_lower}@depth"
        
        queue = asyncio.Queue()
        
        async def callback(data):
            bids = [
                OrderBookLevel(price=Decimal(str(b[0])), volume=Decimal(str(b[1])))
                for b in data.get("b", [])
            ]
            asks = [
                OrderBookLevel(price=Decimal(str(a[0])), volume=Decimal(str(a[1])))
                for a in data.get("a", [])
            ]
            
            orderbook = OrderBook(
                timestamp=datetime.fromtimestamp(data.get("E", 0) / 1000, tz=timezone.utc),
                symbol=symbol,
                bids=bids,
                asks=asks,
            )
            await queue.put(orderbook)
        
        await self._ws_subscribe(stream, callback)
        
        while True:
            yield await queue.get()
