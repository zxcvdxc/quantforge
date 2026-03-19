# qf-monitor 监控模块

## 功能
实时监控、异常报警、绩效可视化

## 监控项
- 账户资金与持仓
- 策略运行状态
- 订单执行情况
- 系统性能指标

## 报警方式
- 邮件
- 企业微信
- 短信

## API接口
```python
from qf_monitor import Monitor

monitor = Monitor()
monitor.check_status()
```

## 测试
```bash
pytest tests/ -v --cov=qf_monitor
```
