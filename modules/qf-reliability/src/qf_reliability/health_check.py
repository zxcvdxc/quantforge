"""健康检查 (Health Check)

依赖服务健康探测、自动故障转移、服务注册/发现
"""
import time
import asyncio
import logging
import threading
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Any, Union
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = auto()      # 健康
    DEGRADED = auto()     # 降级（部分功能异常）
    UNHEALTHY = auto()    # 不健康
    UNKNOWN = auto()      # 未知（未检查）


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    name: str
    status: HealthStatus
    response_time_ms: float
    timestamp: float
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY


@dataclass
class ServiceEndpoint:
    """服务端点"""
    name: str
    host: str
    port: int
    protocol: str = "http"
    weight: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def url(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"


class HealthChecker:
    """健康检查器
    
    功能:
    - 定期检查依赖服务健康状态
    - 自动故障转移
    - 服务发现
    - 健康历史记录
    
    使用示例:
        checker = HealthChecker(check_interval=30.0)
        
        # 注册检查项
        checker.register("mysql", check_mysql_connection)
        checker.register("redis", check_redis_connection)
        
        # 启动检查
        checker.start()
        
        # 获取健康状态
        status = checker.get_overall_status()
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if kwargs.pop('_singleton', True):
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                return cls._instance
        return super().__new__(cls)
    
    def __init__(
        self,
        check_interval: float = 30.0,
        timeout: float = 5.0,
        history_size: int = 100
    ):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.check_interval = check_interval
        self.timeout = timeout
        self.history_size = history_size
        
        # 检查项: name -> check_function
        self._checks: Dict[str, Callable] = {}
        
        # 最新结果: name -> HealthCheckResult
        self._latest_results: Dict[str, HealthCheckResult] = {}
        
        # 历史记录: name -> deque of HealthCheckResult
        self._history: Dict[str, deque] = {}
        
        # 服务端点: service_name -> List[ServiceEndpoint]
        self._endpoints: Dict[str, List[ServiceEndpoint]] = {}
        self._healthy_endpoints: Dict[str, deque] = {}
        
        # 运行状态
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
    
    def register(
        self,
        name: str,
        check_func: Callable,
        custom_timeout: Optional[float] = None
    ):
        """
        注册健康检查项
        
        Args:
            name: 检查项名称
            check_func: 检查函数，返回 bool 或 (bool, str)
            custom_timeout: 自定义超时时间
        """
        with self._lock:
            self._checks[name] = {
                "func": check_func,
                "timeout": custom_timeout or self.timeout
            }
            self._history[name] = deque(maxlen=self.history_size)
            logger.info(f"Registered health check: {name}")
    
    def unregister(self, name: str):
        """注销健康检查项"""
        with self._lock:
            self._checks.pop(name, None)
            self._latest_results.pop(name, None)
            self._history.pop(name, None)
            logger.info(f"Unregistered health check: {name}")
    
    def register_service(
        self,
        service_name: str,
        endpoints: List[ServiceEndpoint]
    ):
        """
        注册服务及其端点
        
        Args:
            service_name: 服务名称
            endpoints: 端点列表
        """
        with self._lock:
            self._endpoints[service_name] = endpoints
            self._healthy_endpoints[service_name] = deque(endpoints)
            logger.info(f"Registered service '{service_name}' with {len(endpoints)} endpoints")
    
    def _execute_check(self, name: str, check_info: Dict) -> HealthCheckResult:
        """执行单个检查"""
        start_time = time.time()
        timeout = check_info["timeout"]
        check_func = check_info["func"]
        
        try:
            # 使用线程执行检查函数以支持超时
            result_queue = deque(maxlen=1)
            
            def run_check():
                try:
                    result = check_func()
                    result_queue.append(result)
                except Exception as e:
                    result_queue.append(e)
            
            check_thread = threading.Thread(target=run_check)
            check_thread.daemon = True
            check_thread.start()
            check_thread.join(timeout=timeout)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            if check_thread.is_alive():
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    response_time_ms=elapsed_ms,
                    timestamp=start_time,
                    message=f"Health check timeout after {timeout}s"
                )
            
            if not result_queue:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    response_time_ms=elapsed_ms,
                    timestamp=start_time,
                    message="No result from health check"
                )
            
            result = result_queue[0]
            
            if isinstance(result, Exception):
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    response_time_ms=elapsed_ms,
                    timestamp=start_time,
                    message=str(result)
                )
            
            # 解析结果
            if isinstance(result, tuple):
                is_healthy, message = result[0], result[1] if len(result) > 1 else ""
                metadata = result[2] if len(result) > 2 else {}
            elif isinstance(result, dict):
                is_healthy = result.get("healthy", False)
                message = result.get("message", "")
                metadata = result.get("metadata", {})
            else:
                is_healthy = bool(result)
                message = ""
                metadata = {}
            
            status = HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY
            
            return HealthCheckResult(
                name=name,
                status=status,
                response_time_ms=elapsed_ms,
                timestamp=start_time,
                message=message,
                metadata=metadata
            )
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=elapsed_ms,
                timestamp=start_time,
                message=f"Check execution error: {e}"
            )
    
    def check_once(self, name: Optional[str] = None) -> Union[HealthCheckResult, Dict[str, HealthCheckResult]]:
        """
        执行一次健康检查
        
        Args:
            name: 特定检查项名称，None表示检查所有
            
        Returns:
            检查结果或所有结果的字典
        """
        with self._lock:
            if name:
                if name not in self._checks:
                    raise ValueError(f"Unknown health check: {name}")
                result = self._execute_check(name, self._checks[name])
                self._latest_results[name] = result
                self._history[name].append(result)
                return result
            else:
                results = {}
                for name, check_info in self._checks.items():
                    result = self._execute_check(name, check_info)
                    self._latest_results[name] = result
                    self._history[name].append(result)
                    results[name] = result
                return results
    
    def start(self):
        """启动定期检查"""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._check_loop)
        self._thread.daemon = True
        self._thread.start()
        logger.info(f"Health checker started (interval: {self.check_interval}s)")
    
    def stop(self):
        """停止定期检查"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Health checker stopped")
    
    def _check_loop(self):
        """检查循环"""
        while self._running and not self._stop_event.is_set():
            try:
                self.check_once()
                self._update_service_endpoints()
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
            
            self._stop_event.wait(timeout=self.check_interval)
    
    def _update_service_endpoints(self):
        """更新服务端点健康状态"""
        for service_name, endpoints in self._endpoints.items():
            healthy = []
            for endpoint in endpoints:
                # 检查端点健康状态
                result = self._latest_results.get(f"{service_name}:{endpoint.name}")
                if result and result.is_healthy:
                    healthy.append(endpoint)
            
            self._healthy_endpoints[service_name] = deque(healthy)
    
    def get_status(self, name: str) -> Optional[HealthCheckResult]:
        """获取特定检查项的最新状态"""
        with self._lock:
            return self._latest_results.get(name)
    
    def get_all_status(self) -> Dict[str, HealthCheckResult]:
        """获取所有检查项的最新状态"""
        with self._lock:
            return self._latest_results.copy()
    
    def get_overall_status(self) -> Dict[str, Any]:
        """
        获取整体健康状态
        
        Returns:
            包含整体状态和各项检查结果的字典
        """
        with self._lock:
            results = self._latest_results.copy()
            
            if not results:
                return {
                    "status": HealthStatus.UNKNOWN.name,
                    "healthy_count": 0,
                    "unhealthy_count": 0,
                    "total": 0,
                    "checks": {}
                }
            
            healthy_count = sum(1 for r in results.values() if r.is_healthy)
            unhealthy_count = len(results) - healthy_count
            
            if unhealthy_count == 0:
                overall = HealthStatus.HEALTHY
            elif healthy_count == 0:
                overall = HealthStatus.UNHEALTHY
            else:
                overall = HealthStatus.DEGRADED
            
            return {
                "status": overall.name,
                "healthy_count": healthy_count,
                "unhealthy_count": unhealthy_count,
                "total": len(results),
                "timestamp": time.time(),
                "checks": {
                    name: {
                        "status": result.status.name,
                        "response_time_ms": result.response_time_ms,
                        "message": result.message
                    }
                    for name, result in results.items()
                }
            }
    
    def get_history(self, name: str, limit: Optional[int] = None) -> List[HealthCheckResult]:
        """获取检查历史"""
        with self._lock:
            history = list(self._history.get(name, []))
            if limit:
                history = history[-limit:]
            return history
    
    def get_healthy_endpoint(self, service_name: str) -> Optional[ServiceEndpoint]:
        """
        获取健康的端点（轮询）
        
        Args:
            service_name: 服务名称
            
        Returns:
            健康端点或None
        """
        with self._lock:
            endpoints = self._healthy_endpoints.get(service_name, deque())
            if not endpoints:
                return None
            
            # 轮询选择
            endpoint = endpoints.popleft()
            endpoints.append(endpoint)
            return endpoint


