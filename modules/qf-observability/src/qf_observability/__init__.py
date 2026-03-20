"""
QuantForge Observability Module - 可观测性模块
提供结构化日志、指标采集、分布式追踪、性能剖析等功能
"""

# Structured Logging
from .logging.json_logger import (
    JSONLogger,
    configure_logging,
    get_logger,
    set_log_level,
    get_context,
    set_context,
    clear_context,
)
from .logging.masking import (
    SensitiveDataFilter,
    mask_sensitive_fields,
    add_sensitive_pattern,
    remove_sensitive_pattern,
)

# Metrics
from .metrics.collector import (
    MetricsCollector,
    get_collector,
    reset_collector,
)
from .metrics.business import (
    TradingMetrics,
    LatencyMetrics,
    SuccessRateMetrics,
)
from .metrics.system import (
    SystemMetrics,
    ResourceUsageCollector,
)
from .metrics.prometheus import (
    PrometheusExporter,
    start_metrics_server,
    get_prometheus_registry,
)

# Distributed Tracing
from .tracing.opentelemetry import (
    TracerProvider,
    get_tracer,
    configure_tracing,
    shutdown_tracing,
)
from .tracing.middleware import (
    TracingMiddleware,
    trace_function,
    trace_async_function,
    get_current_span,
    add_span_attribute,
    add_span_event,
)
from .tracing.context import (
    TraceContext,
    get_trace_id,
    get_span_id,
    inject_context,
    extract_context,
)

# Profiling
from .profiling.performance import (
    PerformanceProfiler,
    profile_function,
    profile_async_function,
    get_hotspots,
)
from .profiling.memory import (
    MemoryProfiler,
    detect_memory_leaks,
    get_memory_usage,
    track_object_growth,
)
from .profiling.async_monitor import (
    AsyncTaskMonitor,
    monitor_async_tasks,
    get_async_task_stats,
)

__version__ = "1.0.0"

__all__ = [
    # Logging
    "JSONLogger",
    "configure_logging",
    "get_logger",
    "set_log_level",
    "get_context",
    "set_context",
    "clear_context",
    "SensitiveDataFilter",
    "mask_sensitive_fields",
    "add_sensitive_pattern",
    "remove_sensitive_pattern",
    # Metrics
    "MetricsCollector",
    "get_collector",
    "reset_collector",
    "TradingMetrics",
    "LatencyMetrics",
    "SuccessRateMetrics",
    "SystemMetrics",
    "ResourceUsageCollector",
    "PrometheusExporter",
    "start_metrics_server",
    "get_prometheus_registry",
    # Tracing
    "TracerProvider",
    "get_tracer",
    "configure_tracing",
    "shutdown_tracing",
    "TracingMiddleware",
    "trace_function",
    "trace_async_function",
    "get_current_span",
    "add_span_attribute",
    "add_span_event",
    "TraceContext",
    "get_trace_id",
    "get_span_id",
    "inject_context",
    "extract_context",
    # Profiling
    "PerformanceProfiler",
    "profile_function",
    "profile_async_function",
    "get_hotspots",
    "MemoryProfiler",
    "detect_memory_leaks",
    "get_memory_usage",
    "track_object_growth",
    "AsyncTaskMonitor",
    "monitor_async_tasks",
    "get_async_task_stats",
]
