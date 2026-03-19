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

## 🧪 测试使用指南

### 运行所有测试
```bash
# 进入模块目录
cd modules/qf-portfolio

# 运行所有测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ -v --cov=src --cov-report=html
```

### 运行特定测试
```bash
# 测试风险平价
pytest tests/test_portfolio.py::TestRiskParity::test_calculate_weights -v

# 测试再平衡
pytest tests/test_portfolio.py::TestRiskParity::test_rebalance -v

# 测试杠杆调整
pytest tests/test_portfolio.py::TestVolatilityTargeting::test_leverage_adjustment -v

# 测试凯利公式
pytest tests/test_portfolio.py::TestKellyCriterion::test_kelly_fraction -v
```

### 测试用例清单

| 测试类 | 测试用例 | 说明 |
|--------|---------|------|
| TestRiskParity | test_calculate_weights | 风险平价权重计算 |
| TestRiskParity | test_rebalance | 再平衡触发条件 |
| TestRiskParity | test_risk_contribution | 风险贡献均衡 |
| TestVolatilityTargeting | test_leverage_adjustment | 杠杆调整 |
| TestVolatilityTargeting | test_target_achievement | 目标达成率 |
| TestKellyCriterion | test_kelly_fraction | 凯利分数计算 |
| TestKellyCriterion | test_half_kelly | 半凯利保守策略 |
| TestMLWeights | test_prediction | ML权重预测 |
| TestMLWeights | test_confidence_filter | 置信度过滤 |

## 依赖
- numpy
- pandas
- scipy
- scikit-learn
- lightgbm
- pytest
- pytest-cov
