"""
性能剖析模块
提供代码热点分析功能
"""

import time
import threading
import functools
from typing import Optional, Dict, List, Any, Callable
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FunctionProfile:
    """函数性能剖析数据"""
    function_name: str
    call_count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    avg_time: float = 0.0
    last_call_time: Optional[datetime] = None
    
    def update(self, duration: float):
        """更新统计"""
        self.call_count += 1
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)
        self.avg_time = self.total_time / self.call_count
        self.last_call_time = datetime.utcnow()


@dataclass
class Hotspot:
    """热点代码"""
    function_name: str
    total_time: float
    call_count: int
    avg_time: float
    percent_of_total: float


class PerformanceProfiler:
    """性能剖析器"""
    
    _instance: Optional['PerformanceProfiler'] = None
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
        
        self._profiles: Dict[str, FunctionProfile] = {}
        self._enabled = True
        self._lock = threading.RLock()
        self._initialized = True
        self._global_start_time = time.time()
    
    def enable(self):
        """启用剖析"""
        self._enabled = True
    
    def disable(self):
        """禁用剖析"""
        self._enabled = False
    
    def record_call(self, function_name: str, duration: float):
        """记录函数调用"""
        if not self._enabled:
            return
        
        with self._lock:
            if function_name not in self._profiles:
                self._profiles[function_name] = FunctionProfile(function_name)
            
            self._profiles[function_name].update(duration)
    
    def get_profile(self, function_name: str) -> Optional[FunctionProfile]:
        """获取函数剖析数据"""
        with self._lock:
            return self._profiles.get(function_name)
    
    def get_all_profiles(self) -> Dict[str, FunctionProfile]:
        """获取所有剖析数据"""
        with self._lock:
            return dict(self._profiles)
    
    def get_hotspots(self, top_n: int = 10) -> List[Hotspot]:
        """获取热点代码"""
        with self._lock:
            if not self._profiles:
                return []
            
            total_time = sum(p.total_time for p in self._profiles.values())
            if total_time == 0:
                return []
            
            hotspots = []
            for name, profile in self._profiles.items():
                hotspot = Hotspot(
                    function_name=name,
                    total_time=profile.total_time,
                    call_count=profile.call_count,
                    avg_time=profile.avg_time,
                    percent_of_total=(profile.total_time / total_time) * 100,
                )
                hotspots.append(hotspot)
            
            # Sort by total time (descending)
            hotspots.sort(key=lambda x: x.total_time, reverse=True)
            return hotspots[:top_n]
    
    def reset(self):
        """重置所有数据"""
        with self._lock:
            self._profiles.clear()
            self._global_start_time = time.time()
    
    def get_summary(self) -> Dict[str, Any]:
        """获取摘要"""
        with self._lock:
            total_calls = sum(p.call_count for p in self._profiles.values())
            total_time = sum(p.total_time for p in self._profiles.values())
            
            return {
                'total_functions': len(self._profiles),
                'total_calls': total_calls,
                'total_time': total_time,
                'profiling_duration': time.time() - self._global_start_time,
                'hotspots': [
                    {
                        'function': h.function_name,
                        'total_time': h.total_time,
                        'avg_time': h.avg_time,
                        'call_count': h.call_count,
                        'percent': h.percent_of_total,
                    }
                    for h in self.get_hotspots(10)
                ],
            }


# Global profiler instance
_profiler_instance: Optional[PerformanceProfiler] = None


def get_profiler() -> PerformanceProfiler:
    """获取全局剖析器"""
    global _profiler_instance
    if _profiler_instance is None:
        _profiler_instance = PerformanceProfiler()
    return _profiler_instance


def profile_function(func: Callable) -> Callable:
    """函数性能剖析装饰器"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        profiler = get_profiler()
        start = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            duration = time.time() - start
            profiler.record_call(f"{func.__module__}.{func.__name__}", duration)
    
    return wrapper


def profile_async_function(func: Callable) -> Callable:
    """异步函数性能剖析装饰器"""
    import asyncio
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        profiler = get_profiler()
        start = time.time()
        try:
            return await func(*args, **kwargs)
        finally:
            duration = time.time() - start
            profiler.record_call(f"{func.__module__}.{func.__name__}", duration)
    
    return wrapper


def get_hotspots(top_n: int = 10) -> List[Hotspot]:
    """获取热点代码"""
    return get_profiler().get_hotspots(top_n)


class Timer:
    """计时器"""
    
    def __init__(self, name: Optional[str] = None):
        self.name = name
        self.start_time: Optional[float] = None
        self.duration: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.time() - self.start_time
        if self.name:
            get_profiler().record_call(self.name, self.duration)
    
    def elapsed(self) -> float:
        """获取已用时间"""
        if self.duration is not None:
            return self.duration
        if self.start_time:
            return time.time() - self.start_time
        return 0.0


def time_block(name: str):
    """代码块计时上下文管理器"""
    return Timer(name)


# External profiler integration (py-spy)
class ExternalProfiler:
    """外部性能剖析器集成"""
    
    def __init__(self):
        self._recording = False
        self._output_file: Optional[str] = None
    
    def start_recording(self, output_file: str = 'profile.svg', duration: int = 60):
        """开始记录（需要py-spy）"""
        try:
            import subprocess
            import os
            
            self._output_file = output_file
            self._recording = True
            
            # Start py-spy in the background
            pid = os.getpid()
            subprocess.Popen([
                'py-spy', 'record',
                '-o', output_file,
                '-d', str(duration),
                '-p', str(pid),
                '--rate', '100',
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        except Exception as e:
            print(f"Failed to start py-spy: {e}")
    
    def generate_flamegraph(self, output_file: str = 'flamegraph.svg'):
        """生成火焰图"""
        # This is handled by py-spy record command
        pass


def start_py_spy_profiling(output_file: str = 'profile.svg', duration: int = 60):
    """启动py-spy性能剖析"""
    profiler = ExternalProfiler()
    profiler.start_recording(output_file, duration)
    return profiler
