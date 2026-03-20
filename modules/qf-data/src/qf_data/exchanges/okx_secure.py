"""
OKX 交易所客户端 - 安全增强版
支持REST API和WebSocket，集成安全模块
API文档: https://www.okx.com/docs-v5/en/
"""
import asyncio
import json
import hmac
import base64
import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, AsyncIterator, Dict, Any
import aiohttp
import websockets

try:
    from qf_security import (
        mask_api_key, 
        mask_password,
        audit_log_event,
        AuditEventType,
        secure_logger,
        load_exchange_config,
    )
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False

from ..base import BaseDataSource
from ..types import KlineData, TickData, OrderBook, OrderBookLevel, SymbolInfo, Exchange, MarketType
from ..exceptions import DataSourceError, ConnectionError, AuthenticationError, RateLimitError

# 使用安全logger或标准logger
if SECURITY_AVAILABLE:
    logger = secure_logger("qf_data.okx")
else:
    logger = logging.getLogger(__name__)


class OKXClient(BaseDataSource):
    """
    OKX交易所客户端 - 安全增强版
    
    安全特性:
    - 配置自动解密
    - 日志脱敏 (API密钥、密码)
    - 操作审计
    """
    
    REST_BASE_URL = "https://www.okx.com"
    WS_PUBLIC_URL = "wss://ws.okx.com:8443/ws/v5/public"
    WS_PRIVATE_URL = "wss://ws.okx.com:8443/ws/v5/private"
    
    # K线周期映射
    INTERVAL_MAP = {
        "1m": "1m",
        "3m": "3m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1H",
        "2h": "2H",
        "4h": "4H",
        "6h": "6H",
        "12h": "12H",
        "1d": "1D",
        "1w": "1W",
        "1M": "1M",
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化OKX客户端
        
        Args:
            config: 配置字典，会自动尝试从安全存储加载
        """
        # 尝试从安全配置加载
        if config is None and SECURITY_AVAILABLE:
            try:
                config = load_exchange_config("okx")
                logger.info("Loaded OKX config from secure storage")
            except Exception as e:
                logger.warning(f"Failed to load secure config: {e}")
        
        super().__init__("OKX", config)
        
        self.api_key = self.config.get("api_key")
        self.api_secret = self.config.get("api_secret")
        self.passphrase = self.config.get("passphrase")
        
        # 统计信息
        self._request_count = 0
        self._error_count = 0
        
        # 会话和连接
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connection = None
        self._ws_subscriptions = {}
        self._ws_callbacks = {}
        
        # 记录初始化审计日志
        if SECURITY_AVAILABLE:
            audit_log_event(
                event_type=AuditEventType.SYSTEM_STATUS,
                resource_type="datasource",
                resource_id="okx",
                action="init",
                status="success",
                metadata={
                    "api_key_masked": mask_api_key(self.api_key) if self.api_key else None,
                    "use_proxy": self.config.get("use_proxy", False),
                }
            )
    
    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """生成API签名"""
        if not self.api_secret:
            raise AuthenticationError("API Secret not configured")
        message = timestamp + method.upper() + path + body
        mac = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode("utf-8")
    
    def _get_headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            headers["OK-ACCESS-KEY"] = self.api_key
            headers["OK-ACCESS-SIGN"] = self._generate_signature(timestamp, method, path, body)
            headers["OK-ACCESS-TIMESTAMP"] = timestamp
            headers["OK-ACCESS-PASSPHRASE"] = self.passphrase or ""
        return headers
    
    async def connect(self) -> None:
        """建立连接"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        self._connected = True
        
        logger.debug("OKX client connected")
    
    async def disconnect(self) -> None:
        """断开连接"""
        if self.ws_connection:
            await self.ws_connection.close()
            self.ws_connection = None
        if self.session:
            await self.session.close()
            self.session = None
        self._connected = False
        
        logger.debug("OKX client disconnected")
    
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Dict:
        """发送HTTP请求"""
        if not self.session:
            await self.connect()
        
        url = f"{self.REST_BASE_URL}{path}"
        body = json.dumps(data) if data else ""
        headers = self._get_headers(method, path, body)
        
        self._request_count += 1
        
        try:
            async with self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                data=body if body else None
            ) as response:
                if response.status == 429:
                    self._error_count += 1
                    
                    # 审计日志记录速率限制
                    if SECURITY_AVAILABLE:
                        audit_log_event(
                            event_type=AuditEventType.SYSTEM_ERROR,
                            resource_type="datasource",
                            resource_id="okx",
                            action="rate_limit",
                            status="failure",
                            error_message="Rate limit exceeded",
                        )
                    
                    raise RateLimitError("OKX API rate limit exceeded")
                
                response.raise_for_status()
                result = await response.json()
                
                if result.get("code") != "0":
                    error_msg = f"OKX API error: {result.get('msg')}"
                    logger.error(error_msg)
                    
                    # 审计日志记录API错误
                    if SECURITY_AVAILABLE:
                        audit_log_event(
                            event_type=AuditEventType.SYSTEM_ERROR,
                            resource_type="datasource",
                            resource_id="okx",
                            action="api_error",
                            status="failure",
                            error_message=error_msg,
                        )
                    
                    raise DataSourceError(error_msg, source="OKX")
                
                return result
        except aiohttp.ClientError as e:
            self._error_count += 1
            logger.error(f"OKX connection error: {e}")
            raise ConnectionError(f"OKX connection error: {e}")
    
    async def get_kline(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[KlineData]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对，如 "BTC-USDT"
            interval: K线周期，如 "1m", "1h", "1d"
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回条数限制，最大1000
        """
        okx_interval = self.INTERVAL_MAP.get(interval, interval)
        params = {
            "instId": symbol,
            "bar": okx_interval,
            "limit": min(limit, 1000),
        }
        if start_time:
            params["after"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["before"] = int(end_time.timestamp() * 1000)
        
        result = await self._request("GET", "/api/v5/market/candles", params=params)
        
        klines = []
        for item in result.get("data", []):
            # OKX返回格式: [timestamp, open, high, low, close, volume, quote_volume]
            klines.append(KlineData(
                timestamp=datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc),
                open=Decimal(str(item[1])),
                high=Decimal(str(item[2])),
                low=Decimal(str(item[3])),
                close=Decimal(str(item[4])),
                volume=Decimal(str(item[5])),
                quote_volume=Decimal(str(item[6])) if len(item) > 6 else None,
            ))
        
        logger.debug(f"Fetched {len(klines)} klines for {symbol}")
        
        # 审计日志
        if SECURITY_AVAILABLE:
            audit_log_event(
                event_type=AuditEventType.DATA_READ,
                resource_type="datasource",
                resource_id="okx",
                action="get_kline",
                status="success",
                metadata={
                    "symbol": symbol,
                    "interval": interval,
                    "count": len(klines),
                }
            )
        
        return sorted(klines, key=lambda x: x.timestamp)
    
    async def get_tick(self, symbol: str, limit: int = 100) -> List[TickData]:
        """获取最近成交数据（Tick数据）"""
        params = {
            "instId": symbol,
            "limit": min(limit, 1000),
        }
        result = await self._request("GET", "/api/v5/market/trades", params=params)
        
        ticks = []
        for item in result.get("data", []):
            ticks.append(TickData(
                timestamp=datetime.fromtimestamp(int(item["ts"]) / 1000, tz=timezone.utc),
                symbol=symbol,
                price=Decimal(str(item["px"])),
                volume=Decimal(str(item["sz"])),
                side=item.get("side"),
            ))
        
        return sorted(ticks, key=lambda x: x.timestamp)
    
    async def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBook:
        """获取订单簿"""
        params = {
            "instId": symbol,
            "sz": min(depth, 400),
        }
        result = await self._request("GET", "/api/v5/market/books", params=params)
        data = result.get("data", [{}])[0]
        
        bids = [
            OrderBookLevel(
                price=Decimal(str(b[0])),
                volume=Decimal(str(b[1])),
                count=int(b[3]) if len(b) > 3 else None
            )
            for b in data.get("bids", [])
        ]
        asks = [
            OrderBookLevel(
                price=Decimal(str(a[0])),
                volume=Decimal(str(a[1])),
                count=int(a[3]) if len(a) > 3 else None
            )
            for a in data.get("asks", [])
        ]
        
        return OrderBook(
            timestamp=datetime.fromtimestamp(int(data.get("ts", 0)) / 1000, tz=timezone.utc),
            symbol=symbol,
            bids=bids,
            asks=asks,
        )
    
    async def get_symbols(self, market_type: Optional[MarketType] = None) -> List[SymbolInfo]:
        """获取交易对列表"""
        inst_type = "SPOT"
        if market_type == MarketType.CRYPTO:
            inst_type = "SPOT"
        
        params = {"instType": inst_type}
        result = await self._request("GET", "/api/v5/public/instruments", params=params)
        
        symbols = []
        for item in result.get("data", []):
            symbols.append(SymbolInfo(
                symbol=item["instId"],
                exchange=Exchange.OKX,
                market_type=MarketType.CRYPTO,
                name=item.get("instNm"),
                base_asset=item.get("baseCcy"),
                quote_asset=item.get("quoteCcy"),
                price_precision=int(item.get("tickSz", "8").split(".")[-1]) if "." in item.get("tickSz", "8") else 0,
                quantity_precision=int(item.get("lotSz", "8").split(".")[-1]) if "." in item.get("lotSz", "8") else 0,
            ))
        
        return symbols
    
    async def _ws_connect(self) -> None:
        """建立WebSocket连接"""
        self.ws_connection = await websockets.connect(self.WS_PUBLIC_URL)
        asyncio.create_task(self._ws_handler())
    
    async def _ws_handler(self) -> None:
        """WebSocket消息处理"""
        try:
            async for message in self.ws_connection:
                data = json.loads(message)
                
                if data.get("event") == "subscribe":
                    continue
                
                if "arg" in data and "channel" in data["arg"]:
                    channel = data["arg"]["channel"]
                    inst_id = data["arg"].get("instId")
                    key = f"{channel}:{inst_id}"
                    
                    if key in self._ws_callbacks:
                        await self._ws_callbacks[key](data.get("data", []))
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
    
    async def _ws_subscribe(self, channel: str, symbol: str, callback) -> None:
        """订阅WebSocket频道"""
        if not self.ws_connection:
            await self._ws_connect()
        
        key = f"{channel}:{symbol}"
        self._ws_callbacks[key] = callback
        
        subscribe_msg = {
            "op": "subscribe",
            "args": [{"channel": channel, "instId": symbol}]
        }
        await self.ws_connection.send(json.dumps(subscribe_msg))
    
    async def subscribe_kline(self, symbol: str, interval: str) -> AsyncIterator[KlineData]:
        """订阅K线数据流"""
        okx_interval = self.INTERVAL_MAP.get(interval, interval)
        channel = f"candle{okx_interval}"
        
        queue = asyncio.Queue()
        
        async def callback(data):
            for item in data:
                kline = KlineData(
                    timestamp=datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc),
                    open=Decimal(str(item[1])),
                    high=Decimal(str(item[2])),
                    low=Decimal(str(item[3])),
                    close=Decimal(str(item[4])),
                    volume=Decimal(str(item[5])),
                    quote_volume=Decimal(str(item[6])) if len(item) > 6 else None,
                )
                await queue.put(kline)
        
        await self._ws_subscribe(channel, symbol, callback)
        
        while True:
            yield await queue.get()
    
    async def subscribe_tick(self, symbol: str) -> AsyncIterator[TickData]:
        """订阅成交数据流"""
        queue = asyncio.Queue()
        
        async def callback(data):
            for item in data:
                tick = TickData(
                    timestamp=datetime.fromtimestamp(int(item["ts"]) / 1000, tz=timezone.utc),
                    symbol=symbol,
                    price=Decimal(str(item["px"])),
                    volume=Decimal(str(item["sz"])),
                    side=item.get("side"),
                )
                await queue.put(tick)
        
        await self._ws_subscribe("trades", symbol, callback)
        
        while True:
            yield await queue.get()
    
    async def subscribe_orderbook(self, symbol: str, depth: int = 20) -> AsyncIterator[OrderBook]:
        """订阅订单簿数据流"""
        if depth <= 5:
            channel = "books5"
        elif depth <= 50:
            channel = "books"
        else:
            channel = "books-l2-tbt"
        
        queue = asyncio.Queue()
        
        async def callback(data):
            for item in data:
                bids = [
                    OrderBookLevel(
                        price=Decimal(str(b[0])),
                        volume=Decimal(str(b[1])),
                        count=int(b[3]) if len(b) > 3 else None
                    )
                    for b in item.get("bids", [])
                ]
                asks = [
                    OrderBookLevel(
                        price=Decimal(str(a[0])),
                        volume=Decimal(str(a[1])),
                        count=int(a[3]) if len(a) > 3 else None
                    )
                    for a in item.get("asks", [])
                ]
                
                orderbook = OrderBook(
                    timestamp=datetime.fromtimestamp(int(item.get("ts", 0)) / 1000, tz=timezone.utc),
                    symbol=symbol,
                    bids=bids,
                    asks=asks,
                )
                await queue.put(orderbook)
        
        await self._ws_subscribe(channel, symbol, callback)
        
        while True:
            yield await queue.get()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "request_count": self._request_count,
            "error_count": self._error_count,
            "connected": self._connected,
        }
