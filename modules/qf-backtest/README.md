# QF-Backtest

QuantForge 回测引擎 - 高性能事件驱动回测框架

## 功能特性

- **事件驱动架构** - 模拟真实交易流程，支持订单提交、成交、取消等完整生命周期
- **BacktestEngine** - 核心回测引擎，支持多品种同时回测
- **滑点模型** - 支持百分比滑点、固定滑点、成交量滑点、波动率滑点
- **手续费模型** - 支持百分比手续费、固定手续费、阶梯手续费、混合手续费
- **绩效分析** - 收益率、夏普比率、最大回撤、胜率、索提诺比率、卡尔玛比率
- **参数优化** - 网格搜索、滚动窗口优化

## 安装

```bash
pip install qf-backtest
```

## 快速开始

```python
import pandas as pd
from qf_backtest import (
    BacktestEngine,
    PercentageSlippage,
    PercentageCommission,
    OrderSide,
)

# 准备数据
data = pd.DataFrame({
    "timestamp": pd.date_range("2024-01-01", periods=100),
    "symbol": "AAPL",
    "open": [...],
    "high": [...],
    "low": [...],
    "close": [...],
    "volume": [...],
})

# 定义策略
def simple_strategy(engine, market_data):
    position = engine.get_position_quantity(market_data.symbol)
    
    if position == 0 and market_data.close > market_data.open:
        engine.submit_order(market_data.symbol, OrderSide.BUY, 100)
    elif position > 0 and market_data.close < market_data.open:
        engine.submit_order(market_data.symbol, OrderSide.SELL, position)

# 创建引擎
engine = BacktestEngine(
    initial_capital=100000.0,
    slippage_model=PercentageSlippage(slippage_pct=0.001),
    commission_model=PercentageCommission(rate=0.001),
)

# 运行回测
equity_curve = engine.run(data, simple_strategy)

# 查看结果
print(equity_curve.tail())
print(engine.get_trades())
```

## 滑点模型

```python
from qf_backtest import (
    NoSlippage,           # 无滑点
    PercentageSlippage,   # 百分比滑点
    FixedSlippage,        # 固定滑点
    VolumeBasedSlippage,  # 成交量滑点
    VolatilityBasedSlippage,  # 波动率滑点
)
```

## 手续费模型

```python
from qf_backtest import (
    NoCommission,           # 无手续费
    PercentageCommission,   # 百分比手续费
    FixedCommission,        # 固定手续费
    TieredCommission,       # 阶梯手续费
    HybridCommission,       # 混合手续费
)
```

## 绩效指标

```python
from qf_backtest import calculate_metrics

metrics = calculate_metrics(
    equity_curve=equity_curve,
    trades=engine.get_trades(),
    initial_capital=100000.0,
)

print(f"总收益率: {metrics.total_return:.2%}")
print(f"夏普比率: {metrics.sharpe_ratio:.2f}")
print(f"最大回撤: {metrics.max_drawdown:.2%}")
print(f"胜率: {metrics.win_rate:.2%}")
```

## 参数优化

```python
from qf_backtest import optimize_parameters

# 定义策略工厂
def strategy_factory(fast_period, slow_period):
    def strategy(engine, data):
        # 使用参数的策略逻辑
        pass
    return strategy

# 参数网格
param_grid = {
    "fast_period": [5, 10, 20],
    "slow_period": [30, 50, 100],
}

# 优化
best_params, best_metrics = optimize_parameters(
    data=data,
    strategy_factory=strategy_factory,
    param_grid=param_grid,
    scoring="sharpe_ratio",
    maximize=True,
)

print(f"最佳参数: {best_params}")
```

## 测试

```bash
pytest tests/ --cov=qf_backtest --cov-report=html
```

## 许可证

MIT License
