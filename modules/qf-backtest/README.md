# qf-backtest 回测模块

## 功能
事件驱动回测、绩效分析、参数优化

## 特性
- 真实成交模拟
- 滑点与手续费
- 多维度绩效分析
- Walk-forward优化

## API接口
```python
from qf_backtest import BacktestEngine

bt = BacktestEngine()
bt.run(strategy, data)
```

## 🧪 测试使用指南

### 运行所有测试
```bash
# 进入模块目录
cd modules/qf-backtest

# 运行所有测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ -v --cov=src --cov-report=html
```

### 运行特定测试
```bash
# 测试回测运行
pytest tests/test_backtest.py::TestBacktestEngine::test_run_backtest -v

# 测试绩效指标
pytest tests/test_backtest.py::TestBacktestEngine::test_performance_metrics -v

# 测试滑点模型
pytest tests/test_backtest.py::TestBacktestEngine::test_slippage_model -v
```

### 测试用例清单

| 测试用例 | 说明 |
|---------|------|
| test_run_backtest | 回测运行流程 |
| test_performance_metrics | 绩效指标计算 |
| test_slippage_model | 滑点模型 |
| test_commission | 手续费计算 |
| test_fill_logic | 成交逻辑 |
| test_event_driven | 事件驱动机制 |
| test_equity_curve | 权益曲线 |
| test_drawdown | 回撤计算 |
| test_sharpe_ratio | 夏普比率 |
| test_walk_forward | Walk-forward优化 |

## 依赖
- numpy
- pandas
- matplotlib
- scipy
- pytest
- pytest-cov
