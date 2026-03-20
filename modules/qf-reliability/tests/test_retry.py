"""重试机制测试"""
import time
import pytest
from unittest.mock import Mock, call

from qf_reliability.retry import (
    RetryManager,
    RetryConfig,
    RetryStrategy,
    RetryExhaustedError,
    retry_with_backoff,
    retry_fixed,
    retry_linear
)


class TestRetryManager:
    """重试管理器测试"""
    
    def test_success_no_retry(self):
        """测试成功时不重试"""
        manager = RetryManager(max_attempts=3)
        
        def success_func():
            return "success"
        
        result = manager.execute(success_func)
        assert result == "success"
        assert manager.stats["total_attempts"] == 1
        assert manager.stats["successful"] == 1
        assert manager.stats["retries"] == 0
    
    def test_retry_on_failure(self):
        """测试失败时重试"""
        manager = RetryManager(max_attempts=3, base_delay=0.01)
        
        mock_func = Mock(side_effect=[ValueError("error"), ValueError("error"), "success"])
        
        result = manager.execute(mock_func)
        assert result == "success"
        assert mock_func.call_count == 3
        assert manager.stats["retries"] == 2
    
    def test_retry_exhausted(self):
        """测试重试次数用尽"""
        manager = RetryManager(max_attempts=3, base_delay=0.01)
        
        def always_fail():
            raise ValueError("always fails")
        
        with pytest.raises(RetryExhaustedError) as exc_info:
            manager.execute(always_fail)
        
        assert "failed after 3 attempts" in str(exc_info.value)
        assert manager.stats["failed"] == 1
    
    def test_fixed_delay(self):
        """测试固定延迟"""
        config = RetryConfig(
            strategy=RetryStrategy.FIXED,
            base_delay=0.05
        )
        manager = RetryManager(config)
        
        delay = manager.calculate_delay(1)
        assert delay == pytest.approx(0.05, abs=0.01)
        
        # 固定延迟不随尝试次数变化
        delay2 = manager.calculate_delay(5)
        assert delay2 == pytest.approx(0.05, abs=0.01)
    
    def test_exponential_delay(self):
        """测试指数延迟"""
        config = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=1.0,
            exponential_base=2.0
        )
        manager = RetryManager(config)
        
        assert manager.calculate_delay(1) == pytest.approx(1.0, abs=0.1)
        assert manager.calculate_delay(2) == pytest.approx(2.0, abs=0.1)
        assert manager.calculate_delay(3) == pytest.approx(4.0, abs=0.1)
    
    def test_linear_delay(self):
        """测试线性延迟"""
        config = RetryConfig(
            strategy=RetryStrategy.LINEAR,
            base_delay=1.0
        )
        manager = RetryManager(config)
        
        assert manager.calculate_delay(1) == pytest.approx(1.0, abs=0.1)
        assert manager.calculate_delay(2) == pytest.approx(2.0, abs=0.1)
        assert manager.calculate_delay(3) == pytest.approx(3.0, abs=0.1)
    
    def test_max_delay(self):
        """测试最大延迟限制"""
        config = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0
        )
        manager = RetryManager(config)
        
        # 第5次尝试的理论延迟是16秒，但应该被限制为10秒
        delay = manager.calculate_delay(5)
        assert delay <= 10.0 + 1.0  # 允许抖动
    
    def test_jitter(self):
        """测试抖动"""
        config = RetryConfig(
            strategy=RetryStrategy.FIXED,
            base_delay=1.0,
            jitter=True,
            jitter_max=0.2
        )
        manager = RetryManager(config)
        
        delays = [manager.calculate_delay(1) for _ in range(10)]
        
        # 所有延迟应该在 0.8 到 1.2 之间
        assert all(0.7 <= d <= 1.3 for d in delays)
        
        # 应该有变化（抖动生效）
        assert len(set(delays)) > 1
    
    def test_specific_exceptions(self):
        """测试指定异常类型"""
        manager = RetryManager(
            max_attempts=3,
            base_delay=0.01,
            retry_on_exceptions=[ValueError]
        )
        
        # ValueError应该重试
        mock_func = Mock(side_effect=[ValueError("error"), "success"])
        result = manager.execute(mock_func)
        assert result == "success"
        
        # TypeError不应该重试
        mock_func2 = Mock(side_effect=[TypeError("error"), "success"])
        with pytest.raises(TypeError):
            manager.execute(mock_func2)
        assert mock_func2.call_count == 1
    
    def test_retry_on_result(self):
        """测试基于结果的重试"""
        def should_retry(result):
            return result is None or result == ""
        
        manager = RetryManager(
            max_attempts=3,
            base_delay=0.01,
            retry_on_result=should_retry
        )
        
        mock_func = Mock(side_effect=[None, "", "success"])
        result = manager.execute(mock_func)
        assert result == "success"
        assert mock_func.call_count == 3
    
    def test_callbacks(self):
        """测试回调函数"""
        on_retry_mock = Mock()
        on_giveup_mock = Mock()
        
        manager = RetryManager(
            max_attempts=2,
            base_delay=0.01,
            on_retry=on_retry_mock,
            on_giveup=on_giveup_mock
        )
        
        def always_fail():
            raise ValueError("error")
        
        with pytest.raises(RetryExhaustedError):
            manager.execute(always_fail)
        
        assert on_retry_mock.called
        assert on_giveup_mock.called


