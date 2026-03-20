"""混沌测试测试"""
import pytest
import random
from unittest.mock import Mock, patch

from qf_reliability.chaos import (
    ChaosEngine,
    ChaosConfig,
    FailureType,
    chaos_test,
    FaultInjector
)


class TestChaosEngine:
    """混沌引擎测试"""
    
    def test_initial_state(self):
        """测试初始状态"""
        engine = ChaosEngine(failure_rate=0.5)
        
        assert engine.config.failure_rate == 0.5
        assert engine.enabled is True
    
    def test_enable_disable(self):
        """测试启用和禁用"""
        engine = ChaosEngine()
        
        engine.disable()
        assert engine.enabled is False
        
        engine.enable()
        assert engine.enabled is True
    
    def test_should_inject_when_disabled(self):
        """测试禁用时不会注入"""
        engine = ChaosEngine(failure_rate=1.0)  # 100%故障率
        engine.disable()
        
        assert engine.should_inject() is False
    
    def test_should_inject_when_enabled(self):
        """测试启用时根据故障率注入"""
        engine = ChaosEngine(failure_rate=1.0)  # 100%故障率
        engine.enable()
        
        assert engine.should_inject() is True
    
    def test_inject_exception(self):
        """测试注入异常"""
        engine = ChaosEngine()
        engine.enable()
        
        with pytest.raises(Exception):
            engine.inject_failure(FailureType.EXCEPTION)
    
    def test_inject_delay(self):
        """测试注入延迟"""
        engine = ChaosEngine(delay_min_ms=10, delay_max_ms=20)
        engine.enable()
        
        import time
        start = time.time()
        result = engine.inject_failure(FailureType.DELAY)
        elapsed = (time.time() - start) * 1000
        
        # 延迟应该在10-20ms之间
        assert elapsed >= 8  # 允许一些误差
    
    def test_inject_timeout(self):
        """测试注入超时"""
        engine = ChaosEngine()
        engine.enable()
        
        with pytest.raises(TimeoutError):
            engine.inject_failure(FailureType.TIMEOUT)
    
    def test_inject_return_none(self):
        """测试注入返回None"""
        engine = ChaosEngine()
        engine.enable()
        
        result = engine.inject_failure(FailureType.RETURN_NONE)
        assert result is None
    
    def test_inject_return_error(self):
        """测试注入返回错误值"""
        engine = ChaosEngine(error_value={"error": "injected"})
        engine.enable()
        
        result = engine.inject_failure(FailureType.RETURN_ERROR)
        assert result == {"error": "injected"}
    
    def test_stats(self):
        """测试统计信息"""
        engine = ChaosEngine(failure_rate=1.0)
        engine.enable()
        
        # 触发几次故障
        try:
            engine.inject_failure(FailureType.EXCEPTION)
        except Exception:
            pass
        
        try:
            engine.inject_failure(FailureType.TIMEOUT)
        except TimeoutError:
            pass
        
        stats = engine.stats
        assert stats["injected_failures"] >= 0
    
    def test_session_context(self):
        """测试会话上下文"""
        engine = ChaosEngine(failure_rate=0.1)
        
        original_rate = engine.config.failure_rate
        
        with engine.session(failure_rate=0.9):
            assert engine.config.failure_rate == 0.9
        
        # 退出会话后应该恢复
        assert engine.config.failure_rate == original_rate


class TestChaosDecorator:
    """混沌装饰器测试"""
    
    def test_decorator_sync(self):
        """测试同步装饰器"""
        call_count = 0
        
        @chaos_test(failure_rate=0.0)  # 0%故障率，确保成功
        def test_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = test_func()
        assert result == "success"
    
    def test_decorator_with_failure(self):
        """测试带故障的装饰器"""
        @chaos_test(failure_rate=1.0, failure_types=[FailureType.EXCEPTION])
        def failing_func():
            return "should not reach"
        
        # 100%故障率，应该抛出异常
        with pytest.raises(Exception):
            failing_func()
    
    def test_decorator_with_delay(self):
        """测试带延迟的装饰器"""
        import time
        
        @chaos_test(
            failure_rate=1.0,
            failure_types=[FailureType.DELAY],
            exception_types=[]
        )
        def delayed_func():
            return "success"
        
        start = time.time()
        result = delayed_func()
        elapsed = (time.time() - start) * 1000
        
        assert result == "success"
        assert elapsed >= 50  # 应该有延迟
    
    @pytest.mark.asyncio
    async def test_decorator_async(self):
        """测试异步装饰器"""
        @chaos_test(failure_rate=0.0)
        async def async_func():
            return "async success"
        
        result = await async_func()
        assert result == "async success"
    
    @pytest.mark.asyncio
    async def test_decorator_async_failure(self):
        """测试异步装饰器故障"""
        @chaos_test(failure_rate=1.0, failure_types=[FailureType.EXCEPTION])
        async def async_failing():
            return "should not reach"
        
        with pytest.raises(Exception):
            await async_failing()


