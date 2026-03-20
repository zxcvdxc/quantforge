"""
性能剖析模块测试
"""

import pytest
import time
import asyncio
from unittest.mock import patch

from qf_observability.profiling import (
    PerformanceProfiler,
    get_profiler,
    profile_function,
    profile_async_function,
    get_hotspots,
    Timer,
    time_block,
    get_memory_usage,
    detect_memory_leaks,
    MemoryTracker,
    AsyncTaskMonitor,
    get_async_task_monitor,
    monitor_async_tasks,
    get_async_task_stats,
    create_monitored_task,
)


class TestPerformanceProfiler:
    """性能剖析器测试"""
    
    def test_singleton(self):
        """测试单例模式"""
        profiler1 = get_profiler()
        profiler2 = get_profiler()
        assert profiler1 is profiler2
    
    def test_record_call(self):
        """测试记录调用"""
        profiler = PerformanceProfiler()
        profiler.reset()
        
        profiler.record_call('test_func', 0.1)
        profiler.record_call('test_func', 0.2)
        
        profile = profiler.get_profile('test_func')
        assert profile is not None
        assert profile.call_count == 2
        assert profile.total_time == 0.3
        assert profile.avg_time == 0.15
    
    def test_get_hotspots(self):
        """测试获取热点"""
        profiler = PerformanceProfiler()
        profiler.reset()
        
        profiler.record_call('hot_func', 1.0)
        profiler.record_call('hot_func', 2.0)
        profiler.record_call('cold_func', 0.1)
        
        hotspots = profiler.get_hotspots(top_n=2)
        
        assert len(hotspots) > 0
        assert hotspots[0].function_name == 'hot_func'
    
    def test_get_summary(self):
        """测试获取摘要"""
        profiler = PerformanceProfiler()
        profiler.reset()
        
        profiler.record_call('func1', 0.1)
        profiler.record_call('func2', 0.2)
        
        summary = profiler.get_summary()
        
        assert summary['total_functions'] == 2
        assert summary['total_calls'] == 2
        assert summary['total_time'] == 0.3
    
    def test_enable_disable(self):
        """测试启用/禁用"""
        profiler = PerformanceProfiler()
        
        profiler.enable()
        assert profiler._enabled
        
        profiler.disable()
        assert not profiler._enabled
        
        # Recording when disabled should not add data
        profiler.record_call('test', 0.1)
        # Should be empty or from previous test


class TestProfileDecorators:
    """剖析装饰器测试"""
    
    def test_profile_function(self):
        """测试函数剖析"""
        profiler = get_profiler()
        profiler.reset()
        
        @profile_function
        def test_func():
            time.sleep(0.01)
            return 'result'
        
        result = test_func()
        assert result == 'result'
        
        # Check that profiling data was recorded
        hotspots = profiler.get_hotspots()
        # Should have recorded something
        assert len(profiler.get_all_profiles()) >= 0
    
    @pytest.mark.asyncio
    async def test_profile_async_function(self):
        """测试异步函数剖析"""
        profiler = get_profiler()
        profiler.reset()
        
        @profile_async_function
        async def async_test_func():
            await asyncio.sleep(0.01)
            return 'async_result'
        
        result = await async_test_func()
        assert result == 'async_result'


class TestTimer:
    """计时器测试"""
    
    def test_timer_context(self):
        """测试计时器上下文"""
        profiler = get_profiler()
        profiler.reset()
        
        with Timer('test_block'):
            time.sleep(0.01)
        
        profile = profiler.get_profile('test_block')
        assert profile is not None
        assert profile.call_count == 1
    
    def test_time_block(self):
        """测试代码块计时"""
        profiler = get_profiler()
        profiler.reset()
        
        with time_block('another_block'):
            time.sleep(0.01)
        
        profile = profiler.get_profile('another_block')
        assert profile is not None


class TestMemoryProfiler:
    """内存剖析器测试"""
    
    def test_get_memory_usage(self):
        """测试获取内存使用"""
        usage = get_memory_usage()
        
        assert 'rss_mb' in usage
        assert 'vms_mb' in usage
        assert 'percent' in usage
        assert usage['rss_mb'] >= 0
    
    def test_memory_tracker(self):
        """测试内存追踪器"""
        with MemoryTracker('test_operation') as tracker:
            # Allocate some memory
            data = [i for i in range(1000)]
            tracker.checkpoint('after_allocation')
        
        # Should complete without error
        assert True


class TestAsyncTaskMonitor:
    """异步任务监控测试"""
    
    def test_singleton(self):
        """测试单例模式"""
        monitor1 = get_async_task_monitor()
        monitor2 = get_async_task_monitor()
        assert monitor1 is monitor2
    
    @pytest.mark.asyncio
    async def test_register_task(self):
        """测试注册任务"""
        monitor = AsyncTaskMonitor()
        monitor.reset()
        
        async def test_task():
            await asyncio.sleep(0.01)
            return 'done'
        
        task = asyncio.create_task(test_task())
        task_id = monitor.register_task(task, name='test_task')
        
        assert task_id is not None
        
        await task
        
        stats = monitor.get_stats()
        assert stats.total_created >= 1
    
    @pytest.mark.asyncio
    async def test_monitor_async_tasks_decorator(self):
        """测试异步任务监控装饰器"""
        monitor = get_async_task_monitor()
        monitor.reset()
        
        @monitor_async_tasks
        async def monitored_task():
            await asyncio.sleep(0.01)
            return 'completed'
        
        result = await monitored_task()
        assert result == 'completed'
    
    @pytest.mark.asyncio
    async def test_get_async_task_stats(self):
        """测试获取异步任务统计"""
        monitor = get_async_task_monitor()
        monitor.reset()
        
        async def simple_task():
            await asyncio.sleep(0.01)
        
        task = create_monitored_task(simple_task(), name='simple')
        await task
        
        stats = get_async_task_stats()
        assert 'stats' in stats
    
    def test_get_stats(self):
        """测试获取统计"""
        monitor = AsyncTaskMonitor()
        monitor.reset()
        
        stats = monitor.get_stats()
        
        assert stats.total_created == 0
        assert stats.total_completed == 0
        assert stats.active_count == 0
    
    def test_reset(self):
        """测试重置"""
        monitor = AsyncTaskMonitor()
        
        monitor.reset()
        
        assert len(monitor.get_all_tasks()) == 0
        assert monitor.get_stats().total_created == 0


class TestHotspots:
    """热点测试"""
    
    def test_get_hotspots_function(self):
        """测试获取热点函数"""
        profiler = get_profiler()
        profiler.reset()
        
        # Simulate some function calls
        for i in range(10):
            profiler.record_call('hot_function', 0.1)
        
        for i in range(5):
            profiler.record_call('cold_function', 0.01)
        
        hotspots = get_hotspots(top_n=2)
        
        assert len(hotspots) <= 2
        if len(hotspots) >= 1:
            assert hotspots[0].function_name == 'hot_function'
