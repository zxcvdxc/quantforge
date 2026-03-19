"""
数据源基类和工厂
"""
from abc import ABC, abstractmethod
from typing import List, Optional, AsyncIterator, Dict, Any
from datetime import datetime
import asyncio

from .types import KlineData, TickData, OrderBook, SymbolInfo, DataSource, MarketType
from .exceptions import DataSourceError


class BaseDataSource(ABC):
    """数据源基类"""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @abstractmethod
    async def connect(self) -> None:
        """建立连接"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        pass
    
    @abstractmethod
    async def get_kline(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[KlineData]:
        """获取K线数据"""
        pass
    
    @abstractmethod
    async def get_tick(
        self,
        symbol: str,
        limit: int = 100
    ) -> List[TickData]:
        """获取Tick数据"""
        pass
    
    @abstractmethod
    async def get_symbols(self, market_type: Optional[MarketType] = None) -> List[SymbolInfo]:
        """获取交易对列表"""
        pass
    
    async def subscribe_kline(
        self,
        symbol: str,
        interval: str
    ) -> AsyncIterator[KlineData]:
        """订阅K线数据流（需要WebSocket支持的数据源）"""
        raise NotImplementedError(f"{self.name} 不支持K线数据流订阅")
    
    async def subscribe_tick(
        self,
        symbol: str
    ) -> AsyncIterator[TickData]:
        """订阅Tick数据流（需要WebSocket支持的数据源）"""
        raise NotImplementedError(f"{self.name} 不支持Tick数据流订阅")
    
    async def subscribe_orderbook(
        self,
        symbol: str,
        depth: int = 20
    ) -> AsyncIterator[OrderBook]:
        """订阅订单簿数据流（需要WebSocket支持的数据源）"""
        raise NotImplementedError(f"{self.name} 不支持订单簿数据流订阅")


class DataSourceFactory:
    """数据源工厂"""
    
    _sources: Dict[DataSource, type] = {}
    
    @classmethod
    def register(cls, source_type: DataSource, source_class: type) -> None:
        """注册数据源"""
        cls._sources[source_type] = source_class
    
    @classmethod
    def create(cls, source_type: DataSource, config: Optional[Dict[str, Any]] = None) -> BaseDataSource:
        """创建数据源实例"""
        if source_type not in cls._sources:
            raise DataSourceError(f"未知的数据源类型: {source_type}")
        return cls._sources[source_type](config)
    
    @classmethod
    def available_sources(cls) -> List[DataSource]:
        """获取可用数据源列表"""
        return list(cls._sources.keys())
