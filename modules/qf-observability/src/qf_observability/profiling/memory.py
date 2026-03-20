"""
内存剖析模块
提供内存泄漏检测和内存使用分析
"""

import gc
import sys
import threading
from typing import Optional, Dict, List, Any, Type
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import psutil
import objgraph


@dataclass
class MemorySnapshot:
    """内存快照"""
    timestamp: datetime
    rss_bytes: int
    vms_bytes: int
    shared_bytes: int
    heap_size: int
    object_count: int
    gc_objects: int


@dataclass
class ObjectGrowth:
    """对象增长"""
    type_name: str
    count_before: int
    count_after: int
    growth: int


class MemoryProfiler:
    """内存剖析器"""
    
    _instance: Optional['MemoryProfiler'] = None
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
        
        self._snapshots: List[MemorySnapshot] = []
        self._enabled = True
        self._max_snapshots = 100
        self._lock = threading.RLock()
        self._initialized = True
        self._baseline_objects: Optional[Dict[str, int]] = None
    
    def enable(self):
        """启用"""
        self._enabled = True
    
    def disable(self):
        """禁用"""
        self._enabled = False
    
    def take_snapshot(self) -> MemorySnapshot:
        """拍摄内存快照"""
        if not self._enabled:
            return None
        
        process = psutil.Process()
        mem_info = process.memory_info()
        
        snapshot = MemorySnapshot(
            timestamp=datetime.utcnow(),
            rss_bytes=mem_info.rss,
            vms_bytes=mem_info.vms,
            shared_bytes=getattr(mem_info, 'shared', 0),
            heap_size=self._get_heap_size(),
            object_count=len(gc.get_objects()),
            gc_objects=len(gc.garbage) if hasattr(gc, 'garbage') else 0,
        )
        
        with self._lock:
            self._snapshots.append(snapshot)
            if len(self._snapshots) > self._max_snapshots:
                self._snapshots.pop(0)
        
        return snapshot
    
    def _get_heap_size(self) -> int:
        """获取堆大小"""
        import sys
        if hasattr(sys, 'gettotalrefcount'):
            # Debug build
            return sys.gettotalrefcount()
        return 0
    
    def get_current_usage(self) -> Dict[str, int]:
        """获取当前内存使用"""
        process = psutil.Process()
        mem_info = process.memory_info()
        
        return {
            'rss_bytes': mem_info.rss,
            'vms_bytes': mem_info.vms,
            'shared_bytes': getattr(mem_info, 'shared', 0),
            'percent': process.memory_percent(),
            'object_count': len(gc.get_objects()),
        }
    
    def get_snapshots(self, count: Optional[int] = None) -> List[MemorySnapshot]:
        """获取快照历史"""
        with self._lock:
            if count:
                return self._snapshots[-count:]
            return list(self._snapshots)
    
    def detect_growth(self, top_n: int = 20) -> List[ObjectGrowth]:
        """检测对象增长"""
        current_counts = objgraph.typestats()
        
        if self._baseline_objects is None:
            self._baseline_objects = current_counts
            return []
        
        growth = []
        for type_name, current_count in current_counts.items():
            baseline_count = self._baseline_objects.get(type_name, 0)
            if current_count > baseline_count:
                growth.append(ObjectGrowth(
                    type_name=type_name,
                    count_before=baseline_count,
                    count_after=current_count,
                    growth=current_count - baseline_count,
                ))
        
        growth.sort(key=lambda x: x.growth, reverse=True)
        return growth[:top_n]
    
    def set_baseline(self):
        """设置基线"""
        gc.collect()
        self._baseline_objects = objgraph.typestats()
    
    def find_leaking_types(self, min_growth: int = 10) -> List[str]:
        """查找可能泄漏的类型"""
        growth = self.detect_growth()
        return [g.type_name for g in growth if g.growth >= min_growth]
    
    def get_most_common_types(self, limit: int = 20) -> List[tuple]:
        """获取最常见的对象类型"""
        return objgraph.most_common_types(limit=limit)
    
    def get_backrefs(self, obj, max_depth: int = 3):
        """获取对象引用链"""
        return objgraph.find_backref_chain(
            obj,
            objgraph.is_proper_module,
            max_depth=max_depth,
        )
    
    def show_growth(self, limit: int = 10) -> str:
        """显示增长情况"""
        import io
        output = io.StringIO()
        objgraph.show_growth(limit=limit, file=output)
        return output.getvalue()


