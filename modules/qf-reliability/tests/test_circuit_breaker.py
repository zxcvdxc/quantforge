"""断路器测试"""
import time
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor

from qf_reliability.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpenError,
    circuit_breaker
)


class TestCircuitBreaker:
    """断路器测试类"""
    
    def test_initial_state(self):
        """测试初始状态"""
        breaker = CircuitBreaker("test", failure_threshold=3)
        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0
        assert breaker._success_count == 0
    
    def test_successful_calls(self):
        """测试成功调用"""
        breaker = CircuitBreaker("test_success", failure_threshold=3)
        
        def success_func():
            return "success"
        
        result = breaker.call(success_func)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0
    
    def test_failure_counting(self):
        """测试失败计数"""
        breaker = CircuitBreaker("test_fail", failure_threshold=3)
        
        def fail_func():
            raise ValueError("test error")
        
        # 失败2次，未达到阈值
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker.call(fail_func)
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 2
        
        # 第3次失败，达到阈值，断路器打开
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        assert breaker.state == CircuitState.OPEN
        assert breaker._failure_count == 3
    
    def test_circuit_opens(self):
        """测试断路器打开"""
        breaker = CircuitBreaker("test_open", failure_threshold=2, timeout=1.0)
        
        def fail_func():
            raise ValueError("test error")
        
        # 触发熔断
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # 断路器打开，应该直接拒绝
        with pytest.raises(CircuitBreakerOpenError):
            breaker.call(lambda: "should not execute")
    
    def test_circuit_recovery(self):
        """测试断路器恢复"""
        breaker = CircuitBreaker(
            "test_recovery",
            failure_threshold=2,
            success_threshold=2,
            timeout=0.1
        )
        
        def fail_func():
            raise ValueError("test error")
        
        def success_func():
            return "success"
        
        # 触发熔断
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # 等待超时，进入半开状态
        time.sleep(0.15)
        
        # 半开状态下成功调用
        result = breaker.call(success_func)
        assert result == "success"
        assert breaker.state == CircuitState.HALF_OPEN
        
        # 再次成功，恢复关闭状态
        result = breaker.call(success_func)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
    
    def test_half_open_failure(self):
        """测试半开状态再次失败"""
        breaker = CircuitBreaker(
            "test_half_fail",
            failure_threshold=2,
            timeout=0.1
        )
        
        def fail_func():
            raise ValueError("test error")
        
        # 触发熔断
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        # 等待超时
        time.sleep(0.15)
        
        # 半开状态下再次失败，应该回到打开状态
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        assert breaker.state == CircuitState.OPEN
    
    def test_reset(self):
        """测试手动重置"""
        breaker = CircuitBreaker("test_reset", failure_threshold=2)
        
        def fail_func():
            raise ValueError("test error")
        
        # 触发熔断
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # 重置
        breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0
        assert breaker._success_count == 0
    
    def test_stats(self):
        """测试统计信息"""
        breaker = CircuitBreaker("test_stats", failure_threshold=5)
        
        def success_func():
            return "success"
        
        def fail_func():
            raise ValueError("test error")
        
        # 执行一些调用
        breaker.call(success_func)
        breaker.call(success_func)
        
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        stats = breaker.stats
        assert stats["total_calls"] == 3
        assert stats["success_calls"] == 2
        assert stats["failure_calls"] == 1
    
    def test_fallback_function(self):
        """测试降级函数"""
        def fallback_func():
            return "fallback"
        
        breaker = CircuitBreaker(
            "test_fallback",
            failure_threshold=1,
            fallback_func=fallback_func
        )
        
        def fail_func():
            raise ValueError("test error")
        
        # 第一次失败
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        # 断路器打开后应该调用降级函数
        result = breaker.call(lambda: "should not execute")
        assert result == "fallback"
    
    def test_singleton(self):
        """测试单例模式 - 同名断路器共享状态"""
        breaker1 = CircuitBreaker("singleton_test", failure_threshold=3)
        breaker2 = CircuitBreaker("singleton_test", failure_threshold=3)
        
        assert breaker1 is breaker2
    
    def test_thread_safety(self):
        """测试线程安全"""
        breaker = CircuitBreaker("thread_test", failure_threshold=10)
        
        def success_func():
            return "success"
        
        results = []
        
        def worker():
            try:
                result = breaker.call(success_func)
                results.append(result)
            except Exception as e:
                results.append(str(e))
        
        # 并发执行
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker) for _ in range(100)]
            for future in futures:
                future.result()
        
        assert len(results) == 100
        assert all(r == "success" for r in results)


class TestCircuitBreakerDecorator:
    """断路器装饰器测试"""
    
    def test_decorator_sync(self):
        """测试同步装饰器"""
        @circuit_breaker(name="decorator_test", failure_threshold=2)
        def my_function(x):
            return x * 2
        
        result = my_function(5)
        assert result == 10
    
    def test_decorator_failure(self):
        """测试装饰器失败"""
        @circuit_breaker(name="decorator_fail", failure_threshold=2)
        def fail_function():
            raise ValueError("test error")
        
        # 触发熔断
        with pytest.raises(ValueError):
            fail_function()
        with pytest.raises(ValueError):
            fail_function()
        
        # 断路器应该打开
        with pytest.raises(CircuitBreakerOpenError):
            fail_function()
    
    @pytest.mark.asyncio
    async def test_decorator_async(self):
        """测试异步装饰器"""
        @circuit_breaker(name="async_test", failure_threshold=2)
        async def async_function(x):
            return x * 2
        
        result = await async_function(5)
        assert result == 10
    
    @pytest.mark.asyncio
    async def test_decorator_async_failure(self):
        """测试异步装饰器失败"""
        @circuit_breaker(name="async_fail", failure_threshold=2)
        async def async_fail_function():
            raise ValueError("test error")
        
        # 触发熔断
        with pytest.raises(ValueError):
            await async_fail_function()
        with pytest.raises(ValueError):
            await async_fail_function()
        
        # 断路器应该打开
        with pytest.raises(CircuitBreakerOpenError):
            await async_fail_function()


class TestCircuitBreakerEdgeCases:
    """断路器边界情况测试"""
    
    def test_expected_exceptions(self):
        """测试预期异常类型"""
        breaker = CircuitBreaker(
            "expected_exc",
            failure_threshold=2,
            expected_exceptions=[ValueError]
        )
        
        # ValueError应该触发熔断
        with pytest.raises(ValueError):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("test")))
        
        # TypeError不是预期异常，不应该触发熔断
        with pytest.raises(TypeError):
            breaker.call(lambda: (_ for _ in ()).throw(TypeError("test")))
        
        assert breaker._failure_count == 1
    
    def test_half_open_max_calls(self):
        """测试半开状态最大调用次数"""
        breaker = CircuitBreaker(
            "half_max",
            failure_threshold=2,
            success_threshold=5,  # 需要5次成功才能恢复
            timeout=0.1,
            half_open_max_calls=3
        )
        
        def fail_func():
            raise ValueError("test error")
        
        # 触发熔断
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        # 等待超时
        time.sleep(0.15)
        
        # 半开状态最多允许3次调用
        assert breaker._should_allow_call()
        assert breaker._should_allow_call()
        assert breaker._should_allow_call()
        
        # 第4次应该被拒绝
        assert not breaker._should_allow_call()
