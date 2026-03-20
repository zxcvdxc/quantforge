"""
分布式追踪模块测试
"""

import pytest
from unittest.mock import patch, MagicMock

from qf_observability.tracing import (
    configure_tracing,
    get_tracer,
    shutdown_tracing,
    get_current_span,
    get_trace_id,
    get_span_id,
    add_span_attribute,
    add_span_event,
    TraceContext,
    trace_function,
    trace_async_function,
    inject_context,
    extract_context,
    ContextPropagator,
    create_child_context,
    get_current_context,
    set_current_context,
)


class TestTracerProvider:
    """追踪器提供器测试"""
    
    def test_configure_tracing(self):
        """测试配置追踪"""
        # Use console export for testing
        provider = configure_tracing(
            service_name='test-service',
            service_version='1.0.0',
            console_export=True,
        )
        
        assert provider is not None
        assert provider.is_initialized()
        
        tracer = get_tracer()
        assert tracer is not None
        
        shutdown_tracing()
    
    def test_get_tracer_before_config(self):
        """测试配置前获取追踪器"""
        shutdown_tracing()  # Ensure clean state
        tracer = get_tracer()
        assert tracer is None


class TestTraceContext:
    """追踪上下文测试"""
    
    def test_trace_context_creation(self):
        """测试追踪上下文创建"""
        ctx = TraceContext(
            trace_id='abc123',
            span_id='def456',
            trace_flags=1,
        )
        
        assert ctx.trace_id == 'abc123'
        assert ctx.span_id == 'def456'
        assert ctx.trace_flags == 1
    
    def test_trace_context_to_dict(self):
        """测试转换为字典"""
        ctx = TraceContext(
            trace_id='abc123',
            span_id='def456',
            trace_flags=1,
        )
        
        data = ctx.to_dict()
        assert data['trace_id'] == 'abc123'
        assert data['span_id'] == 'def456'
    
    def test_create_child_context(self):
        """测试创建子上下文"""
        parent = TraceContext(
            trace_id='parent123',
            span_id='parent456',
        )
        
        child = create_child_context(parent)
        
        assert child.trace_id == parent.trace_id  # Same trace
        assert child.span_id != parent.span_id    # Different span
    
    def test_create_new_trace(self):
        """测试创建新追踪"""
        ctx = create_child_context()
        
        assert len(ctx.trace_id) == 32
        assert len(ctx.span_id) == 16


class TestContextPropagation:
    """上下文传播测试"""
    
    def test_inject_extract_context(self):
        """测试注入和提取上下文"""
        configure_tracing(console_export=True)
        
        # Inject context into carrier
        carrier = inject_context()
        
        assert isinstance(carrier, dict)
        
        # Extract context from carrier
        ctx = extract_context(carrier)
        
        shutdown_tracing()
    
    def test_http_headers_propagation(self):
        """测试HTTP头传播"""
        configure_tracing(console_export=True)
        
        headers = ContextPropagator.to_http_headers()
        
        assert isinstance(headers, dict)
        
        shutdown_tracing()


class TestTracingDecorators:
    """追踪装饰器测试"""
    
    def test_trace_function_decorator(self):
        """测试函数追踪装饰器"""
        configure_tracing(console_export=True)
        
        @trace_function(name='test_operation')
        def test_func():
            return 'result'
        
        result = test_func()
        assert result == 'result'
        
        shutdown_tracing()
    
    @pytest.mark.asyncio
    async def test_trace_async_function_decorator(self):
        """测试异步函数追踪装饰器"""
        configure_tracing(console_export=True)
        
        @trace_async_function(name='async_test_operation')
        async def async_test_func():
            return 'async_result'
        
        result = await async_test_func()
        assert result == 'async_result'
        
        shutdown_tracing()


class TestSpanOperations:
    """Span操作测试"""
    
    def test_add_span_attribute(self):
        """测试添加span属性"""
        configure_tracing(console_export=True)
        
        # This should not throw even without an active span
        add_span_attribute('key', 'value')
        
        shutdown_tracing()
    
    def test_add_span_event(self):
        """测试添加span事件"""
        configure_tracing(console_export=True)
        
        # This should not throw even without an active span
        add_span_event('test_event', {'key': 'value'})
        
        shutdown_tracing()


class TestTraceIDs:
    """追踪ID测试"""
    
    def test_get_trace_id(self):
        """测试获取trace ID"""
        # Without active span, should return None
        trace_id = get_trace_id()
        # May be None if no active span
        assert trace_id is None or isinstance(trace_id, str)
    
    def test_get_span_id(self):
        """测试获取span ID"""
        # Without active span, should return None
        span_id = get_span_id()
        # May be None if no active span
        assert span_id is None or isinstance(span_id, str)


class TestContextManagement:
    """上下文管理测试"""
    
    def test_set_get_context(self):
        """测试设置和获取上下文"""
        ctx = TraceContext(
            trace_id='test-trace-123',
            span_id='test-span-456',
        )
        
        set_current_context(ctx)
        
        current = get_current_context()
        assert current is not None
        assert current.trace_id == 'test-trace-123'
        assert current.span_id == 'test-span-456'
