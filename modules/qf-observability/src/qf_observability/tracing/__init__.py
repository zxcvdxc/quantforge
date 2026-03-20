"""
分布式追踪模块 - OpenTelemetry集成
"""

from .opentelemetry import (
    TracerProvider,
    configure_tracing,
    get_tracer,
    shutdown_tracing,
    start_span,
    end_span,
    get_current_span,
    get_trace_id,
    get_span_id,
    add_span_attribute,
    add_span_event,
    record_span_exception,
    SpanContext,
    trace_function,
    trace_async_function,
)

from .middleware import (
    TracingMiddleware,
    HTTPTracingMiddleware,
    DatabaseTracingMiddleware,
    MessageQueueTracingMiddleware,
    trace_function,
    trace_async_function,
    trace_class_methods,
)

from .context import (
    TraceContext,
    get_current_context,
    set_current_context,
    get_trace_id,
    get_span_id,
    inject_context,
    extract_context,
    with_context,
    ContextPropagator,
    TraceContextManager,
    create_child_context,
    propagate_context,
    get_current_trace_id,
    get_current_span_id,
)

__all__ = [
    # OpenTelemetry
    'TracerProvider',
    'configure_tracing',
    'get_tracer',
    'shutdown_tracing',
    'start_span',
    'end_span',
    'get_current_span',
    'get_trace_id',
    'get_span_id',
    'add_span_attribute',
    'add_span_event',
    'record_span_exception',
    'SpanContext',
    'trace_function',
    'trace_async_function',
    # Middleware
    'TracingMiddleware',
    'HTTPTracingMiddleware',
    'DatabaseTracingMiddleware',
    'MessageQueueTracingMiddleware',
    'trace_class_methods',
    # Context
    'TraceContext',
    'get_current_context',
    'set_current_context',
    'inject_context',
    'extract_context',
    'with_context',
    'ContextPropagator',
    'TraceContextManager',
    'create_child_context',
    'propagate_context',
    'get_current_trace_id',
    'get_current_span_id',
]
