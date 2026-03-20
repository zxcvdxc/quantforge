"""
QuantForge 策略模块 - 交易信号生成

提供多种量化交易策略实现：
- BasisStrategy: 期现套利策略
- CalendarSpread: 跨期套利策略  
- DualMA: 双均线趋势跟踪策略
"""

from qf_strategy.base import BaseStrategy, Signal, SignalType, StrategyParameter, BarData, TickData
from qf_strategy.basis_arbitrage import BasisStrategy
from qf_strategy.calendar_spread import CalendarSpread
from qf_strategy.dual_ma import DualMA

__version__ = "0.1.0"
__all__ = [
    # 基类
    "BaseStrategy",
    "Signal", 
    "SignalType",
    "StrategyParameter",
    "BarData",
    "TickData",
    # 策略实现
    "BasisStrategy",
    "CalendarSpread",
    "DualMA",
]
