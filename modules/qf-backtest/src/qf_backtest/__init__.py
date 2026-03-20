"""QuantForge Backtesting Engine

A high-performance event-driven backtesting framework for quantitative trading strategies.
"""

from .engine import BacktestEngine
from .slippage import SlippageModel, PercentageSlippage, FixedSlippage, NoSlippage, VolumeBasedSlippage, VolatilityBasedSlippage
from .commission import CommissionModel, PercentageCommission, FixedCommission, TieredCommission, HybridCommission, NoCommission
from .metrics import PerformanceMetrics, calculate_metrics
from .optimization import GridSearchOptimizer, optimize_parameters

__version__ = "0.1.0"

__all__ = [
    # Engine
    "BacktestEngine",
    # Slippage models
    "SlippageModel",
    "PercentageSlippage",
    "FixedSlippage",
    "NoSlippage",
    "VolumeBasedSlippage",
    "VolatilityBasedSlippage",
    # Commission models
    "CommissionModel",
    "PercentageCommission",
    "FixedCommission",
    "TieredCommission",
    "HybridCommission",
    "NoCommission",
    # Metrics
    "PerformanceMetrics",
    "calculate_metrics",
    # Optimization
    "GridSearchOptimizer",
    "optimize_parameters",
]
