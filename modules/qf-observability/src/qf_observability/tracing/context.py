"""
追踪上下文模块
提供跨服务的追踪上下文传递
"""

from typing import Optional, Dict, Any, Callable
from contextvars import ContextVar
from dataclasses import dataclass

from opentelemetry import trace, context
from opentelemetry.propagate import extract, inject, set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Set global propagator
set_global_textmap(TraceContextTextMapPropagator())

# Context variable for trace context
_trace_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar('trace_context', default=None)


@dataclass
class TraceContext:
    """追踪上下文"""
    trace_id: str
    span_id: str
    trace_flags: int = 1
    trace_state: Optional[str] = None
    
    @classmethod
    def from_span(cls, span: trace.Span) -> 'TraceContext':
        """从span创建上下文"""
        span_context = span.get_span_context()
        return cls(
            trace_id=format(span_context.trace_id, '032x'),
            span_id=format(span_context.span_id, '016x'),
            trace_flags=span_context.trace_flags,
            trace_state=str(span_context.trace_state) if span_context.trace_state else None,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'trace_id': self.trace_id,
            'span_id': self.span_id,
            'trace_flags': self.trace_flags,
            'trace_state': self.trace_state,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TraceContext':
        """从字典创建"""
        return cls(
            trace_id=data.get('trace_id', ''),
            span_id=data.get('span_id', ''),
            trace_flags=data.get('trace_flags', 1),
            trace_state=data.get('trace_state'),
        )


def get_current_context() -> Optional[TraceContext]:
    """获取当前追踪上下文"""
    ctx = _trace_context.get()
    if ctx:
        return TraceContext.from_dict(ctx)
    
    # Try to get from current span
    current_span = trace.get_current_span()
    if current_span:
        span_context = current_span.get_span_context()
        if span_context.is_valid:
            return TraceContext.from_span(current_span)
    
    return None


def set_current_context(trace_ctx: TraceContext):
    """设置当前追踪上下文"""
    _trace_context.set(trace_ctx.to_dict())


def get_trace_id() -> Optional[str]:
    """获取当前trace ID"""
    ctx = get_current_context()
    return ctx.trace_id if ctx else None


def get_span_id() -> Optional[str]:
    """获取当前span ID"""
    ctx = get_current_context()
    return ctx.span_id if ctx else None


def inject_context(carrier: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """将当前上下文注入到carrier"""
    if carrier is None:
        carrier = {}
    
    inject(carrier)
    return carrier


def extract_context(carrier: Dict[str, str]) -> context.Context:
    """从carrier提取上下文"""
    return extract(carrier)


def with_context(trace_ctx: TraceContext):
    """上下文装饰器"""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            token = _trace_context.set(trace_ctx.to_dict())
            try:
                return func(*args, **kwargs)
            finally:
                _trace_context.reset(token)
        return wrapper
    return decorator


class ContextPropagator:
    """上下文传播器"""
    
    @staticmethod
    def to_http_headers() -> Dict[str, str]:
        """转换为HTTP头"""
        headers = {}
        inject_context(headers)
        return headers
    
    @staticmethod
    def from_http_headers(headers: Dict[str, str]) -> context.Context:
        """从HTTP头提取上下文"""
        return extract_context(headers)
    
    @staticmethod
    def to_message_metadata() -> Dict[str, str]:
        """转换为消息元数据"""
        metadata = {}
        inject_context(metadata)
        return metadata
    
    @staticmethod
    def from_message_metadata(metadata: Dict[str, str]) -> context.Context:
        """从消息元数据提取上下文"""
        return extract_context(metadata)


class TraceContextManager:
    """追踪上下文管理器"""
    
    def __init__(self, trace_ctx: Optional[TraceContext] = None):
        self.trace_ctx = trace_ctx
        self.token = None
        self.previous_context = None
    
    def __enter__(self):
        if self.trace_ctx:
            self.previous_context = _trace_context.get()
            self.token = _trace_context.set(self.trace_ctx.to_dict())
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.token:
            _trace_context.reset(self.token)
            if self.previous_context:
                _trace_context.set(self.previous_context)


def create_child_context(parent_context: Optional[TraceContext] = None) -> TraceContext:
    """创建子上下文"""
    import uuid
    
    if parent_context:
        # Same trace, new span
        return TraceContext(
            trace_id=parent_context.trace_id,
            span_id=uuid.uuid4().hex[:16],
            trace_flags=parent_context.trace_flags,
            trace_state=parent_context.trace_state,
        )
    else:
        # New trace
        return TraceContext(
            trace_id=uuid.uuid4().hex[:32],
            span_id=uuid.uuid4().hex[:16],
        )


def propagate_context(func: Callable) -> Callable:
    """上下文传播装饰器"""
    def wrapper(*args, **kwargs):
        # Extract context from kwargs if present
        context_data = kwargs.pop('trace_context', None)
        
        if context_data:
            if isinstance(context_data, dict):
                trace_ctx = TraceContext.from_dict(context_data)
            else:
                trace_ctx = context_data
            
            with TraceContextManager(trace_ctx):
                return func(*args, **kwargs)
        
        return func(*args, **kwargs)
    
    return wrapper


# Backwards compatibility aliases
get_current_trace_id = get_trace_id
get_current_span_id = get_span_id
