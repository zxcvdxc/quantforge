"""
Audit Module - 审计日志模块
提供交易操作记录、配置变更审计、权限变更记录等功能
"""

import json
import logging
import functools
from enum import Enum, auto
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Lock

from .exceptions import AuditLogError


class AuditEventType(Enum):
    """审计事件类型"""
    # 登录相关
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    SESSION_EXPIRED = "session_expired"
    
    # 交易相关
    ORDER_CREATED = "order_created"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_MODIFIED = "order_modified"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    
    # 配置相关
    CONFIG_READ = "config_read"
    CONFIG_UPDATED = "config_updated"
    CONFIG_DELETED = "config_deleted"
    
    # 用户相关
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_ROLE_CHANGED = "user_role_changed"
    
    # API密钥相关
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    API_KEY_DELETED = "api_key_deleted"
    API_KEY_USED = "api_key_used"
    
    # 权限相关
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    
    # 系统相关
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    SYSTEM_ERROR = "system_error"
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"
    
    # 数据相关
    DATA_EXPORTED = "data_exported"
    DATA_IMPORTED = "data_imported"
    DATA_DELETED = "data_deleted"


class AuditLevel(Enum):
    """审计级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """审计事件数据结构"""
    
    event_type: AuditEventType
    timestamp: datetime
    user_id: Optional[str] = None
    api_key_id: Optional[str] = None
    client_ip: Optional[str] = None
    resource_type: Optional[str] = None  # 资源类型 (order, config, user等)
    resource_id: Optional[str] = None    # 资源ID
    action: Optional[str] = None         # 动作描述
    old_value: Optional[Any] = None      # 变更前值
    new_value: Optional[Any] = None      # 变更后值
    status: str = "success"              # success, failure
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    level: AuditLevel = AuditLevel.INFO
    request_id: Optional[str] = None     # 请求追踪ID
    session_id: Optional[str] = None     # 会话ID
    
    def to_dict(self, mask_sensitive: bool = True) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "api_key_id": self.api_key_id,
            "client_ip": self.client_ip,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "old_value": self._serialize_value(self.old_value, mask_sensitive),
            "new_value": self._serialize_value(self.new_value, mask_sensitive),
            "status": self.status,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "level": self.level.value,
            "request_id": self.request_id,
            "session_id": self.session_id,
        }
        return data
    
    def to_json(self, mask_sensitive: bool = True) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(mask_sensitive), ensure_ascii=False, default=str)
    
    def _serialize_value(self, value: Any, mask_sensitive: bool) -> Any:
        """序列化值"""
        if value is None:
            return None
        
        if mask_sensitive and isinstance(value, dict):
            # 脱敏敏感字段
            from .masking import mask_sensitive_data, MaskingConfig
            return mask_sensitive_data(value, MaskingConfig(enabled=True))
        
        if isinstance(value, (dict, list)):
            return value
        
        return str(value)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEvent":
        """从字典创建事件"""
        return cls(
            event_type=AuditEventType(data["event_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            user_id=data.get("user_id"),
            api_key_id=data.get("api_key_id"),
            client_ip=data.get("client_ip"),
            resource_type=data.get("resource_type"),
            resource_id=data.get("resource_id"),
            action=data.get("action"),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            status=data.get("status", "success"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
            level=AuditLevel(data.get("level", "info")),
            request_id=data.get("request_id"),
            session_id=data.get("session_id"),
        )


class AuditLogger:
    """
    审计日志记录器
    
    支持多种输出方式：
    - 文件日志
    - 数据库存储
    - 远程日志服务
    - 内存缓冲 (用于批量写入)
    """
    
    def __init__(
        self,
        log_file: Optional[Path] = None,
        db_connection: Optional[Any] = None,
        buffer_size: int = 100,
        flush_interval: int = 60,
        enable_console: bool = False,
    ):
        self.log_file = log_file
        self.db_connection = db_connection
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.enable_console = enable_console
        
        # 内存缓冲
        self._buffer: Queue = Queue(maxsize=buffer_size)
        self._lock = Lock()
        
        # 初始化文件日志
        if log_file:
            self._file_handler = self._setup_file_handler(log_file)
        else:
            self._file_handler = None
        
        # 初始化控制台日志
        if enable_console:
            self._console_handler = logging.StreamHandler()
            self._console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "%(asctime)s - AUDIT - %(message)s"
            )
            self._console_handler.setFormatter(formatter)
        else:
            self._console_handler = None
        
        # 统计
        self._stats = {
            "total_events": 0,
            "buffered_events": 0,
            "written_events": 0,
            "error_count": 0,
        }
    
    def _setup_file_handler(self, log_file: Path) -> logging.Handler:
        """设置文件处理器"""
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(message)s"
        )
        handler.setFormatter(formatter)
        return handler
    
    def log(self, event: AuditEvent) -> bool:
        """
        记录审计事件
        
        Args:
            event: 审计事件
            
        Returns:
            是否成功
        """
        try:
            with self._lock:
                self._stats["total_events"] += 1
                
                # 写入文件
                if self._file_handler:
                    self._file_handler.emit(
                        logging.LogRecord(
                            name="audit",
                            level=logging.INFO,
                            pathname="",
                            lineno=0,
                            msg=event.to_json(mask_sensitive=True),
                            args=(),
                            exc_info=None,
                        )
                    )
                
                # 控制台输出
                if self._console_handler:
                    self._console_handler.emit(
                        logging.LogRecord(
                            name="audit",
                            level=logging.INFO,
                            pathname="",
                            lineno=0,
                            msg=event.to_json(mask_sensitive=True),
                            args=(),
                            exc_info=None,
                        )
                    )
                
                # 写入数据库 (如果配置了)
                if self.db_connection:
                    self._write_to_db(event)
                
                self._stats["written_events"] += 1
                return True
                
        except Exception as e:
            self._stats["error_count"] += 1
            # 审计日志失败不应影响主流程，只记录错误
            logging.error(f"Failed to write audit log: {e}")
            return False
    
    def _write_to_db(self, event: AuditEvent) -> None:
        """写入数据库"""
        # 这里需要根据实际的数据库连接实现
        # 示例使用简单的SQL插入
        if hasattr(self.db_connection, "execute"):
            try:
                sql = """
                    INSERT INTO audit_logs (
                        event_type, timestamp, user_id, api_key_id, client_ip,
                        resource_type, resource_id, action, old_value, new_value,
                        status, error_message, metadata, level, request_id, session_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                self.db_connection.execute(sql, (
                    event.event_type.value,
                    event.timestamp,
                    event.user_id,
                    event.api_key_id,
                    event.client_ip,
                    event.resource_type,
                    event.resource_id,
                    event.action,
                    json.dumps(event.old_value, default=str) if event.old_value else None,
                    json.dumps(event.new_value, default=str) if event.new_value else None,
                    event.status,
                    event.error_message,
                    json.dumps(event.metadata),
                    event.level.value,
                    event.request_id,
                    event.session_id,
                ))
            except Exception as e:
                raise AuditLogError(f"Database write failed: {e}")
    
    def query(
        self,
        event_type: Optional[AuditEventType] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """
        查询审计日志
        
        注意：文件日志需要实现解析逻辑，这里仅提供接口
        """
        events = []
        
        if self.db_connection:
            # 从数据库查询
            conditions = []
            params = []
            
            if event_type:
                conditions.append("event_type = ?")
                params.append(event_type.value)
            if user_id:
                conditions.append("user_id = ?")
                params.append(user_id)
            if start_time:
                conditions.append("timestamp >= ?")
                params.append(start_time)
            if end_time:
                conditions.append("timestamp <= ?")
                params.append(end_time)
            if resource_type:
                conditions.append("resource_type = ?")
                params.append(resource_type)
            if resource_id:
                conditions.append("resource_id = ?")
                params.append(resource_id)
            
            sql = "SELECT * FROM audit_logs"
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            try:
                cursor = self.db_connection.execute(sql, params)
                rows = cursor.fetchall()
                
                for row in rows:
                    events.append(self._row_to_event(row))
            except Exception as e:
                logging.error(f"Failed to query audit logs: {e}")
        
        elif self.log_file:
            # 从文件查询 (简单实现)
            events = self._query_from_file(
                event_type, user_id, start_time, end_time,
                resource_type, resource_id, limit
            )
        
        return events
    
    def _query_from_file(
        self,
        event_type: Optional[AuditEventType],
        user_id: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        resource_type: Optional[str],
        resource_id: Optional[str],
        limit: int,
    ) -> List[AuditEvent]:
        """从文件查询日志"""
        events = []
        
        if not self.log_file or not self.log_file.exists():
            return events
        
        try:
            with open(self.log_file, "r") as f:
                lines = f.readlines()
            
            # 从后向前读取 (最新的在前)
            for line in reversed(lines):
                if len(events) >= limit:
                    break
                
                try:
                    # 解析JSON
                    # 格式: "2024-01-01 12:00:00 - {json}"
                    json_start = line.find(" - ")
                    if json_start == -1:
                        continue
                    
                    json_str = line[json_start + 3:].strip()
                    data = json.loads(json_str)
                    event = AuditEvent.from_dict(data)
                    
                    # 过滤
                    if event_type and event.event_type != event_type:
                        continue
                    if user_id and event.user_id != user_id:
                        continue
                    if start_time and event.timestamp < start_time:
                        continue
                    if end_time and event.timestamp > end_time:
                        continue
                    if resource_type and event.resource_type != resource_type:
                        continue
                    if resource_id and event.resource_id != resource_id:
                        continue
                    
                    events.append(event)
                    
                except (json.JSONDecodeError, ValueError):
                    continue
                    
        except Exception as e:
            logging.error(f"Failed to read audit log file: {e}")
        
        return events
    
    def _row_to_event(self, row: Any) -> AuditEvent:
        """将数据库行转换为事件对象"""
        # 这里需要根据实际的数据库行结构实现
        return AuditEvent(
            event_type=AuditEventType(row["event_type"]),
            timestamp=row["timestamp"],
            user_id=row.get("user_id"),
            api_key_id=row.get("api_key_id"),
            client_ip=row.get("client_ip"),
            resource_type=row.get("resource_type"),
            resource_id=row.get("resource_id"),
            action=row.get("action"),
            old_value=json.loads(row["old_value"]) if row.get("old_value") else None,
            new_value=json.loads(row["new_value"]) if row.get("new_value") else None,
            status=row.get("status", "success"),
            error_message=row.get("error_message"),
            metadata=json.loads(row["metadata"]) if row.get("metadata") else {},
            level=AuditLevel(row.get("level", "info")),
            request_id=row.get("request_id"),
            session_id=row.get("session_id"),
        )
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()
    
    def close(self) -> None:
        """关闭日志记录器"""
        if self._file_handler:
            self._file_handler.close()


# 全局审计日志记录器实例
_global_audit_logger: Optional[AuditLogger] = None


def init_audit_logger(
    log_file: Optional[Path] = None,
    db_connection: Optional[Any] = None,
    **kwargs
) -> AuditLogger:
    """初始化全局审计日志记录器"""
    global _global_audit_logger
    _global_audit_logger = AuditLogger(
        log_file=log_file,
        db_connection=db_connection,
        **kwargs
    )
    return _global_audit_logger


def get_audit_logger() -> Optional[AuditLogger]:
    """获取全局审计日志记录器"""
    return _global_audit_logger


def audit_log(event: AuditEvent) -> bool:
    """
    记录审计事件 (便捷函数)
    
    Example:
        audit_log(AuditEvent(
            event_type=AuditEventType.ORDER_CREATED,
            timestamp=datetime.now(),
            user_id="user_123",
            resource_type="order",
            resource_id="order_456",
            new_value={"symbol": "BTC-USDT", "side": "buy", "quantity": 1.0},
        ))
    """
    logger = get_audit_logger()
    if logger:
        return logger.log(event)
    
    # 如果没有初始化，输出到标准日志
    logging.warning(f"Audit log not initialized: {event.to_json()}")
    return False


def audit_log_event(
    event_type: AuditEventType,
    user_id: Optional[str] = None,
    api_key_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    action: Optional[str] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    level: AuditLevel = AuditLevel.INFO,
    client_ip: Optional[str] = None,
    request_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> bool:
    """
    创建并记录审计事件 (便捷函数)
    
    Example:
        audit_log_event(
            event_type=AuditEventType.ORDER_CREATED,
            user_id="user_123",
            resource_type="order",
            resource_id="order_456",
            new_value={"symbol": "BTC-USDT", "side": "buy"},
        )
    """
    event = AuditEvent(
        event_type=event_type,
        timestamp=datetime.now(),
        user_id=user_id,
        api_key_id=api_key_id,
        client_ip=client_ip,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        status=status,
        error_message=error_message,
        metadata=metadata or {},
        level=level,
        request_id=request_id,
        session_id=session_id,
    )
    return audit_log(event)


# ============ 装饰器 ============

def audit_trail(
    event_type: AuditEventType,
    resource_type: Optional[str] = None,
    get_resource_id: Optional[Callable] = None,
    get_user_id: Optional[Callable] = None,
    log_args: bool = False,
    log_result: bool = False,
):
    """
    审计追踪装饰器
    
    自动记录函数调用审计日志
    
    Example:
        @audit_trail(
            event_type=AuditEventType.ORDER_CREATED,
            resource_type="order",
            get_resource_id=lambda result: result.order_id if result else None,
        )
        async def create_order(user_id: str, order_data: dict):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await _execute_and_log(
                func, args, kwargs, event_type, resource_type,
                get_resource_id, get_user_id, log_args, log_result
            )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return _execute_and_log(
                func, args, kwargs, event_type, resource_type,
                get_resource_id, get_user_id, log_args, log_result
            )
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def _execute_and_log(
    func: Callable,
    args: tuple,
    kwargs: dict,
    event_type: AuditEventType,
    resource_type: Optional[str],
    get_resource_id: Optional[Callable],
    get_user_id: Optional[Callable],
    log_args: bool,
    log_result: bool,
):
    """执行函数并记录审计日志"""
    import asyncio
    
    # 获取用户信息
    user_id = None
    if get_user_id:
        try:
            user_id = get_user_id(*args, **kwargs)
        except:
            pass
    
    # 尝试从参数中提取user_id
    if user_id is None:
        for arg in args:
            if isinstance(arg, str):
                user_id = arg
                break
        if user_id is None:
            user_id = kwargs.get("user_id")
    
    # 构建审计元数据
    metadata = {}
    if log_args:
        metadata["args"] = [str(arg) for arg in args]
        metadata["kwargs"] = {k: str(v) for k, v in kwargs.items()}
    
    # 执行函数
    error_message = None
    status = "success"
    result = None
    
    try:
        if asyncio.iscoroutinefunction(func):
            # 异步函数
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(func(*args, **kwargs))
        else:
            result = func(*args, **kwargs)
    except Exception as e:
        status = "failure"
        error_message = str(e)
        raise
    finally:
        # 获取资源ID
        resource_id = None
        if get_resource_id:
            try:
                resource_id = get_resource_id(result)
            except:
                pass
        
        # 构建新值
        new_value = None
        if log_result and result is not None:
            try:
                if hasattr(result, "to_dict"):
                    new_value = result.to_dict()
                elif hasattr(result, "__dict__"):
                    new_value = result.__dict__
                else:
                    new_value = {"result": str(result)}
            except:
                new_value = {"result": str(result)}
        
        # 记录审计日志
        audit_log_event(
            event_type=event_type,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            error_message=error_message,
            metadata=metadata,
            new_value=new_value,
        )
    
    return result


# 导入asyncio用于检测异步函数
import asyncio
