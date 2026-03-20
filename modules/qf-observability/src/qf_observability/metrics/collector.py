"""
指标采集器模块
提供统一的指标采集接口
"""

import time
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Set
from datetime import datetime


@dataclass
class MetricValue:
    """指标值"""
    name: str
    value: float
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)
    metric_type: str = 'gauge'  # gauge, counter, histogram, summary


class MetricCollector(ABC):
    """指标采集器基类"""
    
    @abstractmethod
    def collect(self) -> List[MetricValue]:
        """采集指标"""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """获取采集器名称"""
        pass


class MetricsCollector:
    """统一指标采集器"""
    
    _instance: Optional['MetricsCollector'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._collectors: Dict[str, MetricCollector] = {}
        self._custom_metrics: Dict[str, Any] = {}
        self._callbacks: List[Callable] = []
        self._lock = threading.RLock()
        self._initialized = True
        self._enabled = True
    
    def register_collector(self, collector: MetricCollector):
        """注册指标采集器"""
        with self._lock:
            self._collectors[collector.get_name()] = collector
    
    def unregister_collector(self, name: str):
        """注销指标采集器"""
        with self._lock:
            self._collectors.pop(name, None)
    
    def register_callback(self, callback: Callable):
        """注册采集回调"""
        with self._lock:
            self._callbacks.append(callback)
    
    def collect_all(self) -> Dict[str, List[MetricValue]]:
        """采集所有指标"""
        if not self._enabled:
            return {}
        
        results = {}
        
        with self._lock:
            # Collect from all registered collectors
            for name, collector in self._collectors.items():
                try:
                    metrics = collector.collect()
                    if metrics:
                        results[name] = metrics
                except Exception as e:
                    results[name] = [
                        MetricValue(
                            name=f"{name}_collection_error",
                            value=1.0,
                            timestamp=datetime.utcnow(),
                            labels={'error': str(e)},
                        )
                    ]
            
            # Execute callbacks
            for callback in self._callbacks:
                try:
                    callback(results)
                except Exception:
                    pass
        
        return results
    
    def record_custom_metric(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        metric_type: str = 'gauge',
    ):
        """记录自定义指标"""
        with self._lock:
            if name not in self._custom_metrics:
                self._custom_metrics[name] = []
            
            self._custom_metrics[name].append(MetricValue(
                name=name,
                value=value,
                timestamp=datetime.utcnow(),
                labels=labels or {},
                metric_type=metric_type,
            ))
    
    def get_custom_metrics(self, name: Optional[str] = None) -> Dict[str, List[MetricValue]]:
        """获取自定义指标"""
        with self._lock:
            if name:
                return {name: self._custom_metrics.get(name, [])}
            return dict(self._custom_metrics)
    
    def clear_custom_metrics(self, name: Optional[str] = None):
        """清除自定义指标"""
        with self._lock:
            if name:
                self._custom_metrics.pop(name, None)
            else:
                self._custom_metrics.clear()
    
    def enable(self):
        """启用采集"""
        self._enabled = True
    
    def disable(self):
        """禁用采集"""
        self._enabled = False
    
    def reset(self):
        """重置采集器"""
        with self._lock:
            self._collectors.clear()
            self._custom_metrics.clear()
            self._callbacks.clear()
            self._enabled = True


# Global collector instance
_collector_instance: Optional[MetricsCollector] = None


def get_collector() -> MetricsCollector:
    """获取全局采集器实例"""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = MetricsCollector()
    return _collector_instance


def reset_collector():
    """重置全局采集器"""
    global _collector_instance
    _collector_instance = MetricsCollector()


class Counter:
    """计数器"""
    
    def __init__(self, name: str, description: str = '', labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value = 0.0
        self._lock = threading.Lock()
    
    def inc(self, amount: float = 1.0):
        """增加计数"""
        with self._lock:
            self._value += amount
    
    def get(self) -> float:
        """获取当前值"""
        with self._lock:
            return self._value
    
    def reset(self):
        """重置计数器"""
        with self._lock:
            self._value = 0.0


class Gauge:
    """仪表盘"""
    
    def __init__(self, name: str, description: str = '', labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value = 0.0
        self._lock = threading.Lock()
    
    def set(self, value: float):
        """设置值"""
        with self._lock:
            self._value = value
    
    def inc(self, amount: float = 1.0):
        """增加值"""
        with self._lock:
            self._value += amount
    
    def dec(self, amount: float = 1.0):
        """减少值"""
        with self._lock:
            self._value -= amount
    
    def get(self) -> float:
        """获取当前值"""
        with self._lock:
            return self._value


class Histogram:
    """直方图"""
    
    DEFAULT_BUCKETS = [.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0]
    
    def __init__(
        self,
        name: str,
        description: str = '',
        labels: Optional[Dict[str, str]] = None,
        buckets: Optional[List[float]] = None,
    ):
        self.name = name
        self.description = description
        self.labels = labels or {}
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        self._counts: Dict[float, int] = {b: 0 for b in self.buckets}
        self._sum = 0.0
        self._count = 0
        self._lock = threading.Lock()
    
    def observe(self, value: float):
        """观察一个值"""
        with self._lock:
            self._sum += value
            self._count += 1
            
            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[bucket] += 1
    
    def get(self) -> Dict[str, Any]:
        """获取直方图数据"""
        with self._lock:
            return {
                'count': self._count,
                'sum': self._sum,
                'buckets': dict(self._counts),
            }


class Summary:
    """摘要"""
    
    DEFAULT_QUANTILES = [.5, .75, .9, .95, .99]
    
    def __init__(
        self,
        name: str,
        description: str = '',
        labels: Optional[Dict[str, str]] = None,
        max_age_seconds: float = 600,
        age_buckets: int = 5,
    ):
        self.name = name
        self.description = description
        self.labels = labels or {}
        self.max_age_seconds = max_age_seconds
        self.age_buckets = age_buckets
        self._values: List[tuple] = []  # (timestamp, value)
        self._lock = threading.Lock()
    
    def observe(self, value: float):
        """观察一个值"""
        with self._lock:
            now = time.time()
            self._values.append((now, value))
            self._cleanup_old_values(now)
    
    def _cleanup_old_values(self, now: float):
        """清理过期值"""
        cutoff = now - self.max_age_seconds
        self._values = [(t, v) for t, v in self._values if t >= cutoff]
    
    def get(self, quantiles: Optional[List[float]] = None) -> Dict[str, Any]:
        """获取摘要统计"""
        with self._lock:
            if not self._values:
                return {'count': 0, 'sum': 0.0, 'quantiles': {}}
            
            now = time.time()
            self._cleanup_old_values(now)
            
            values = sorted([v for _, v in self._values])
            quantiles = quantiles or self.DEFAULT_QUANTILES
            
            quantile_values = {}
            for q in quantiles:
                idx = int(len(values) * q)
                if idx >= len(values):
                    idx = len(values) - 1
                quantile_values[q] = values[idx]
            
            return {
                'count': len(values),
                'sum': sum(values),
                'quantiles': quantile_values,
            }


class Timer:
    """计时器上下文管理器"""
    
    def __init__(self, histogram: Optional[Histogram] = None, summary: Optional[Summary] = None):
        self.histogram = histogram
        self.summary = summary
        self._start_time: Optional[float] = None
        self.duration: Optional[float] = None
    
    def __enter__(self):
        self._start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.time() - self._start_time
        
        if self.histogram:
            self.histogram.observe(self.duration)
        
        if self.summary:
            self.summary.observe(self.duration)
    
    def observe(self, duration: float):
        """手动记录时长"""
        self.duration = duration
        
        if self.histogram:
            self.histogram.observe(duration)
        
        if self.summary:
            self.summary.observe(duration)


def timed(histogram: Optional[Histogram] = None, summary: Optional[Summary] = None):
    """函数计时装饰器"""
    def decorator(func):
        nonlocal histogram, summary
        
        # Create default histogram if not provided
        if histogram is None:
            histogram = Histogram(f"{func.__name__}_duration_seconds")
        
        def wrapper(*args, **kwargs):
            with Timer(histogram, summary):
                return func(*args, **kwargs)
        
        return wrapper
    return decorator
