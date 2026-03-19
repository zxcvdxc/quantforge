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

## 🧪 测试使用指南

### 运行所有测试
```bash
# 进入模块目录
cd modules/qf-risk

# 运行所有测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ -v --cov=src --cov-report=html
```

### 运行特定测试
```bash
# 测试仓位限制
pytest tests/test_risk.py::TestRiskManager::test_position_limit -v

# 测试止损
pytest tests/test_risk.py::TestRiskManager::test_stop_loss -v

# 测试熔断
pytest tests/test_risk.py::TestRiskManager::test_circuit_breaker -v

# 测试VaR计算
pytest tests/test_risk.py::TestRiskManager::test_var_calculation -v
```

### 测试覆盖率
```bash
# 强制覆盖率>80%
pytest tests/ --cov=src --cov-fail-under=80
```

## 测试用例清单

| 测试用例 | 说明 |
|---------|------|
| test_position_limit | 单一品种/总仓位限制 |
| test_stop_loss | 止损触发条件 |
| test_take_profit | 止盈触发条件 |
| test_circuit_breaker | 熔断机制 |
| test_var_calculation | 风险价值计算 |
| test_max_drawdown | 最大回撤控制 |
| test_daily_loss_limit | 日亏损上限 |
| test_correlation_risk | 相关性风险 |

## 依赖
- numpy
- pandas
- scipy
- pytest
- pytest-cov
