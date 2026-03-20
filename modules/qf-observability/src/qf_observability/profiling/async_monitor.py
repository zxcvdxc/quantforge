"""
异步任务监控模块
提供异步任务监控功能
"""

import asyncio
import time
import threading
from typing import Optional, Dict, List, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    name: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled: bool = False
    exception: Optional[str] = None
    duration_ms: Optional[float] = None
    coroutine_name: str = ''


@dataclass
class TaskStats:
    """任务统计"""
    total_created: int = 0
    total_completed: int = 0
    total_cancelled: int = 0
    total_failed: int = 0
    active_count: int = 0
    avg_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')


class AsyncTaskMonitor:
    """异步任务监控器"""
    
    _instance: Optional['AsyncTaskMonitor'] = None
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
        
        self._tasks: Dict[str, TaskInfo] = {}
        self._active_tasks: Set[str] = set()
        self._stats: TaskStats = TaskStats()
        self._task_durations: List[float] = []
        self._max_durations = 1000
        self._enabled = True
        self._lock = threading.RLock()
        self._task_counter = 0
        self._initialized = True
        self._monitored_tasks: Set[asyncio.Task] = set()
    
    def enable(self):
        """启用监控"""
        self._enabled = True
    
    def disable(self):
        """禁用监控"""
        self._enabled = False
    
    def _generate_task_id(self) -> str:
        """生成任务ID"""
        with self._lock:
            self._task_counter += 1
            return f"task_{self._task_counter}_{int(time.time() * 1000)}"
    
    def register_task(self, task: asyncio.Task, name: Optional[str] = None) -> str:
        """注册任务"""
        if not self._enabled:
            return ''
        
        task_id = self._generate_task_id()
        
        coro_name = ''
        if hasattr(task, 'get_coro') and task.get_coro():
            coro = task.get_coro()
            coro_name = getattr(coro, '__name__', str(coro))
        
        task_info = TaskInfo(
            task_id=task_id,
            name=name or coro_name or task_id,
            created_at=datetime.utcnow(),
            coroutine_name=coro_name,
        )
        
        with self._lock:
            self._tasks[task_id] = task_info
            self._active_tasks.add(task_id)
            self._stats.total_created += 1
            self._stats.active_count = len(self._active_tasks)
            self._monitored_tasks.add(task)
        
        # Add done callback
        task.add_done_callback(lambda t, tid=task_id: self._on_task_done(t, tid))
        
        return task_id
    
    def _on_task_done(self, task: asyncio.Task, task_id: str):
        """任务完成回调"""
        with self._lock:
            if task_id not in self._tasks:
                return
            
            task_info = self._tasks[task_id]
            task_info.completed_at = datetime.utcnow()
            
            if task_id in self._active_tasks:
                self._active_tasks.remove(task_id)
            
            # Check if cancelled
            if task.cancelled():
                task_info.cancelled = True
                self._stats.total_cancelled += 1
            else:
                # Check for exception
                try:
                    task.result()
                    self._stats.total_completed += 1
                except Exception as e:
                    task_info.exception = str(e)
                    self._stats.total_failed += 1
            
            # Calculate duration
            if task_info.created_at:
                duration = (task_info.completed_at - task_info.created_at).total_seconds() * 1000
                task_info.duration_ms = duration
                self._task_durations.append(duration)
                
                if len(self._task_durations) > self._max_durations:
                    self._task_durations.pop(0)
                
                # Update stats
                self._stats.max_duration_ms = max(self._stats.max_duration_ms, duration)
                self._stats.min_duration_ms = min(self._stats.min_duration_ms, duration)
                if self._task_durations:
                    self._stats.avg_duration_ms = sum(self._task_durations) / len(self._task_durations)
            
            self._stats.active_count = len(self._active_tasks)
            
            # Cleanup completed tasks from monitored set
            self._monitored_tasks.discard(task)
    
    def start_task(self, task_id: str):
        """标记任务开始"""
        if not self._enabled:
            return
        
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].started_at = datetime.utcnow()
    
    def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        with self._lock:
            return self._tasks.get(task_id)
    
    def get_active_tasks(self) -> List[TaskInfo]:
        """获取活跃任务"""
        with self._lock:
            return [self._tasks[tid] for tid in self._active_tasks if tid in self._tasks]
    
    def get_all_tasks(self) -> List[TaskInfo]:
        """获取所有任务"""
        with self._lock:
            return list(self._tasks.values())
    
    def get_stats(self) -> TaskStats:
        """获取统计信息"""
        with self._lock:
            # Update active count
            self._stats.active_count = len(self._active_tasks)
            
            # Return a copy
            return TaskStats(
                total_created=self._stats.total_created,
                total_completed=self._stats.total_completed,
                total_cancelled=self._stats.total_cancelled,
                total_failed=self._stats.total_failed,
                active_count=self._stats.active_count,
                avg_duration_ms=self._stats.avg_duration_ms,
                max_duration_ms=self._stats.max_duration_ms,
                min_duration_ms=self._stats.min_duration_ms if self._stats.min_duration_ms != float('inf') else 0,
            )
    
    def get_slow_tasks(self, threshold_ms: float = 1000.0) -> List[TaskInfo]:
        """获取慢任务"""
        with self._lock:
            slow = []
            for task_id in self._active_tasks:
                if task_id in self._tasks:
                    task = self._tasks[task_id]
                    if task.created_at:
                        duration = (datetime.utcnow() - task.created_at).total_seconds() * 1000
                        if duration > threshold_ms:
                            slow.append(task)
            return slow
    
    def get_task_summary(self) -> Dict[str, Any]:
        """获取任务摘要"""
        with self._lock:
            stats = self.get_stats()
            
            # Group by coroutine name
            coroutine_stats = defaultdict(lambda: {'count': 0, 'total_duration': 0.0})
            for task in self._tasks.values():
                name = task.coroutine_name or 'unknown'
                coroutine_stats[name]['count'] += 1
                if task.duration_ms:
                    coroutine_stats[name]['total_duration'] += task.duration_ms
            
            return {
                'stats': {
                    'total_created': stats.total_created,
                    'total_completed': stats.total_completed,
                    'total_cancelled': stats.total_cancelled,
                    'total_failed': stats.total_failed,
                    'active_count': stats.active_count,
                    'avg_duration_ms': stats.avg_duration_ms,
                    'max_duration_ms': stats.max_duration_ms,
                    'min_duration_ms': stats.min_duration_ms,
                },
                'active_tasks': [
                    {
                        'id': t.task_id,
                        'name': t.name,
                        'coroutine': t.coroutine_name,
                        'created_at': t.created_at.isoformat() if t.created_at else None,
                    }
                    for t in self.get_active_tasks()
                ],
                'coroutine_breakdown': {
                    name: {
                        'count': data['count'],
                        'avg_duration_ms': data['total_duration'] / data['count'] if data['count'] > 0 else 0,
                    }
                    for name, data in coroutine_stats.items()
                },
            }
    
    def reset(self):
        """重置"""
        with self._lock:
            self._tasks.clear()
            self._active_tasks.clear()
            self._monitored_tasks.clear()
            self._stats = TaskStats()
            self._task_durations.clear()
            self._task_counter = 0
    
    def cancel_all(self):
        """取消所有监控的任务"""
        with self._lock:
            for task in list(self._monitored_tasks):
                if not task.done():
                    task.cancel()


