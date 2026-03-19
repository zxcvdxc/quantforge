# qf-risk 风险管理模块

## 功能
仓位控制、止损、熔断、风险计算

## 风险控制
- 总仓位上限
- 单一品种限制
- 止损止盈
- 熔断机制

## API接口
```python
from qf_risk import RiskManager

risk = RiskManager()
risk.check_order(order)
```

## 测试
```bash
pytest tests/ -v --cov=qf_risk
```
