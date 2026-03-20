"""
Volatility Targeting - 波动率目标配置

动态调整杠杆以达到目标波动率（默认15%年化）
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


class VolatilityTargeting:
    """
    波动率目标配置器
    
    根据当前市场波动率动态调整杠杆，使组合波动率维持在目标水平
    """
    
    def __init__(
        self,
        target_volatility: float = 0.15,      # 目标年化波动率（默认15%）
        max_leverage: float = 2.0,             # 最大杠杆倍数
        min_leverage: float = 0.5,             # 最小杠杆倍数
        lookback_period: int = 60,             # 回望期（交易日）
        volatility_scaling: str = "sqrt",      # 波动率年化方法
        vol_calc_method: str = "ewm",          # 波动率计算方法: 'simple', 'ewm'
        ewm_span: int = 30,                    # 指数加权移动平均跨度
        smoothing_factor: float = 0.1,         # 杠杆平滑系数
    ):
        """
        初始化波动率目标配置器
        
        Args:
            target_volatility: 目标年化波动率
            max_leverage: 最大杠杆倍数
            min_leverage: 最小杠杆倍数
            lookback_period: 计算波动率的回望期
            volatility_scaling: 波动率年化方法 ('sqrt' 或 'fixed')
            vol_calc_method: 波动率计算方法 ('simple' 或 'ewm')
            ewm_span: 指数加权移动平均的span参数
            smoothing_factor: 杠杆调整平滑系数
        """
        self.target_volatility = target_volatility
        self.max_leverage = max_leverage
        self.min_leverage = min_leverage
        self.lookback_period = lookback_period
        self.volatility_scaling = volatility_scaling
        self.vol_calc_method = vol_calc_method
        self.ewm_span = ewm_span
        self.smoothing_factor = smoothing_factor
        
        self.current_leverage: float = 1.0
        self.leverage_history: List[float] = []
        self.volatility_history: List[float] = []
    
    def calculate_weights(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame] = None,
        base_weights: Optional[Dict[str, float]] = None,
        current_volatility: Optional[float] = None,
        **kwargs
    ) -> Tuple[Dict[str, float], float]:
        """
        计算波动率目标配置权重
        
        Args:
            symbols: 资产代码列表
            returns_data: 历史收益率数据
            base_weights: 基础权重（未加杠杆）
            current_volatility: 当前波动率（如果提供则直接使用）
            **kwargs: 额外参数
        
        Returns:
            Tuple[Dict[str, float], float]: (配置权重, 杠杆倍数)
        """
        n = len(symbols)
        if n == 0:
            return {}, 1.0
        
        # 基础权重
        if base_weights is None:
            if returns_data is not None and not returns_data.empty:
                # 使用逆波动率作为基础权重
                base_weights = self._inverse_vol_weights(symbols, returns_data)
            else:
                # 等权重
                base_weights = {s: 1.0 / n for s in symbols}
        
        # 计算当前波动率
        if current_volatility is None:
            current_volatility = self._calculate_current_volatility(
                symbols, returns_data, base_weights
            )
        
        # 计算目标杠杆
        target_leverage = self._calculate_leverage(current_volatility)
        
        # 平滑杠杆调整
        leverage = self._smooth_leverage(target_leverage)
        self.current_leverage = leverage
        
        # 应用杠杆
        weights = {s: w * leverage for s, w in base_weights.items()}
        
        self.leverage_history.append(leverage)
        self.volatility_history.append(current_volatility)
        
        return weights, leverage
    
    def calculate_volatility_adjusted_weights(
        self,
        symbols: List[str],
        returns_data: pd.DataFrame,
        volatility_lookback: int = 20,
    ) -> Dict[str, float]:
        """
        计算基于各资产波动率调整的权重
        
        对每个资产单独应用波动率缩放
        
        Args:
            symbols: 资产代码列表
            returns_data: 历史收益率数据
            volatility_lookback: 波动率计算回望期
        
        Returns:
            Dict[str, float]: 波动率调整后的权重
        """
        if returns_data.empty or len(symbols) == 0:
            return {s: 1.0 / len(symbols) for s in symbols}
        
        volatilities = {}
        for symbol in symbols:
            if symbol in returns_data.columns:
                vol = self._calculate_volatility(
                    returns_data[symbol].dropna(),
                    lookback=min(volatility_lookback, len(returns_data))
                )
                volatilities[symbol] = vol
            else:
                volatilities[symbol] = 0.2  # 默认20%波动率
        
        # 逆波动率权重
        inv_vols = {s: 1.0 / max(v, 1e-6) for s, v in volatilities.items()}
        total = sum(inv_vols.values())
        
        if total > 0:
            weights = {s: v / total for s, v in inv_vols.items()}
        else:
            weights = {s: 1.0 / len(symbols) for s in symbols}
        
        return weights
    
    def get_volatility_forecast(
        self,
        returns_data: pd.DataFrame,
        method: str = "garch",
        horizon: int = 1,
    ) -> float:
        """
        预测未来波动率
        
        Args:
            returns_data: 历史收益率数据
            method: 预测方法 ('simple', 'ewm', 'garch')
            horizon: 预测 horizon
        
        Returns:
            float: 预测的年化波动率
        """
        if returns_data.empty:
            return self.target_volatility
        
        if method == "simple":
            # 简单历史波动率
            vol = returns_data.std() * np.sqrt(252)
            return float(vol.mean())
        
        elif method == "ewm":
            # 指数加权移动平均
            ewm_vol = returns_data.ewm(span=self.ewm_span).std().iloc[-1]
            return float(ewm_vol.mean() * np.sqrt(252))
        
        elif method == "garch":
            # 简化GARCH(1,1)实现
            return self._garch_forecast(returns_data, horizon)
        
        else:
            return self.target_volatility
    
    def get_risk_metrics(self) -> Dict[str, float]:
        """获取风险指标"""
        metrics = {
            "target_volatility": self.target_volatility,
            "current_leverage": self.current_leverage,
            "max_leverage": self.max_leverage,
            "min_leverage": self.min_leverage,
        }
        
        if self.leverage_history:
            metrics["avg_leverage"] = np.mean(self.leverage_history)
            metrics["max_historical_leverage"] = max(self.leverage_history)
            metrics["min_historical_leverage"] = min(self.leverage_history)
        
        if self.volatility_history:
            metrics["current_volatility"] = self.volatility_history[-1]
            metrics["avg_volatility"] = np.mean(self.volatility_history)
        
        return metrics
    
    def _calculate_current_volatility(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame],
        weights: Dict[str, float],
    ) -> float:
        """计算当前组合波动率"""
        if returns_data is None or returns_data.empty:
            return self.target_volatility * 0.8  # 假设当前波动率略低于目标
        
        # 过滤存在的列
        available_symbols = [s for s in symbols if s in returns_data.columns]
        if not available_symbols:
            return self.target_volatility
        
        # 计算回望期
        lookback = min(self.lookback_period, len(returns_data))
        recent_returns = returns_data[available_symbols].tail(lookback)
        
        if len(recent_returns) < 2:
            return self.target_volatility
        
        # 计算加权组合收益率序列
        w = np.array([weights.get(s, 0) for s in available_symbols])
        portfolio_returns = recent_returns @ w
        
        # 计算波动率
        volatility = self._calculate_volatility(portfolio_returns, lookback)
        
        # 年化
        if self.volatility_scaling == "sqrt":
            volatility *= np.sqrt(252)
        
        return volatility
    
    def _calculate_volatility(
        self,
        returns: pd.Series,
        lookback: int,
    ) -> float:
        """计算波动率"""
        returns = returns.dropna()
        
        if len(returns) < 2:
            return 0.01  # 默认1%波动率
        
        if self.vol_calc_method == "ewm":
            # 指数加权移动平均
            vol = returns.ewm(span=min(self.ewm_span, len(returns))).std().iloc[-1]
        else:
            # 简单标准差
            vol = returns.std()
        
        return float(vol) if not pd.isna(vol) else 0.01
    
    def _calculate_leverage(self, current_volatility: float) -> float:
        """计算目标杠杆"""
        if current_volatility <= 0:
            return 1.0
        
        # 杠杆 = 目标波动率 / 当前波动率
        leverage = self.target_volatility / current_volatility
        
        # 应用限制
        leverage = np.clip(leverage, self.min_leverage, self.max_leverage)
        
        return leverage
    
    def _smooth_leverage(self, target_leverage: float) -> float:
        """平滑杠杆调整"""
        # 使用指数平滑
        smoothed = (
            self.smoothing_factor * target_leverage +
            (1 - self.smoothing_factor) * self.current_leverage
        )
        return smoothed
    
    def _inverse_vol_weights(
        self,
        symbols: List[str],
        returns_data: pd.DataFrame,
    ) -> Dict[str, float]:
        """计算逆波动率权重"""
        volatilities = []
        
        for symbol in symbols:
            if symbol in returns_data.columns:
                vol = returns_data[symbol].tail(self.lookback_period).std()
                volatilities.append(vol if not pd.isna(vol) else 0.2)
            else:
                volatilities.append(0.2)
        
        volatilities = np.array(volatilities)
        volatilities = np.maximum(volatilities, 1e-6)
        
        inv_vols = 1.0 / volatilities
        weights = inv_vols / inv_vols.sum()
        
        return {symbols[i]: weights[i] for i in range(len(symbols))}
    
    def _garch_forecast(
        self,
        returns_data: pd.DataFrame,
        horizon: int = 1,
    ) -> float:
        """
        简化的GARCH(1,1)波动率预测
        
        omega + alpha * r^2_{t-1} + beta * sigma^2_{t-1}
        """
        if returns_data.empty:
            return self.target_volatility
        
        # 使用组合收益率
        returns = returns_data.mean(axis=1).dropna()
        
        if len(returns) < 30:
            return float(returns.std() * np.sqrt(252))
        
        # GARCH(1,1)参数估计（简化）
        omega = 0.01
        alpha = 0.1
        beta = 0.85
        
        # 计算历史方差
        returns_squared = returns ** 2
        
        # 初始化方差
        var = returns.var()
        
        # GARCH迭代
        for i in range(1, len(returns)):
            var = omega + alpha * returns_squared.iloc[i-1] + beta * var
        
        # 预测
        for _ in range(horizon):
            var = omega + (alpha + beta) * var
        
        forecast_vol = np.sqrt(var) * np.sqrt(252)
        
        return float(min(forecast_vol, self.target_volatility * 3))
    
    def reset(self) -> None:
        """重置状态"""
        self.current_leverage = 1.0
        self.leverage_history.clear()
        self.volatility_history.clear()
