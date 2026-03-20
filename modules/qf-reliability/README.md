# qf-reliability: QuantForge 可靠性模块

提供断路器、重试机制、优雅降级和健康检查功能。

## 功能特性

### 1. 断路器模式 (Circuit Breaker)
- 防止级联故障
- 自动熔断和恢复
- 三种状态: CLOSED(正常)、OPEN(熔断)、HALF_OPEN(半开)
- 支持同步和异步函数

### 2. 重试机制 (Retry)
- 指数退避重试
- 多种重试策略: FIXED、EXPONENTIAL、LINEAR、RANDOM
- 支持最大延迟限制
- 支持抖动(jitter)避免惊群效应

### 3. 优雅降级 (Fallback)
- 缓存降级: 使用本地/远程缓存
- 静态降级: 返回默认值
- 备用服务: 切换到备用API/服务
- 部分数据: 返回简化版数据
- 历史数据降级: 当实时数据不可用时使用历史数据

### 4. 健康检查 (Health Check)
- 定期检查依赖服务健康状态
- 自动故障转移
- 服务发现
- 健康历史记录
- 服务端点管理

### 5. 混沌测试 (Chaos)
- 随机故障注入
- 多种故障类型: 异常、延迟、超时、返回错误值
- 可配置的故障率
- 细粒度故障注入控制

## 安装

```bash
cd modules/qf-reliability
pip install -e .
```

## 使用示例

### 断路器

```python
from qf_reliability import circuit_breaker, CircuitBreaker

# 装饰器方式
@circuit_breaker(name="mysql_query", failure_threshold=5, timeout=60.0)
def query_database(sql):
    return execute(sql)

# 直接使用
breaker = CircuitBreaker("api_call", failure_threshold=3)
try:
    result = breaker.call(call_external_api, url)
except CircuitBreakerOpenError:
    # 断路器打开，使用降级逻辑
    result = get_cached_data()
```

### 重试机制

```python
from qf_reliability import retry_with_backoff, RetryStrategy

@retry_with_backoff(
    max_attempts=5,
    base_delay=1.0,
    max_delay=30.0,
    strategy=RetryStrategy.EXPONENTIAL,
    retry_on_exceptions=[ConnectionError, TimeoutError]
)
def call_unreliable_api():
    return requests.get("https://api.example.com/data")
```

### 优雅降级

```python
from qf_reliability import fallback, DegradationStrategy

@fallback(
    strategy=DegradationStrategy.CACHE,
    cache_ttl=300
)
def get_market_data(symbol):
    return fetch_from_api(symbol)

@fallback(
    strategy=DegradationStrategy.STATIC,
    static_value={"price": 0, "volume": 0}
)
def get_ticker(symbol):
    return fetch_ticker(symbol)
```

### 健康检查

```python
from qf_reliability import HealthChecker, health_check

checker = HealthChecker(check_interval=30.0)

# 注册检查项
checker.register("mysql", check_mysql_connection)
checker.register("redis", check_redis_connection)

# 启动检查
checker.start()

# 获取健康状态
status = checker.get_overall_status()
```

### 混沌测试

```python
from qf_reliability import chaos_test, FailureType, ChaosEngine

# 装饰器方式
@chaos_test(failure_rate=0.2, failure_types=[FailureType.EXCEPTION])
def test_function():
    return something()

# 引擎方式
chaos = ChaosEngine(failure_rate=0.1)
chaos.enable()

with chaos.session(failure_rate=0.5):
    result = operation()
```

## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行混沌测试
pytest tests/ -v -m chaos

# 带覆盖率
pytest tests/ --cov=qf_reliability --cov-report=html
```

## 架构设计

```
qf_reliability/
├── __init__.py          # 模块导出
├── circuit_breaker.py   # 断路器实现
├── retry.py             # 重试机制
├── fallback.py          # 优雅降级
├── health_check.py      # 健康检查
└── chaos.py             # 混沌测试
```

## 集成到 QuantForge

```python
from qf_reliability import (
    circuit_breaker,
    retry_with_backoff,
    fallback,
    DegradationStrategy,
    HealthChecker
)

# 数据库连接带断路器和重试
@circuit_breaker(name="db_connection", failure_threshold=5)
@retry_with_backoff(max_attempts=3, retry_on_exceptions=[ConnectionError])
def connect_database():
    return create_connection()

# API调用带降级
@fallback(strategy=DegradationStrategy.CACHE, cache_ttl=60)
@retry_with_backoff(max_attempts=3)
def fetch_market_data(symbol):
    return api.get_ticker(symbol)
```

## 许可证

MIT
