"""
业务指标模块
提供交易、延迟、成功率等业务指标采集
"""

import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import threading

from .collector import Counter, Gauge, Histogram, Summary, Timer, timed


@dataclass
class TradeRecord:
    """交易记录"""
    trade_id: str
    symbol: str
    side: str  # buy/sell
    quantity: float
    price: float
    timestamp: datetime
    latency_ms: float
    status: str  # success/failed
    error: Optional[str] = None


class TradingMetrics:
    """交易指标"""
    
    def __init__(self, namespace: str = 'quantforge'):
        self.namespace = namespace
        self._lock = threading.Lock()
        
        # Trade counters
        self.trades_total = Counter(
            f"{namespace}_trades_total",
            "Total number of trades",
        )
        self.trades_successful = Counter(
            f"{namespace}_trades_successful_total",
            "Total number of successful trades",
        )
        self.trades_failed = Counter(
            f"{namespace}_trades_failed_total",
            "Total number of failed trades",
        )
        
        # Trade volume
        self.trade_volume = Counter(
            f"{namespace}_trade_volume_total",
            "Total trade volume",
        )
        self.trade_notional = Counter(
            f"{namespace}_trade_notional_total",
            "Total trade notional value",
        )
        
        # Trade latency
        self.trade_latency = Histogram(
            f"{namespace}_trade_latency_seconds",
            "Trade execution latency",
            buckets=[.001, .005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0],
        )
        
        # Active trades gauge
        self.active_trades = Gauge(
            f"{namespace}_active_trades",
            "Number of active trades",
        )
        
        # Symbol-specific metrics
        self._symbol_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'trades': 0,
            'volume': 0.0,
            'notional': 0.0,
            'failures': 0,
        })
        
        # Recent trades for analysis
        self._recent_trades: list = []
        self._max_recent = 1000
    
    def record_trade(self, trade: TradeRecord):
        """记录交易"""
        with self._lock:
            # Update counters
            self.trades_total.inc()
            
            if trade.status == 'success':
                self.trades_successful.inc()
                self.trade_volume.inc(trade.quantity)
                self.trade_notional.inc(trade.quantity * trade.price)
            else:
                self.trades_failed.inc()
            
            # Record latency
            self.trade_latency.observe(trade.latency_ms / 1000.0)
            
            # Update symbol stats
            self._symbol_stats[trade.symbol]['trades'] += 1
            self._symbol_stats[trade.symbol]['volume'] += trade.quantity
            self._symbol_stats[trade.symbol]['notional'] += trade.quantity * trade.price
            if trade.status != 'success':
                self._symbol_stats[trade.symbol]['failures'] += 1
            
            # Store recent trade
            self._recent_trades.append(trade)
            if len(self._recent_trades) > self._max_recent:
                self._recent_trades.pop(0)
    
    def start_trade(self):
        """开始交易（增加活跃交易计数）"""
        self.active_trades.inc()
    
    def end_trade(self):
        """结束交易（减少活跃交易计数）"""
        self.active_trades.dec()
    
    def get_symbol_stats(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """获取交易对统计"""
        with self._lock:
            if symbol:
                return dict(self._symbol_stats[symbol])
            return dict(self._symbol_stats)
    
    def get_success_rate(self, symbol: Optional[str] = None) -> float:
        """获取成功率"""
        with self._lock:
            if symbol:
                stats = self._symbol_stats[symbol]
                total = stats['trades']
                if total == 0:
                    return 0.0
                return (total - stats['failures']) / total
            else:
                total = self.trades_total.get()
                if total == 0:
                    return 0.0
                return self.trades_successful.get() / total
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        return {
            'trades_total': self.trades_total.get(),
            'trades_successful': self.trades_successful.get(),
            'trades_failed': self.trades_failed.get(),
            'trade_volume': self.trade_volume.get(),
            'trade_notional': self.trade_notional.get(),
            'active_trades': self.active_trades.get(),
            'success_rate': self.get_success_rate(),
            'trade_latency': self.trade_latency.get(),
        }


class LatencyMetrics:
    """延迟指标"""
    
    def __init__(self, namespace: str = 'quantforge'):
        self.namespace = namespace
        
        # Operation latencies
        self.operation_latencies: Dict[str, Histogram] = {}
        
        # API latencies
        self.api_latency = Histogram(
            f"{namespace}_api_latency_seconds",
            "API call latency",
            buckets=[.001, .005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0],
        )
        
        # Database latencies
        self.db_latency = Histogram(
            f"{namespace}_db_latency_seconds",
            "Database operation latency",
            buckets=[.001, .005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0],
        )
        
        # Network latencies
        self.network_latency = Histogram(
            f"{namespace}_network_latency_seconds",
            "Network latency",
            buckets=[.001, .005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0],
        )
        
        # P99, P95 latencies (tracked via Summary)
        self.latency_summary = Summary(
            f"{namespace}_latency_summary_seconds",
            "Latency summary for quantiles",
        )
    
    def get_or_create_histogram(self, name: str, **kwargs) -> Histogram:
        """获取或创建直方图"""
        if name not in self.operation_latencies:
            self.operation_latencies[name] = Histogram(
                f"{self.namespace}_{name}_latency_seconds",
                **kwargs
            )
        return self.operation_latencies[name]
    
    def record_api_latency(self, duration: float, endpoint: Optional[str] = None):
        """记录API延迟"""
        self.api_latency.observe(duration)
        self.latency_summary.observe(duration)
        
        if endpoint:
            hist = self.get_or_create_histogram(
                f"api_{endpoint}",
                description=f"API {endpoint} latency",
            )
            hist.observe(duration)
    
    def record_db_latency(self, duration: float, operation: Optional[str] = None):
        """记录数据库延迟"""
        self.db_latency.observe(duration)
        self.latency_summary.observe(duration)
        
        if operation:
            hist = self.get_or_create_histogram(
                f"db_{operation}",
                description=f"DB {operation} latency",
            )
            hist.observe(duration)
    
    def record_network_latency(self, duration: float, peer: Optional[str] = None):
        """记录网络延迟"""
        self.network_latency.observe(duration)
        
        if peer:
            hist = self.get_or_create_histogram(
                f"network_{peer}",
                description=f"Network latency to {peer}",
            )
            hist.observe(duration)
    
    def record_operation_latency(self, operation: str, duration: float):
        """记录操作延迟"""
        hist = self.get_or_create_histogram(operation)
        hist.observe(duration)
        self.latency_summary.observe(duration)
    
    def time_operation(self, operation: str):
        """计时上下文管理器"""
        hist = self.get_or_create_histogram(operation)
        return Timer(histogram=hist, summary=self.latency_summary)


class SuccessRateMetrics:
    """成功率指标"""
    
    def __init__(self, namespace: str = 'quantforge'):
        self.namespace = namespace
        self._lock = threading.Lock()
        
        # Overall success rate
        self.operations_total = Counter(
            f"{namespace}_operations_total",
            "Total number of operations",
        )
        self.operations_successful = Counter(
            f"{namespace}_operations_successful_total",
            "Total number of successful operations",
        )
        self.operations_failed = Counter(
            f"{namespace}_operations_failed_total",
            "Total number of failed operations",
        )
        
        # Error counter
        self.errors_total = Counter(
            f"{namespace}_errors_total",
            "Total number of errors",
        )
        
        # Per-operation counters
        self._operation_counters: Dict[str, Dict[str, Counter]] = {}
        
        # Error types
        self._error_counts: Dict[str, int] = defaultdict(int)
    
    def _get_operation_counters(self, operation: str) -> Dict[str, Counter]:
        """获取操作计数器"""
        if operation not in self._operation_counters:
            self._operation_counters[operation] = {
                'total': Counter(f"{self.namespace}_{operation}_total"),
                'successful': Counter(f"{self.namespace}_{operation}_successful_total"),
                'failed': Counter(f"{self.namespace}_{operation}_failed_total"),
            }
        return self._operation_counters[operation]
    
    def record_success(self, operation: Optional[str] = None):
        """记录成功"""
        with self._lock:
            self.operations_total.inc()
            self.operations_successful.inc()
            
            if operation:
                counters = self._get_operation_counters(operation)
                counters['total'].inc()
                counters['successful'].inc()
    
    def record_failure(self, operation: Optional[str] = None, error_type: Optional[str] = None):
        """记录失败"""
        with self._lock:
            self.operations_total.inc()
            self.operations_failed.inc()
            self.errors_total.inc()
            
            if operation:
                counters = self._get_operation_counters(operation)
                counters['total'].inc()
                counters['failed'].inc()
            
            if error_type:
                self._error_counts[error_type] += 1
    
    def get_success_rate(self, operation: Optional[str] = None) -> float:
        """获取成功率"""
        with self._lock:
            if operation:
                counters = self._get_operation_counters(operation)
                total = counters['total'].get()
                if total == 0:
                    return 0.0
                return counters['successful'].get() / total
            else:
                total = self.operations_total.get()
                if total == 0:
                    return 0.0
                return self.operations_successful.get() / total
    
    def get_error_rate(self) -> float:
        """获取错误率"""
        with self._lock:
            total = self.operations_total.get()
            if total == 0:
                return 0.0
            return self.errors_total.get() / total
    
    def get_error_breakdown(self) -> Dict[str, int]:
        """获取错误分类统计"""
        with self._lock:
            return dict(self._error_counts)
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        return {
            'operations_total': self.operations_total.get(),
            'operations_successful': self.operations_successful.get(),
            'operations_failed': self.operations_failed.get(),
            'errors_total': self.errors_total.get(),
            'success_rate': self.get_success_rate(),
            'error_rate': self.get_error_rate(),
            'error_breakdown': self.get_error_breakdown(),
        }


class BusinessMetricsCollector:
    """业务指标采集器"""
    
    def __init__(self, namespace: str = 'quantforge'):
        self.namespace = namespace
        self.trading = TradingMetrics(namespace)
        self.latency = LatencyMetrics(namespace)
        self.success_rate = SuccessRateMetrics(namespace)
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有业务指标"""
        return {
            'trading': self.trading.get_metrics(),
            'latency': {
                'api_latency': self.latency.api_latency.get(),
                'db_latency': self.latency.db_latency.get(),
                'network_latency': self.latency.network_latency.get(),
            },
            'success_rate': self.success_rate.get_metrics(),
        }
