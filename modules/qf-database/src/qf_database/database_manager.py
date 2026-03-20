"""数据库管理器 - 统一管理 MySQL + InfluxDB + Redis

性能优化特性:
- 统一连接池配置管理
- 批量操作API
- 健康检查和监控
- 性能统计
"""
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field
import time
import logging

from .mysql_manager import MySQLManager
from .influxdb_manager import InfluxDBManager
from .redis_manager import RedisManager
from .models import Contract, Trade, Account, Kline, Tick

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """数据库配置 - 优化版"""
    # MySQL配置
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "quantforge"
    mysql_pool_size: int = 20
    mysql_max_overflow: int = 30
    mysql_pool_recycle: int = 3600
    mysql_pool_timeout: int = 30
    
    # InfluxDB配置
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = ""
    influxdb_org: str = "quantforge"
    influxdb_bucket: str = "market_data"
    influxdb_batch_size: int = 5000
    influxdb_flush_interval: int = 1000
    influxdb_max_retries: int = 5
    influxdb_write_mode: str = "batch"  # batch, sync, async
    
    # Redis配置
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_max_connections: int = 100
    redis_socket_timeout: float = 5.0


class DatabaseManager:
    """
    统一数据库管理器 - 优化版
    
    整合MySQL、InfluxDB、Redis三大数据库，提供统一的量化交易数据管理接口
    
    优化特性:
    - 优化的连接池配置
    - 批量操作API
    - 健康检查和监控
    - 性能统计
    """
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        初始化数据库管理器
        
        Args:
            config: 数据库配置，若为None则使用默认配置
        """
        self.config = config or DatabaseConfig()
        
        # 初始化各管理器 - 使用优化配置
        self.mysql = MySQLManager(
            host=self.config.mysql_host,
            port=self.config.mysql_port,
            user=self.config.mysql_user,
            password=self.config.mysql_password,
            database=self.config.mysql_database,
            pool_size=self.config.mysql_pool_size,
            max_overflow=self.config.mysql_max_overflow,
            pool_recycle=self.config.mysql_pool_recycle,
            pool_timeout=self.config.mysql_pool_timeout
        )
        
        self.influxdb = InfluxDBManager(
            url=self.config.influxdb_url,
            token=self.config.influxdb_token,
            org=self.config.influxdb_org,
            bucket=self.config.influxdb_bucket,
            batch_size=self.config.influxdb_batch_size,
            flush_interval=self.config.influxdb_flush_interval,
            max_retries=self.config.influxdb_max_retries,
            write_mode=self.config.influxdb_write_mode
        )
        
        self.redis = RedisManager(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_db,
            password=self.config.redis_password,
            max_connections=self.config.redis_max_connections,
            socket_timeout=self.config.redis_socket_timeout
        )
        
        logger.info("DatabaseManager initialized with optimized configuration")
    
    def connect_all(self) -> Dict[str, bool]:
        """
        连接所有数据库
        
        Returns:
            各数据库连接状态字典
        """
        return {
            "mysql": self.mysql.connect(),
            "influxdb": self.influxdb.connect(),
            "redis": self.redis.connect()
        }
    
    def disconnect_all(self) -> None:
        """断开所有数据库连接"""
        self.mysql.disconnect()
        self.influxdb.disconnect()
        self.redis.disconnect()
    
    def check_health(self) -> Dict[str, Any]:
        """
        检查所有数据库健康状态 - 优化版
        
        Returns:
            健康状态字典
        """
        health = {
            "mysql": {"connected": False, "latency_ms": 0, "pool_status": {}},
            "influxdb": {"connected": False, "latency_ms": 0, "write_stats": {}},
            "redis": {"connected": False, "latency_ms": 0, "pool_status": {}},
            "overall": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # 检查MySQL
        try:
            connected, latency, error = self.mysql.health_check()
            health["mysql"]["connected"] = connected
            health["mysql"]["latency_ms"] = round(latency, 2)
            health["mysql"]["pool_status"] = self.mysql.get_pool_status()
            if error:
                health["mysql"]["error"] = error
        except Exception as e:
            health["mysql"]["error"] = str(e)
        
        # 检查InfluxDB
        try:
            connected, latency, error = self.influxdb.health_check()
            health["influxdb"]["connected"] = connected
            health["influxdb"]["latency_ms"] = round(latency, 2)
            health["influxdb"]["write_stats"] = self.influxdb.get_write_stats()
            if error:
                health["influxdb"]["error"] = error
        except Exception as e:
            health["influxdb"]["error"] = str(e)
        
        # 检查Redis
        try:
            connected, latency, error = self.redis.health_check()
            health["redis"]["connected"] = connected
            health["redis"]["latency_ms"] = round(latency, 2)
            health["redis"]["pool_status"] = self.redis.get_pool_status()
            health["redis"]["stats"] = self.redis.get_stats()
            if error:
                health["redis"]["error"] = error
        except Exception as e:
            health["redis"]["error"] = str(e)
        
        # 整体状态
        connected_count = sum([
            health["mysql"]["connected"],
            health["influxdb"]["connected"],
            health["redis"]["connected"]
        ])
        
        if connected_count == 3:
            health["overall"] = "healthy"
        elif connected_count >= 1:
            health["overall"] = "degraded"
        
        return health
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        获取性能统计信息
        
        Returns:
            性能统计字典
        """
        return {
            "mysql": {
                "pool_status": self.mysql.get_pool_status(),
                "connection_stats": self.mysql.connection_stats
            },
            "influxdb": {
                "write_stats": self.influxdb.get_write_stats()
            },
            "redis": {
                "pool_status": self.redis.get_pool_status(),
                "stats": self.redis.get_stats()
            }
        }
    
    # ==================== 快捷方法：合约管理 ====================
    
    def save_contract(self, contract: Contract) -> bool:
        """保存合约信息"""
        return self.mysql.save_contract(contract)
    
    def get_contract(self, symbol: str, exchange: str) -> Optional[Contract]:
        """获取合约信息"""
        return self.mysql.get_contract(symbol, exchange)
    
    def list_contracts(
        self,
        exchange: Optional[str] = None,
        contract_type: Optional[str] = None,
        status: str = "active"
    ) -> List[Contract]:
        """列出合约"""
        return self.mysql.list_contracts(exchange, contract_type, status)
    
    # ==================== 快捷方法：交易记录管理 ====================
    
    def save_trade(self, trade: Trade) -> bool:
        """保存交易记录"""
        return self.mysql.save_trade(trade)
    
    def get_trade(self, trade_id: int) -> Optional[Trade]:
        """获取交易记录"""
        return self.mysql.get_trade(trade_id)
    
    def query_trades(
        self,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Trade]:
        """查询交易记录"""
        return self.mysql.query_trades(
            account_id=account_id,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
    
    # ==================== 快捷方法：账户管理 ====================
    
    def save_account(self, account: Account) -> bool:
        """保存账户信息"""
        return self.mysql.save_account(account)
    
    def get_account(
        self,
        account_id: str,
        exchange: str,
        asset: str
    ) -> Optional[Account]:
        """获取账户信息"""
        return self.mysql.get_account(account_id, exchange, asset)
    
    def list_accounts(
        self,
        account_id: Optional[str] = None,
        exchange: Optional[str] = None
    ) -> List[Account]:
        """列出账户"""
        return self.mysql.list_accounts(account_id, exchange)
    
    # ==================== 快捷方法：K线数据管理 ====================
    
    def save_kline(self, kline: Kline, cache: bool = True) -> bool:
        """
        保存K线数据
        
        Args:
            kline: K线数据
            cache: 是否同时缓存到Redis
        """
        # 保存到InfluxDB
        success = self.influxdb.save_kline(kline)
        
        # 缓存到Redis
        if success and cache:
            self.redis.cache_kline(kline)
        
        return success
    
    def save_klines(self, klines: List[Kline], cache: bool = True) -> bool:
        """
        批量保存K线数据
        
        Args:
            klines: K线数据列表
            cache: 是否同时缓存最后一条到Redis
        """
        # 保存到InfluxDB
        success = self.influxdb.save_klines(klines)
        
        # 缓存最后一条到Redis
        if success and cache and klines:
            self.redis.cache_kline(klines[-1])
        
        return success
    
    def get_kline(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        use_cache: bool = True
    ) -> Optional[Kline]:
        """
        获取最新K线数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            interval: 时间间隔
            use_cache: 是否优先从缓存获取
        """
        # 优先从缓存获取
        if use_cache:
            cached = self.redis.get_cached_kline(symbol, exchange, interval)
            if cached:
                return cached
        
        # 从InfluxDB获取
        return self.influxdb.get_latest_kline(symbol, exchange, interval)
    
    def query_klines(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Kline]:
        """查询K线数据范围"""
        return self.influxdb.query_klines(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
    
    # ==================== 快捷方法：Tick数据管理 ====================
    
    def save_tick(self, tick: Tick, cache: bool = True) -> bool:
        """
        保存Tick数据
        
        Args:
            tick: Tick数据
            cache: 是否同时缓存到Redis
        """
        # 保存到InfluxDB
        success = self.influxdb.save_tick(tick)
        
        # 缓存到Redis
        if success and cache:
            self.redis.cache_tick(tick)
        
        return success
    
    def save_ticks(self, ticks: List[Tick], cache: bool = True) -> bool:
        """
        批量保存Tick数据
        
        Args:
            ticks: Tick数据列表
            cache: 是否同时缓存到Redis
        """
        # 保存到InfluxDB
        success = self.influxdb.save_ticks(ticks)
        
        # 缓存到Redis
        if success and cache:
            self.redis.cache_ticks_batch(ticks)
        
        return success
    
    def get_tick(
        self,
        symbol: str,
        exchange: str,
        use_cache: bool = True
    ) -> Optional[Tick]:
        """
        获取最新Tick数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            use_cache: 是否优先从缓存获取
        """
        # 优先从缓存获取
        if use_cache:
            cached = self.redis.get_cached_tick(symbol, exchange)
            if cached:
                return cached
        
        # 从InfluxDB获取
        return self.influxdb.get_latest_tick(symbol, exchange)
    
    def query_ticks(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 10000
    ) -> List[Tick]:
        """查询Tick数据范围"""
        return self.influxdb.query_ticks(
            symbol=symbol,
            exchange=exchange,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
    
    # ==================== 快捷方法：缓存管理 ====================
    
    def cache_ticker(
        self,
        symbol: str,
        exchange: str,
        ticker_data: Dict[str, Any],
        ttl: int = 10
    ) -> bool:
        """缓存Ticker数据"""
        return self.redis.cache_ticker(symbol, exchange, ticker_data, ttl)
    
    def get_cached_ticker(self, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
        """获取缓存的Ticker数据"""
        return self.redis.get_cached_ticker(symbol, exchange)
    
    def cache_orderbook(
        self,
        symbol: str,
        exchange: str,
        orderbook_data: Dict[str, Any],
        ttl: int = 5
    ) -> bool:
        """缓存OrderBook数据"""
        return self.redis.cache_orderbook(symbol, exchange, orderbook_data, ttl)
    
    def get_cached_orderbook(self, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
        """获取缓存的OrderBook数据"""
        return self.redis.get_cached_orderbook(symbol, exchange)
    
    # ==================== 初始化方法 ====================
    
    def init_mysql_tables(self) -> None:
        """初始化MySQL表结构"""
        self.mysql.create_tables()
    
    def init_influxdb_bucket(self) -> bool:
        """初始化InfluxDB存储桶"""
        return self.influxdb.ensure_bucket()
    
    def init_all(self) -> Dict[str, bool]:
        """
        初始化所有数据库
        
        Returns:
            初始化结果字典
        """
        return {
            "mysql_tables": self.init_mysql_tables() or True,  # create_tables返回None
            "influxdb_bucket": self.init_influxdb_bucket(),
            "redis_connection": self.redis.connect()
        }
    
    # ==================== 上下文管理器 ====================
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect_all()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect_all()
        return False