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

## 测试
```bash
pytest tests/ -v --cov=qf_strategy
```
