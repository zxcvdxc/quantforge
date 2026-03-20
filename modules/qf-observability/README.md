# qf-observability - QuantForge可观测性模块

QuantForge可观测性模块提供全模块可观测性架构，包括结构化日志、指标采集、分布式追踪和性能剖析。

## 功能特性

### 1. 结构化日志 (Logging)
- **JSON格式日志**: 统一日志格式，便于解析和分析
- **日志级别动态调整**: 运行时调整日志级别
- **上下文传递**: 支持 trace_id、span_id 等上下文传递
- **敏感字段自动脱敏**: 自动识别和脱敏敏感信息

### 2. 指标采集 (Metrics)
- **Prometheus格式**: 兼容Prometheus的指标格式
- **业务指标**: 交易延迟、成功率等业务指标
- **系统指标**: CPU、内存、连接数等系统指标
- **自定义指标注册**: 支持自定义业务指标

### 3. 分布式追踪 (Tracing)
- **OpenTelemetry集成**: 基于OpenTelemetry标准
- **请求链路追踪**: 全链路追踪请求
- **性能瓶颈定位**: 快速定位性能问题
- **跨模块追踪**: 支持跨服务/模块追踪

### 4. 性能剖析 (Profiling)
- **代码热点分析**: 识别性能瓶颈
- **内存泄漏检测**: 检测内存泄漏
- **异步任务监控**: 监控异步任务状态

## 快速开始

### 安装

```bash
cd modules/qf-observability
pip install -e .
```

### 基础用法

#### 结构化日志

```python
from qf_observability.logging import configure_logging, get_logger, set_context

# 配置日志
configure_logging(name='myapp', level='INFO')

# 设置上下文
set_context(trace_id='abc123', request_id='req456')

# 获取日志记录器
logger = get_logger()

# 记录日志
logger.info('用户登录成功', user_id='123', ip='192.168.1.1')
```

#### 指标采集

```python
from qf_observability.metrics import (
    TradingMetrics, 
    start_metrics_server,
    get_collector
)

# 启动Prometheus指标服务器
start_metrics_server(port=9090)

# 使用交易指标
trading = TradingMetrics()

# 记录交易
from qf_observability.metrics import TradeRecord
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
trading.record_trade(trade)
```

#### 分布式追踪

```python
from qf_observability.tracing import (
    configure_tracing,
    trace_function,
    get_trace_id,
)

# 配置追踪
configure_tracing(
    service_name='trading-service',
    otlp_endpoint='http://localhost:4317',
    console_export=True,
)

# 使用装饰器追踪函数
@trace_function(name='execute_trade')
def execute_trade(symbol, quantity):
    # 业务逻辑
    pass

# 获取当前trace ID
print(f"Current trace: {get_trace_id()}")
```

#### 性能剖析

```python
from qf_observability.profiling import (
    profile_function,
    get_hotspots,
    MemoryTracker,
)

# 使用装饰器剖析函数
@profile_function
def process_data(data):
    # 处理数据
    return result

# 获取热点
hotspots = get_hotspots(top_n=10)
for hotspot in hotspots:
    print(f"{hotspot.function_name}: {hotspot.total_time}s")

# 内存追踪
with MemoryTracker('data_processing'):
    process_large_dataset()
```

## API文档

### 日志模块

#### `configure_logging(name, level, log_file, json_output)`
配置结构化日志。

**参数:**
- `name`: 日志名称
- `level`: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `log_file`: 日志文件路径 (可选)
- `json_output`: 是否输出JSON格式

#### `get_logger(name)`
获取日志记录器。

#### `set_context(trace_id, span_id, request_id)`
设置日志上下文。

#### `mask_sensitive_fields(data)`
脱敏敏感字段。

### 指标模块

#### `start_metrics_server(port, host)`
启动Prometheus指标服务器。

#### `TradingMetrics()`
交易指标采集器。

方法:
- `record_trade(trade)`: 记录交易
- `get_success_rate()`: 获取成功率
- `get_metrics()`: 获取所有指标

#### `SystemMetrics()`
系统指标采集器。

方法:
- `collect()`: 采集系统指标
- `get_current_usage()`: 获取当前使用情况

### 追踪模块

#### `configure_tracing(service_name, otlp_endpoint, ...)`
配置分布式追踪。

#### `trace_function(name, kind, attributes)`
函数追踪装饰器。

#### `get_current_span()`
获取当前span。

#### `add_span_attribute(key, value)`
添加span属性。

### 性能剖析模块

#### `profile_function(func)`
函数性能剖析装饰器。

#### `get_hotspots(top_n)`
获取热点代码。

#### `detect_memory_leaks()`
检测内存泄漏。

#### `get_async_task_stats()`
获取异步任务统计。

## 配置示例

### Docker Compose

```yaml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
  
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"
      - "4317:4317"
```

### Prometheus配置

```yaml
scrape_configs:
  - job_name: 'quantforge'
    static_configs:
      - targets: ['localhost:9090']
```

## 测试

```bash
# 运行所有测试
pytest

# 运行特定模块测试
pytest tests/test_logging/
pytest tests/test_metrics/
pytest tests/test_tracing/
pytest tests/test_profiling/

# 生成覆盖率报告
pytest --cov=qf_observability --cov-report=html
```

## 集成指南

### 与qf-data集成

```python
from qf_data import DataCollector
from qf_observability import get_logger, get_tracer, TradingMetrics

class ObservableDataCollector(DataCollector):
    def __init__(self):
        self.logger = get_logger('qf_data')
        self.tracer = get_tracer()
        self.metrics = TradingMetrics()
    
    def fetch_data(self, symbol):
        with self.tracer.start_span('fetch_data') as span:
            span.set_attribute('symbol', symbol)
            self.logger.info('Fetching data', symbol=symbol)
            # ... fetch logic
```

### 与qf-execution集成

```python
from qf_observability.tracing import trace_function
from qf_observability.metrics import TradingMetrics

class ObservableExecutionEngine:
    def __init__(self):
        self.metrics = TradingMetrics()
    
    @trace_function(name='execute_order')
    def execute_order(self, order):
        self.metrics.start_trade()
        try:
            # ... execution logic
            self.metrics.record_trade(trade)
        finally:
            self.metrics.end_trade()
```

## 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 许可证

MIT License
