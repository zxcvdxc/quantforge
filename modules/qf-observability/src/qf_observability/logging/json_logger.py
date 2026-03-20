"""
结构化JSON日志模块
提供JSON格式日志、上下文传递和动态日志级别调整
"""

import logging
import logging.config
import sys
import threading
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional, List, Callable, Union
from functools import wraps

import structlog
from pythonjsonlogger import jsonlogger

# Context variables for trace propagation
_trace_id: ContextVar[str] = ContextVar('trace_id', default='')
_span_id: ContextVar[str] = ContextVar('span_id', default='')
_request_id: ContextVar[str] = ContextVar('request_id', default='')

# Thread-local storage for context
_local_context = threading.local()


class JSONLogFormatter(jsonlogger.JsonFormatter):
    """自定义JSON日志格式化器"""
    
    def __init__(self, fmt: Optional[str] = None, **kwargs):
        super().__init__(fmt, **kwargs)
        self._hostname = self._get_hostname()
    
    def _get_hostname(self) -> str:
        import socket
        try:
            return socket.gethostname()
        except:
            return 'unknown'
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]):
        super().add_fields(log_record, record, message_dict)
        
        # Add standard fields
        log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['hostname'] = self._hostname
        log_record['source'] = {
            'file': record.filename,
            'line': record.lineno,
            'function': record.funcName,
        }
        
        # Add trace context
        trace_id = _trace_id.get() or getattr(_local_context, 'trace_id', '')
        span_id = _span_id.get() or getattr(_local_context, 'span_id', '')
        request_id = _request_id.get() or getattr(_local_context, 'request_id', '')
        
        if trace_id:
            log_record['trace_id'] = trace_id
        if span_id:
            log_record['span_id'] = span_id
        if request_id:
            log_record['request_id'] = request_id


class JSONLogger:
    """结构化JSON日志记录器"""
    
    LEVELS = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }
    
    _instance: Optional['JSONLogger'] = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, name: str = 'quantforge', level: str = 'INFO'):
        if self._initialized:
            return
        
        self.name = name
        self.level = level
        self._loggers: Dict[str, logging.Logger] = {}
        self._processors: List[Callable] = []
        self._initialized = True
        
        self._configure()
    
    def _configure(self):
        """配置日志系统"""
        # Configure standard library logging
        formatter = JSONLogFormatter()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(self.LEVELS.get(self.level, logging.INFO))
        root_logger.handlers = [handler]
        
        # Configure structlog
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    def get_logger(self, name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
        """获取结构化日志记录器"""
        logger_name = name or self.name
        return structlog.get_logger(logger_name)
    
    def set_level(self, level: str):
        """动态设置日志级别"""
        self.level = level.upper()
        logging.getLogger().setLevel(self.LEVELS.get(self.level, logging.INFO))
    
    def add_processor(self, processor: Callable):
        """添加日志处理器"""
        self._processors.append(processor)
    
    def bind_context(self, **kwargs) -> structlog.stdlib.BoundLogger:
        """绑定上下文到日志记录器"""
        logger = self.get_logger()
        return logger.bind(**kwargs)


# Global logger instance
_logger_instance: Optional[JSONLogger] = None


def configure_logging(
    name: str = 'quantforge',
    level: str = 'INFO',
    log_file: Optional[str] = None,
    json_output: bool = True,
) -> JSONLogger:
    """配置结构化日志"""
    global _logger_instance
    _logger_instance = JSONLogger(name, level)
    
    if log_file:
        file_handler = logging.FileHandler(log_file)
        if json_output:
            file_handler.setFormatter(JSONLogFormatter())
        logging.getLogger().addHandler(file_handler)
    
    return _logger_instance


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """获取日志记录器"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = JSONLogger()
    return _logger_instance.get_logger(name)


def set_log_level(level: str):
    """动态设置日志级别"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = JSONLogger()
    _logger_instance.set_level(level)


def get_context() -> Dict[str, str]:
    """获取当前上下文"""
    return {
        'trace_id': _trace_id.get() or getattr(_local_context, 'trace_id', ''),
        'span_id': _span_id.get() or getattr(_local_context, 'span_id', ''),
        'request_id': _request_id.get() or getattr(_local_context, 'request_id', ''),
    }


def set_context(
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    request_id: Optional[str] = None,
):
    """设置上下文"""
    if trace_id:
        _trace_id.set(trace_id)
        _local_context.trace_id = trace_id
    if span_id:
        _span_id.set(span_id)
        _local_context.span_id = span_id
    if request_id:
        _request_id.set(request_id)
        _local_context.request_id = request_id


def clear_context():
    """清除上下文"""
    _trace_id.set('')
    _span_id.set('')
    _request_id.set('')
    _local_context.trace_id = ''
    _local_context.span_id = ''
    _local_context.request_id = ''


def generate_trace_id() -> str:
    """生成新的trace ID"""
    return uuid.uuid4().hex[:32]


def generate_span_id() -> str:
    """生成新的span ID"""
    return uuid.uuid4().hex[:16]


def log_with_context(
    level: str,
    message: str,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    **kwargs
):
    """带上下文的日志记录"""
    ctx = get_context()
    
    if trace_id:
        ctx['trace_id'] = trace_id
    if span_id:
        ctx['span_id'] = span_id
    
    logger = get_logger()
    logger_with_ctx = logger.bind(**ctx, **kwargs)
    
    log_method = getattr(logger_with_ctx, level.lower(), logger_with_ctx.info)
    log_method(message)


class ContextManager:
    """上下文管理器"""
    
    def __init__(self, **kwargs):
        self.context = kwargs
        self.previous_context = {}
    
    def __enter__(self):
        self.previous_context = get_context()
        set_context(**self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore previous context
        for key in self.context:
            if key in self.previous_context:
                setattr(_local_context, key, self.previous_context[key])
            else:
                setattr(_local_context, key, '')


def with_context(**context_kwargs):
    """装饰器：为函数添加上下文"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with ContextManager(**context_kwargs):
                return func(*args, **kwargs)
        return wrapper
    return decorator
