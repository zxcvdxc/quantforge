"""健康检查测试"""
import time
import pytest
from unittest.mock import Mock, patch

from qf_reliability.health_check import (
    HealthChecker,
    HealthStatus,
    HealthCheckResult,
    ServiceEndpoint,
    FailoverManager,
    health_check
)


@pytest.fixture(autouse=True)
def reset_health_checker():
    """重置健康检查器单例"""
    HealthChecker._instance = None
    yield
    HealthChecker._instance = None


class TestHealthChecker:
    """健康检查器测试"""
    
    def test_initial_state(self):
        """测试初始状态"""
        checker = HealthChecker()
        
        status = checker.get_overall_status()
        assert status["status"] == HealthStatus.UNKNOWN.name
        assert status["total"] == 0
    
    def test_register_check(self):
        """测试注册检查项"""
        checker = HealthChecker()
        
        def check_func():
            return True
        
        checker.register("test_service", check_func)
        
        assert "test_service" in checker._checks
    
    def test_check_once_success(self):
        """测试单次检查成功"""
        checker = HealthChecker()
        
        def check_func():
            return True
        
        checker.register("success_service", check_func)
        result = checker.check_once("success_service")
        
        assert result.name == "success_service"
        assert result.status == HealthStatus.HEALTHY
        assert result.is_healthy is True
    
    def test_check_once_failure(self):
        """测试单次检查失败"""
        checker = HealthChecker()
        
        def check_func():
            return False, "service unavailable"
        
        checker.register("fail_service", check_func)
        result = checker.check_once("fail_service")
        
        assert result.status == HealthStatus.UNHEALTHY
        assert result.message == "service unavailable"
    
    def test_check_once_exception(self):
        """测试检查异常"""
        checker = HealthChecker()
        
        def check_func():
            raise RuntimeError("check error")
        
        checker.register("error_service", check_func)
        result = checker.check_once("error_service")
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "check error" in result.message
    
    def test_check_all(self):
        """测试检查所有项"""
        checker = HealthChecker()
        
        checker.register("service1", lambda: True)
        checker.register("service2", lambda: False)
        
        results = checker.check_once()
        
        assert len(results) == 2
        assert results["service1"].is_healthy is True
        assert results["service2"].is_healthy is False
    
    def test_overall_status_healthy(self):
        """测试整体健康状态-健康"""
        checker = HealthChecker()
        
        checker.register("service1", lambda: True)
        checker.register("service2", lambda: True)
        
        checker.check_once()
        status = checker.get_overall_status()
        
        assert status["status"] == HealthStatus.HEALTHY.name
        assert status["healthy_count"] == 2
        assert status["unhealthy_count"] == 0
    
    def test_overall_status_degraded(self):
        """测试整体健康状态-降级"""
        checker = HealthChecker()
        
        checker.register("service1", lambda: True)
        checker.register("service2", lambda: False)
        
        checker.check_once()
        status = checker.get_overall_status()
        
        assert status["status"] == HealthStatus.DEGRADED.name
        assert status["healthy_count"] == 1
        assert status["unhealthy_count"] == 1
    
    def test_overall_status_unhealthy(self):
        """测试整体健康状态-不健康"""
        checker = HealthChecker()
        
        checker.register("service1", lambda: False)
        checker.register("service2", lambda: False)
        
        checker.check_once()
        status = checker.get_overall_status()
        
        assert status["status"] == HealthStatus.UNHEALTHY.name
        assert status["healthy_count"] == 0
        assert status["unhealthy_count"] == 2
    
    def test_check_timeout(self):
        """测试检查超时"""
        checker = HealthChecker(timeout=0.1)
        
        def slow_check():
            time.sleep(1.0)  # 比超时时间长
            return True
        
        checker.register("slow_service", slow_check)
        result = checker.check_once("slow_service")
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "timeout" in result.message.lower()
    
    def test_check_response_time(self):
        """测试响应时间记录"""
        checker = HealthChecker()
        
        def check_with_delay():
            time.sleep(0.05)
            return True
        
        checker.register("delay_service", check_with_delay)
        result = checker.check_once("delay_service")
        
        assert result.response_time_ms >= 50  # 至少50ms
    
    def test_history(self):
        """测试历史记录"""
        checker = HealthChecker(history_size=5)
        
        checker.register("test", lambda: True)
        
        # 执行多次检查
        for _ in range(3):
            checker.check_once("test")
        
        history = checker.get_history("test")
        
        assert len(history) == 3
        assert all(r.is_healthy for r in history)
    
    def test_history_limit(self):
        """测试历史记录限制"""
        checker = HealthChecker(history_size=3)
        
        checker.register("test", lambda: True)
        
        # 执行超过限制次数的检查
        for _ in range(5):
            checker.check_once("test")
        
        history = checker.get_history("test")
        
        # 应该只保留最近的3次
        assert len(history) == 3
    
    def test_unregister(self):
        """测试注销检查项"""
        checker = HealthChecker()
        
        checker.register("test", lambda: True)
        checker.unregister("test")
        
        assert "test" not in checker._checks
        
        with pytest.raises(ValueError):
            checker.check_once("test")
    
    def test_custom_timeout_per_check(self):
        """测试每个检查项的自定义超时"""
        checker = HealthChecker(timeout=1.0)
        
        def fast_check():
            return True
        
        # 为这个检查设置更短的超时
        checker.register("fast", fast_check, custom_timeout=0.5)
        
        result = checker.check_once("fast")
        assert result.is_healthy is True


