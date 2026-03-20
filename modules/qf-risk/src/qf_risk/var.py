"""
Value at Risk (VaR) calculation with performance optimizations.

Optimizations:
- NumPy vectorized operations throughout
- LRU cache for repeated calculations
- Efficient percentile and statistics computations
- Optimized Monte Carlo simulation with vectorization
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Union, Tuple
from functools import lru_cache
import numpy as np
from scipy import stats


class VaRMethod(Enum):
    """VaR calculation methods."""
    HISTORICAL = "historical"
    PARAMETRIC = "parametric"
    MONTE_CARLO = "monte_carlo"


@dataclass(frozen=True)
class VaRResult:
    """
    VaR calculation result.
    
    Attributes:
        var_value: VaR value in currency
        var_pct: VaR as percentage
        confidence_level: Confidence level (e.g., 0.95 for 95%)
        method: Calculation method used
        holding_period_days: Holding period in days
        expected_shortfall: CVaR/Expected Shortfall (optional)
    """
    var_value: float
    var_pct: float
    confidence_level: float
    method: VaRMethod
    holding_period_days: int
    expected_shortfall: Optional[float] = None


class VaRCalculator:
    """
    High-performance calculator for Value at Risk (VaR).
    
    Optimizations:
    - Vectorized NumPy operations for all calculations
    - LRU cache for parametric statistics
    - Efficient Monte Carlo simulation
    - Pre-allocated arrays where possible
    """
    
    def __init__(self, confidence_level: float = 0.95, holding_period_days: int = 1):
        """
        Initialize VaR calculator.
        
        Args:
            confidence_level: Confidence level (e.g., 0.95 for 95%)
            holding_period_days: Holding period in days
        """
        self.confidence_level = confidence_level
        self.holding_period_days = holding_period_days
        self._sqrt_holding_period = np.sqrt(holding_period_days)
    
    def calculate(
        self,
        returns: Union[List[float], np.ndarray],
        portfolio_value: float,
        method: VaRMethod = VaRMethod.HISTORICAL,
        num_simulations: int = 10000
    ) -> VaRResult:
        """
        Calculate VaR with optimized methods.
        
        Args:
            returns: Historical returns (decimal, e.g., 0.01 for 1%)
            portfolio_value: Current portfolio value
            method: Calculation method
            num_simulations: Number of simulations for Monte Carlo
            
        Returns:
            VaRResult with calculated VaR
        """
        returns_array = np.asarray(returns, dtype=np.float64)
        
        if method == VaRMethod.HISTORICAL:
            return self._calculate_historical(returns_array, portfolio_value)
        elif method == VaRMethod.PARAMETRIC:
            return self._calculate_parametric(returns_array, portfolio_value)
        elif method == VaRMethod.MONTE_CARLO:
            return self._calculate_monte_carlo(
                returns_array, portfolio_value, num_simulations
            )
        else:
            raise ValueError(f"Unknown VaR method: {method}")
    
    def _calculate_historical(
        self,
        returns: np.ndarray,
        portfolio_value: float
    ) -> VaRResult:
        """
        Calculate historical VaR using vectorized operations.
        
        Uses NumPy's efficient percentile and boolean indexing for
        expected shortfall calculation.
        """
        # Scale returns to holding period - vectorized
        scaled_returns = returns * self._sqrt_holding_period
        
        # Calculate percentile using NumPy's efficient implementation
        var_pct = np.percentile(scaled_returns, (1 - self.confidence_level) * 100)
        var_value = abs(var_pct) * portfolio_value
        
        # Calculate Expected Shortfall (CVaR) - vectorized
        tail_mask = scaled_returns <= var_pct
        tail_returns = scaled_returns[tail_mask]
        
        if len(tail_returns) > 0:
            expected_shortfall = abs(np.mean(tail_returns)) * portfolio_value
        else:
            expected_shortfall = var_value
        
        return VaRResult(
            var_value=var_value,
            var_pct=abs(var_pct),
            confidence_level=self.confidence_level,
            method=VaRMethod.HISTORICAL,
            holding_period_days=self.holding_period_days,
            expected_shortfall=expected_shortfall
        )
    
    def _calculate_parametric(
        self,
        returns: np.ndarray,
        portfolio_value: float
    ) -> VaRResult:
        """
        Calculate parametric (variance-covariance) VaR.
        
        Uses vectorized NumPy statistics and pre-computed Z-scores
        for efficiency.
        """
        # Vectorized mean and std calculation
        mean = np.mean(returns)
        std = np.std(returns, ddof=1)
        
        # Scale to holding period - vectorized
        scaled_mean = mean * self.holding_period_days
        scaled_std = std * self._sqrt_holding_period
        
        # Calculate VaR using normal distribution - cached Z-score lookup
        z_score = self._get_z_score(self.confidence_level)
        var_pct = -(scaled_mean + z_score * scaled_std)
        var_value = var_pct * portfolio_value
        
        # Calculate Expected Shortfall using analytical formula
        # ES = -μ + σ * φ(z) / (1 - α)
        pdf_z = stats.norm.pdf(z_score)
        es_pct = -(scaled_mean - scaled_std * pdf_z / (1 - self.confidence_level))
        expected_shortfall = es_pct * portfolio_value
        
        return VaRResult(
            var_value=var_value,
            var_pct=var_pct,
            confidence_level=self.confidence_level,
            method=VaRMethod.PARAMETRIC,
            holding_period_days=self.holding_period_days,
            expected_shortfall=expected_shortfall
        )
    
    def _calculate_monte_carlo(
        self,
        returns: np.ndarray,
        portfolio_value: float,
        num_simulations: int
    ) -> VaRResult:
        """
        Calculate Monte Carlo VaR with vectorized simulation.
        
        Generates all random samples at once for maximum efficiency.
        """
        mean = np.mean(returns)
        std = np.std(returns, ddof=1)
        
        # Vectorized random number generation
        random_returns = np.random.normal(
            mean * self.holding_period_days,
            std * self._sqrt_holding_period,
            size=num_simulations
        )
        
        # Vectorized percentile calculation
        var_pct = np.percentile(random_returns, (1 - self.confidence_level) * 100)
        var_value = abs(var_pct) * portfolio_value
        
        # Vectorized Expected Shortfall calculation
        tail_mask = random_returns <= var_pct
        tail_returns = random_returns[tail_mask]
        
        if len(tail_returns) > 0:
            expected_shortfall = abs(np.mean(tail_returns)) * portfolio_value
        else:
            expected_shortfall = var_value
        
        return VaRResult(
            var_value=var_value,
            var_pct=abs(var_pct),
            confidence_level=self.confidence_level,
            method=VaRMethod.MONTE_CARLO,
            holding_period_days=self.holding_period_days,
            expected_shortfall=expected_shortfall
        )
    
    @staticmethod
    @lru_cache(maxsize=128)
    def _get_z_score(confidence_level: float) -> float:
        """
        Cached Z-score lookup for normal distribution.
        
        Args:
            confidence_level: Confidence level for Z-score
            
        Returns:
            Z-score for the given confidence level
        """
        return stats.norm.ppf(1 - confidence_level)
    
    def calculate_portfolio_var(
        self,
        weights: Union[List[float], np.ndarray],
        returns_matrix: Union[List[List[float]], np.ndarray],
        portfolio_value: float,
        method: VaRMethod = VaRMethod.PARAMETRIC
    ) -> VaRResult:
        """
        Calculate portfolio VaR using correlation matrix.
        
        Uses vectorized matrix operations for efficient computation.
        
        Args:
            weights: Asset weights (sum to 1)
            returns_matrix: Matrix of asset returns (assets x time)
            portfolio_value: Portfolio value
            method: Calculation method
            
        Returns:
            VaRResult with portfolio VaR
        """
        weights_array = np.asarray(weights, dtype=np.float64)
        returns_array = np.asarray(returns_matrix, dtype=np.float64)
        
        # Vectorized portfolio returns calculation using matrix multiplication
        portfolio_returns = np.dot(weights_array, returns_array)
        
        return self.calculate(portfolio_returns, portfolio_value, method)
    
    def component_var(
        self,
        weights: Union[List[float], np.ndarray],
        returns_matrix: Union[List[List[float]], np.ndarray],
        portfolio_value: float
    ) -> List[dict]:
        """
        Calculate component VaR for each asset using vectorized operations.
        
        Args:
            weights: Asset weights
            returns_matrix: Matrix of asset returns
            portfolio_value: Portfolio value
            
        Returns:
            List of component VaR data for each asset
        """
        weights_array = np.asarray(weights, dtype=np.float64)
        returns_array = np.asarray(returns_matrix, dtype=np.float64)
        
        # Vectorized covariance matrix calculation
        cov_matrix = np.cov(returns_array)
        
        # Vectorized portfolio variance and standard deviation
        port_variance = np.dot(weights_array.T, np.dot(cov_matrix, weights_array))
        port_std = np.sqrt(port_variance)
        
        if port_std == 0:
            n_assets = len(weights_array)
            return [
                {
                    "asset_index": i,
                    "weight": float(weights_array[i]),
                    "marginal_var": 0.0,
                    "component_var": 0.0,
                    "component_var_pct": 0.0
                }
                for i in range(n_assets)
            ]
        
        # Vectorized Z-score lookup
        z_score = self._get_z_score(self.confidence_level)
        
        # Vectorized marginal VaR calculation
        marginal_var = np.dot(cov_matrix, weights_array) * z_score / port_std
        marginal_var *= self._sqrt_holding_period
        
        # Vectorized portfolio VaR
        port_var_pct = port_std * z_score * self._sqrt_holding_period
        port_var = port_var_pct * portfolio_value
        
        # Vectorized component VaR calculation
        component_vars = marginal_var * weights_array * portfolio_value
        
        # Build result using vectorized operations
        return [
            {
                "asset_index": i,
                "weight": float(weights_array[i]),
                "marginal_var": float(marginal_var[i]),
                "component_var": float(component_vars[i]),
                "component_var_pct": (
                    float(component_vars[i] / port_var) if port_var != 0 else 0.0
                )
            }
            for i in range(len(weights_array))
        ]
    
    def batch_calculate(
        self,
        returns_list: List[Union[List[float], np.ndarray]],
        portfolio_values: List[float],
        method: VaRMethod = VaRMethod.HISTORICAL
    ) -> List[VaRResult]:
        """
        Batch calculate VaR for multiple portfolios.
        
        Args:
            returns_list: List of returns arrays
            portfolio_values: List of portfolio values
            method: Calculation method
            
        Returns:
            List of VaRResult objects
        """
        return [
            self.calculate(returns, value, method)
            for returns, value in zip(returns_list, portfolio_values)
        ]
