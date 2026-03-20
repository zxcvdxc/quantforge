"""
Prometheus指标导出模块
提供Prometheus格式的指标暴露端点
"""

import threading
from typing import Optional, Dict, Any, List
from http.server import HTTPServer, BaseHTTPRequestHandler
from prometheus_client import (
    CollectorRegistry,
    Counter as PCounter,
    Gauge as PGauge,
    Histogram as PHistogram,
    Summary as PSummary,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from .collector import (
    MetricsCollector,
    Counter,
    Gauge,
    Histogram,
    Summary,
    get_collector,
)


class PrometheusExporter:
    """Prometheus指标导出器"""
    
    _instance: Optional['PrometheusExporter'] = None
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
        
        self.registry = CollectorRegistry()
        self._prometheus_metrics: Dict[str, Any] = {}
        self._collector = get_collector()
        self._initialized = True
        self._server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
    
    def _get_prometheus_metric(self, name: str, metric_type: str, description: str = '', labels: Optional[List[str]] = None):
        """获取或创建Prometheus指标"""
        if name not in self._prometheus_metrics:
            labels = labels or []
            
            if metric_type == 'counter':
                metric = PCounter(
                    name,
                    description,
                    labels,
                    registry=self.registry,
                )
            elif metric_type == 'gauge':
                metric = PGauge(
                    name,
                    description,
                    labels,
                    registry=self.registry,
                )
            elif metric_type == 'histogram':
                metric = PHistogram(
                    name,
                    description,
                    labels,
                    registry=self.registry,
                )
            elif metric_type == 'summary':
                metric = PSummary(
                    name,
                    description,
                    labels,
                    registry=self.registry,
                )
            else:
                raise ValueError(f"Unknown metric type: {metric_type}")
            
            self._prometheus_metrics[name] = metric
        
        return self._prometheus_metrics[name]
    
    def export_counter(self, counter: Counter, labels: Optional[Dict[str, str]] = None):
        """导出计数器"""
        prom_metric = self._get_prometheus_metric(
            counter.name,
            'counter',
            counter.description,
            list(labels.keys()) if labels else [],
        )
        
        if labels:
            prom_metric.labels(**labels).inc(counter.get())
        else:
            # Only set if not already set (counters are cumulative)
            prom_metric.inc(0)
    
    def export_gauge(self, gauge: Gauge, labels: Optional[Dict[str, str]] = None):
        """导出仪表盘"""
        prom_metric = self._get_prometheus_metric(
            gauge.name,
            'gauge',
            gauge.description,
            list(labels.keys()) if labels else [],
        )
        
        if labels:
            prom_metric.labels(**labels).set(gauge.get())
        else:
            prom_metric.set(gauge.get())
    
    def export_histogram(self, histogram: Histogram, labels: Optional[Dict[str, str]] = None):
        """导出直方图"""
        prom_metric = self._get_prometheus_metric(
            histogram.name,
            'histogram',
            histogram.description,
            list(labels.keys()) if labels else [],
        )
        
        # Note: This is a simplified version. Real histogram export would
        # require tracking observed values, not just summary stats
        data = histogram.get()
        
        if labels:
            metric = prom_metric.labels(**labels)
        else:
            metric = prom_metric
        
        # Set bucket counts
        for bucket, count in data.get('buckets', {}).items():
            metric.observe(bucket)
    
    def export_summary(self, summary: Summary, labels: Optional[Dict[str, str]] = None):
        """导出摘要"""
        prom_metric = self._get_prometheus_metric(
            summary.name,
            'summary',
            summary.description,
            list(labels.keys()) if labels else [],
        )
        
        data = summary.get()
        
        if labels:
            metric = prom_metric.labels(**labels)
        else:
            metric = prom_metric
        
        # Observe values to build summary
        if data.get('count', 0) > 0:
            avg = data['sum'] / data['count']
            metric.observe(avg)
    
    def update_from_collector(self):
        """从采集器更新指标"""
        metrics = self._collector.collect_all()
        
        for collector_name, metric_values in metrics.items():
            for metric_value in metric_values:
                name = f"{collector_name}_{metric_value.name}"
                labels = metric_value.labels
                
                if metric_value.metric_type == 'counter':
                    prom_metric = self._get_prometheus_metric(name, 'counter')
                    if labels:
                        prom_metric.labels(**labels).inc(metric_value.value)
                    else:
                        prom_metric.inc(metric_value.value)
                
                elif metric_value.metric_type == 'gauge':
                    prom_metric = self._get_prometheus_metric(name, 'gauge')
                    if labels:
                        prom_metric.labels(**labels).set(metric_value.value)
                    else:
                        prom_metric.set(metric_value.value)
    
    def get_metrics_text(self) -> bytes:
        """获取Prometheus格式的指标文本"""
        self.update_from_collector()
        return generate_latest(self.registry)
    
    def start_http_server(self, port: int = 9090, host: str = '0.0.0.0'):
        """启动HTTP服务器"""
        if self._server is not None:
            return
        
        class MetricsHandler(BaseHTTPRequestHandler):
            exporter = self
            
            def do_GET(self):
                if self.path == '/metrics':
                    data = self.exporter.get_metrics_text()
                    self.send_response(200)
                    self.send_header('Content-Type', CONTENT_TYPE_LATEST)
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                elif self.path == '/health':
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'OK')
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def log_message(self, format, *args):
                # Suppress default logging
                pass
        
        self._server = HTTPServer((host, port), MetricsHandler)
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()
    
    def stop_http_server(self):
        """停止HTTP服务器"""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._server_thread:
            self._server_thread.join(timeout=5)
            self._server_thread = None


# Global exporter instance
_exporter_instance: Optional[PrometheusExporter] = None


def get_prometheus_registry() -> CollectorRegistry:
    """获取Prometheus注册表"""
    global _exporter_instance
    if _exporter_instance is None:
        _exporter_instance = PrometheusExporter()
    return _exporter_instance.registry


def start_metrics_server(port: int = 9090, host: str = '0.0.0.0') -> PrometheusExporter:
    """启动指标服务器"""
    global _exporter_instance
    if _exporter_instance is None:
        _exporter_instance = PrometheusExporter()
    
    _exporter_instance.start_http_server(port, host)
    return _exporter_instance


def stop_metrics_server():
    """停止指标服务器"""
    global _exporter_instance
    if _exporter_instance:
        _exporter_instance.stop_http_server()


def export_metric(metric, labels: Optional[Dict[str, str]] = None):
    """导出单个指标到Prometheus"""
    global _exporter_instance
    if _exporter_instance is None:
        _exporter_instance = PrometheusExporter()
    
    if isinstance(metric, Counter):
        _exporter_instance.export_counter(metric, labels)
    elif isinstance(metric, Gauge):
        _exporter_instance.export_gauge(metric, labels)
    elif isinstance(metric, Histogram):
        _exporter_instance.export_histogram(metric, labels)
    elif isinstance(metric, Summary):
        _exporter_instance.export_summary(metric, labels)