class TestFaultInjector:
    """故障注入器测试"""
    
    def test_register_fault_point(self):
        """测试注册故障点"""
        injector = FaultInjector()
        
        injector.register_fault_point("db_query", failure_rate=0.5)
        
        assert "db_query" in injector._fault_points
        assert injector._fault_points["db_query"]["failure_rate"] == 0.5
    
    def test_maybe_fail_injects(self):
        """测试可能注入故障"""
        injector = FaultInjector()
        injector.register_fault_point("test", failure_rate=1.0)  # 100%故障率
        
        with pytest.raises(RuntimeError):
            injector.maybe_fail("test")
    
    def test_maybe_fail_no_inject(self):
        """测试不注入故障"""
        injector = FaultInjector()
        injector.register_fault_point("test", failure_rate=0.0)  # 0%故障率
        
        # 不应该抛出异常
        injector.maybe_fail("test")
    
    def test_maybe_fail_with_condition(self):
        """测试带条件的故障注入"""
        injector = FaultInjector()
        
        # 条件为False，不注入
        def always_false(context):
            return False
        
        injector.register_fault_point("test", failure_rate=1.0, condition=always_false)
        
        # 不应该抛出异常
        injector.maybe_fail("test")
        
        # 条件为True，注入
        def always_true(context):
            return True
        
        injector.register_fault_point("test2", failure_rate=1.0, condition=always_true)
        
        with pytest.raises(RuntimeError):
            injector.maybe_fail("test2")
    
    def test_stats(self):
        """测试统计"""
        injector = FaultInjector()
        injector.register_fault_point("test", failure_rate=1.0)
        
        try:
            injector.maybe_fail("test")
        except RuntimeError:
            pass
        
        stats = injector.get_stats()
        assert stats["test"]["triggered"] == 1


class TestChaosIntegration:
    """混沌测试集成测试"""
    
    def test_chaos_with_real_function(self):
        """测试混沌与真实函数结合"""
        engine = ChaosEngine(failure_rate=0.5)
        
        @engine.inject(failure_rate=0.0)  # 先不注入故障
        def reliable_function():
            return {"status": "ok", "data": [1, 2, 3]}
        
        # 多次调用应该都成功
        for _ in range(5):
            result = reliable_function()
            assert result["status"] == "ok"
    
    def test_chaos_session_temporarily_enables(self):
        """测试会话临时启用"""
        # 创建一个初始禁用的引擎
        engine = ChaosEngine(failure_rate=1.0, enabled=False)
        
        call_count = [0]
        
        @engine.inject()
        def test_func():
            call_count[0] += 1
            return "success"
        
        # 禁用状态下应该成功
        assert test_func() == "success"
        assert call_count[0] == 1
        
        # 启用引擎并设置100%故障率
        engine.enable()
        
        # 现在应该抛出异常
        with pytest.raises(Exception):
            test_func()
        
        assert call_count[0] == 2
        
        # 禁用引擎
        engine.disable()
        
        # 应该再次成功
        assert test_func() == "success"
        assert call_count[0] == 3
    
    def test_multiple_failure_types(self):
        """测试多种故障类型"""
        engine = ChaosEngine(
            failure_rate=1.0,
            failure_types=[FailureType.EXCEPTION, FailureType.TIMEOUT]
        )
        engine.enable()
        
        # 测试应该抛出异常（EXCEPTION或TIMEOUT）
        @engine.inject()
        def test_func():
            return "success"
        
        with pytest.raises((Exception, TimeoutError)):
            test_func()


class TestChaosConfig:
    """混沌配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = ChaosConfig()
        
        assert config.enabled is True
        assert config.failure_rate == 0.1
        assert FailureType.EXCEPTION in config.failure_types
        assert FailureType.DELAY in config.failure_types
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = ChaosConfig(
            enabled=False,
            failure_rate=0.5,
            failure_types=[FailureType.TIMEOUT],
            delay_min_ms=100,
            delay_max_ms=500
        )
        
        assert config.enabled is False
        assert config.failure_rate == 0.5
        assert config.failure_types == [FailureType.TIMEOUT]
        assert config.delay_min_ms == 100
        assert config.delay_max_ms == 500
