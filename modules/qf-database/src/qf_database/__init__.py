"""
qf-database: QuantForge 数据库模块

提供MySQL、InfluxDB、Redis的统一管理接口
"""

from .models import Contract, Trade, Account, Kline, Tick
from .mysql_manager import MySQLManager
from .influxdb_manager import InfluxDBManager
from .redis_manager import RedisManager
from .database_manager import DatabaseManager, DatabaseConfig

__version__ = "0.1.0"
__all__ = [
    # 模型类
    "Contract",
    "Trade", 
    "Account",
    "Kline",
    "Tick",
    # 管理器类
    "MySQLManager",
    "InfluxDBManager",
    "RedisManager",
    "DatabaseManager",
    "DatabaseConfig",
]