class TestRetryDecorator:
    """重试装饰器测试"""
    
    def test_decorator_success(self):
        """测试装饰器成功"""
        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def success_func():
            return "success"
        
        result = success_func()
        assert result == "success"
    
    def test_decorator_retry(self):
        """测试装饰器重试"""
        call_count = 0
        
        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("error")
            return "success"
        
        result = flaky_func()
        assert result == "success"
        assert call_count == 3
    
    def test_decorator_exhausted(self):
        """测试装饰器重试用尽"""
        @retry_with_backoff(max_attempts=2, base_delay=0.01)
        def always_fail():
            raise ValueError("error")
        
        with pytest.raises(RetryExhaustedError):
            always_fail()
    
    def test_retry_fixed_decorator(self):
        """测试固定重试装饰器"""
        @retry_fixed(max_attempts=3, delay=0.01)
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"
    
    def test_retry_linear_decorator(self):
        """测试线性重试装饰器"""
        @retry_linear(max_attempts=3, base_delay=0.01)
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_async_retry(self):
        """测试异步重试"""
        call_count = 0
        
        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        async def async_flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("error")
            return "success"
        
        result = await async_flaky()
        assert result == "success"
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_async_retry_exhausted(self):
        """测试异步重试用尽"""
        @retry_with_backoff(max_attempts=2, base_delay=0.01)
        async def async_fail():
            raise ValueError("error")
        
        with pytest.raises(RetryExhaustedError):
            await async_fail()


class TestRetryEdgeCases:
    """重试边界情况测试"""
    
    def test_zero_attempts(self):
        """测试零次尝试"""
        manager = RetryManager(max_attempts=1, base_delay=0.01)
        
        def fail_once():
            raise ValueError("error")
        
        with pytest.raises(RetryExhaustedError):
            manager.execute(fail_once)
    
    def test_no_jitter(self):
        """测试无抖动"""
        config = RetryConfig(
            strategy=RetryStrategy.FIXED,
            base_delay=1.0,
            jitter=False
        )
        manager = RetryManager(config)
        
        delays = [manager.calculate_delay(1) for _ in range(5)]
        # 无抖动时，所有延迟应该相同
        assert all(d == delays[0] for d in delays)
    
    def test_chained_exceptions(self):
        """测试异常链"""
        manager = RetryManager(max_attempts=2, base_delay=0.01)
        
        def fail():
            raise ValueError("original error")
        
        with pytest.raises(RetryExhaustedError) as exc_info:
            manager.execute(fail)
        
        # 检查异常链
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