class TestHealthCheckerAsync:
    """健康检查异步测试"""
    
    @pytest.mark.asyncio
    async def test_async_check(self):
        """测试异步检查支持"""
        # HealthChecker 目前使用线程来执行检查
        # 这里测试基本功能
        checker = HealthChecker()
        
        def async_compatible_check():
            return True
        
        checker.register("async_test", async_compatible_check)
        result = checker.check_once("async_test")
        
        assert result.is_healthy is True


class TestServiceEndpoint:
    """服务端点测试"""
    
    def test_endpoint_creation(self):
        """测试端点创建"""
        endpoint = ServiceEndpoint(
            name="primary",
            host="localhost",
            port=3306,
            weight=5
        )
        
        assert endpoint.name == "primary"
        assert endpoint.host == "localhost"
        assert endpoint.port == 3306
        assert endpoint.url == "http://localhost:3306"
        assert endpoint.weight == 5


class TestFailoverManager:
    """故障转移管理器测试"""
    
    def test_add_endpoint(self):
        """测试添加端点"""
        manager = FailoverManager()
        
        manager.add_endpoint("db", "primary", "192.168.1.1", 3306, weight=5)
        
        endpoints = manager.get_all_endpoints("db")
        assert len(endpoints) == 1
        assert endpoints[0].name == "primary"
    
    def test_get_healthy_endpoint(self):
        """测试获取健康端点"""
        manager = FailoverManager()
        
        manager.add_endpoint("db", "primary", "192.168.1.1", 3306)
        manager.update_health("db", "primary", HealthStatus.HEALTHY)
        
        endpoint = manager.get_endpoint("db")
        
        assert endpoint is not None
        assert endpoint.name == "primary"
    
    def test_get_endpoint_no_healthy(self):
        """测试没有健康端点时"""
        manager = FailoverManager()
        
        manager.add_endpoint("db", "primary", "192.168.1.1", 3306)
        manager.update_health("db", "primary", HealthStatus.UNHEALTHY)
        
        # 没有健康端点，但应该返回第一个（降级）
        endpoint = manager.get_endpoint("db")
        
        # 当前实现会返回第一个端点作为降级
        assert endpoint is not None
    
    def test_weighted_selection(self):
        """测试加权选择 - 优先选择权重高的"""
        manager = FailoverManager()
        
        manager.add_endpoint("db", "replica1", "192.168.1.2", 3306, weight=1)
        manager.add_endpoint("db", "replica2", "192.168.1.3", 3306, weight=2)
        
        manager.update_health("db", "replica1", HealthStatus.HEALTHY)
        manager.update_health("db", "replica2", HealthStatus.HEALTHY)
        
        # 使用 prefer_primary=False 应该优先选择权重高的
        endpoint = manager.get_endpoint("db", prefer_primary=False)
        assert endpoint.weight == 2


class TestHealthCheckDecorator:
    """健康检查装饰器测试"""
    
    def test_decorator(self):
        """测试装饰器"""
        @health_check(name="decorator_test", timeout=3.0)
        def my_check():
            return True
        
        result = my_check()
        assert result is True
        
        # 检查是否已注册
        assert hasattr(my_check, '_health_check_name')
        assert my_check._health_check_name == "decorator_test"


class TestHealthCheckerIntegration:
    """健康检查集成测试"""
    
    def test_start_stop(self):
        """测试启动和停止"""
        checker = HealthChecker(check_interval=0.1)
        
        checker.register("test", lambda: True)
        
        checker.start()
        assert checker._running is True
        
        time.sleep(0.2)  # 等待至少一次检查
        
        checker.stop()
        assert checker._running is False
    
    def test_check_with_metadata(self):
        """测试带元数据的检查"""
        checker = HealthChecker()
        
        def check_with_meta():
            return {
                "healthy": True,
                "message": "ok",
                "metadata": {"version": "1.0", "connections": 10}
            }
        
        checker.register("meta_test", check_with_meta)
        result = checker.check_once("meta_test")
        
        assert result.is_healthy is True
        assert result.metadata["version"] == "1.0"
