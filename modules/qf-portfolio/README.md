# qf-portfolio 资金配置模块

## 功能
风险平价、波动率目标、凯利公式、ML权重预测

## 配置策略
1. 风险平价 (Risk Parity)
2. 波动率目标 (Volatility Targeting)
3. 凯利公式 (Kelly Criterion)
4. 机器学习优化

## API接口
```python
from qf_portfolio import PortfolioAllocator

allocator = PortfolioAllocator(capital=1000000)
weights = allocator.calculate_weights()
```

## 测试
```bash
pytest tests/ -v --cov=qf_portfolio
```
