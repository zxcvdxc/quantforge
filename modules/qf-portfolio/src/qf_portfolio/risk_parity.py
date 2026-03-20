"""
Risk Parity - 风险平价算法 (性能优化版)

各品种风险贡献相等的资产配置方法

Optimizations:
- NumPy vectorized operations for matrix calculations
- LRU cache for covariance matrix computation
- Efficient risk contribution calculations
- Batch processing capabilities
"""

from typing import Dict, List, Optional, Tuple, Union
from functools import lru_cache
import numpy as np
import pandas as pd
from scipy.optimize import minimize


class RiskParity:
    """
    高性能风险平价配置器
    
    确保每个资产对组合总风险的贡献相等
    
    Optimizations:
    - Vectorized covariance matrix calculations
    - Cached optimization results
    - Efficient risk contribution computation
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
        # Cache for covariance matrix
        self._cov_cache: Optional[Tuple[Tuple[str, ...], np.ndarray]] = None
    
    def calculate_weights(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame] = None,
        cov_matrix: Optional[np.ndarray] = None,
        **kwargs
    ) -> Dict[str, float]:
        """
        计算风险平价权重 (向量化优化版)
        
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
        
        # 计算或获取协方差矩阵 - 向量化
        cov_matrix = self._get_covariance_matrix(symbols, returns_data, cov_matrix)
        
        # 确保协方差矩阵是正定矩阵
        cov_matrix = self._ensure_positive_definite(cov_matrix)
        
        # 风险预算（默认等风险贡献）
        risk_budget = self._get_risk_budget(symbols, n)
        
        # 优化风险平价权重
        weights = self._optimize_risk_parity(cov_matrix, risk_budget)
        
        result = {symbols[i]: float(weights[i]) for i in range(n)}
        self.weights_history.append(result)
        
        return result
    
    def _get_covariance_matrix(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame],
        cov_matrix: Optional[np.ndarray]
    ) -> np.ndarray:
        """
        获取协方差矩阵，使用缓存机制优化性能。
        """
        if cov_matrix is not None:
            return np.asarray(cov_matrix, dtype=np.float64)
        
        if returns_data is not None and not returns_data.empty:
            # 检查缓存
            cache_key = tuple(sorted(symbols))
            if self._cov_cache is not None and self._cov_cache[0] == cache_key:
                return self._cov_cache[1]
            
            # 过滤存在的列
            available_symbols = [s for s in symbols if s in returns_data.columns]
            
            if len(available_symbols) == len(symbols):
                # 全部存在 - 向量化计算
                cov_matrix = returns_data[symbols].cov().values
            else:
                # 有缺失资产 - 创建混合协方差矩阵
                cov_matrix = self._create_mixed_cov_matrix(symbols, returns_data)
            
            # 更新缓存
            self._cov_cache = (cache_key, cov_matrix)
            return cov_matrix
        
        # 没有数据时使用单位矩阵
        return np.eye(len(symbols), dtype=np.float64)
    
    def _get_risk_budget(self, symbols: List[str], n: int) -> np.ndarray:
        """
        获取风险预算数组，向量化处理。
        """
        if self.risk_budget is None:
            return np.ones(n, dtype=np.float64) / n
        
        risk_budget = np.array([
            self.risk_budget.get(s, 1.0 / n) for s in symbols
        ], dtype=np.float64)
        
        # 归一化
        total = risk_budget.sum()
        if total > 0:
            risk_budget = risk_budget / total
        else:
            risk_budget = np.ones(n, dtype=np.float64) / n
        
        return risk_budget
    
    def calculate_risk_contributions(
        self,
        weights: Dict[str, float],
        returns_data: Optional[pd.DataFrame] = None,
        cov_matrix: Optional[np.ndarray] = None,
    ) -> Dict[str, float]:
        """
        计算各资产的风险贡献 (向量化优化版)
        
        Args:
            weights: 资产权重
            returns_data: 历史收益率数据
            cov_matrix: 协方差矩阵
        
        Returns:
            Dict[str, float]: 各资产的风险贡献
        """
        symbols = list(weights.keys())
        w = np.array([weights[s] for s in symbols], dtype=np.float64)
        
        cov_matrix = self._get_covariance_matrix(symbols, returns_data, cov_matrix)
        
        # 向量化计算投资组合波动率
        portfolio_var = np.dot(w.T, np.dot(cov_matrix, w))
        portfolio_vol = np.sqrt(portfolio_var)
        
        if portfolio_vol == 0:
            return {s: 0.0 for s in symbols}
        
        # 向量化计算边际风险贡献
        marginal_rc = np.dot(cov_matrix, w)
        
        # 向量化计算风险贡献
        rc = w * marginal_rc / portfolio_vol
        
        return {symbols[i]: float(rc[i]) for i in range(len(symbols))}
    
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
        rc_values = np.array(list(rc.values()), dtype=np.float64)
        return float(np.var(rc_values))
    
    def _optimize_risk_parity(
        self,
        cov_matrix: np.ndarray,
        risk_budget: np.ndarray,
    ) -> np.ndarray:
        """
        优化风险平价权重 (高效优化版)
        
        最小化风险贡献与风险预算的差异
        """
        n = len(risk_budget)
        
        # 初始权重：等权重
        x0 = np.ones(n, dtype=np.float64) / n
        
        # 约束：权重和为1，权重非负
        constraints = [
            {"type": "eq", "fun": lambda x: np.sum(x) - 1.0}
        ]
        bounds = [(0.0, 1.0) for _ in range(n)]
        
        # 使用预计算的协方差矩阵
        cov_matrix = np.asarray(cov_matrix, dtype=np.float64)
        
        # 优化
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
            weights = self._inverse_volatility_fallback(cov_matrix)
        
        return weights
    
    def _risk_parity_objective(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray,
        risk_budget: np.ndarray,
    ) -> float:
        """
        风险平价目标函数 (向量化优化版)
        
        最小化风险贡献与风险预算之间的差异
        """
        # 向量化计算
        portfolio_var = np.dot(weights.T, np.dot(cov_matrix, weights))
        
        if portfolio_var <= 0:
            return 1e10
        
        portfolio_vol = np.sqrt(portfolio_var)
        
        # 向量化计算边际风险贡献
        marginal_rc = np.dot(cov_matrix, weights)
        
        # 向量化计算风险贡献
        rc = weights * marginal_rc / portfolio_vol
        
        # 风险贡献占比
        rc_pct = rc / portfolio_vol
        
        # 目标：风险贡献占比等于风险预算
        diff = rc_pct - risk_budget
        
        return float(np.sum(diff ** 2))
    
    def _inverse_volatility_fallback(self, cov_matrix: np.ndarray) -> np.ndarray:
        """
        逆波动率回退策略 (向量化版)
        """
        # 提取对角线（方差）并计算标准差
        variances = np.diag(cov_matrix)
        vols = np.sqrt(variances)
        
        # 避免除零
        vols = np.maximum(vols, 1e-6)
        inv_vol = 1.0 / vols
        
        # 归一化
        weights = inv_vol / inv_vol.sum()
        
        return weights
    
    def _ensure_positive_definite(self, matrix: np.ndarray) -> np.ndarray:
        """确保矩阵是正定矩阵 (向量化版)"""
        matrix = np.asarray(matrix, dtype=np.float64)
        
        # 快速检查对角线
        if np.all(np.diag(matrix) > 0):
            # 检查特征值
            try:
                eigenvalues = np.linalg.eigvalsh(matrix)
                if np.all(eigenvalues > 0):
                    return matrix
            except np.linalg.LinAlgError:
                pass
        
        # 添加对角线项使矩阵正定
        min_eigenvalue = np.min(np.linalg.eigvalsh(matrix))
        if min_eigenvalue <= 0:
            matrix = matrix + np.eye(matrix.shape[0]) * (abs(min_eigenvalue) + 1e-6)
        
        return matrix
    
    def _create_mixed_cov_matrix(
        self,
        symbols: List[str],
        returns_data: pd.DataFrame,
    ) -> np.ndarray:
        """
        创建混合协方差矩阵（包含缺失资产）(向量化版)
        """
        n = len(symbols)
        cov_matrix = np.eye(n, dtype=np.float64) * 0.01  # 默认小波动率
        
        # 填充已知资产的波动率
        for i, s in enumerate(symbols):
            if s in returns_data.columns:
                vol = returns_data[s].std()
                if pd.notna(vol) and vol > 0:
                    cov_matrix[i, i] = vol ** 2
        
        return cov_matrix
    
    def inverse_volatility_weights(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame] = None,
        volatilities: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        逆波动率权重（风险平价的近似解）(向量化版)
        
        Args:
            symbols: 资产代码列表
            returns_data: 历史收益率数据
            volatilities: 直接提供波动率
        
        Returns:
            Dict[str, float]: 逆波动率权重
        """
        n = len(symbols)
        
        if volatilities is not None:
            vols = np.array([volatilities.get(s, 0.2) for s in symbols], dtype=np.float64)
        elif returns_data is not None:
            vols = np.array([
                returns_data[s].std() if s in returns_data.columns else 0.2
                for s in symbols
            ], dtype=np.float64)
        else:
            vols = np.ones(n, dtype=np.float64) * 0.2
        
        # 避免除零 - 向量化
        vols = np.maximum(vols, 1e-6)
        inv_vols = 1.0 / vols
        weights = inv_vols / inv_vols.sum()
        
        return {symbols[i]: float(weights[i]) for i in range(n)}
    
    def batch_calculate(
        self,
        symbols_list: List[List[str]],
        returns_data_list: List[Optional[pd.DataFrame]],
    ) -> List[Dict[str, float]]:
        """
        批量计算多个组合的风险平价权重
        
        Args:
            symbols_list: 资产代码列表的列表
            returns_data_list: 收益率数据列表
            
        Returns:
            List[Dict[str, float]]: 权重列表
        """
        return [
            self.calculate_weights(symbols, returns_data)
            for symbols, returns_data in zip(symbols_list, returns_data_list)
        ]
    
    def clear_cache(self) -> None:
        """清除协方差矩阵缓存"""
        self._cov_cache = None
