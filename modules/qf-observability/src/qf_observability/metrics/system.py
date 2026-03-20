"""
系统指标模块
提供CPU、内存、连接数等系统指标采集
"""

import os
import time
import threading
import psutil
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from collections import deque

from .collector import MetricCollector, MetricValue, Counter, Gauge


@dataclass
class ResourceSnapshot:
    """资源快照"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    disk_percent: float
    network_io_bytes_sent: int
    network_io_bytes_recv: int
    connections_count: int
    threads_count: int
    processes_count: int
    load_average: tuple


class SystemMetrics:
    """系统指标"""
    
    def __init__(self, namespace: str = 'quantforge'):
        self.namespace = namespace
        
        # CPU metrics
        self.cpu_usage = Gauge(
            f"{namespace}_cpu_usage_percent",
            "CPU usage percentage",
        )
        self.cpu_usage_per_core: Dict[int, Gauge] = {}
        
        # Memory metrics
        self.memory_usage = Gauge(
            f"{namespace}_memory_usage_percent",
            "Memory usage percentage",
        )
        self.memory_used_bytes = Gauge(
            f"{namespace}_memory_used_bytes",
            "Memory used in bytes",
        )
        self.memory_available_bytes = Gauge(
            f"{namespace}_memory_available_bytes",
            "Memory available in bytes",
        )
        
        # Disk metrics
        self.disk_usage = Gauge(
            f"{namespace}_disk_usage_percent",
            "Disk usage percentage",
        )
        self.disk_used_bytes = Gauge(
            f"{namespace}_disk_used_bytes",
            "Disk used in bytes",
        )
        self.disk_free_bytes = Gauge(
            f"{namespace}_disk_free_bytes",
            "Disk free in bytes",
        )
        
        # Network metrics
        self.network_bytes_sent = Counter(
            f"{namespace}_network_bytes_sent_total",
            "Total network bytes sent",
        )
        self.network_bytes_recv = Counter(
            f"{namespace}_network_bytes_recv_total",
            "Total network bytes received",
        )
        self.network_connections = Gauge(
            f"{namespace}_network_connections",
            "Number of network connections",
        )
        
        # Process metrics
        self.process_threads = Gauge(
            f"{namespace}_process_threads",
            "Number of threads in process",
        )
        self.process_memory = Gauge(
            f"{namespace}_process_memory_bytes",
            "Process memory usage in bytes",
        )
        self.process_cpu = Gauge(
            f"{namespace}_process_cpu_percent",
            "Process CPU usage percentage",
        )
        self.open_files = Gauge(
            f"{namespace}_process_open_files",
            "Number of open files",
        )
        
        # Load average
        self.load_average_1m = Gauge(
            f"{namespace}_load_average_1m",
            "System load average (1 minute)",
        )
        self.load_average_5m = Gauge(
            f"{namespace}_load_average_5m",
            "System load average (5 minutes)",
        )
        self.load_average_15m = Gauge(
            f"{namespace}_load_average_15m",
            "System load average (15 minutes)",
        )
        
        # History for trending
        self._history: deque = deque(maxlen=3600)  # 1 hour at 1 sample/second
        self._last_network_io: Optional[tuple] = None
        self._last_collect_time: Optional[float] = None
    
    def collect(self) -> Dict[str, Any]:
        """采集系统指标"""
        metrics = {}
        
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        self.cpu_usage.set(cpu_percent)
        metrics['cpu_percent'] = cpu_percent
        
        # CPU per core
        per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)
        for i, percent in enumerate(per_cpu):
            if i not in self.cpu_usage_per_core:
                self.cpu_usage_per_core[i] = Gauge(
                    f"{self.namespace}_cpu_core_{i}_usage_percent",
                    f"CPU core {i} usage percentage",
                )
            self.cpu_usage_per_core[i].set(percent)
        
        # Memory
        memory = psutil.virtual_memory()
        self.memory_usage.set(memory.percent)
        self.memory_used_bytes.set(memory.used)
        self.memory_available_bytes.set(memory.available)
        metrics['memory'] = {
            'percent': memory.percent,
            'used_bytes': memory.used,
            'available_bytes': memory.available,
            'total_bytes': memory.total,
        }
        
        # Disk
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        self.disk_usage.set(disk_percent)
        self.disk_used_bytes.set(disk.used)
        self.disk_free_bytes.set(disk.free)
        metrics['disk'] = {
            'percent': disk_percent,
            'used_bytes': disk.used,
            'free_bytes': disk.free,
        }
        
        # Network
        net_io = psutil.net_io_counters()
        if self._last_network_io:
            bytes_sent = net_io.bytes_sent - self._last_network_io[0]
            bytes_recv = net_io.bytes_recv - self._last_network_io[1]
            self.network_bytes_sent.inc(bytes_sent)
            self.network_bytes_recv.inc(bytes_recv)
        self._last_network_io = (net_io.bytes_sent, net_io.bytes_recv)
        
        # Connections
        try:
            connections = len(psutil.net_connections())
            self.network_connections.set(connections)
            metrics['connections'] = connections
        except (psutil.AccessDenied, PermissionError):
            pass
        
        # Process info
        process = psutil.Process()
        self.process_threads.set(process.num_threads())
        self.process_memory.set(process.memory_info().rss)
        self.process_cpu.set(process.cpu_percent(interval=0.1))
        try:
            self.open_files.set(len(process.open_files()))
        except (psutil.AccessDenied, PermissionError):
            pass
        
        metrics['process'] = {
            'threads': process.num_threads(),
            'memory_rss': process.memory_info().rss,
            'cpu_percent': process.cpu_percent(interval=0.1),
        }
        
        # Load average (Unix only)
        try:
            load1, load5, load15 = os.getloadavg()
            self.load_average_1m.set(load1)
            self.load_average_5m.set(load5)
            self.load_average_15m.set(load15)
            metrics['load_average'] = (load1, load5, load15)
        except (AttributeError, OSError):
            pass
        
        # Store snapshot
        snapshot = ResourceSnapshot(
            timestamp=datetime.utcnow(),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_bytes=memory.used,
            memory_total_bytes=memory.total,
            disk_percent=disk_percent,
            network_io_bytes_sent=net_io.bytes_sent,
            network_io_bytes_recv=net_io.bytes_recv,
            connections_count=metrics.get('connections', 0),
            threads_count=process.num_threads(),
            processes_count=len(psutil.pids()),
            load_average=metrics.get('load_average', (0, 0, 0)),
        )
        self._history.append(snapshot)
        
        self._last_collect_time = time.time()
        
        return metrics
    
    def get_history(self, duration_seconds: int = 300) -> List[ResourceSnapshot]:
        """获取历史记录"""
        cutoff = datetime.utcnow().timestamp() - duration_seconds
        return [s for s in self._history if s.timestamp.timestamp() >= cutoff]
    
    def get_average(self, duration_seconds: int = 300) -> Dict[str, float]:
        """获取平均值"""
        history = self.get_history(duration_seconds)
        if not history:
            return {}
        
        return {
            'cpu_avg': sum(s.cpu_percent for s in history) / len(history),
            'memory_avg': sum(s.memory_percent for s in history) / len(history),
            'connections_avg': sum(s.connections_count for s in history) / len(history),
        }


class ResourceUsageCollector(MetricCollector):
    """资源使用采集器 - 实现MetricCollector接口"""
    
    def __init__(self, namespace: str = 'quantforge'):
        self.system_metrics = SystemMetrics(namespace)
    
    def get_name(self) -> str:
        return 'system'
    
    def collect(self) -> List[MetricValue]:
        """采集系统指标"""
        metrics = self.system_metrics.collect()
        timestamp = datetime.utcnow()
        
        results = []
        
        # CPU
        results.append(MetricValue(
            name='cpu_usage_percent',
            value=metrics.get('cpu_percent', 0),
            timestamp=timestamp,
            labels={},
            metric_type='gauge',
        ))
        
        # Memory
        memory = metrics.get('memory', {})
        results.append(MetricValue(
            name='memory_usage_percent',
            value=memory.get('percent', 0),
            timestamp=timestamp,
            labels={},
            metric_type='gauge',
        ))
        results.append(MetricValue(
            name='memory_used_bytes',
            value=memory.get('used_bytes', 0),
            timestamp=timestamp,
            labels={},
            metric_type='gauge',
        ))
        
        # Disk
        disk = metrics.get('disk', {})
        results.append(MetricValue(
            name='disk_usage_percent',
            value=disk.get('percent', 0),
            timestamp=timestamp,
            labels={},
            metric_type='gauge',
        ))
        
        # Connections
        results.append(MetricValue(
            name='network_connections',
            value=metrics.get('connections', 0),
            timestamp=timestamp,
            labels={},
            metric_type='gauge',
        ))
        
        # Process
        process = metrics.get('process', {})
        results.append(MetricValue(
            name='process_threads',
            value=process.get('threads', 0),
            timestamp=timestamp,
            labels={},
            metric_type='gauge',
        ))
        results.append(MetricValue(
            name='process_memory_bytes',
            value=process.get('memory_rss', 0),
            timestamp=timestamp,
            labels={},
            metric_type='gauge',
        ))
        
        return results


class ConnectionPoolMetrics:
    """连接池指标"""
    
    def __init__(self, namespace: str = 'quantforge'):
        self.namespace = namespace
        
        self.pool_size = Gauge(
            f"{namespace}_connection_pool_size",
            "Current connection pool size",
        )
        self.pool_max_size = Gauge(
            f"{namespace}_connection_pool_max_size",
            "Maximum connection pool size",
        )
        self.connections_in_use = Gauge(
            f"{namespace}_connections_in_use",
            "Number of connections currently in use",
        )
        self.connections_waiting = Gauge(
            f"{namespace}_connections_waiting",
            "Number of connections waiting",
        )
        self.connection_requests_total = Counter(
            f"{namespace}_connection_requests_total",
            "Total number of connection requests",
        )
        self.connection_waits_total = Counter(
            f"{namespace}_connection_waits_total",
            "Total number of connection waits",
        )
        self.connection_timeouts_total = Counter(
            f"{namespace}_connection_timeouts_total",
            "Total number of connection timeouts",
        )
    
    def update_pool_size(self, size: int, max_size: int):
        """更新连接池大小"""
        self.pool_size.set(size)
        self.pool_max_size.set(max_size)
    
    def record_connection_request(self, had_to_wait: bool = False):
        """记录连接请求"""
        self.connection_requests_total.inc()
        if had_to_wait:
            self.connection_waits_total.inc()
    
    def record_connection_timeout(self):
        """记录连接超时"""
        self.connection_timeouts_total.inc()
    
    def update_in_use(self, count: int):
        """更新正在使用的连接数"""
        self.connections_in_use.set(count)
    
    def update_waiting(self, count: int):
        """更新等待的连接数"""
        self.connections_waiting.set(count)
