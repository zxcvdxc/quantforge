"""
数据采集器主类
统一封装多种数据源的采集接口
"""
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any, Union, AsyncIterator
import pandas as pd

from .base import BaseDataSource, DataSourceFactory
from .types import KlineData, TickData, OrderBook, SymbolInfo, DataSource, MarketType, Exchange
from .exchanges import OKXClient, BinanceClient, TushareClient, AKShareClient, CTPClient
from .exceptions import DataSourceError, DataCollectionError


# 注册数据源
DataSourceFactory.register(DataSource.OKX, OKXClient)
DataSourceFactory.register(DataSource.BINANCE, BinanceClient)
DataSourceFactory.register(DataSource.TUSHARE, TushareClient)
DataSourceFactory.register(DataSource.AKSHARE, AKShareClient)
DataSourceFactory.register(DataSource.CTP, CTPClient)


class DataCollector:
    """数据采集器
    
    统一封装多种数据源的采集接口，支持：
    - A股数据: Tushare, AKShare
    - 期货数据: CTP
    - 数字货币: OKX, Binance
    
    Example:
        ```python
        collector = DataCollector()
        
        # 获取数字货币K线
        data = await collector.get_kline(
            symbol="BTC-USDT",
            interval="1m",
            source=DataSource.OKX
        )
        
        # 获取A股数据
        df = await collector.get_kline_df(
            symbol="000001.SZ",
            interval="1d",
            source=DataSource.AKSHARE
        )
        ```
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化数据采集器
        
        Args:
            config: 配置字典，格式为:
                {
                    "okx": {"api_key": "...", "api_secret": "..."},
                    "binance": {"api_key": "...", "api_secret": "..."},
                    "tushare": {"token": "..."},
                    "ctp": {"front_address": "...", "broker_id": "..."},
                }
        """
        self.config = config or {}
        self._sources: Dict[DataSource, BaseDataSource] = {}
        self._default_source: Optional[DataSource] = None
    
    def _get_source(self, source: Optional[DataSource] = None) -> BaseDataSource:
        """获取或创建数据源实例"""
        if source is None:
            if self._default_source is None:
                raise DataCollectionError("No default source configured")
            source = self._default_source
        
        if source not in self._sources:
            source_config = self.config.get(source.value, {})
            self._sources[source] = DataSourceFactory.create(source, source_config)
        
        return self._sources[source]
    
    def set_default_source(self, source: DataSource) -> None:
        """设置默认数据源"""
        self._default_source = source
    
    async def connect(self, source: Optional[DataSource] = None) -> None:
        """连接数据源"""
        src = self._get_source(source)
        await src.connect()
    
    async def disconnect(self, source: Optional[DataSource] = None) -> None:
        """断开数据源连接
        
        Args:
            source: 指定数据源，None表示断开所有
        """
        if source:
            if source in self._sources:
                await self._sources[source].disconnect()
        else:
            for src in self._sources.values():
                await src.disconnect()
    
    async def get_kline(
        self,
        symbol: str,
        interval: str = "1d",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
        source: Optional[DataSource] = None
    ) -> List[KlineData]:
        """获取K线数据
        
        Args:
            symbol: 标的代码
            interval: K线周期，如 "1m", "5m", "1h", "1d"
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回条数限制
            source: 数据源，None使用默认数据源
        
        Returns:
            K线数据列表
        """
        src = self._get_source(source)
        await src.connect()
        return await src.get_kline(symbol, interval, start_time, end_time, limit)
    
    async def get_kline_df(
        self,
        symbol: str,
        interval: str = "1d",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
        source: Optional[DataSource] = None
    ) -> pd.DataFrame:
        """获取K线数据并转换为DataFrame
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        klines = await self.get_kline(symbol, interval, start_time, end_time, limit, source)
        
        if not klines:
            return pd.DataFrame()
        
        data = [k.to_dict() for k in klines]
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df
    
    async def get_tick(
        self,
        symbol: str,
        limit: int = 100,
        source: Optional[DataSource] = None
    ) -> List[TickData]:
        """获取Tick数据
        
        Args:
            symbol: 标的代码
            limit: 返回条数限制
            source: 数据源
        
        Returns:
            Tick数据列表
        """
        src = self._get_source(source)
        await src.connect()
        return await src.get_tick(symbol, limit)
    
    async def get_tick_df(
        self,
        symbol: str,
        limit: int = 100,
        source: Optional[DataSource] = None
    ) -> pd.DataFrame:
        """获取Tick数据并转换为DataFrame"""
        ticks = await self.get_tick(symbol, limit, source)
        
        if not ticks:
            return pd.DataFrame()
        
        data = [t.to_dict() for t in ticks]
        df = pd.DataFrame(data)
        if not df.empty:
            df.set_index("timestamp", inplace=True)
        return df
    
    async def get_orderbook(
        self,
        symbol: str,
        depth: int = 20,
        source: Optional[DataSource] = None
    ) -> OrderBook:
        """获取订单簿
        
        Args:
            symbol: 标的代码
            depth: 深度档位数
            source: 数据源
        
        Returns:
            OrderBook对象
        """
        src = self._get_source(source)
        await src.connect()
        
        if hasattr(src, "get_orderbook"):
            return await src.get_orderbook(symbol, depth)
        else:
            raise DataSourceError(f"{src.name} does not support orderbook query")
    
    async def get_symbols(
        self,
        market_type: Optional[MarketType] = None,
        source: Optional[DataSource] = None
    ) -> List[SymbolInfo]:
        """获取交易对/股票列表
        
        Args:
            market_type: 市场类型过滤
            source: 数据源
        
        Returns:
            SymbolInfo列表
        """
        src = self._get_source(source)
        await src.connect()
        return await src.get_symbols(market_type)
    
    async def subscribe_kline(
        self,
        symbol: str,
        interval: str,
        source: Optional[DataSource] = None
    ) -> AsyncIterator[KlineData]:
        """订阅K线数据流（WebSocket）
        
        Args:
            symbol: 标的代码
            interval: K线周期
            source: 数据源
        
        Yields:
            KlineData对象
        """
        src = self._get_source(source)
        await src.connect()
        
        async for kline in src.subscribe_kline(symbol, interval):
            yield kline
    
    async def subscribe_tick(
        self,
        symbol: str,
        source: Optional[DataSource] = None
    ) -> AsyncIterator[TickData]:
        """订阅Tick数据流（WebSocket）
        
        Args:
            symbol: 标的代码
            source: 数据源
        
        Yields:
            TickData对象
        """
        src = self._get_source(source)
        await src.connect()
        
        async for tick in src.subscribe_tick(symbol):
            yield tick
    
    async def subscribe_orderbook(
        self,
        symbol: str,
        depth: int = 20,
        source: Optional[DataSource] = None
    ) -> AsyncIterator[OrderBook]:
        """订阅订单簿数据流（WebSocket）
        
        Args:
            symbol: 标的代码
            depth: 深度档位数
            source: 数据源
        
        Yields:
            OrderBook对象
        """
        src = self._get_source(source)
        await src.connect()
        
        async for orderbook in src.subscribe_orderbook(symbol, depth):
            yield orderbook
    
    def get_available_sources(self) -> List[DataSource]:
        """获取可用数据源列表"""
        return DataSourceFactory.available_sources()
    
    async def multi_source_kline(
        self,
        symbol: str,
        sources: List[DataSource],
        interval: str = "1m",
        limit: int = 100
    ) -> Dict[DataSource, List[KlineData]]:
        """从多个数据源获取K线数据进行对比
        
        Args:
            symbol: 标的代码
            sources: 数据源列表
            interval: K线周期
            limit: 返回条数
        
        Returns:
            各数据源的K线数据字典
        """
        results = {}
        
        async def fetch_from_source(source: DataSource):
            try:
                src = self._get_source(source)
                await src.connect()
                data = await src.get_kline(symbol, interval, limit=limit)
                results[source] = data
            except Exception as e:
                results[source] = []
        
        await asyncio.gather(*[fetch_from_source(s) for s in sources])
        return results


# 便捷函数
async def get_crypto_kline(
    symbol: str,
    interval: str = "1h",
    limit: int = 1000,
    exchange: str = "okx"
) -> pd.DataFrame:
    """获取数字货币K线数据便捷函数
    
    Args:
        symbol: 交易对，如 "BTC-USDT"
        interval: K线周期
        limit: 返回条数
        exchange: 交易所，"okx" 或 "binance"
    
    Returns:
        DataFrame
    """
    source = DataSource.OKX if exchange.lower() == "okx" else DataSource.BINANCE
    collector = DataCollector()
    return await collector.get_kline_df(symbol, interval, limit=limit, source=source)


async def get_stock_kline(
    symbol: str,
    interval: str = "1d",
    limit: int = 1000,
    source: str = "akshare"
) -> pd.DataFrame:
    """获取A股K线数据便捷函数
    
    Args:
        symbol: 股票代码，如 "000001.SZ" 或 "000001"
        interval: K线周期
        limit: 返回条数
        source: 数据源，"akshare" 或 "tushare"
    
    Returns:
        DataFrame
    """
    data_source = DataSource.AKSHARE if source.lower() == "akshare" else DataSource.TUSHARE
    collector = DataCollector()
    return await collector.get_kline_df(symbol, interval, limit=limit, source=data_source)
