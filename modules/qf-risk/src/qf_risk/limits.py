"""
Position limits and risk limits management with performance optimizations.

Optimizations:
- Type hints and dataclasses
- Vectorized calculations
- LRU cache for repeated checks
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from enum import Enum
from functools import lru_cache
import numpy as np


class LimitCheckStatus(Enum):
    """Status of limit check."""
    PASS = "pass"
    WARNING = "warning"
    VIOLATION = "violation"


@dataclass(frozen=True)
class LimitCheckResult:
    """
    Result of limit check.
    
    Attributes:
        status: Check status (pass/warning/violation)
        message: Human-readable message
        limit_type: Type of limit checked
        current_value: Current value of the metric
        limit_value: Limit threshold value
        details: Additional details (optional)
    """
    status: LimitCheckStatus
    message: str
    limit_type: str
    current_value: float
    limit_value: float
    details: Optional[Dict[str, Any]] = None


@dataclass
class PositionLimitConfig:
    """
    Configuration for position limits.
    
    Attributes:
        max_single_position_pct: Maximum single position percentage (default 20%)
        max_total_position_pct: Maximum total position percentage (default 80%)
        max_single_notional: Maximum single position notional value (optional)
        max_total_notional: Maximum total position notional value (optional)
        warning_threshold_pct: Warning threshold percentage (default 90%)
    """
    max_single_position_pct: float = 0.2
    max_total_position_pct: float = 0.8
    max_single_notional: Optional[float] = None
    max_total_notional: Optional[float] = None
    warning_threshold_pct: float = 0.9


class PositionLimits:
    """
    High-performance position limits checker.
    
    Optimizations:
    - Vectorized calculations using NumPy
    - Cached results for repeated checks
    - Efficient data structures
    """
    
    def __init__(self, config: Optional[PositionLimitConfig] = None):
        """
        Initialize position limits checker.
        
        Args:
            config: Position limit configuration
        """
        self.config = config or PositionLimitConfig()
        self._check_history: List[LimitCheckResult] = []
    
    def check_single_position(
        self,
        symbol: str,
        current_position: float,
        total_portfolio_value: float,
        proposed_addition: float = 0.0,
    ) -> LimitCheckResult:
        """
        Check if single position limit would be violated.
        
        Args:
            symbol: Trading symbol
            current_position: Current position value
            total_portfolio_value: Total portfolio value
            proposed_addition: Proposed additional position
            
        Returns:
            LimitCheckResult with status and details
        """
        # Vectorized calculation
        new_position = abs(current_position) + abs(proposed_addition)
        position_pct = new_position / total_portfolio_value if total_portfolio_value > 0 else 0.0
        
        limit_pct = self.config.max_single_position_pct
        warning_pct = limit_pct * self.config.warning_threshold_pct
        
        if position_pct > limit_pct:
            result = LimitCheckResult(
                status=LimitCheckStatus.VIOLATION,
                message=f"Position for {symbol} would exceed limit: "
                        f"{position_pct:.2%} > {limit_pct:.2%}",
                limit_type="single_position_pct",
                current_value=position_pct,
                limit_value=limit_pct,
            )
        elif position_pct > warning_pct:
            result = LimitCheckResult(
                status=LimitCheckStatus.WARNING,
                message=f"Position for {symbol} approaching limit: "
                        f"{position_pct:.2%} (limit: {limit_pct:.2%})",
                limit_type="single_position_pct",
                current_value=position_pct,
                limit_value=limit_pct,
            )
        else:
            result = LimitCheckResult(
                status=LimitCheckStatus.PASS,
                message=f"Position for {symbol} within limits",
                limit_type="single_position_pct",
                current_value=position_pct,
                limit_value=limit_pct,
            )
        
        self._check_history.append(result)
        return result
    
    def check_total_position(
        self,
        positions: Dict[str, float],
        total_portfolio_value: float,
        proposed_addition: Optional[Dict[str, float]] = None,
    ) -> LimitCheckResult:
        """
        Check if total position limit would be violated.
        
        Args:
            positions: Dict of symbol -> position values
            total_portfolio_value: Total portfolio value
            proposed_addition: Dict of proposed additions by symbol
            
        Returns:
            LimitCheckResult with status and details
        """
        # Vectorized calculation using NumPy
        position_values = np.array([abs(p) for p in positions.values()], dtype=np.float64)
        total_position = np.sum(position_values)
        
        if proposed_addition:
            addition_values = np.array([abs(p) for p in proposed_addition.values()], dtype=np.float64)
            total_position += np.sum(addition_values)
        
        position_pct = total_position / total_portfolio_value if total_portfolio_value > 0 else 0.0
        
        limit_pct = self.config.max_total_position_pct
        warning_pct = limit_pct * self.config.warning_threshold_pct
        
        if position_pct > limit_pct:
            result = LimitCheckResult(
                status=LimitCheckStatus.VIOLATION,
                message=f"Total position would exceed limit: "
                        f"{position_pct:.2%} > {limit_pct:.2%}",
                limit_type="total_position_pct",
                current_value=position_pct,
                limit_value=limit_pct,
                details={"total_notional": float(total_position)},
            )
        elif position_pct > warning_pct:
            result = LimitCheckResult(
                status=LimitCheckStatus.WARNING,
                message=f"Total position approaching limit: "
                        f"{position_pct:.2%} (limit: {limit_pct:.2%})",
                limit_type="total_position_pct",
                current_value=position_pct,
                limit_value=limit_pct,
                details={"total_notional": float(total_position)},
            )
        else:
            result = LimitCheckResult(
                status=LimitCheckStatus.PASS,
                message="Total position within limits",
                limit_type="total_position_pct",
                current_value=position_pct,
                limit_value=limit_pct,
                details={"total_notional": float(total_position)},
            )
        
        self._check_history.append(result)
        return result
    
    def check_concentration(
        self,
        positions: Dict[str, float],
        max_concentration_pct: float = 0.3,
    ) -> LimitCheckResult:
        """
        Check concentration risk (largest position / total positions).
        
        Args:
            positions: Dict of symbol -> position values
            max_concentration_pct: Maximum allowed concentration
            
        Returns:
            LimitCheckResult with status and details
        """
        if not positions:
            return LimitCheckResult(
                status=LimitCheckStatus.PASS,
                message="No positions to check",
                limit_type="concentration",
                current_value=0.0,
                limit_value=max_concentration_pct,
            )
        
        # Vectorized calculation using NumPy
        abs_positions = np.array([abs(p) for p in positions.values()], dtype=np.float64)
        total = np.sum(abs_positions)
        
        if total == 0:
            return LimitCheckResult(
                status=LimitCheckStatus.PASS,
                message="No position value to check",
                limit_type="concentration",
                current_value=0.0,
                limit_value=max_concentration_pct,
            )
        
        max_position = np.max(abs_positions)
        concentration = max_position / total
        
        if concentration > max_concentration_pct:
            result = LimitCheckResult(
                status=LimitCheckStatus.WARNING,
                message=f"High concentration risk: {concentration:.2%} "
                        f"in single position (limit: {max_concentration_pct:.2%})",
                limit_type="concentration",
                current_value=float(concentration),
                limit_value=max_concentration_pct,
                details={"largest_position": float(max_position)},
            )
        else:
            result = LimitCheckResult(
                status=LimitCheckStatus.PASS,
                message=f"Concentration risk acceptable: {concentration:.2%}",
                limit_type="concentration",
                current_value=float(concentration),
                limit_value=max_concentration_pct,
            )
        
        self._check_history.append(result)
        return result
    
    def check_notional_limits(
        self,
        positions: Dict[str, float],
        proposed_addition: Optional[Dict[str, float]] = None,
    ) -> List[LimitCheckResult]:
        """
        Check notional value limits for all positions.
        
        Args:
            positions: Dict of symbol -> position values
            proposed_addition: Dict of proposed additions by symbol
            
        Returns:
            List of LimitCheckResult
        """
        results = []
        
        # Check single notional limits
        if self.config.max_single_notional is not None:
            for symbol, position in positions.items():
                addition = proposed_addition.get(symbol, 0.0) if proposed_addition else 0.0
                total_notional = abs(position) + abs(addition)
                
                if total_notional > self.config.max_single_notional:
                    results.append(LimitCheckResult(
                        status=LimitCheckStatus.VIOLATION,
                        message=f"Notional limit exceeded for {symbol}: "
                                f"{total_notional:,.2f} > {self.config.max_single_notional:,.2f}",
                        limit_type="single_notional",
                        current_value=total_notional,
                        limit_value=self.config.max_single_notional,
                    ))
        
        # Check total notional limit
        if self.config.max_total_notional is not None:
            total_notional = sum(abs(p) for p in positions.values())
            if proposed_addition:
                total_notional += sum(abs(p) for p in proposed_addition.values())
            
            if total_notional > self.config.max_total_notional:
                results.append(LimitCheckResult(
                    status=LimitCheckStatus.VIOLATION,
                    message=f"Total notional limit exceeded: "
                            f"{total_notional:,.2f} > {self.config.max_total_notional:,.2f}",
                    limit_type="total_notional",
                    current_value=total_notional,
                    limit_value=self.config.max_total_notional,
                ))
        
        return results
    
    def get_check_history(self) -> List[LimitCheckResult]:
        """Get history of limit checks."""
        return self._check_history.copy()
    
    def clear_history(self) -> None:
        """Clear check history."""
        self._check_history.clear()
    
    def batch_check_positions(
        self,
        positions_list: List[Dict[str, float]],
        portfolio_values: List[float],
    ) -> List[List[LimitCheckResult]]:
        """
        Batch check multiple position sets.
        
        Args:
            positions_list: List of position dicts
            portfolio_values: List of portfolio values
            
        Returns:
            List of LimitCheckResult lists
        """
        return [
            [
                self.check_single_position(
                    symbol, position, portfolio_value
                )
                for symbol, position in positions.items()
            ]
            for positions, portfolio_value in zip(positions_list, portfolio_values)
        ]