def get_memory_usage() -> Dict[str, Any]:
    """获取内存使用情况"""
    process = psutil.Process()
    mem_info = process.memory_info()
    
    return {
        'rss_mb': mem_info.rss / 1024 / 1024,
        'vms_mb': mem_info.vms / 1024 / 1024,
        'percent': process.memory_percent(),
        'object_count': len(gc.get_objects()),
    }


def detect_memory_leaks(iterations: int = 3, threshold_mb: float = 10.0) -> Dict[str, Any]:
    """检测内存泄漏"""
    profiler = MemoryProfiler()
    
    # Force garbage collection
    gc.collect()
    gc.collect()
    
    # Take initial snapshot
    initial = profiler.get_current_usage()
    
    # Track growth over iterations
    growth_data = []
    for i in range(iterations):
        gc.collect()
        current = profiler.get_current_usage()
        
        growth = (current['rss_bytes'] - initial['rss_bytes']) / 1024 / 1024
        growth_data.append({
            'iteration': i,
            'growth_mb': growth,
            'object_count': current['object_count'],
        })
        
        if growth > threshold_mb:
            break
    
    # Check for potential leaks
    final_growth = growth_data[-1]['growth_mb'] if growth_data else 0
    
    return {
        'has_leak': final_growth > threshold_mb,
        'growth_mb': final_growth,
        'initial_usage_mb': initial['rss_bytes'] / 1024 / 1024,
        'final_usage_mb': current['rss_bytes'] / 1024 / 1024,
        'growth_data': growth_data,
        'most_common_types': profiler.get_most_common_types(10),
        'suspected_leaks': profiler.find_leaking_types() if final_growth > threshold_mb else [],
    }


def track_object_growth(duration_seconds: int = 60, interval_seconds: int = 5):
    """追踪对象增长"""
    import time
    
    profiler = MemoryProfiler()
    profiler.set_baseline()
    
    results = []
    elapsed = 0
    
    while elapsed < duration_seconds:
        time.sleep(interval_seconds)
        elapsed += interval_seconds
        
        growth = profiler.detect_growth(top_n=10)
        snapshot = profiler.take_snapshot()
        
        results.append({
            'timestamp': datetime.utcnow().isoformat(),
            'growth': [
                {
                    'type': g.type_name,
                    'growth': g.growth,
                    'total': g.count_after,
                }
                for g in growth
            ],
            'memory_mb': snapshot.rss_bytes / 1024 / 1024 if snapshot else 0,
        })
    
    return results


def find_reference_cycles():
    """查找引用循环"""
    gc.collect()
    
    # Get objects that might be in cycles
    unreachable = gc.garbage if hasattr(gc, 'garbage') else []
    
    return {
        'unreachable_count': len(unreachable),
        'unreachable_types': defaultdict(int),
    }


class MemoryTracker:
    """内存追踪器"""
    
    def __init__(self, name: str = 'default'):
        self.name = name
        self.start_usage: Optional[Dict[str, Any]] = None
        self.peak_usage = 0
    
    def __enter__(self):
        gc.collect()
        self.start_usage = get_memory_usage()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        final_usage = get_memory_usage()
        
        if self.start_usage:
            growth = final_usage['rss_mb'] - self.start_usage['rss_mb']
            print(f"[{self.name}] Memory growth: {growth:.2f} MB")
            print(f"[{self.name}] Peak usage: {final_usage['rss_mb']:.2f} MB")
    
    def checkpoint(self, label: str = ''):
        """检查点"""
        current = get_memory_usage()
        self.peak_usage = max(self.peak_usage, current['rss_mb'])
        
        if self.start_usage:
            growth = current['rss_mb'] - self.start_usage['rss_mb']
            print(f"[{self.name}] {label} - Current: {current['rss_mb']:.2f} MB, Growth: {growth:.2f} MB")
