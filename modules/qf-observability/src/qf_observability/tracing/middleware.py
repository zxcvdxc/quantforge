"""
追踪中间件模块
提供追踪中间件和装饰器
"""

from typing import Optional, Dict, Any, Callable
from functools import wraps

from opentelemetry import trace
from opentelemetry.propagate import extract, inject, set_global_textmap
from opentelemetry.propagators.textmap import TextMapPropagator

from .opentelemetry import (
    SpanContext,
    get_current_span,
    add_span_attribute,
    add_span_event,
    get_trace_id,
    get_span_id,
)


class TracingMiddleware:
    """追踪中间件基类"""
    
    def __init__(
        self,
        service_name: str = 'quantforge',
        capture_headers: bool = True,
        capture_body: bool = False,
    ):
        self.service_name = service_name
        self.capture_headers = capture_headers
        self.capture_body = capture_body
    
    def start_request_span(
        self,
        operation: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> SpanContext:
        """开始请求span"""
        attrs = attributes or {}
        attrs['service.name'] = self.service_name
        attrs['operation'] = operation
        
        return SpanContext(
            name=f"{self.service_name}.{operation}",
            kind=trace.SpanKind.SERVER,
            attributes=attrs,
        )
    
    def end_request_span(self, span_context: SpanContext, error: Optional[Exception] = None):
        """结束请求span"""
        if error:
            from .opentelemetry import record_span_exception
            record_span_exception(error)


class HTTPTracingMiddleware(TracingMiddleware):
    """HTTP追踪中间件"""
    
    def process_request(self, request) -> SpanContext:
        """处理请求"""
        # Extract trace context from headers
        carrier = dict(request.headers) if hasattr(request, 'headers') else {}
        context = extract(carrier)
        
        # Build attributes
        attributes = {
            'http.method': getattr(request, 'method', 'UNKNOWN'),
            'http.url': getattr(request, 'url', ''),
            'http.host': getattr(request, 'host', ''),
            'http.scheme': getattr(request, 'scheme', 'http'),
        }
        
        if self.capture_headers:
            for key, value in carrier.items():
                if key.lower().startswith('x-'):
                    attributes[f'http.header.{key}'] = value
        
        operation = f"{request.method}_{request.url.path}" if hasattr(request, 'url') else 'unknown'
        
        span_context = SpanContext(
            name=f"HTTP {request.method} {getattr(request.url, 'path', '')}",
            kind=trace.SpanKind.SERVER,
            attributes=attributes,
        )
        
        # Store span in request
        request.span_context = span_context
        
        return span_context
    
    def process_response(self, request, response):
        """处理响应"""
        span = get_current_span()
        if span:
            status_code = getattr(response, 'status_code', 0)
            add_span_attribute('http.status_code', status_code)
            
            if status_code >= 400:
                add_span_attribute('error', True)
    
    def process_exception(self, request, exception):
        """处理异常"""
        from .opentelemetry import record_span_exception
        record_span_exception(exception)


class DatabaseTracingMiddleware(TracingMiddleware):
    """数据库追踪中间件"""
    
    def trace_query(self, operation: str, query: str, parameters: Optional[Dict] = None):
        """追踪查询"""
        attributes = {
            'db.operation': operation,
            'db.statement': query[:1000],  # Limit query length
        }
        
        if parameters and self.capture_body:
            # Sanitize parameters
            safe_params = {k: '?' for k in parameters.keys()}
            attributes['db.parameters'] = str(safe_params)
        
        return SpanContext(
            name=f"DB {operation}",
            kind=trace.SpanKind.CLIENT,
            attributes=attributes,
        )


class MessageQueueTracingMiddleware(TracingMiddleware):
    """消息队列追踪中间件"""
    
    def trace_publish(self, topic: str, message_size: int) -> SpanContext:
        """追踪消息发布"""
        return SpanContext(
            name=f"MQ PUBLISH {topic}",
            kind=trace.SpanKind.PRODUCER,
            attributes={
                'mq.topic': topic,
                'mq.message_size': message_size,
                'mq.operation': 'publish',
            },
        )
    
    def trace_consume(self, topic: str, message_id: str) -> SpanContext:
        """追踪消息消费"""
        return SpanContext(
            name=f"MQ CONSUME {topic}",
            kind=trace.SpanKind.CONSUMER,
            attributes={
                'mq.topic': topic,
                'mq.message_id': message_id,
                'mq.operation': 'consume',
            },
        )


def trace_function(
    name: Optional[str] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
):
    """函数追踪装饰器"""
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__
        attrs = attributes or {}
        attrs['function.name'] = func.__name__
        attrs['function.module'] = func.__module__
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            with SpanContext(
                name=span_name,
                kind=kind,
                attributes=attrs,
            ) as span:
                # Add args info
                if args:
                    add_span_attribute('function.args_count', len(args))
                if kwargs:
                    add_span_attribute('function.kwargs_keys', list(kwargs.keys()))
                
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


def trace_async_function(
    name: Optional[str] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
):
    """异步函数追踪装饰器"""
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__
        attrs = attributes or {}
        attrs['function.name'] = func.__name__
        attrs['function.module'] = func.__module__
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with SpanContext(
                name=span_name,
                kind=kind,
                attributes=attrs,
            ) as span:
                if args:
                    add_span_attribute('function.args_count', len(args))
                if kwargs:
                    add_span_attribute('function.kwargs_keys', list(kwargs.keys()))
                
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def trace_class_methods(exclude: Optional[list] = None):
    """类方法追踪装饰器"""
    exclude_list = exclude or ['__init__', '__str__', '__repr__']
    
    def decorator(cls):
        for attr_name in dir(cls):
            if attr_name.startswith('_') or attr_name in exclude_list:
                continue
            
            attr = getattr(cls, attr_name)
            if callable(attr):
                setattr(
                    cls,
                    attr_name,
                    trace_function(name=f"{cls.__name__}.{attr_name}")(attr)
                )
        
        return cls
    return decorator
