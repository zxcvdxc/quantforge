"""
QuantForge Portfolio Allocation Module

qf-portfolio: 资金配置核心模块
支持风险平价、波动率目标、凯利公式和ML权重预测
"""

from .allocator import PortfolioAllocator, AllocationStrategy
from .risk_parity import RiskParity
from .volatility_target import VolatilityTargeting
from .kelly import KellyCriterion
from .ml_weights import MLWeightsPredictor

__version__ = "0.1.0"
__all__ = [
    "PortfolioAllocator",
    "AllocationStrategy",
    "RiskParity",
    "VolatilityTargeting",
    "KellyCriterion",
    "MLWeightsPredictor",
]
