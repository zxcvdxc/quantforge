"""
OpenTelemetry分布式追踪模块
提供分布式追踪功能
"""

import os
from typing import Optional, Dict, Any, Callable
from contextvars import ContextVar

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider as OTelTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


# Context variables
_current_span: ContextVar[Optional[trace.Span]] = ContextVar('current_span', default=None)


class TracerProvider:
    """追踪器提供器"""
    
    _instance: Optional['TracerProvider'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._provider: Optional[OTelTracerProvider] = None
        self._tracer: Optional[trace.Tracer] = None
        self._service_name = 'quantforge'
        self._service_version = '1.0.0'
        self._initialized = False
    
    def configure(
        self,
        service_name: str = 'quantforge',
        service_version: str = '1.0.0',
        otlp_endpoint: Optional[str] = None,
        otlp_headers: Optional[Dict[str, str]] = None,
        console_export: bool = False,
        sampling_rate: float = 1.0,
    ):
        """配置追踪器"""
        self._service_name = service_name
        self._service_version = service_version
        
        # Create resource
        resource = Resource.create({
            'service.name': service_name,
            'service.version': service_version,
            'service.instance.id': os.uname().nodename if hasattr(os, 'uname') else 'unknown',
        })
        
        # Create provider
        self._provider = OTelTracerProvider(
            resource=resource,
            sampler=trace.sampling.TraceIdRatioBased(sampling_rate),
        )
        
        # Add exporters
        if console_export:
            console_exporter = ConsoleSpanExporter()
            self._provider.add_span_processor(
                BatchSpanProcessor(console_exporter)
            )
        
        if otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                headers=otlp_headers,
            )
            self._provider.add_span_processor(
                BatchSpanProcessor(otlp_exporter)
            )
        
        # Set global provider
        trace.set_tracer_provider(self._provider)
        
        # Create tracer
        self._tracer = trace.get_tracer(service_name, service_version)
        self._initialized = True
    
    def get_tracer(self) -> Optional[trace.Tracer]:
        """获取追踪器"""
        return self._tracer
    
    def shutdown(self):
        """关闭追踪器"""
        if self._provider:
            self._provider.shutdown()
            self._provider = None
        self._tracer = None
        self._initialized = False
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized


# Global provider instance
_provider_instance = TracerProvider()


def configure_tracing(
    service_name: str = 'quantforge',
    service_version: str = '1.0.0',
    otlp_endpoint: Optional[str] = None,
    otlp_headers: Optional[Dict[str, str]] = None,
    console_export: bool = False,
    sampling_rate: float = 1.0,
) -> TracerProvider:
    """配置分布式追踪"""
    _provider_instance.configure(
        service_name=service_name,
        service_version=service_version,
        otlp_endpoint=otlp_endpoint,
        otlp_headers=otlp_headers,
        console_export=console_export,
        sampling_rate=sampling_rate,
    )
    return _provider_instance


def get_tracer() -> Optional[trace.Tracer]:
    """获取追踪器"""
    return _provider_instance.get_tracer()


def shutdown_tracing():
    """关闭追踪"""
    _provider_instance.shutdown()


def start_span(
    name: str,
    context: Optional[trace.Context] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
    links: Optional[list] = None,
    start_time: Optional[int] = None,
    record_exception: bool = True,
    set_status_on_exception: bool = True,
) -> trace.Span:
    """启动一个span"""
    tracer = get_tracer()
    if tracer is None:
        raise RuntimeError("Tracing not configured. Call configure_tracing() first.")
    
    span = tracer.start_span(
        name=name,
        context=context,
        kind=kind,
        attributes=attributes,
        links=links,
        start_time=start_time,
        record_exception=record_exception,
        set_status_on_exception=set_status_on_exception,
    )
    
    _current_span.set(span)
    return span


def end_span(span: Optional[trace.Span] = None):
    """结束span"""
    if span is None:
        span = _current_span.get()
    
    if span:
        span.end()
        _current_span.set(None)


def get_current_span() -> Optional[trace.Span]:
    """获取当前span"""
    return _current_span.get() or trace.get_current_span()


def get_trace_id() -> Optional[str]:
    """获取当前trace ID"""
    span = get_current_span()
    if span:
        ctx = span.get_span_context()
        if ctx.is_valid:
            return format(ctx.trace_id, '032x')
    return None


def get_span_id() -> Optional[str]:
    """获取当前span ID"""
    span = get_current_span()
    if span:
        ctx = span.get_span_context()
        if ctx.is_valid:
            return format(ctx.span_id, '016x')
    return None


def add_span_attribute(key: str, value: Any):
    """添加span属性"""
    span = get_current_span()
    if span:
        span.set_attribute(key, value)


def add_span_event(name: str, attributes: Optional[Dict[str, Any]] = None):
    """添加span事件"""
    span = get_current_span()
    if span:
        span.add_event(name, attributes or {})


def record_span_exception(exception: Exception):
    """记录span异常"""
    span = get_current_span()
    if span:
        span.record_exception(exception)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))


class SpanContext:
    """Span上下文管理器"""
    
    def __init__(
        self,
        name: str,
        kind: trace.SpanKind = trace.SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.kind = kind
        self.attributes = attributes or {}
        self.span: Optional[trace.Span] = None
        self.token = None
    
    def __enter__(self):
        self.span = start_span(
            name=self.name,
            kind=self.kind,
            attributes=self.attributes,
        )
        self.token = _current_span.set(self.span)
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            record_span_exception(exc_val)
        
        if self.span:
            self.span.end()
        
        if self.token:
            _current_span.reset(self.token)


def trace_function(
    name: Optional[str] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
):
    """函数追踪装饰器"""
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__
        
        def wrapper(*args, **kwargs):
            with SpanContext(
                name=span_name,
                kind=kind,
                attributes=attributes,
            ):
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


async def trace_async_function(
    name: Optional[str] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
):
    """异步函数追踪装饰器"""
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__
        
        async def wrapper(*args, **kwargs):
            with SpanContext(
                name=span_name,
                kind=kind,
                attributes=attributes,
            ):
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator
