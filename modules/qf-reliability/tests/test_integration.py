"""可靠性模块集成测试

测试断路器、重试、降级、健康检查、混沌测试的协同工作
"""
import time
import pytest
from unittest.mock import Mock

from qf_reliability import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    circuit_breaker,
    retry_with_backoff,
    fallback,
    DegradationStrategy,
    HealthChecker,
    HealthStatus,
    ChaosEngine,
    FailureType,
)


class TestReliabilityIntegration:
    """可靠性集成测试"""
    
    def test_circuit_breaker_with_retry(self):
        """测试断路器与重试结合"""
        call_count = 0
        
        # 注意：retry_with_backoff 在外层，circuit_breaker 在内层
        # 这样先进行重试，重试失败后才触发断路器计数
        @retry_with_backoff(max_attempts=3, base_delay=0.01, retry_on_exceptions=[ConnectionError])
        @circuit_breaker(name="cb_retry_test", failure_threshold=5)
        def unreliable_service():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("connection failed")
            return "success"
        
        # 第一次调用：重试3次后成功
        result = unreliable_service()
        assert result == "success"
        
        # 断路器应该仍然是CLOSED状态
        breaker = unreliable_service._circuit_breaker
        assert breaker.state.name == "CLOSED"
    
    def test_circuit_breaker_opens_after_retries_exhausted(self):
        """测试重试用尽后断路器熔断"""
        call_count = 0
        
        @circuit_breaker(name="cb_open_test", failure_threshold=2, timeout=0.1)
        @retry_with_backoff(max_attempts=2, base_delay=0.01)
        def always_failing():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")
        
        # 第一次调用：重试2次都失败，断路器计数+1
        with pytest.raises(Exception):
            always_failing()
        
        # 第二次调用：断路器还未打开，继续失败
        with pytest.raises(Exception):
            always_failing()
        
        # 第三次调用：断路器应该已经打开
        with pytest.raises(CircuitBreakerOpenError):
            always_failing()
    
    def test_fallback_with_circuit_breaker(self):
        """测试降级与断路器结合"""
        fallback_called = False
        
        def fallback_func():
            nonlocal fallback_called
            fallback_called = True
            return {"cached": "data"}
        
        @circuit_breaker(
            name="fb_cb_test",
            failure_threshold=1,
            fallback_func=fallback_func
        )
        def failing_service():
            raise ConnectionError("service down")
        
        # 第一次调用失败
        with pytest.raises(ConnectionError):
            failing_service()
        
        # 第二次调用：断路器打开，调用降级函数
        result = failing_service()
        assert result == {"cached": "data"}
        assert fallback_called is True
    
    def test_health_check_triggers_degradation(self):
        """测试健康检查触发降级"""
        checker = HealthChecker()
        
        # 模拟一个不健康的检查
        checker.register("api", lambda: False)
        result = checker.check_once("api")
        
        assert result.status == HealthStatus.UNHEALTHY
        
        # 基于健康状态，系统可以选择降级
        overall = checker.get_overall_status()
        assert overall["status"] == HealthStatus.UNHEALTHY.name
    
    def test_chaos_reveals_failure_handling(self):
        """测试混沌测试暴露故障处理"""
        engine = ChaosEngine(failure_rate=0.5)
        
        success_count = 0
        failure_count = 0
        
        @engine.inject()
        @retry_with_backoff(max_attempts=2, base_delay=0.01)
        def service_under_test():
            return "success"
        
        # 多次调用，统计成功率
        for _ in range(10):
            try:
                service_under_test()
                success_count += 1
            except Exception:
                failure_count += 1
        
        # 由于有重试，成功率应该比故障率高
        assert success_count >= failure_count


class TestResilienceScenario:
    """弹性场景测试"""
    
    def test_database_failure_scenario(self):
        """测试数据库故障场景"""
        db_call_count = 0
        cache_hit = False
        
        # 先调用成功一次，缓存数据
        @retry_with_backoff(max_attempts=2, base_delay=0.01, retry_on_exceptions=[ConnectionError])
        def query_database_first(sql):
            return {"data": "fresh"}
        
        # 保存缓存数据
        cached_data = {"data": "cached"}
        
        # 模拟后续调用都失败
        @circuit_breaker(name="db_query_fail", failure_threshold=1, timeout=0.5)
        @retry_with_backoff(max_attempts=2, base_delay=0.01, retry_on_exceptions=[ConnectionError])
        def query_database_fail(sql):
            nonlocal db_call_count
            db_call_count += 1
            raise ConnectionError("database down")
        
        def get_with_fallback():
            try:
                return query_database_fail("SELECT * FROM trades")
            except (ConnectionError, CircuitBreakerOpenError, Exception):
                nonlocal cache_hit
                cache_hit = True
                return cached_data
        
        # 调用应该使用缓存
        result = get_with_fallback()
        assert result == cached_data
        assert cache_hit is True
    
    def test_api_rate_limit_scenario(self):
        """测试API限流场景"""
        request_count = 0
        
        @retry_with_backoff(
            max_attempts=3,
            base_delay=0.1,
            strategy=RetryStrategy.EXPONENTIAL,
            retry_on_result=lambda r: r.get("status") == 429
        )
        def call_api():
            nonlocal request_count
            request_count += 1
            if request_count < 3:
                return {"status": 429, "message": "rate limited"}
            return {"status": 200, "data": "success"}
        
        result = call_api()
        assert result["status"] == 200
        assert request_count == 3
    
    def test_partial_degradation_scenario(self):
        """测试部分降级场景"""
        service_health = {"orders": True, "market_data": False, "notifications": True}
        
        checker = HealthChecker()
        checker.register("orders", lambda: service_health["orders"])
        checker.register("market_data", lambda: service_health["market_data"])
        checker.register("notifications", lambda: service_health["notifications"])
        
        status = checker.get_overall_status()
        
        # 2个健康，1个不健康，应该是 DEGRADED
        assert status["healthy_count"] == 2
        assert status["unhealthy_count"] == 1
        assert status["status"] == HealthStatus.DEGRADED.name


class TestRecoveryScenario:
    """恢复场景测试"""
    
    def test_circuit_breaker_recovery(self):
        """测试断路器自动恢复"""
        failure_count = 0
        
        @circuit_breaker(
            name="recovery_test",
            failure_threshold=2,
            success_threshold=2,
            timeout=0.1
        )
        def flaky_service():
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 2:
                raise ConnectionError("service unavailable")
            return "recovered"
        
        # 触发熔断
        with pytest.raises(ConnectionError):
            flaky_service()
        with pytest.raises(ConnectionError):
            flaky_service()
        
        breaker = flaky_service._circuit_breaker
        assert breaker.state.name == "OPEN"
        
        # 等待恢复
        time.sleep(0.15)
        
        # 半开状态下成功2次，应该恢复
        result = flaky_service()
        assert result == "recovered"
        result = flaky_service()
        assert result == "recovered"
        
        assert breaker.state.name == "CLOSED"
    
    def test_health_check_recovery_detection(self):
        """测试健康检查检测恢复"""
        service_healthy = [False, False, True]  # 模拟服务恢复
        call_index = 0
        
        def check_service():
            nonlocal call_index
            result = service_healthy[min(call_index, len(service_healthy) - 1)]
            call_index += 1
            return result
        
        checker = HealthChecker()
        checker.register("recovering_service", check_service)
        
        # 第一次检查：不健康
        result1 = checker.check_once("recovering_service")
        assert result1.status == HealthStatus.UNHEALTHY
        
        # 第二次检查：不健康
        result2 = checker.check_once("recovering_service")
        assert result2.status == HealthStatus.UNHEALTHY
        
        # 第三次检查：已恢复
        result3 = checker.check_once("recovering_service")
        assert result3.status == HealthStatus.HEALTHY


from qf_reliability.retry import RetryStrategy


class TestChaosResilience:
    """混沌弹性测试"""
    
    def test_system_survives_chaos(self):
        """测试系统在混沌中存活"""
        engine = ChaosEngine(
            failure_rate=0.3,
            failure_types=[FailureType.EXCEPTION, FailureType.DELAY],
            exception_types=[ValueError]
        )
        
        @engine.inject()
        @circuit_breaker(name="chaos_test", failure_threshold=10, timeout=0.1)
        @retry_with_backoff(max_attempts=2, base_delay=0.01, retry_on_exceptions=[ValueError])
        def resilient_service():
            return {"status": "ok"}
        
        # 多次调用，验证系统仍然可用
        success_count = 0
        for _ in range(20):
            try:
                result = resilient_service()
                if result and result.get("status") == "ok":
                    success_count += 1
            except Exception:
                pass  # 允许一些失败
        
        # 应该有一定数量的成功
        assert success_count >= 5
    
    def test_chaos_reveals_weaknesses(self):
        """测试混沌暴露弱点"""
        engine = ChaosEngine(failure_rate=0.5)
        
        # 一个没有适当保护的脆弱服务
        @engine.inject(failure_type=FailureType.EXCEPTION)
        def vulnerable_service():
            return "success"
        
        # 一个有保护的弹性服务
        @engine.inject(failure_type=FailureType.EXCEPTION)
        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def resilient_service():
            return "success"
        
        vulnerable_success = 0
        resilient_success = 0
        
        for _ in range(10):
            try:
                vulnerable_service()
                vulnerable_success += 1
            except Exception:
                pass
            
            try:
                resilient_service()
                resilient_success += 1
            except Exception:
                pass
        
        # 弹性服务应该有更高的成功率
        assert resilient_success >= vulnerable_success
