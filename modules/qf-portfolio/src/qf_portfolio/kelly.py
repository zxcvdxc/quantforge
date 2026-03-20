"""
Kelly Criterion - 凯利公式

最优资产配置公式：f = (bp - q) / b
其中：b = 赔率, p = 胜率, q = 败率

对于投资组合，使用半凯利策略以降低风险
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import minimize


class KellyCriterion:
    """
    凯利公式配置器
    
    基于凯利公式计算最优仓位，支持半凯利等保守策略
    """
    
    def __init__(
        self,
        use_half_kelly: bool = True,          # 使用半凯利策略
        kelly_fraction: float = 0.5,          # 凯利分数（0.5=半凯利）
        max_position: float = 1.0,             # 单个资产最大仓位
        min_position: float = 0.0,             # 单个资产最小仓位
        risk_free_rate: float = 0.02,          # 无风险利率
        window_size: int = 252,                # 历史数据窗口
    ):
        """
        初始化凯利公式配置器
        
        Args:
            use_half_kelly: 是否使用半凯利策略
            kelly_fraction: 凯利分数系数
            max_position: 单个资产最大仓位
            min_position: 单个资产最小仓位
            risk_free_rate: 年化无风险利率
            window_size: 计算统计量的窗口大小
        """
        self.use_half_kelly = use_half_kelly
        self.kelly_fraction = kelly_fraction if use_half_kelly else 1.0
        self.max_position = max_position
        self.min_position = min_position
        self.risk_free_rate = risk_free_rate
        self.window_size = window_size
        
        self.kelly_history: List[Dict[str, float]] = []
    
    def calculate_weights(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame] = None,
        win_rates: Optional[Dict[str, float]] = None,
        payoffs: Optional[Dict[str, float]] = None,
        **kwargs
    ) -> Dict[str, float]:
        """
        计算凯利配置权重
        
        Args:
            symbols: 资产代码列表
            returns_data: 历史收益率数据
            win_rates: 胜率字典（可选）
            payoffs: 赔率字典（可选）
            **kwargs: 额外参数
        
        Returns:
            Dict[str, float]: 各资产权重
        """
        n = len(symbols)
        if n == 0:
            return {}
        
        # 如果有历史数据，使用基于均值方差的凯利公式
        if returns_data is not None and not returns_data.empty:
            weights = self._kelly_mean_variance(symbols, returns_data)
        else:
            # 使用简单的凯利公式
            weights = self._simple_kelly(symbols, win_rates, payoffs)
        
        # 应用凯利分数
        weights = {s: w * self.kelly_fraction for s, w in weights.items()}
        
        # 应用仓位限制
        weights = self._apply_position_limits(weights)
        
        # 归一化
        weights = self._normalize_weights(weights)
        
        self.kelly_history.append(weights)
        
        return weights
    
    def calculate_kelly_fraction(
        self,
        symbol: str,
        returns_data: Optional[pd.Series] = None,
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None,
    ) -> float:
        """
        计算单个资产的凯利分数
        
        Args:
            symbol: 资产代码
            returns_data: 历史收益率序列
            win_rate: 胜率
            avg_win: 平均盈利
            avg_loss: 平均亏损
        
        Returns:
            float: 凯利分数（最优仓位比例）
        """
        if returns_data is not None and not returns_data.empty:
            # 从历史数据计算
            returns = returns_data.dropna()
            if len(returns) == 0:
                return 0.0
            
            # 计算胜率
            wins = returns[returns > 0]
            losses = returns[returns < 0]
            
            if len(wins) == 0:
                return 0.0
            
            p = len(wins) / len(returns)  # 胜率
            
            # 计算平均盈亏
            avg_win = wins.mean() if len(wins) > 0 else 0
            avg_loss = abs(losses.mean()) if len(losses) > 0 else avg_win * 0.5
            
            if avg_loss == 0:
                avg_loss = avg_win * 0.5
        else:
            # 使用提供的参数
            if win_rate is None or avg_win is None:
                return 0.0
            p = win_rate
            avg_loss = abs(avg_loss) if avg_loss is not None else avg_win * 0.5
        
        q = 1 - p  # 败率
        b = avg_win / avg_loss if avg_loss > 0 else 1.0  # 赔率
        
        if b == 0:
            return 0.0
        
        # 凯利公式: f = (bp - q) / b
        f = (b * p - q) / b
        
        # 应用凯利分数
        f *= self.kelly_fraction
        
        return np.clip(f, -self.max_position, self.max_position)
    
    def calculate_growth_rate(
        self,
        weights: Dict[str, float],
        returns_data: pd.DataFrame,
    ) -> float:
        """
        计算配置的预期增长率
        
        G = r_f + sum(w_i * (mu_i - r_f)) - 0.5 * sum(sum(w_i * w_j * cov_ij))
        
        Args:
            weights: 资产权重
            returns_data: 历史收益率数据
        
        Returns:
            float: 预期增长率
        """
        symbols = list(weights.keys())
        available_symbols = [s for s in symbols if s in returns_data.columns]
        
        if not available_symbols:
            return 0.0
        
        w = np.array([weights.get(s, 0) for s in available_symbols])
        
        # 预期收益
        mean_returns = returns_data[available_symbols].mean()
        expected_return = np.dot(w, mean_returns)
        
        # 方差项
        cov_matrix = returns_data[available_symbols].cov()
        variance = np.dot(w.T, np.dot(cov_matrix, w))
        
        # 增长率 = 收益 - 0.5 * 方差
        growth_rate = expected_return - 0.5 * variance
        
        return float(growth_rate)
    
    def calculate_expected_bankruptcy(
        self,
        weights: Dict[str, float],
        returns_data: pd.DataFrame,
        threshold: float = 0.5,
    ) -> float:
        """
        计算破产概率（简化模型）
        
        Args:
            weights: 资产权重
            returns_data: 历史收益率数据
            threshold: 破产阈值（剩余资金比例）
        
        Returns:
            float: 估计的破产概率
        """
        growth_rate = self.calculate_growth_rate(weights, returns_data)
        volatility = self._calculate_portfolio_volatility(weights, returns_data)
        
        if volatility == 0:
            return 0.0 if growth_rate > 0 else 1.0
        
        # 简化模型：基于正态分布假设
        # P(ruin) ≈ exp(-2 * growth_rate * log(1/threshold) / volatility^2)
        from math import log, exp
        ruin_prob = exp(-2 * growth_rate * log(1 / threshold) / (volatility ** 2))
        
        return min(ruin_prob, 1.0)
    
    def get_kelly_summary(self) -> Dict[str, float]:
        """获取凯利公式摘要信息"""
        return {
            "kelly_fraction": self.kelly_fraction,
            "is_half_kelly": self.use_half_kelly,
            "max_position": self.max_position,
            "min_position": self.min_position,
            "risk_free_rate": self.risk_free_rate,
        }
    
    def _kelly_mean_variance(
        self,
        symbols: List[str],
        returns_data: pd.DataFrame,
    ) -> Dict[str, float]:
        """
        基于均值-方差的凯利最优配置
        
        求解：max w^T * mu - 0.5 * w^T * Sigma * w
        约束：sum(w) <= 1, w >= 0
        """
        available_symbols = [s for s in symbols if s in returns_data.columns]
        
        if not available_symbols:
            return {s: 0.0 for s in symbols}
        
        # 计算超额收益和协方差
        mean_returns = returns_data[available_symbols].mean()
        excess_returns = mean_returns - self.risk_free_rate / 252  # 日度化
        cov_matrix = returns_data[available_symbols].cov()
        
        # 确保协方差矩阵正定
        cov_matrix = self._ensure_positive_definite(cov_matrix.values)
        
        n = len(available_symbols)
        
        # 优化目标：最大化增长率
        def objective(w):
            return -(np.dot(w, excess_returns) - 0.5 * np.dot(w.T, np.dot(cov_matrix, w)))
        
        # 约束
        constraints = [
            {"type": "ineq", "fun": lambda w: 1.0 - np.sum(w)},  # sum(w) <= 1
        ]
        bounds = [(0.0, self.max_position) for _ in range(n)]
        
        # 初始猜测：等权重
        x0 = np.ones(n) / n
        
        # 优化
        result = minimize(
            objective,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )
        
        if result.success:
            weights = result.x
        else:
            # 回退到解析解
            try:
                inv_cov = np.linalg.inv(cov_matrix)
                weights = np.dot(inv_cov, excess_returns)
                weights = np.maximum(weights, 0)
                if weights.sum() > 0:
                    weights = weights / weights.sum()
            except np.linalg.LinAlgError:
                weights = np.ones(n) / n
        
        # 构建结果字典
        result_dict = {s: 0.0 for s in symbols}
        for i, s in enumerate(available_symbols):
            result_dict[s] = weights[i]
        
        return result_dict
    
    def _simple_kelly(
        self,
        symbols: List[str],
        win_rates: Optional[Dict[str, float]],
        payoffs: Optional[Dict[str, float]],
    ) -> Dict[str, float]:
        """简单凯利公式（基于胜率和赔率）"""
        weights = {}
        
        for symbol in symbols:
            p = win_rates.get(symbol, 0.5) if win_rates else 0.5
            b = payoffs.get(symbol, 1.0) if payoffs else 1.0
            q = 1 - p
            
            if b > 0:
                f = (b * p - q) / b
                f *= self.kelly_fraction
            else:
                f = 0.0
            
            weights[symbol] = max(f, 0.0)
        
        return weights
    
    def _apply_position_limits(self, weights: Dict[str, float]) -> Dict[str, float]:
        """应用仓位限制"""
        return {
            s: np.clip(w, self.min_position, self.max_position)
            for s, w in weights.items()
        }
    
    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """归一化权重"""
        total = sum(abs(w) for w in weights.values())
        if total > 0:
            normalized = {s: w / total for s, w in weights.items()}
            # 再次应用限制并重新归一化
            constrained = self._apply_position_limits(normalized)
            constrained_total = sum(abs(w) for w in constrained.values())
            if constrained_total > 0:
                return {s: w / constrained_total for s, w in constrained.items()}
            return constrained
        n = len(weights)
        return {s: 1.0 / n for s in weights.keys()}
    
    def _calculate_portfolio_volatility(
        self,
        weights: Dict[str, float],
        returns_data: pd.DataFrame,
    ) -> float:
        """计算组合波动率"""
        symbols = list(weights.keys())
        available_symbols = [s for s in symbols if s in returns_data.columns]
        
        if not available_symbols:
            return 0.0
        
        w = np.array([weights.get(s, 0) for s in available_symbols])
        cov_matrix = returns_data[available_symbols].cov()
        
        volatility = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
        return float(volatility)
    
    def _ensure_positive_definite(self, matrix: np.ndarray) -> np.ndarray:
        """确保矩阵是正定矩阵"""
        eigenvalues = np.linalg.eigvals(matrix)
        if np.all(eigenvalues > 0):
            return matrix
        
        min_eigenvalue = np.min(eigenvalues)
        if min_eigenvalue <= 0:
            matrix = matrix + np.eye(matrix.shape[0]) * (abs(min_eigenvalue) + 1e-6)
        
        return matrix
