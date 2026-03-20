"""
Risk Parity - 风险平价算法

各品种风险贡献相等的资产配置方法
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import minimize


class RiskParity:
    """
    风险平价配置器
    
    确保每个资产对组合总风险的贡献相等
    """
    
    def __init__(
        self,
        risk_budget: Optional[Dict[str, float]] = None,
        max_iter: int = 1000,
        tol: float = 1e-6,
    ):
        """
        初始化风险平价配置器
        
        Args:
            risk_budget: 自定义风险预算（默认等风险贡献）
            max_iter: 优化最大迭代次数
            tol: 优化收敛容差
        """
        self.risk_budget = risk_budget
        self.max_iter = max_iter
        self.tol = tol
        self.weights_history: List[Dict[str, float]] = []
    
    def calculate_weights(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame] = None,
        cov_matrix: Optional[np.ndarray] = None,
        **kwargs
    ) -> Dict[str, float]:
        """
        计算风险平价权重
        
        Args:
            symbols: 资产代码列表
            returns_data: 历史收益率数据
            cov_matrix: 协方差矩阵（可选，如果提供了returns_data则自动计算）
            **kwargs: 额外参数
        
        Returns:
            Dict[str, float]: 各资产权重
        """
        n = len(symbols)
        if n == 0:
            return {}
        
        # 计算或验证协方差矩阵
        if cov_matrix is None:
            if returns_data is not None and not returns_data.empty:
                # 过滤存在的列
                available_symbols = [s for s in symbols if s in returns_data.columns]
                if len(available_symbols) < n:
                    missing = set(symbols) - set(available_symbols)
                    # 为缺失的资产创建对角协方差矩阵
                    cov_matrix = self._create_simple_cov_matrix(symbols, returns_data)
                else:
                    cov_matrix = returns_data[symbols].cov().values
            else:
                # 没有数据时使用单位矩阵
                cov_matrix = np.eye(n)
        
        # 确保协方差矩阵是正定矩阵
        cov_matrix = self._ensure_positive_definite(cov_matrix)
        
        # 风险预算（默认等风险贡献）
        if self.risk_budget is None:
            risk_budget = np.ones(n) / n
        else:
            risk_budget = np.array([
                self.risk_budget.get(s, 1.0 / n) for s in symbols
            ])
            risk_budget = risk_budget / risk_budget.sum()
        
        # 优化风险平价权重
        weights = self._optimize_risk_parity(cov_matrix, risk_budget)
        
        result = {symbols[i]: weights[i] for i in range(n)}
        self.weights_history.append(result)
        
        return result
    
    def calculate_risk_contributions(
        self,
        weights: Dict[str, float],
        returns_data: Optional[pd.DataFrame] = None,
        cov_matrix: Optional[np.ndarray] = None,
    ) -> Dict[str, float]:
        """
        计算各资产的风险贡献
        
        Args:
            weights: 资产权重
            returns_data: 历史收益率数据
            cov_matrix: 协方差矩阵
        
        Returns:
            Dict[str, float]: 各资产的风险贡献
        """
        symbols = list(weights.keys())
        w = np.array([weights[s] for s in symbols])
        
        if cov_matrix is None:
            if returns_data is not None:
                available_symbols = [s for s in symbols if s in returns_data.columns]
                if set(available_symbols) == set(symbols):
                    cov_matrix = returns_data[symbols].cov().values
                else:
                    cov_matrix = self._create_simple_cov_matrix(symbols, returns_data)
            else:
                n = len(symbols)
                cov_matrix = np.eye(n)
        
        # 投资组合波动率
        portfolio_var = np.dot(w.T, np.dot(cov_matrix, w))
        portfolio_vol = np.sqrt(portfolio_var)
        
        if portfolio_vol == 0:
            return {s: 0.0 for s in symbols}
        
        # 边际风险贡献
        marginal_rc = np.dot(cov_matrix, w)
        
        # 风险贡献
        rc = w * marginal_rc / portfolio_vol
        
        return {symbols[i]: rc[i] for i in range(len(symbols))}
    
    def get_risk_parity_deviation(
        self,
        weights: Dict[str, float],
        returns_data: Optional[pd.DataFrame] = None,
    ) -> float:
        """
        计算风险平价的偏离度
        
        返回各资产风险贡献的方差，越小表示越接近风险平价
        """
        rc = self.calculate_risk_contributions(weights, returns_data)
        rc_values = list(rc.values())
        return float(np.var(rc_values))
    
    def _optimize_risk_parity(
        self,
        cov_matrix: np.ndarray,
        risk_budget: np.ndarray,
    ) -> np.ndarray:
        """
        优化风险平价权重
        
        最小化风险贡献与风险预算的差异
        """
        n = len(risk_budget)
        
        # 初始权重：等权重
        x0 = np.ones(n) / n
        
        # 约束：权重和为1，权重非负
        constraints = [
            {"type": "eq", "fun": lambda x: np.sum(x) - 1.0}
        ]
        bounds = [(0.0, 1.0) for _ in range(n)]
        
        # 优化目标：最小化风险贡献与风险预算的差异
        result = minimize(
            self._risk_parity_objective,
            x0,
            args=(cov_matrix, risk_budget),
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": self.max_iter, "ftol": self.tol},
        )
        
        if result.success:
            weights = result.x
        else:
            # 优化失败时回退到简单逆波动率
            inv_vol = 1.0 / np.sqrt(np.diag(cov_matrix))
            weights = inv_vol / inv_vol.sum()
        
        return weights
    
    def _risk_parity_objective(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray,
        risk_budget: np.ndarray,
    ) -> float:
        """
        风险平价目标函数
        
        最小化风险贡献与风险预算之间的差异
        """
        portfolio_var = np.dot(weights.T, np.dot(cov_matrix, weights))
        
        if portfolio_var == 0:
            return 1e10
        
        portfolio_vol = np.sqrt(portfolio_var)
        
        # 边际风险贡献
        marginal_rc = np.dot(cov_matrix, weights)
        
        # 风险贡献
        rc = weights * marginal_rc / portfolio_vol
        
        # 风险贡献占比
        rc_pct = rc / portfolio_vol if portfolio_vol > 0 else np.zeros_like(rc)
        
        # 目标：风险贡献占比等于风险预算
        diff = rc_pct - risk_budget
        
        return np.sum(diff ** 2)
    
    def _ensure_positive_definite(self, matrix: np.ndarray) -> np.ndarray:
        """确保矩阵是正定矩阵"""
        eigenvalues = np.linalg.eigvals(matrix)
        if np.all(eigenvalues > 0):
            return matrix
        
        # 添加对角线项使矩阵正定
        min_eigenvalue = np.min(eigenvalues)
        if min_eigenvalue <= 0:
            matrix = matrix + np.eye(matrix.shape[0]) * (abs(min_eigenvalue) + 1e-6)
        
        return matrix
    
    def _create_simple_cov_matrix(
        self,
        symbols: List[str],
        returns_data: pd.DataFrame,
    ) -> np.ndarray:
        """创建简化协方差矩阵（包含缺失资产）"""
        n = len(symbols)
        cov_matrix = np.eye(n) * 0.01  # 默认小波动率
        
        for i, s1 in enumerate(symbols):
            if s1 in returns_data.columns:
                vol = returns_data[s1].std()
                cov_matrix[i, i] = vol ** 2 if not pd.isna(vol) else 0.01
        
        return cov_matrix
    
    def inverse_volatility_weights(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame] = None,
        volatilities: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        逆波动率权重（风险平价的近似解）
        
        Args:
            symbols: 资产代码列表
            returns_data: 历史收益率数据
            volatilities: 直接提供波动率
        
        Returns:
            Dict[str, float]: 逆波动率权重
        """
        if volatilities is not None:
            vols = np.array([volatilities.get(s, 0.2) for s in symbols])
        elif returns_data is not None:
            vols = np.array([
                returns_data[s].std() if s in returns_data.columns else 0.2
                for s in symbols
            ])
        else:
            vols = np.ones(len(symbols)) * 0.2
        
        # 避免除零
        vols = np.maximum(vols, 1e-6)
        inv_vols = 1.0 / vols
        weights = inv_vols / inv_vols.sum()
        
        return {symbols[i]: weights[i] for i in range(len(symbols))}