def health_check(
    name: Optional[str] = None,
    timeout: float = 5.0,
    check_interval: float = 30.0
):
    """
    健康检查装饰器
    
    Args:
        name: 检查项名称
        timeout: 超时时间
        check_interval: 检查间隔
        
    使用示例:
        @health_check(name="mysql", timeout=3.0)
        def check_mysql():
            return db.ping()
            
        @health_check(name="api", check_interval=60.0)
        async def check_api():
            return await fetch_status()
    """
    def decorator(func: Callable) -> Callable:
        check_name = name or func.__name__
        checker = HealthChecker()
        checker.register(check_name, func, timeout)
        
        # 返回原函数，但添加健康检查能力
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        wrapper._health_check_name = check_name
        wrapper._health_checker = checker
        return wrapper
    
    return decorator


class FailoverManager:
    """故障转移管理器
    
    管理多个服务端点，自动故障转移
    
    使用示例:
        failover = FailoverManager()
        
        # 添加端点
        failover.add_endpoint("db", "primary", "192.168.1.1", 3306)
        failover.add_endpoint("db", "replica", "192.168.1.2", 3306)
        
        # 使用
        endpoint = failover.get_endpoint("db")
        if endpoint:
            connect_to(endpoint)
    """
    
    def __init__(self):
        self._endpoints: Dict[str, Dict[str, ServiceEndpoint]] = {}
        self._health_status: Dict[str, Dict[str, HealthStatus]] = {}
        self._lock = threading.RLock()
    
    def add_endpoint(
        self,
        service_name: str,
        endpoint_name: str,
        host: str,
        port: int,
        weight: int = 1,
        **kwargs
    ):
        """添加服务端点"""
        with self._lock:
            if service_name not in self._endpoints:
                self._endpoints[service_name] = {}
                self._health_status[service_name] = {}
            
            endpoint = ServiceEndpoint(
                name=endpoint_name,
                host=host,
                port=port,
                weight=weight,
                metadata=kwargs
            )
            self._endpoints[service_name][endpoint_name] = endpoint
            self._health_status[service_name][endpoint_name] = HealthStatus.UNKNOWN
    
    def update_health(self, service_name: str, endpoint_name: str, status: HealthStatus):
        """更新端点健康状态"""
        with self._lock:
            if service_name in self._health_status:
                self._health_status[service_name][endpoint_name] = status
    
    def get_endpoint(self, service_name: str, prefer_primary: bool = True) -> Optional[ServiceEndpoint]:
        """
        获取可用端点
        
        Args:
            service_name: 服务名称
            prefer_primary: 是否优先主节点
            
        Returns:
            可用端点或None
        """
        with self._lock:
            if service_name not in self._endpoints:
                return None
            
            endpoints = self._endpoints[service_name]
            health_status = self._health_status[service_name]
            
            # 获取健康端点
            healthy_endpoints = [
                ep for name, ep in endpoints.items()
                if health_status.get(name) == HealthStatus.HEALTHY
            ]
            
            if healthy_endpoints:
                # 按权重选择
                if prefer_primary and healthy_endpoints[0].weight > 0:
                    return healthy_endpoints[0]
                return max(healthy_endpoints, key=lambda ep: ep.weight)
            
            # 如果没有健康端点，返回第一个（可能是降级）
            return next(iter(endpoints.values()), None)
    
    def get_all_endpoints(self, service_name: str) -> List[ServiceEndpoint]:
        """获取所有端点"""
        with self._lock:
            return list(self._endpoints.get(service_name, {}).values())
