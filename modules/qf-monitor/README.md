# qf-monitor 监控报警模块

QuantForge 监控报警模块，提供实时监控、异常检测和多渠道报警功能。

## 功能特性

### 1. Monitor 监控核心
- 异步监控循环
- 可插拔检查项
- 事件回调机制
- 报警冷却控制

### 2. 实时监控
- **账户检查**: 余额监控、回撤检测
- **持仓检查**: 持仓数量、集中度监控
- **订单检查**: 挂单数量、拒单率、超时订单
- **策略检查**: 运行状态、心跳检测、错误收集

### 3. 异常检测
- **数据延迟**: 行情数据延迟检测
- **系统健康**: CPU、内存、磁盘监控
- **数据库连接**: 连接状态检测

### 4. 报警系统
- 多级报警级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- 报警历史管理
- 级别过滤

### 5. 多渠道通知
- **邮件**: SMTP 支持
- **企业微信**: Webhook 机器人
- **钉钉**: Webhook 机器人（支持加签）

### 6. 结构化日志
- 使用 structlog 记录结构化日志
- 便于日志收集和分析

## 安装

```bash
cd modules/qf-monitor
pip install -e ".[dev]"
```

## 快速开始

```python
import asyncio
from qf_monitor import Monitor, MonitorConfig
from qf_monitor.checks import AccountCheck, PositionCheck, SystemHealthCheck

# 创建配置
config = MonitorConfig(
    check_interval=30,      # 每30秒检查一次
    alert_cooldown=300,     # 报警冷却5分钟
)

# 创建监控器
monitor = Monitor(config)

# 添加检查项
monitor.register_check(AccountCheck(min_balance=50000))
monitor.register_check(PositionCheck(max_positions=50))
monitor.register_check(SystemHealthCheck())

# 添加通知器
from qf_monitor.notifiers import EmailNotifier
email_notifier = EmailNotifier(
    smtp_host="smtp.example.com",
    smtp_port=587,
    username="alert@example.com",
    password="password",
    from_addr="alert@example.com",
    to_addrs=["admin@example.com"],
)
monitor.add_notifier("email", email_notifier)

# 启动监控
asyncio.run(monitor.start())
```

## API 文档

### Monitor 类

```python
from qf_monitor import Monitor, MonitorConfig

# 配置
config = MonitorConfig(
    check_interval=30,           # 检查间隔（秒）
    data_delay_threshold=60,     # 数据延迟阈值（秒）
    cpu_threshold=80.0,          # CPU 阈值
    memory_threshold=80.0,       # 内存阈值
    disk_threshold=90.0,         # 磁盘阈值
    alert_cooldown=300,          # 报警冷却（秒）
)

monitor = Monitor(config)
```

### 检查项

```python
from qf_monitor.checks import (
    AccountCheck,
    PositionCheck,
    OrderCheck,
    StrategyCheck,
    DataDelayCheck,
    SystemHealthCheck,
    DatabaseHealthCheck,
)

# 账户检查
account_check = AccountCheck(
    get_account_func=lambda: {"balance": 100000, "equity": 100000},
    min_balance=50000,
    max_drawdown=0.2,
)

# 持仓检查
position_check = PositionCheck(
    get_positions_func=lambda: [...],
    max_positions=100,
    max_concentration=0.3,
)

# 策略检查
strategy_check = StrategyCheck(
    get_strategies_func=lambda: [...],
    max_staleness=300,
)

# 系统健康检查
health_check = SystemHealthCheck(
    cpu_threshold=80.0,
    memory_threshold=80.0,
    disk_threshold=90.0,
)
```

### 通知器

```python
from qf_monitor.notifiers import EmailNotifier, WechatWorkNotifier, DingTalkNotifier

# 邮件
email = EmailNotifier(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    username="your@email.com",
    password="password",
    from_addr="your@email.com",
    to_addrs=["admin@email.com"],
)

# 企业微信
wechat = WechatWorkNotifier(
    webhook_key="your-webhook-key",
    mentioned_list=["@all"],
)

# 钉钉
ding = DingTalkNotifier(
    access_token="your-access-token",
    secret="your-secret",  # 可选，用于加签
    at_mobiles=["138xxxx"],
)
```

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ -v --cov=src --cov-report=html

# 运行特定测试
pytest tests/test_monitor.py::TestMonitor -v
```

### 测试覆盖

当前测试覆盖率: **90.4%** (70个测试用例)

## 项目结构

```
qf-monitor/
├── src/qf_monitor/
│   ├── __init__.py          # 模块导出
│   ├── monitor.py           # 监控核心
│   ├── checks.py            # 检查项
│   ├── alerts.py            # 报警管理
│   └── notifiers/           # 通知器
│       ├── __init__.py
│       ├── email.py         # 邮件通知
│       ├── wechat.py        # 企业微信
│       └── dingtalk.py      # 钉钉
├── tests/
│   ├── test_monitor.py      # 核心测试
│   └── test_notifiers.py    # 通知器测试
├── pyproject.toml           # 项目配置
└── README.md               # 本文件
```

## 依赖

- requests >= 2.31.0
- prometheus-client >= 0.17.0
- pyyaml >= 6.0
- pydantic >= 2.0.0
- structlog >= 23.0.0
- psutil >= 5.9.0

## 许可证

MIT License
