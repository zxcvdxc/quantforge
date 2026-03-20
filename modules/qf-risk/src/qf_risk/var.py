"""Value at Risk (VaR) calculation."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Union
import numpy as np
from scipy import stats


class VaRMethod(Enum):
    """VaR calculation methods."""
    HISTORICAL = "historical"
    PARAMETRIC = "parametric"
    MONTE_CARLO = "monte_carlo"


@dataclass
class VaRResult:
    """VaR calculation result."""
    var_value: float  # VaR value in currency
    var_pct: float    # VaR as percentage
    confidence_level: float
    method: VaRMethod
    holding_period_days: int
    expected_shortfall: Optional[float] = None  # CVaR/Expected Shortfall


class VaRCalculator:
    """Calculator for Value at Risk (VaR)."""
    
    def __init__(self, confidence_level: float = 0.95, holding_period_days: int = 1):
        """Initialize VaR calculator.
        
        Args:
            confidence_level: Confidence level (e.g., 0.95 for 95%)
            holding_period_days: Holding period in days
        """
        self.confidence_level = confidence_level
        self.holding_period_days = holding_period_days
    
    def calculate(
        self,
        returns: List[float],
        portfolio_value: float,
        method: VaRMethod = VaRMethod.HISTORICAL,
        num_simulations: int = 10000
    ) -> VaRResult:
        """Calculate VaR.
        
        Args:
            returns: Historical returns (decimal, e.g., 0.01 for 1%)
            portfolio_value: Current portfolio value
            method: Calculation method
            num_simulations: Number of simulations for Monte Carlo
            
        Returns:
            VaRResult with calculated VaR
        """
        returns_array = np.array(returns)
        
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
        """Calculate historical VaR."""
        # Scale returns to holding period
        scaled_returns = returns * np.sqrt(self.holding_period_days)
        
        # Calculate percentile
        var_pct = np.percentile(scaled_returns, (1 - self.confidence_level) * 100)
        var_value = abs(var_pct) * portfolio_value
        
        # Calculate Expected Shortfall (CVaR)
        tail_returns = scaled_returns[scaled_returns <= var_pct]
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
        """Calculate parametric (variance-covariance) VaR."""
        mean = np.mean(returns)
        std = np.std(returns, ddof=1)
        
        # Scale to holding period
        scaled_mean = mean * self.holding_period_days
        scaled_std = std * np.sqrt(self.holding_period_days)
        
        # Calculate VaR using normal distribution
        z_score = stats.norm.ppf(1 - self.confidence_level)
        var_pct = -(scaled_mean + z_score * scaled_std)
        var_value = var_pct * portfolio_value
        
        # Calculate Expected Shortfall for normal distribution
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
        """Calculate Monte Carlo VaR."""
        mean = np.mean(returns)
        std = np.std(returns, ddof=1)
        
        # Generate random returns
        random_returns = np.random.normal(
            mean * self.holding_period_days,
            std * np.sqrt(self.holding_period_days),
            num_simulations
        )
        
        # Calculate percentile
        var_pct = np.percentile(random_returns, (1 - self.confidence_level) * 100)
        var_value = abs(var_pct) * portfolio_value
        
        # Calculate Expected Shortfall
        tail_returns = random_returns[random_returns <= var_pct]
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
    
    def calculate_portfolio_var(
        self,
        weights: List[float],
        returns_matrix: List[List[float]],
        portfolio_value: float,
        method: VaRMethod = VaRMethod.PARAMETRIC
    ) -> VaRResult:
        """Calculate portfolio VaR using correlation matrix.
        
        Args:
            weights: Asset weights (sum to 1)
            returns_matrix: Matrix of asset returns (assets x time)
            portfolio_value: Portfolio value
            method: Calculation method
            
        Returns:
            VaRResult with portfolio VaR
        """
        weights_array = np.array(weights)
        returns_array = np.array(returns_matrix)
        
        # Calculate portfolio returns
        portfolio_returns = np.dot(weights_array, returns_array)
        
        return self.calculate(portfolio_returns.tolist(), portfolio_value, method)
    
    def component_var(
        self,
        weights: List[float],
        returns_matrix: List[List[float]],
        portfolio_value: float
    ) -> List[dict]:
        """Calculate component VaR for each asset.
        
        Args:
            weights: Asset weights
            returns_matrix: Matrix of asset returns
            portfolio_value: Portfolio value
            
        Returns:
            List of component VaR data for each asset
        """
        weights_array = np.array(weights)
        returns_array = np.array(returns_matrix)
        
        # Calculate covariance matrix
        cov_matrix = np.cov(returns_array)
        
        # Calculate portfolio variance and standard deviation
        port_variance = np.dot(weights_array.T, np.dot(cov_matrix, weights_array))
        port_std = np.sqrt(port_variance)
        
        # Calculate portfolio VaR
        z_score = stats.norm.ppf(1 - self.confidence_level)
        port_var_pct = port_std * z_score * np.sqrt(self.holding_period_days)
        port_var = port_var_pct * portfolio_value
        
        # Calculate marginal VaR for each asset
        marginal_var = np.dot(cov_matrix, weights_array) * z_score / port_std
        marginal_var *= np.sqrt(self.holding_period_days)
        
        # Calculate component VaR
        component_var_list = []
        for i, weight in enumerate(weights):
            component_var = marginal_var[i] * weight * portfolio_value
            component_var_list.append({
                "asset_index": i,
                "weight": weight,
                "marginal_var": marginal_var[i],
                "component_var": component_var,
                "component_var_pct": component_var / port_var if port_var != 0 else 0
            })
        
        return component_var_list
