"""
Portfolio Allocator - 资金配置核心类

核心功能：
- 多策略资金配置
- 月度再平衡
- 权重约束管理
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Tuple, Any
import numpy as np
import pandas as pd


class AllocationStrategy(Enum):
    """资金配置策略枚举"""
    EQUAL_WEIGHT = auto()           # 等权重
    RISK_PARITY = auto()            # 风险平价
    VOLATILITY_TARGET = auto()      # 波动率目标
    KELLY_CRITERION = auto()        # 凯利公式
    ML_WEIGHTS = auto()             # 机器学习权重预测
    COMBINED = auto()               # 组合策略


@dataclass
class AssetConfig:
    """资产配置参数"""
    symbol: str
    min_weight: float = 0.0         # 最小权重
    max_weight: float = 1.0         # 最大权重
    target_weight: float = 0.0      # 目标权重
    volatility: float = 0.0         # 历史波动率
    expected_return: float = 0.0    # 预期收益
    correlation: float = 0.0        # 相关性系数


@dataclass
class AllocationResult:
    """配置结果"""
    weights: Dict[str, float]
    timestamp: datetime
    rebalanced: bool = False
    leverage: float = 1.0
    expected_risk: float = 0.0
    expected_return: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class PortfolioAllocator:
    """
    资金配置核心类
    
    支持多种配置策略，实现月度再平衡
    """
    
    def __init__(
        self,
        capital: float = 1000000.0,
        rebalance_frequency: str = "M",  # M:月度, W:周度, D:日度
        target_volatility: float = 0.15,  # 目标年化波动率15%
        min_weight: float = 0.0,
        max_weight: float = 1.0,
        max_leverage: float = 2.0,
    ):
        self.capital = capital
        self.rebalance_frequency = rebalance_frequency
        self.target_volatility = target_volatility
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.max_leverage = max_leverage
        
        # 资产配置列表
        self.assets: Dict[str, AssetConfig] = {}
        
        # 当前配置状态
        self.current_weights: Dict[str, float] = {}
        self.last_rebalance_date: Optional[datetime] = None
        self.allocation_history: List[AllocationResult] = []
        
        # 策略实例
        self._strategies: Dict[AllocationStrategy, Any] = {}
        
        # 策略权重（组合策略时使用）
        self.strategy_weights: Dict[AllocationStrategy, float] = {
            AllocationStrategy.RISK_PARITY: 0.3,
            AllocationStrategy.VOLATILITY_TARGET: 0.3,
            AllocationStrategy.KELLY_CRITERION: 0.2,
            AllocationStrategy.ML_WEIGHTS: 0.2,
        }
    
    def add_asset(
        self,
        symbol: str,
        min_weight: Optional[float] = None,
        max_weight: Optional[float] = None,
        volatility: float = 0.0,
        expected_return: float = 0.0,
    ) -> None:
        """添加配置资产"""
        self.assets[symbol] = AssetConfig(
            symbol=symbol,
            min_weight=min_weight if min_weight is not None else self.min_weight,
            max_weight=max_weight if max_weight is not None else self.max_weight,
            volatility=volatility,
            expected_return=expected_return,
        )
        if symbol not in self.current_weights:
            self.current_weights[symbol] = 0.0
    
    def remove_asset(self, symbol: str) -> None:
        """移除配置资产"""
        if symbol in self.assets:
            del self.assets[symbol]
        if symbol in self.current_weights:
            del self.current_weights[symbol]
    
    def register_strategy(
        self,
        strategy: AllocationStrategy,
        instance: Any,
    ) -> None:
        """注册策略实例"""
        self._strategies[strategy] = instance
    
    def should_rebalance(self, current_date: Optional[datetime] = None) -> bool:
        """检查是否需要再平衡"""
        if self.last_rebalance_date is None:
            return True
        
        current_date = current_date or datetime.now()
        days_since_rebalance = (current_date - self.last_rebalance_date).days
        
        if self.rebalance_frequency == "D":
            return days_since_rebalance >= 1
        elif self.rebalance_frequency == "W":
            return days_since_rebalance >= 7
        elif self.rebalance_frequency == "M":
            return days_since_rebalance >= 30
        elif self.rebalance_frequency == "Q":
            return days_since_rebalance >= 90
        
        return False
    
    def calculate_weights(
        self,
        strategy: AllocationStrategy = AllocationStrategy.COMBINED,
        returns_data: Optional[pd.DataFrame] = None,
        **kwargs
    ) -> AllocationResult:
        """
        计算资产配置权重
        
        Args:
            strategy: 配置策略
            returns_data: 历史收益率数据
            **kwargs: 额外的策略参数
        
        Returns:
            AllocationResult: 配置结果
        """
        symbols = list(self.assets.keys())
        if not symbols:
            raise ValueError("没有配置任何资产")
        
        if strategy == AllocationStrategy.EQUAL_WEIGHT:
            weights = self._calculate_equal_weight(symbols)
        elif strategy == AllocationStrategy.RISK_PARITY:
            weights = self._calculate_risk_parity(symbols, returns_data, **kwargs)
        elif strategy == AllocationStrategy.VOLATILITY_TARGET:
            weights = self._calculate_volatility_target(symbols, returns_data, **kwargs)
        elif strategy == AllocationStrategy.KELLY_CRITERION:
            weights = self._calculate_kelly(symbols, returns_data, **kwargs)
        elif strategy == AllocationStrategy.ML_WEIGHTS:
            weights = self._calculate_ml_weights(symbols, returns_data, **kwargs)
        elif strategy == AllocationStrategy.COMBINED:
            weights = self._calculate_combined(symbols, returns_data, **kwargs)
        else:
            raise ValueError(f"未知的配置策略: {strategy}")
        
        # 应用权重约束
        weights = self._apply_constraints(weights)
        
        # 归一化权重
        weights = self._normalize_weights(weights)
        
        # 计算预期风险和收益
        expected_risk, expected_return = self._calculate_portfolio_metrics(
            weights, returns_data
        )
        
        result = AllocationResult(
            weights=weights,
            timestamp=datetime.now(),
            rebalanced=True,
            expected_risk=expected_risk,
            expected_return=expected_return,
            metadata={
                "strategy": strategy.name,
                "capital": self.capital,
                "symbols": symbols,
            }
        )
        
        return result
    
    def rebalance(
        self,
        strategy: AllocationStrategy = AllocationStrategy.COMBINED,
        returns_data: Optional[pd.DataFrame] = None,
        force: bool = False,
        **kwargs
    ) -> Optional[AllocationResult]:
        """
        执行再平衡
        
        Args:
            strategy: 配置策略
            returns_data: 历史收益率数据
            force: 是否强制再平衡
            **kwargs: 额外的策略参数
        
        Returns:
            AllocationResult: 配置结果，如果不需要再平衡则返回None
        """
        if not force and not self.should_rebalance():
            return None
        
        result = self.calculate_weights(strategy, returns_data, **kwargs)
        
        self.current_weights = result.weights.copy()
        self.last_rebalance_date = result.timestamp
        self.allocation_history.append(result)
        
        return result
    
    def get_position_sizes(self, prices: Dict[str, float]) -> Dict[str, float]:
        """根据权重计算各资产的持仓数量"""
        positions = {}
        for symbol, weight in self.current_weights.items():
            if symbol in prices and prices[symbol] > 0:
                positions[symbol] = (self.capital * weight) / prices[symbol]
            else:
                positions[symbol] = 0.0
        return positions
    
    def get_rebalance_trades(
        self,
        current_positions: Dict[str, float],
        prices: Dict[str, float],
    ) -> Dict[str, float]:
        """计算再平衡交易"""
        target_positions = self.get_position_sizes(prices)
        trades = {}
        
        all_symbols = set(current_positions.keys()) | set(target_positions.keys())
        for symbol in all_symbols:
            current = current_positions.get(symbol, 0.0)
            target = target_positions.get(symbol, 0.0)
            trades[symbol] = target - current
        
        return trades
    
    def _calculate_equal_weight(self, symbols: List[str]) -> Dict[str, float]:
        """等权重配置"""
        n = len(symbols)
        return {symbol: 1.0 / n for symbol in symbols}
    
    def _calculate_risk_parity(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame],
        **kwargs
    ) -> Dict[str, float]:
        """风险平价配置"""
        if AllocationStrategy.RISK_PARITY in self._strategies:
            strategy = self._strategies[AllocationStrategy.RISK_PARITY]
            weights = strategy.calculate_weights(symbols, returns_data, **kwargs)
        else:
            # 默认实现
            from .risk_parity import RiskParity
            strategy = RiskParity()
            weights = strategy.calculate_weights(symbols, returns_data, **kwargs)
        
        return weights
    
    def _calculate_volatility_target(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame],
        **kwargs
    ) -> Dict[str, float]:
        """波动率目标配置"""
        if AllocationStrategy.VOLATILITY_TARGET in self._strategies:
            strategy = self._strategies[AllocationStrategy.VOLATILITY_TARGET]
            result = strategy.calculate_weights(symbols, returns_data, **kwargs)
            if isinstance(result, tuple):
                weights, leverage = result
            else:
                weights = result
                leverage = 1.0
        else:
            from .volatility_target import VolatilityTargeting
            strategy = VolatilityTargeting(target_volatility=self.target_volatility)
            weights, leverage = strategy.calculate_weights(symbols, returns_data, **kwargs)
        
        return weights
    
    def _calculate_kelly(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame],
        **kwargs
    ) -> Dict[str, float]:
        """凯利公式配置"""
        if AllocationStrategy.KELLY_CRITERION in self._strategies:
            strategy = self._strategies[AllocationStrategy.KELLY_CRITERION]
            weights = strategy.calculate_weights(symbols, returns_data, **kwargs)
        else:
            from .kelly import KellyCriterion
            strategy = KellyCriterion(use_half_kelly=True)
            weights = strategy.calculate_weights(symbols, returns_data, **kwargs)
        
        return weights
    
    def _calculate_ml_weights(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame],
        **kwargs
    ) -> Dict[str, float]:
        """ML权重预测配置"""
        if AllocationStrategy.ML_WEIGHTS in self._strategies:
            strategy = self._strategies[AllocationStrategy.ML_WEIGHTS]
            weights = strategy.predict_weights(symbols, returns_data, **kwargs)
        else:
            from .ml_weights import MLWeightsPredictor
            strategy = MLWeightsPredictor()
            weights = strategy.predict_weights(symbols, returns_data, **kwargs)
        
        return weights
    
    def _calculate_combined(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame],
        **kwargs
    ) -> Dict[str, float]:
        """组合策略配置"""
        combined_weights: Dict[str, float] = {s: 0.0 for s in symbols}
        
        for strategy_type, weight in self.strategy_weights.items():
            if weight <= 0:
                continue
            
            try:
                if strategy_type == AllocationStrategy.RISK_PARITY:
                    weights = self._calculate_risk_parity(symbols, returns_data, **kwargs)
                elif strategy_type == AllocationStrategy.VOLATILITY_TARGET:
                    weights = self._calculate_volatility_target(symbols, returns_data, **kwargs)
                elif strategy_type == AllocationStrategy.KELLY_CRITERION:
                    weights = self._calculate_kelly(symbols, returns_data, **kwargs)
                elif strategy_type == AllocationStrategy.ML_WEIGHTS:
                    weights = self._calculate_ml_weights(symbols, returns_data, **kwargs)
                else:
                    continue
                
                for symbol in symbols:
                    combined_weights[symbol] += weight * weights.get(symbol, 0.0)
            except Exception as e:
                # 如果某个策略失败，跳过
                continue
        
        return combined_weights
    
    def _apply_constraints(self, weights: Dict[str, float]) -> Dict[str, float]:
        """应用权重约束"""
        constrained = {}
        for symbol, weight in weights.items():
            if symbol in self.assets:
                asset = self.assets[symbol]
                constrained[symbol] = np.clip(weight, asset.min_weight, asset.max_weight)
            else:
                constrained[symbol] = np.clip(weight, self.min_weight, self.max_weight)
        return constrained
    
    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """归一化权重"""
        total = sum(abs(w) for w in weights.values())
        if total > 0:
            return {s: w / total for s, w in weights.items()}
        # 如果权重全为0，使用等权重
        n = len(weights)
        return {s: 1.0 / n for s in weights.keys()}
    
    def _calculate_portfolio_metrics(
        self,
        weights: Dict[str, float],
        returns_data: Optional[pd.DataFrame],
    ) -> Tuple[float, float]:
        """计算组合风险和预期收益"""
        if returns_data is None or returns_data.empty:
            # 使用配置的参数
            expected_return = sum(
                weights.get(s, 0) * self.assets[s].expected_return
                for s in self.assets
            )
            # 简化风险计算
            expected_risk = np.sqrt(sum(
                (weights.get(s, 0) * self.assets[s].volatility) ** 2
                for s in self.assets
            ))
            return expected_risk, expected_return
        
        # 使用历史数据计算
        symbols = list(weights.keys())
        available_symbols = [s for s in symbols if s in returns_data.columns]
        
        if not available_symbols:
            return 0.0, 0.0
        
        w = np.array([weights.get(s, 0) for s in available_symbols])
        
        # 预期收益
        mean_returns = returns_data[available_symbols].mean()
        expected_return = np.dot(w, mean_returns)
        
        # 风险（标准差）
        cov_matrix = returns_data[available_symbols].cov()
        expected_risk = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
        
        return expected_risk, expected_return
    
    def get_allocation_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        return {
            "capital": self.capital,
            "assets": list(self.assets.keys()),
            "current_weights": self.current_weights,
            "last_rebalance_date": self.last_rebalance_date,
            "rebalance_count": len(self.allocation_history),
            "rebalance_frequency": self.rebalance_frequency,
            "target_volatility": self.target_volatility,
        }