# Global monitor instance
_monitor_instance: Optional[AsyncTaskMonitor] = None


def get_async_task_monitor() -> AsyncTaskMonitor:
    """获取全局监控器"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = AsyncTaskMonitor()
    return _monitor_instance


def monitor_async_tasks(func):
    """异步函数监控装饰器"""
    async def wrapper(*args, **kwargs):
        monitor = get_async_task_monitor()
        task = asyncio.current_task()
        
        if task:
            task_id = monitor.register_task(task, name=func.__name__)
            monitor.start_task(task_id)
        
        try:
            return await func(*args, **kwargs)
        finally:
            pass  # Task completion is handled by callback
    
    return wrapper


def get_async_task_stats() -> Dict[str, Any]:
    """获取异步任务统计"""
    return get_async_task_monitor().get_task_summary()


def create_monitored_task(coro, name: Optional[str] = None) -> asyncio.Task:
    """创建受监控的任务"""
    task = asyncio.create_task(coro)
    monitor = get_async_task_monitor()
    monitor.register_task(task, name=name)
    return task


class TaskGroupMonitor:
    """任务组监控"""
    
    def __init__(self, name: str):
        self.name = name
        self.tasks: List[asyncio.Task] = []
        self.monitor = get_async_task_monitor()
    
    def add_task(self, coro, task_name: Optional[str] = None) -> asyncio.Task:
        """添加任务"""
        task = asyncio.create_task(coro)
        full_name = f"{self.name}.{task_name}" if task_name else self.name
        self.monitor.register_task(task, name=full_name)
        self.tasks.append(task)
        return task
    
    async def wait_all(self, timeout: Optional[float] = None):
        """等待所有任务"""
        if timeout:
            done, pending = await asyncio.wait(
                self.tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED,
            )
            for task in pending:
                task.cancel()
        else:
            await asyncio.gather(*self.tasks, return_exceptions=True)
    
    def get_results(self) -> List[Any]:
        """获取结果"""
        results = []
        for task in self.tasks:
            if task.done() and not task.cancelled():
                try:
                    results.append(task.result())
                except Exception as e:
                    results.append(e)
            else:
                results.append(None)
        return results
