"""qf-data 基础模块

提供数据源基类和数据收集器，支持多种交易所和数据源。

性能优化特性:
- aiohttp session 复用
- 连接池管理
- 异步请求优化
"""
from abc import ABC, abstractmethod
from typing import List, Optional, AsyncIterator, Dict, Any
from datetime import datetime
import asyncio
import logging

import aiohttp

from .types import KlineData, TickData, OrderBook, SymbolInfo, DataSource, MarketType
from .exceptions import DataSourceError, ConnectionError

logger = logging.getLogger(__name__)


class BaseDataSource(ABC):
    """数据源基类 - 优化版
    
    所有交易所客户端的基类，提供统一的接口和连接管理。
    
    优化特性:
    - aiohttp session 复用
    - 连接池自动管理
    - 请求超时控制
    - 自动重试机制
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        初始化数据源
        
        Args:
            name: 数据源名称
            config: 配置字典，包含 api_key, api_secret, timeout 等
        """
        self.name = name
        self.config = config or {}
        self._connected = False
        
        # 配置参数
        self.timeout = self.config.get("timeout", 30)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 1.0)
        
        # aiohttp session - 延迟初始化
        self._session: Optional[aiohttp.ClientSession] = None
        
        # 请求统计
        self._stats = {
            "requests": 0,
            "errors": 0,
            "retries": 0
        }
    
    @property
    def session(self) -> aiohttp.ClientSession:
        """获取或创建aiohttp session - 延迟初始化"""
        if self._session is None or self._session.closed:
            # 创建带连接池的session
            connector = aiohttp.TCPConnector(
                limit=100,  # 总连接数限制
                limit_per_host=30,  # 每个主机的连接数限制
                enable_cleanup_closed=True,  # 清理关闭的连接
                force_close=False,  # 保持连接
                ttl_dns_cache=300,  # DNS缓存时间
                use_dns_cache=True,  # 启用DNS缓存
            )
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
        return self._session
    
    @session.setter
    def session(self, value: Optional[aiohttp.ClientSession]) -> None:
        """设置session（用于兼容性）"""
        self._session = value
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
    
    @property
    def stats(self) -> Dict[str, int]:
        """获取请求统计信息"""
        return self._stats.copy()
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {"requests": 0, "errors": 0, "retries": 0}
    
    async def connect(self) -> None:
        """
        建立连接
        
        初始化aiohttp session并测试连接
        """
        if not self._connected:
            # 触发session初始化
            _ = self.session
            self._connected = True
            logger.debug(f"{self.name} connected")
    
    async def disconnect(self) -> None:
        """
        断开连接
        
        关闭aiohttp session
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        self._connected = False
        logger.debug(f"{self.name} disconnected")
    
    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        带重试机制的HTTP请求
        
        Args:
            method: HTTP方法
            url: 请求URL
            **kwargs: 传递给aiohttp的请求参数
            
        Returns:
            响应JSON数据
            
        Raises:
            ConnectionError: 连接失败
            DataSourceError: 数据源错误
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                self._stats["requests"] += 1
                
                async with self.session.request(method, url, **kwargs) as response:
                    response.raise_for_status()
                    return await response.json()
                    
            except aiohttp.ClientError as e:
                self._stats["errors"] += 1
                last_error = e
                logger.warning(
                    f"{self.name} request failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                
                if attempt < self.max_retries - 1:
                    self._stats["retries"] += 1
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))  # 指数退避
                    
        raise ConnectionError(
            f"{self.name} request failed after {self.max_retries} retries: {last_error}"
        )
    
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
