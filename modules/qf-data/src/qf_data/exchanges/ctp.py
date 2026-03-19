"""
期货数据源 - CTP (Comprehensive Transaction Platform)
CTP是上期所开发的期货交易系统接口
API文档: http://www.sfit.com.cn/5_2_DocumentDown.htm
"""
import asyncio
import struct
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, AsyncIterator, Dict, Any, Callable
import socket
import threading
import queue

from ..base import BaseDataSource
from ..types import KlineData, TickData, OrderBook, OrderBookLevel, SymbolInfo, Exchange, MarketType
from ..exceptions import DataSourceError, ConnectionError, AuthenticationError


class CTPClient(BaseDataSource):
    """CTP期货行情客户端
    
    注意：这是CTP接口的简化实现。实际使用时需要:
    1. 安装openctp或vnpy等CTP封装库
    2. 配置CTP柜台地址和认证信息
    3. 处理CTP特有的流控和重连机制
    
    CTP API分为:
    - MdApi: 行情接口
    - TraderApi: 交易接口
    
    这里只实现行情接口
    """
    
    # 交易所代码映射
    EXCHANGE_MAP = {
        "SHFE": Exchange.SHFE,      # 上期所
        "DCE": Exchange.DCE,        # 大商所
        "CZCE": Exchange.CZCE,      # 郑商所
        "CFFEX": Exchange.CFFEX,    # 中金所
        "INE": Exchange.INE,        # 能源中心
        "GFEX": Exchange.SHFE,      # 广期所 (暂映射到上期所)
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("CTP", config)
        self.front_address = self.config.get("front_address", "tcp://180.168.146.187:10131")
        self.broker_id = self.config.get("broker_id", "9999")
        self.user_id = self.config.get("user_id", "")
        self.password = self.config.get("password", "")
        self.investor_id = self.config.get("investor_id", "")
        
        # CTP API实例 (实际使用时需要openctp或py_ctp)
        self.md_api = None
        self.trader_api = None
        
        # 回调数据缓存
        self._tick_cache: Dict[str, TickData] = {}
        self._depth_cache: Dict[str, OrderBook] = {}
        self._subscribed_symbols: set = set()
        
        # 异步队列
        self._tick_queues: Dict[str, asyncio.Queue] = {}
        self._depth_queues: Dict[str, asyncio.Queue] = {}
    
    async def connect(self) -> None:
        """建立CTP连接"""
        try:
            # 尝试导入CTP库
            # 优先尝试openctp，然后是其他实现
            try:
                from openctp import MdApi
                self._init_openctp(MdApi)
            except ImportError:
                try:
                    from vnpy_ctp import MdApi
                    self._init_vnpy_ctp(MdApi)
                except ImportError:
                    # 模拟模式 - 用于测试
                    self._init_mock()
            
            self._connected = True
        except Exception as e:
            raise ConnectionError(f"CTP connection failed: {e}")
    
    def _init_openctp(self, MdApi):
        """初始化openctp接口"""
        # 这里应该实现openctp的初始化
        # 由于CTP库需要特定环境，这里使用模拟
        self._init_mock()
    
    def _init_vnpy_ctp(self, MdApi):
        """初始化vnpy_ctp接口"""
        # 这里应该实现vnpy_ctp的初始化
        self._init_mock()
    
    def _init_mock(self):
        """初始化模拟模式（用于测试）"""
        self.md_api = MockCTPMdApi(self)
        self._connected = True
    
    async def disconnect(self) -> None:
        """断开CTP连接"""
        if self.md_api:
            # 退订所有行情
            for symbol in list(self._subscribed_symbols):
                self.md_api.UnSubscribeMarketData(symbol)
            self.md_api.Release()
            self.md_api = None
        
        self._connected = False
        self._tick_cache.clear()
        self._depth_cache.clear()
    
    def on_tick(self, tick: TickData) -> None:
        """行情推送回调"""
        self._tick_cache[tick.symbol] = tick
        
        # 推送到队列
        if tick.symbol in self._tick_queues:
            try:
                self._tick_queues[tick.symbol].put_nowait(tick)
            except asyncio.QueueFull:
                pass
    
    def on_depth(self, symbol: str, orderbook: OrderBook) -> None:
        """深度数据回调"""
        self._depth_cache[symbol] = orderbook
        
        if symbol in self._depth_queues:
            try:
                self._depth_queues[symbol].put_nowait(orderbook)
            except asyncio.QueueFull:
                pass
    
    async def get_kline(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[KlineData]:
        """获取K线数据
        
        注意：CTP不直接提供历史K线，需要从其他数据源获取
        这里返回基于Tick数据合成的K线或空列表
        """
        # CTP主要提供实时行情，历史K线需要通过其他方式获取
        # 可以接入Tdx、Pytdx等库获取历史数据
        
        # 尝试使用pytdx获取
        try:
            return await self._get_kline_from_tdx(symbol, interval, start_time, end_time, limit)
        except Exception:
            # 如果pytdx不可用，返回空列表
            return []
    
    async def _get_kline_from_tdx(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        limit: int
    ) -> List[KlineData]:
        """通过pytdx获取K线数据"""
        try:
            from pytdx.hq import TdxHq_API
            
            api = TdxHq_API()
            # TDX服务器地址
            with api.connect('119.147.212.81', 7709):
                # 解析合约代码
                # symbol格式: rb2401@SHFE 或 rb2401
                if "@" in symbol:
                    code, exchange = symbol.split("@")
                else:
                    code = symbol
                    exchange = self._guess_exchange(code)
                
                # TDX市场代码: 0=深圳, 1=上海, 28=中金所, 29=大商所, 30=郑商所, 31=上期所
                market_map = {
                    "SHFE": 31,
                    "DCE": 29,
                    "CZCE": 30,
                    "CFFEX": 28,
                    "INE": 31,
                }
                market = market_map.get(exchange, 29)
                
                # 获取K线数据
                data = api.get_security_bars(
                    9 if interval == "1d" else 0,  # 9=日线, 0=1分钟
                    market,
                    code,
                    0,
                    limit
                )
                
                klines = []
                for item in data:
                    klines.append(KlineData(
                        timestamp=datetime.strptime(str(item["datetime"]), "%Y%m%d%H%M").replace(tzinfo=timezone.utc),
                        open=Decimal(str(item["open"])),
                        high=Decimal(str(item["high"])),
                        low=Decimal(str(item["low"])),
                        close=Decimal(str(item["close"])),
                        volume=Decimal(str(item["vol"])),
                    ))
                
                return klines
        except ImportError:
            return []
    
    def _guess_exchange(self, code: str) -> str:
        """根据合约代码猜测交易所"""
        # 简单规则，实际应使用配置
        product = ''.join(filter(str.isalpha, code)).upper()
        product_map = {
            # 上期所
            "CU": "SHFE", "AL": "SHFE", "ZN": "SHFE", "PB": "SHFE", "NI": "SHFE",
            "SN": "SHFE", "AU": "SHFE", "AG": "SHFE", "RB": "SHFE", "HC": "SHFE",
            "BU": "SHFE", "RU": "SHFE", "FU": "SHFE", "SP": "SHFE", "SS": "SHFE",
            "WR": "SHFE", "SC": "INE", "LU": "INE", "NR": "INE",
            # 大商所
            "C": "DCE", "CS": "DCE", "A": "DCE", "B": "DCE", "M": "DCE",
            "Y": "DCE", "P": "DCE", "FB": "DCE", "BB": "DCE", "JD": "DCE",
            "L": "DCE", "V": "DCE", "PP": "DCE", "J": "DCE", "JM": "DCE",
            "I": "DCE", "EG": "DCE", "EB": "DCE", "PG": "DCE", "RR": "DCE",
            # 郑商所
            "SR": "CZCE", "CF": "CZCE", "TA": "CZCE", "OI": "CZCE", "MA": "CZCE",
            "FG": "CZCE", "RM": "CZCE", "ZC": "CZCE", "CY": "CZCE", "AP": "CZCE",
            "UR": "CZCE", "SA": "CZCE", "PF": "CZCE", "PK": "CZCE",
            # 中金所
            "IF": "CFFEX", "IC": "CFFEX", "IH": "CFFEX", "T": "CFFEX", "TF": "CFFEX",
            "TS": "CFFEX", "TL": "CFFEX", "IM": "CFFEX",
        }
        return product_map.get(product, "SHFE")
    
    async def get_tick(self, symbol: str, limit: int = 100) -> List[TickData]:
        """获取最新Tick数据"""
        # 订阅行情并等待数据
        if symbol not in self._subscribed_symbols:
            await self._subscribe_symbol(symbol)
        
        # 等待数据到达
        for _ in range(50):  # 等待最多5秒
            if symbol in self._tick_cache:
                return [self._tick_cache[symbol]]
            await asyncio.sleep(0.1)
        
        return []
    
    async def _subscribe_symbol(self, symbol: str) -> None:
        """订阅合约行情"""
        if self.md_api and symbol not in self._subscribed_symbols:
            # CTP格式: 合约代码@交易所
            if "@" not in symbol:
                exchange = self._guess_exchange(symbol)
                ctp_symbol = f"{symbol}@{exchange}"
            else:
                ctp_symbol = symbol
            
            self.md_api.SubscribeMarketData(ctp_symbol)
            self._subscribed_symbols.add(symbol)
    
    async def get_symbols(self, market_type: Optional[MarketType] = None) -> List[SymbolInfo]:
        """获取合约列表"""
        # CTP通过查询合约接口获取
        # 这里返回主要期货合约
        main_contracts = [
            # 上期所
            ("CU", "SHFE", "沪铜"),
            ("AL", "SHFE", "沪铝"),
            ("ZN", "SHFE", "沪锌"),
            ("AU", "SHFE", "沪金"),
            ("AG", "SHFE", "沪银"),
            ("RB", "SHFE", "螺纹钢"),
            ("HC", "SHFE", "热卷"),
            ("BU", "SHFE", "沥青"),
            ("RU", "SHFE", "橡胶"),
            # 大商所
            ("C", "DCE", "玉米"),
            ("M", "DCE", "豆粕"),
            ("Y", "DCE", "豆油"),
            ("P", "DCE", "棕榈油"),
            ("JD", "DCE", "鸡蛋"),
            ("L", "DCE", "塑料"),
            ("PP", "DCE", "聚丙烯"),
            ("J", "DCE", "焦炭"),
            ("JM", "DCE", "焦煤"),
            ("I", "DCE", "铁矿石"),
            # 郑商所
            ("SR", "CZCE", "白糖"),
            ("CF", "CZCE", "棉花"),
            ("TA", "CZCE", "PTA"),
            ("MA", "CZCE", "甲醇"),
            ("FG", "CZCE", "玻璃"),
            ("RM", "CZCE", "菜粕"),
            # 中金所
            ("IF", "CFFEX", "沪深300"),
            ("IC", "CFFEX", "中证500"),
            ("IH", "CFFEX", "上证50"),
            ("IM", "CFFEX", "中证1000"),
            ("T", "CFFEX", "10年期国债"),
            ("TF", "CFFEX", "5年期国债"),
        ]
        
        from datetime import datetime
        year = datetime.now().year % 100
        
        symbols = []
        for code, exchange, name in main_contracts:
            # 生成最近几个合约月
            for month in [1, 5, 9]:  # 主力合约月
                contract = f"{code}{(year if month >= datetime.now().month else year+1):02d}{month:02d}"
                symbols.append(SymbolInfo(
                    symbol=f"{contract}@{exchange}",
                    exchange=self.EXCHANGE_MAP.get(exchange, Exchange.SHFE),
                    market_type=MarketType.FUTURES,
                    name=name,
                ))
        
        return symbols
    
    async def subscribe_tick(self, symbol: str) -> AsyncIterator[TickData]:
        """订阅Tick数据流"""
        if symbol not in self._tick_queues:
            self._tick_queues[symbol] = asyncio.Queue(maxsize=1000)
        
        await self._subscribe_symbol(symbol)
        
        while True:
            tick = await self._tick_queues[symbol].get()
            yield tick
    
    async def subscribe_orderbook(self, symbol: str, depth: int = 5) -> AsyncIterator[OrderBook]:
        """订阅订单簿数据流"""
        if symbol not in self._depth_queues:
            self._depth_queues[symbol] = asyncio.Queue(maxsize=100)
        
        await self._subscribe_symbol(symbol)
        
        while True:
            orderbook = await self._depth_queues[symbol].get()
            yield orderbook


class MockCTPMdApi:
    """模拟CTP行情API（用于测试）"""
    
    def __init__(self, client: CTPClient):
        self.client = client
        self._running = False
        self._subscriptions = set()
    
    def SubscribeMarketData(self, symbol: str):
        """订阅行情"""
        self._subscriptions.add(symbol)
        if not self._running:
            self._running = True
            asyncio.create_task(self._generate_mock_data())
    
    def UnSubscribeMarketData(self, symbol: str):
        """退订行情"""
        self._subscriptions.discard(symbol)
    
    def Release(self):
        """释放资源"""
        self._running = False
        self._subscriptions.clear()
    
    async def _generate_mock_data(self):
        """生成模拟行情数据"""
        import random
        
        base_prices = {
            "RB": 3800,
            "CU": 68000,
            "AU": 450,
            "SC": 550,
        }
        
        while self._running:
            for symbol in list(self._subscriptions):
                # 解析合约代码
                code = symbol.split("@")[0] if "@" in symbol else symbol
                product = ''.join(filter(str.isalpha, code)).upper()
                base_price = base_prices.get(product, 1000)
                
                # 生成模拟数据
                price = base_price * (1 + random.uniform(-0.001, 0.001))
                tick = TickData(
                    timestamp=datetime.now(timezone.utc),
                    symbol=symbol,
                    price=Decimal(str(round(price, 2))),
                    volume=Decimal(str(random.randint(1, 100))),
                    bid_price=Decimal(str(round(price * 0.9999, 2))),
                    ask_price=Decimal(str(round(price * 1.0001, 2))),
                )
                self.client.on_tick(tick)
                
                # 生成模拟深度
                bids = [OrderBookLevel(
                    price=Decimal(str(round(price * (1 - 0.0001 * i), 2))),
                    volume=Decimal(str(random.randint(10, 1000)))
                ) for i in range(1, 6)]
                asks = [OrderBookLevel(
                    price=Decimal(str(round(price * (1 + 0.0001 * i), 2))),
                    volume=Decimal(str(random.randint(10, 1000)))
                ) for i in range(1, 6)]
                
                orderbook = OrderBook(
                    timestamp=datetime.now(timezone.utc),
                    symbol=symbol,
                    bids=bids,
                    asks=asks,
                )
                self.client.on_depth(symbol, orderbook)
            
            await asyncio.sleep(1)
