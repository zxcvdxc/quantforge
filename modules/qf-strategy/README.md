# qf-strategy 策略模块

## 功能
策略基类与套利策略实现

## 策略列表
- 期现套利 (Basis Arbitrage)
- 跨期套利 (Calendar Spread)
- 跨品种套利
- 趋势跟踪

## API接口
```python
from qf_strategy import BasisStrategy

strategy = BasisStrategy()
signal = strategy.on_bar(bar)
```

## 🧪 测试使用指南

### 运行所有测试
```bash
# 进入模块目录
cd modules/qf-strategy

# 运行所有测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ -v --cov=src --cov-report=html
```

### 运行特定测试
```bash
# 测试期现套利信号
pytest tests/test_strategy.py::TestBasisStrategy::test_signal_generation -v

# 测试基差计算
pytest tests/test_strategy.py::TestBasisStrategy::test_basis_calculation -v

# 测试跨期套利
pytest tests/test_strategy.py::TestCalendarSpread::test_spread_calculation -v
```

### 测试用例清单

| 策略类 | 测试用例 | 说明 |
|--------|---------|------|
| TestBasisStrategy | test_signal_generation | 套利信号生成 |
| TestBasisStrategy | test_basis_calculation | 基差计算 |
| TestBasisStrategy | test_open_position | 开仓条件 |
| TestBasisStrategy | test_close_position | 平仓条件 |
| TestCalendarSpread | test_spread_calculation | 价差计算 |
| TestCalendarSpread | test_convergence | 收敛判断 |
| TestTrendFollowing | test_trend_detection | 趋势检测 |
| TestTrendFollowing | test_ma_cross | 均线交叉 |

## 依赖
- numpy
- pandas
- ta-lib
- pytest
- pytest-cov
