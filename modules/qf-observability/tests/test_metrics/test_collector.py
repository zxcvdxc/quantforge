"""
指标采集模块测试
"""

import pytest
import time
from unittest.mock import patch, MagicMock

from qf_observability.metrics import (
    Counter,
    Gauge,
    Histogram,
    Summary,
    Timer,
    timed,
    get_collector,
    reset_collector,
    MetricsCollector,
    TradingMetrics,
    LatencyMetrics,
    SuccessRateMetrics,
    SystemMetrics,
    ResourceUsageCollector,
)


class TestBasicMetrics:
    """基础指标测试"""
    
    def test_counter(self):
        """测试计数器"""
        counter = Counter('test_counter', 'Test counter')
        
        assert counter.get() == 0
        
        counter.inc()
        assert counter.get() == 1
        
        counter.inc(5)
        assert counter.get() == 6
        
        counter.reset()
        assert counter.get() == 0
    
    def test_gauge(self):
        """测试仪表盘"""
        gauge = Gauge('test_gauge', 'Test gauge')
        
        gauge.set(100)
        assert gauge.get() == 100
        
        gauge.inc(10)
        assert gauge.get() == 110
        
        gauge.dec(20)
        assert gauge.get() == 90
    
    def test_histogram(self):
        """测试直方图"""
        histogram = Histogram('test_histogram', 'Test histogram')
        
        histogram.observe(0.5)
        histogram.observe(1.0)
        histogram.observe(2.5)
        
        data = histogram.get()
        assert data['count'] == 3
        assert data['sum'] == 4.0
        assert len(data['buckets']) > 0
    
    def test_summary(self):
        """测试摘要"""
        summary = Summary('test_summary', 'Test summary')
        
        summary.observe(100)
        summary.observe(200)
        summary.observe(300)
        
        data = summary.get()
        assert data['count'] == 3
        assert data['sum'] == 600
        assert len(data['quantiles']) > 0
    
    def test_timer(self):
        """测试计时器"""
        histogram = Histogram('test_timer_hist', 'Test')
        
        with Timer(histogram) as timer:
            time.sleep(0.01)
        
        assert timer.duration is not None
        assert timer.duration >= 0.01


class TestMetricsCollector:
    """指标采集器测试"""
    
    def test_singleton(self):
        """测试单例模式"""
        collector1 = get_collector()
        collector2 = get_collector()
        assert collector1 is collector2
    
    def test_custom_metric(self):
        """测试自定义指标"""
        collector = get_collector()
        
        collector.record_custom_metric('custom_metric', 100, labels={'env': 'test'})
        
        metrics = collector.get_custom_metrics('custom_metric')
        assert 'custom_metric' in metrics
        assert len(metrics['custom_metric']) == 1
        assert metrics['custom_metric'][0].value == 100
    
    def test_enable_disable(self):
        """测试启用/禁用"""
        collector = get_collector()
        
        collector.enable()
        assert collector._enabled
        
        collector.disable()
        assert not collector._enabled
        
        # Should return empty when disabled
        assert collector.collect_all() == {}


class TestTradingMetrics:
    """交易指标测试"""
    
    def test_trade_recording(self):
        """测试交易记录"""
        from qf_observability.metrics import TradeRecord
        from datetime import datetime
        
        metrics = TradingMetrics()
        
        trade = TradeRecord(
            trade_id='1',
            symbol='BTC/USD',
            side='buy',
            quantity=1.0,
            price=50000.0,
            timestamp=datetime.utcnow(),
            latency_ms=50.0,
            status='success',
        )
        
        metrics.record_trade(trade)
        
        assert metrics.trades_total.get() == 1
        assert metrics.trades_successful.get() == 1
        assert metrics.trade_volume.get() == 1.0
    
    def test_success_rate(self):
        """测试成功率计算"""
        from qf_observability.metrics import TradeRecord
        from datetime import datetime
        
        metrics = TradingMetrics()
        
        # Add successful trades
        for i in range(8):
            trade = TradeRecord(
                trade_id=str(i),
                symbol='BTC/USD',
                side='buy',
                quantity=1.0,
                price=50000.0,
                timestamp=datetime.utcnow(),
                latency_ms=50.0,
                status='success',
            )
            metrics.record_trade(trade)
        
        # Add failed trades
        for i in range(8, 10):
            trade = TradeRecord(
                trade_id=str(i),
                symbol='BTC/USD',
                side='buy',
                quantity=1.0,
                price=50000.0,
                timestamp=datetime.utcnow(),
                latency_ms=50.0,
                status='failed',
            )
            metrics.record_trade(trade)
        
        assert metrics.get_success_rate() == 0.8


class TestLatencyMetrics:
    """延迟指标测试"""
    
    def test_api_latency(self):
        """测试API延迟"""
        metrics = LatencyMetrics()
        
        metrics.record_api_latency(0.1, endpoint='/api/trades')
        metrics.record_api_latency(0.2, endpoint='/api/trades')
        
        data = metrics.api_latency.get()
        assert data['count'] == 2
    
    def test_db_latency(self):
        """测试数据库延迟"""
        metrics = LatencyMetrics()
        
        metrics.record_db_latency(0.05, operation='select')
        metrics.record_db_latency(0.1, operation='insert')
        
        data = metrics.db_latency.get()
        assert data['count'] == 2


class TestSuccessRateMetrics:
    """成功率指标测试"""
    
    def test_record_success_failure(self):
        """测试记录成功和失败"""
        metrics = SuccessRateMetrics()
        
        metrics.record_success('operation1')
        metrics.record_success('operation1')
        metrics.record_failure('operation1', error_type='timeout')
        
        assert metrics.get_success_rate('operation1') == 2/3
        assert metrics.get_error_breakdown() == {'timeout': 1}


class TestSystemMetrics:
    """系统指标测试"""
    
    def test_collect(self):
        """测试采集"""
        metrics = SystemMetrics()
        
        data = metrics.collect()
        
        assert 'cpu_percent' in data
        assert 'memory' in data
        assert 'disk' in data
    
    def test_get_usage(self):
        """测试获取使用情况"""
        metrics = SystemMetrics()
        
        usage = metrics.get_current_usage()
        
        assert 'rss_bytes' in usage
        assert 'vms_bytes' in usage
        assert 'percent' in usage


class TestResourceCollector:
    """资源采集器测试"""
    
    def test_metric_collector_interface(self):
        """测试指标采集器接口"""
        collector = ResourceUsageCollector()
        
        assert collector.get_name() == 'system'
        
        metrics = collector.collect()
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        
        # Check metric structure
        for metric in metrics:
            assert hasattr(metric, 'name')
            assert hasattr(metric, 'value')
            assert hasattr(metric, 'timestamp')
