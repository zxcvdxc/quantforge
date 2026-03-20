"""
Secure Database Manager - 安全数据库管理器

集成安全模块:
- 数据库连接字符串加密
- 敏感操作审计
- 日志脱敏
"""
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field
import time
import logging

try:
    from qf_security import (
        SecureConfig,
        mask_connection_string,
        mask_password,
        audit_log_event,
        AuditEventType,
        secure_logger,
    )
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False

# 使用安全logger或标准logger
if SECURITY_AVAILABLE:
    logger = secure_logger("qf_database")
else:
    logger = logging.getLogger(__name__)

from .mysql_manager import MySQLManager
from .influxdb_manager import InfluxDBManager
from .redis_manager import RedisManager
from .models import Contract, Trade, Account, Kline, Tick


@dataclass
class SecureDatabaseConfig:
    """安全数据库配置 - 支持加密字段"""
    
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
    influxdb_write_mode: str = "batch"
    
    # Redis配置
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_max_connections: int = 100
    redis_socket_timeout: float = 5.0
    
    @classmethod
    def from_encrypted_config(cls, secure_config: Optional[Any] = None) -> "SecureDatabaseConfig":
        """
        从加密配置加载
        
        Args:
            secure_config: SecureConfig实例，若为None则创建新实例
        """
        if not SECURITY_AVAILABLE:
            return cls()
        
        if secure_config is None:
            secure_config = SecureConfig()
        
        try:
            # 尝试加载加密配置
            full_config = secure_config.load_encrypted_config()
            db_config = full_config.get("database", {})
            
            # 构建配置
            return cls(
                # MySQL
                mysql_host=db_config.get("mysql", {}).get("host", "localhost"),
                mysql_port=db_config.get("mysql", {}).get("port", 3306),
                mysql_user=db_config.get("mysql", {}).get("user", "root"),
                mysql_password=db_config.get("mysql", {}).get("password", ""),
                mysql_database=db_config.get("mysql", {}).get("database", "quantforge"),
                mysql_pool_size=db_config.get("mysql", {}).get("pool_size", 20),
                mysql_max_overflow=db_config.get("mysql", {}).get("max_overflow", 30),
                
                # InfluxDB
                influxdb_url=db_config.get("influxdb", {}).get("url", "http://localhost:8086"),
                influxdb_token=db_config.get("influxdb", {}).get("token", ""),
                influxdb_org=db_config.get("influxdb", {}).get("org", "quantforge"),
                influxdb_bucket=db_config.get("influxdb", {}).get("bucket", "market_data"),
                
                # Redis
                redis_host=db_config.get("redis", {}).get("host", "localhost"),
                redis_port=db_config.get("redis", {}).get("port", 6379),
                redis_db=db_config.get("redis", {}).get("db", 0),
                redis_password=db_config.get("redis", {}).get("password"),
            )
        except Exception as e:
            logger.warning(f"Failed to load encrypted database config: {e}")
            return cls()
    
    def get_mysql_connection_string(self) -> str:
        """获取MySQL连接字符串（脱敏）"""
        conn_str = f"mysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        return mask_connection_string(conn_str) if SECURITY_AVAILABLE else conn_str
    
    def get_influxdb_connection_string(self) -> str:
        """获取InfluxDB连接字符串（脱敏）"""
        conn_str = f"{self.influxdb_url}?token={self.influxdb_token}"
        # 脱敏token
        if SECURITY_AVAILABLE and self.influxdb_token:
            return conn_str.replace(self.influxdb_token, "****")
        return conn_str


class SecureDatabaseManager:
    """
    安全数据库管理器
    
    特性:
    - 加密配置自动解密
    - 连接字符串脱敏
    - 敏感操作审计
    - 自动重试和错误处理
    """
    
    def __init__(self, config: Optional[SecureDatabaseConfig] = None):
        """
        初始化安全数据库管理器
        
        Args:
            config: 数据库配置，若为None则尝试从加密配置加载
        """
        # 尝试从加密配置加载
        if config is None and SECURITY_AVAILABLE:
            config = SecureDatabaseConfig.from_encrypted_config()
        
        self.config = config or SecureDatabaseConfig()
        
        # 记录脱敏的连接字符串
        logger.info(f"MySQL connection: {self.config.get_mysql_connection_string()}")
        
        # 初始化各管理器
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
        
        # 审计日志
        if SECURITY_AVAILABLE:
            audit_log_event(
                event_type=AuditEventType.SYSTEM_STATUS,
                resource_type="database",
                resource_id="manager",
                action="init",
                status="success",
                metadata={
                    "mysql_host": self.config.mysql_host,
                    "influxdb_url": mask_connection_string(self.config.influxdb_url) if SECURITY_AVAILABLE else self.config.influxdb_url,
                }
            )
        
        logger.info("SecureDatabaseManager initialized")
    
    def connect_all(self) -> Dict[str, bool]:
        """连接所有数据库"""
        results = {
            "mysql": self.mysql.connect(),
            "influxdb": self.influxdb.connect(),
            "redis": self.redis.connect()
        }
        
        # 审计日志
        if SECURITY_AVAILABLE:
            audit_log_event(
                event_type=AuditEventType.SYSTEM_STATUS,
                resource_type="database",
                resource_id="manager",
                action="connect_all",
                status="success" if all(results.values()) else "partial",
                metadata=results,
            )
        
        return results
    
    def disconnect_all(self) -> None:
        """断开所有数据库连接"""
        self.mysql.disconnect()
        self.influxdb.disconnect()
        self.redis.disconnect()
        
        logger.info("All database connections closed")
    
    def check_health(self) -> Dict[str, Any]:
        """检查所有数据库健康状态"""
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
    
    # ============ 交易操作（带审计） ============
    
    def save_trade(self, trade: Trade, user_id: Optional[str] = None) -> bool:
        """
        保存交易记录（带审计）
        
        Args:
            trade: 交易记录
            user_id: 操作用户ID
        """
        result = self.mysql.save_trade(trade)
        
        if result and SECURITY_AVAILABLE:
            audit_log_event(
                event_type=AuditEventType.ORDER_FILLED,
                user_id=user_id,
                resource_type="trade",
                resource_id=str(trade.id) if hasattr(trade, 'id') else None,
                new_value={
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "quantity": str(trade.quantity),
                    "price": str(trade.price),
                },
            )
        
        return result
    
    def save_account(self, account: Account, user_id: Optional[str] = None) -> bool:
        """
        保存账户信息（带审计）
        
        Args:
            account: 账户信息
            user_id: 操作用户ID
        """
        result = self.mysql.save_account(account)
        
        if result and SECURITY_AVAILABLE:
            audit_log_event(
                event_type=AuditEventType.DATA_WRITE,
                user_id=user_id,
                resource_type="account",
                resource_id=account.account_id,
                new_value={
                    "exchange": account.exchange,
                    "balance": str(account.balance) if hasattr(account, 'balance') else None,
                },
            )
        
        return result
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect_all()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect_all()
        return False


# 向后兼容
DatabaseConfig = SecureDatabaseConfig
DatabaseManager = SecureDatabaseManager
