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

## 测试
```bash
pytest tests/ -v --cov=qf_backtest
```
