"""批量检查处理器 - 监控检查批量化和性能优化

提供监控检查的批量化处理，支持并行检查、结果聚合、报警限流等功能。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple, Type, Union
from datetime import datetime, timedelta
from collections import deque
import heapq

from .checks import CheckResult, HealthCheck
from .alerts import Alert, AlertLevel

logger = logging.getLogger(__name__)


@dataclass
class BatchCheckConfig:
    """批量检查配置"""
    # 并发设置
    max_concurrent_checks: int = 10
    
    # 批处理设置
    batch_size: int = 20
    batch_timeout_ms: float = 100.0
    
    # 超时设置
    check_timeout: float = 30.0
    
    # 重试设置
    max_retries: int = 2
    retry_delay_ms: float = 500.0


@dataclass
class CheckPriority:
    """检查优先级"""
    HIGH = 1
    NORMAL = 5
    LOW = 10


@dataclass
class BatchCheckResult:
    """批量检查结果"""
    results: List[CheckResult] = field(default_factory=list)
    duration_ms: float = 0.0
    checks_total: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    
    @property
    def all_healthy(self) -> bool:
        """是否全部健康"""
        return all(r.is_healthy for r in self.results)
    
    @property
    def failed_results(self) -> List[CheckResult]:
        """获取失败的检查结果"""
        return [r for r in self.results if not r.is_healthy]


class BatchCheckProcessor:
    """批量检查处理器
    
    功能：
    - 并行执行多个检查项
    - 批量结果聚合
    - 优先级队列
    - 超时和重试机制
    - 检查项依赖管理
    
    Example:
        processor = BatchCheckProcessor(config)
        
        # 批量执行检查
        checks = [AccountCheck(), PositionCheck(), OrderCheck()]
        result = await processor.run_checks_batch(checks)
        
        # 获取失败的检查
        failed = result.failed_results
    """
    
    def __init__(self, config: Optional[BatchCheckConfig] = None) -> None:
        self.config = config or BatchCheckConfig()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_checks)
        self._running_checks: Dict[str, asyncio.Task] = {}
        self._stats = {
            "total_checks": 0,
            "passed_checks": 0,
            "failed_checks": 0,
            "timeout_checks": 0,
            "error_checks": 0,
        }
    
    async def run_checks_batch(
        self,
        checks: List[HealthCheck],
        timeout: Optional[float] = None,
        priority: int = CheckPriority.NORMAL,
    ) -> BatchCheckResult:
        """批量执行检查
        
        Args:
            checks: 检查项列表
            timeout: 超时时间
            priority: 优先级
        
        Returns:
            BatchCheckResult: 批量检查结果
        """
        start_time = time.time()
        timeout = timeout or self.config.check_timeout
        
        # 创建任务
        tasks = []
        for check in checks:
            task = self._run_check_with_semaphore(check, timeout)
            tasks.append(task)
        
        # 并行执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        check_results: List[CheckResult] = []
        for check, result in zip(checks, results):
            if isinstance(result, Exception):
                # 检查执行异常
                check_results.append(CheckResult(
                    name=check.__class__.__name__,
                    is_healthy=False,
                    message=f"检查执行异常: {str(result)}",
                    details={"error": str(result), "severity": "error"},
                ))
                self._stats["error_checks"] += 1
            elif isinstance(result, CheckResult):
                check_results.append(result)
                if result.is_healthy:
                    self._stats["passed_checks"] += 1
                else:
                    self._stats["failed_checks"] += 1
            self._stats["total_checks"] += 1
        
        duration_ms = (time.time() - start_time) * 1000
        
        return BatchCheckResult(
            results=check_results,
            duration_ms=duration_ms,
            checks_total=len(checks),
            checks_passed=sum(1 for r in check_results if r.is_healthy),
            checks_failed=sum(1 for r in check_results if not r.is_healthy),
        )
    
    async def run_checks_by_dependency(
        self,
        checks_with_deps: List[Tuple[HealthCheck, List[str]]],
        timeout: Optional[float] = None,
    ) -> BatchCheckResult:
        """按依赖关系执行检查
        
        Args:
            checks_with_deps: (检查项, 依赖的检查名称列表)
            timeout: 超时时间
        
        Returns:
            BatchCheckResult: 批量检查结果
        """
        start_time = time.time()
        timeout = timeout or self.config.check_timeout
        
        results_map: Dict[str, CheckResult] = {}
        remaining = list(checks_with_deps)
        
        while remaining:
            # 找出可以执行的检查（依赖已满足）
            ready = []
            still_remaining = []
            
            for check, deps in remaining:
                check_name = check.__class__.__name__
                
                # 检查依赖是否已满足
                deps_satisfied = all(
                    dep in results_map and results_map[dep].is_healthy
                    for dep in deps
                )
                
                if deps_satisfied:
                    ready.append(check)
                else:
                    still_remaining.append((check, deps))
            
            if not ready:
                # 存在循环依赖或依赖失败的检查
                logger.error("Dependency resolution failed for checks")
                for check, deps in still_remaining:
                    results_map[check.__class__.__name__] = CheckResult(
                        name=check.__class__.__name__,
                        is_healthy=False,
                        message="依赖解析失败",
                        details={"dependencies": deps, "severity": "error"},
                    )
                break
            
            # 执行就绪的检查
            batch_result = await self.run_checks_batch(ready, timeout)
            for result in batch_result.results:
                results_map[result.name] = result
            
            remaining = still_remaining
        
        duration_ms = (time.time() - start_time) * 1000
        all_results = list(results_map.values())
        
        return BatchCheckResult(
            results=all_results,
            duration_ms=duration_ms,
            checks_total=len(all_results),
            checks_passed=sum(1 for r in all_results if r.is_healthy),
            checks_failed=sum(1 for r in all_results if not r.is_healthy),
        )
    
    async def _run_check_with_semaphore(
        self,
        check: HealthCheck,
        timeout: float,
    ) -> CheckResult:
        """带信号量的检查执行"""
        async with self._semaphore:
            try:
                return await asyncio.wait_for(check.check(), timeout=timeout)
            except asyncio.TimeoutError:
                self._stats["timeout_checks"] += 1
                return CheckResult(
                    name=check.__class__.__name__,
                    is_healthy=False,
                    message=f"检查超时 ({timeout}s)",
                    details={"timeout": timeout, "severity": "error"},
                )
            except Exception as e:
                logger.error(f"Check error: {e}")
                self._stats["error_checks"] += 1
                return CheckResult(
                    name=check.__class__.__name__,
                    is_healthy=False,
                    message=f"检查异常: {str(e)}",
                    details={"error": str(e), "severity": "error"},
                )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            "total_checks": 0,
            "passed_checks": 0,
            "failed_checks": 0,
            "timeout_checks": 0,
            "error_checks": 0,
        }


@dataclass
class AlertRateLimitConfig:
    """报警限流配置"""
    # 冷却时间（秒）
    cooldown_seconds: float = 300.0
    
    # 不同级别的冷却时间
    level_cooldowns: Dict[AlertLevel, float] = field(default_factory=lambda: {
        AlertLevel.CRITICAL: 60.0,
        AlertLevel.ERROR: 300.0,
        AlertLevel.WARNING: 600.0,
        AlertLevel.INFO: 3600.0,
        AlertLevel.DEBUG: 86400.0,
    })
    
    # 相同内容的报警合并窗口（秒）
    duplicate_window_seconds: float = 60.0
    
    # 报警风暴检测
    storm_threshold: int = 10  # 单位时间内报警数量阈值
    storm_window_seconds: float = 60.0
    storm_suppression_seconds: float = 300.0
    
    # 最大报警队列大小
    max_queue_size: int = 1000
    
    # 批量发送设置
    enable_batching: bool = True
    batch_size: int = 10
    batch_timeout_ms: float = 5000.0


@dataclass
class AlertHistoryEntry:
    """报警历史记录"""
    alert: Alert
    sent_at: datetime
    count: int = 1
    
    @property
    def age_seconds(self) -> float:
        return (datetime.now() - self.sent_at).total_seconds()


class AlertRateLimiter:
    """报警限流器
    
    功能：
    - 报警冷却时间控制
    - 相同报警合并
    - 报警风暴检测和抑制
    - 批量发送
    
    Example:
        limiter = AlertRateLimiter(config)
        
        # 检查是否可以发送报警
        if await limiter.should_send(alert):
            await send_alert(alert)
            limiter.record_sent(alert)
        
        # 或者使用自动处理
        await limiter.process_alert(alert, send_func)
    """
    
    def __init__(self, config: Optional[AlertRateLimitConfig] = None) -> None:
        self.config = config or AlertRateLimitConfig()
        
        # 报警历史
        self._alert_history: Dict[str, AlertHistoryEntry] = {}  # 按报警ID
        self._recent_alerts: deque = deque(maxlen=1000)  # 按时间
        
        # 风暴检测
        self._storm_active = False
        self._storm_suppressed_until: Optional[datetime] = None
        
        # 批量队列
        self._batch_queue: List[Alert] = []
        self._batch_timer: Optional[asyncio.Task] = None
        self._batch_lock = asyncio.Lock()
        
        # 统计
        self._stats = {
            "alerts_received": 0,
            "alerts_sent": 0,
            "alerts_suppressed": 0,
            "alerts_merged": 0,
            "storm_events": 0,
        }
    
    async def should_send(self, alert: Alert) -> Tuple[bool, Optional[str]]:
        """检查是否应该发送报警
        
        Args:
            alert: 报警信息
        
        Returns:
            (是否应该发送, 原因)
        """
        self._stats["alerts_received"] += 1
        
        # 检查报警风暴
        if self._is_storm_active():
            self._stats["alerts_suppressed"] += 1
            return False, "Storm suppression active"
        
        # 更新风暴检测
        self._update_storm_detection()
        
        # 生成报警标识
        alert_key = self._generate_alert_key(alert)
        
        # 检查冷却时间
        if alert_key in self._alert_history:
            entry = self._alert_history[alert_key]
            cooldown = self.config.level_cooldowns.get(
                alert.level, self.config.cooldown_seconds
            )
            
            if entry.age_seconds < cooldown:
                # 在冷却期内，增加计数
                entry.count += 1
                self._stats["alerts_merged"] += 1
                return False, f"In cooldown ({entry.count} similar alerts merged)"
        
        return True, None
    
    async def process_alert(
        self,
        alert: Alert,
        send_func: Callable[[Alert], Coroutine[Any, Any, bool]],
    ) -> bool:
        """处理报警（包含限流逻辑）
        
        Args:
            alert: 报警信息
            send_func: 发送函数
        
        Returns:
            bool: 是否发送成功
        """
        should_send, reason = await self.should_send(alert)
        
        if not should_send:
            logger.debug(f"Alert suppressed: {reason}")
            return False
        
        # 记录发送
        self.record_sent(alert)
        
        if self.config.enable_batching:
            # 加入批量队列
            async with self._batch_lock:
                self._batch_queue.append(alert)
                
                if len(self._batch_queue) >= self.config.batch_size:
                    return await self._flush_batch(send_func)
                elif self._batch_timer is None:
                    # 启动批量定时器
                    self._batch_timer = asyncio.create_task(
                        self._batch_timeout(send_func)
                    )
            return True
        else:
            # 直接发送
            success = await send_func(alert)
            if success:
                self._stats["alerts_sent"] += 1
            return success
    
    async def _batch_timeout(
        self,
        send_func: Callable[[Alert], Coroutine[Any, Any, bool]],
    ) -> None:
        """批量发送超时处理"""
        await asyncio.sleep(self.config.batch_timeout_ms / 1000)
        
        async with self._batch_lock:
            if self._batch_queue:
                await self._flush_batch(send_func)
            self._batch_timer = None
    
    async def _flush_batch(
        self,
        send_func: Callable[[Alert], Coroutine[Any, Any, bool]],
    ) -> bool:
        """刷新批量队列"""
        if not self._batch_queue:
            return True
        
        alerts_to_send = self._batch_queue.copy()
        self._batch_queue.clear()
        
        # 合并相同类型的报警
        merged_alerts = self._merge_similar_alerts(alerts_to_send)
        
        # 批量发送
        results = await asyncio.gather(*[
            send_func(alert) for alert in merged_alerts
        ])
        
        success_count = sum(results)
        self._stats["alerts_sent"] += success_count
        
        return success_count > 0
    
    def record_sent(self, alert: Alert) -> None:
        """记录已发送的报警"""
        alert_key = self._generate_alert_key(alert)
        
        self._alert_history[alert_key] = AlertHistoryEntry(
            alert=alert,
            sent_at=datetime.now(),
            count=1,
        )
        
        self._recent_alerts.append(alert)
    
    def _generate_alert_key(self, alert: Alert) -> str:
        """生成报警标识"""
        # 基于报警类型和级别生成标识
        return f"{alert.level.value}:{alert.title}"
    
    def _is_storm_active(self) -> bool:
        """检查报警风暴是否激活"""
        if self._storm_suppressed_until:
            if datetime.now() < self._storm_suppressed_until:
                return True
            else:
                # 风暴抑制结束
                self._storm_suppressed_until = None
                self._storm_active = False
        return False
    
    def _update_storm_detection(self) -> None:
        """更新风暴检测"""
        if self._storm_active:
            return
        
        # 清理过期的报警记录
        cutoff = datetime.now() - timedelta(seconds=self.config.storm_window_seconds)
        
        while self._recent_alerts and self._recent_alerts[0].timestamp < cutoff:
            self._recent_alerts.popleft()
        
        # 检查是否触发风暴
        if len(self._recent_alerts) >= self.config.storm_threshold:
            logger.warning(
                f"Alert storm detected: {len(self._recent_alerts)} alerts in "
                f"{self.config.storm_window_seconds}s"
            )
            self._storm_active = True
            self._storm_suppressed_until = datetime.now() + timedelta(
                seconds=self.config.storm_suppression_seconds
            )
            self._stats["storm_events"] += 1
            
            # 发送风暴报警
            storm_alert = Alert(
                level=AlertLevel.CRITICAL,
                title="报警风暴检测",
                message=f"检测到报警风暴，已抑制 {self.config.storm_suppression_seconds} 秒",
                details={
                    "alert_count": len(self._recent_alerts),
                    "window_seconds": self.config.storm_window_seconds,
                    "suppression_seconds": self.config.storm_suppression_seconds,
                },
            )
            # 这里应该立即发送风暴报警
    
    def _merge_similar_alerts(self, alerts: List[Alert]) -> List[Alert]:
        """合并相似的报警"""
        merged: Dict[str, Alert] = {}
        
        for alert in alerts:
            key = self._generate_alert_key(alert)
            
            if key in merged:
                # 更新已有报警的详情
                existing = merged[key]
                existing.details["merged_count"] = existing.details.get("merged_count", 1) + 1
            else:
                merged[key] = alert
        
        return list(merged.values())
    
    async def flush(self, send_func: Callable[[Alert], Coroutine[Any, Any, bool]]) -> None:
        """强制刷新所有待发送的报警"""
        async with self._batch_lock:
            if self._batch_queue:
                await self._flush_batch(send_func)
            
            if self._batch_timer:
                self._batch_timer.cancel()
                try:
                    await self._batch_timer
                except asyncio.CancelledError:
                    pass
                self._batch_timer = None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "history_size": len(self._alert_history),
            "recent_alerts": len(self._recent_alerts),
            "storm_active": self._storm_active,
            "batch_queue_size": len(self._batch_queue),
        }
    
    def clear_history(self) -> None:
        """清除历史记录"""
        self._alert_history.clear()
        self._recent_alerts.clear()
    
    def reset_storm(self) -> None:
        """重置风暴状态"""
        self._storm_active = False
        self._storm_suppressed_until = None
