# qf-monitor 监控模块

## 功能
实时监控、异常报警、绩效可视化

## 监控项
- 账户资金与持仓
- 策略运行状态
- 订单执行情况
- 系统性能指标

## API接口
```python
from qf_monitor import Monitor

monitor = Monitor()
monitor.check_status()
```

## 🧪 测试使用指南

### 运行所有测试
```bash
# 进入模块目录
cd modules/qf-monitor

# 运行所有测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ -v --cov=src --cov-report=html
```

### 运行特定测试
```bash
# 测试账户检查
pytest tests/test_monitor.py::TestMonitor::test_check_account -v

# 测试报警发送
pytest tests/test_monitor.py::TestMonitor::test_send_alert -v

# 测试健康检查
pytest tests/test_monitor.py::TestMonitor::test_health_check -v
```

### 测试用例清单

| 测试用例 | 说明 |
|---------|------|
| test_check_account | 账户资金检查 |
| test_check_position | 持仓检查 |
| test_send_alert | 报警发送 |
| test_check_strategy_health | 策略健康检查 |
| test_check_data_delay | 数据延迟检测 |
| test_health_check | 系统健康检查 |
| test_email_alert | 邮件报警 |
| test_wechat_alert | 微信报警 |

## 依赖
- requests
- prometheus-client
- pyyaml
- pytest
- pytest-cov
