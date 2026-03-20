"""Position limits and risk limits management."""

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum


class LimitCheckStatus(Enum):
    """Status of limit check."""
    PASS = "pass"
    WARNING = "warning"
    VIOLATION = "violation"


@dataclass
class LimitCheckResult:
    """Result of limit check."""
    status: LimitCheckStatus
    message: str
    limit_type: str
    current_value: float
    limit_value: float
    details: Optional[Dict] = None


@dataclass
class PositionLimitConfig:
    """Configuration for position limits."""
    max_single_position_pct: float = 0.2  # 单一品种最大仓位比例
    max_total_position_pct: float = 0.8   # 总仓位最大比例
    max_single_notional: Optional[float] = None  # 单一品种最大名义价值
    max_total_notional: Optional[float] = None   # 总仓位最大名义价值
    warning_threshold_pct: float = 0.9    # 预警阈值比例


class PositionLimits:
    """Position limits checker."""
    
    def __init__(self, config: Optional[PositionLimitConfig] = None):
        self.config = config or PositionLimitConfig()
        self._check_history: List[LimitCheckResult] = []
    
    def check_single_position(
        self,
        symbol: str,
        current_position: float,
        total_portfolio_value: float,
        proposed_addition: float = 0.0
    ) -> LimitCheckResult:
        """Check if single position limit would be violated.
        
        Args:
            symbol: Trading symbol
            current_position: Current position value
            total_portfolio_value: Total portfolio value
            proposed_addition: Proposed additional position
            
        Returns:
            LimitCheckResult with status and details
        """
        new_position = abs(current_position) + abs(proposed_addition)
        position_pct = new_position / total_portfolio_value if total_portfolio_value > 0 else 0
        
        limit_pct = self.config.max_single_position_pct
        warning_pct = limit_pct * self.config.warning_threshold_pct
        
        if position_pct > limit_pct:
            result = LimitCheckResult(
                status=LimitCheckStatus.VIOLATION,
                message=f"Position for {symbol} would exceed limit: "
                        f"{position_pct:.2%} > {limit_pct:.2%}",
                limit_type="single_position_pct",
                current_value=position_pct,
                limit_value=limit_pct
            )
        elif position_pct > warning_pct:
            result = LimitCheckResult(
                status=LimitCheckStatus.WARNING,
                message=f"Position for {symbol} approaching limit: "
                        f"{position_pct:.2%} (limit: {limit_pct:.2%})",
                limit_type="single_position_pct",
                current_value=position_pct,
                limit_value=limit_pct
            )
        else:
            result = LimitCheckResult(
                status=LimitCheckStatus.PASS,
                message=f"Position for {symbol} within limits",
                limit_type="single_position_pct",
                current_value=position_pct,
                limit_value=limit_pct
            )
        
        self._check_history.append(result)
        return result
    
    def check_total_position(
        self,
        positions: Dict[str, float],
        total_portfolio_value: float,
        proposed_addition: Optional[Dict[str, float]] = None
    ) -> LimitCheckResult:
        """Check if total position limit would be violated.
        
        Args:
            positions: Dict of symbol -> position values
            total_portfolio_value: Total portfolio value
            proposed_addition: Dict of proposed additions by symbol
            
        Returns:
            LimitCheckResult with status and details
        """
        total_position = sum(abs(p) for p in positions.values())
        
        if proposed_addition:
            total_position += sum(abs(p) for p in proposed_addition.values())
        
        position_pct = total_position / total_portfolio_value if total_portfolio_value > 0 else 0
        
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
                details={"total_notional": total_position}
            )
        elif position_pct > warning_pct:
            result = LimitCheckResult(
                status=LimitCheckStatus.WARNING,
                message=f"Total position approaching limit: "
                        f"{position_pct:.2%} (limit: {limit_pct:.2%})",
                limit_type="total_position_pct",
                current_value=position_pct,
                limit_value=limit_pct,
                details={"total_notional": total_position}
            )
        else:
            result = LimitCheckResult(
                status=LimitCheckStatus.PASS,
                message="Total position within limits",
                limit_type="total_position_pct",
                current_value=position_pct,
                limit_value=limit_pct,
                details={"total_notional": total_position}
            )
        
        self._check_history.append(result)
        return result
    
    def check_concentration(
        self,
        positions: Dict[str, float],
        max_concentration_pct: float = 0.3
    ) -> LimitCheckResult:
        """Check concentration risk (largest position / total positions).
        
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
                limit_value=max_concentration_pct
            )
        
        abs_positions = {s: abs(p) for s, p in positions.items()}
        total = sum(abs_positions.values())
        
        if total == 0:
            return LimitCheckResult(
                status=LimitCheckStatus.PASS,
                message="No position value to check",
                limit_type="concentration",
                current_value=0.0,
                limit_value=max_concentration_pct
            )
        
        max_position = max(abs_positions.values())
        concentration = max_position / total
        
        if concentration > max_concentration_pct:
            result = LimitCheckResult(
                status=LimitCheckStatus.WARNING,
                message=f"High concentration risk: {concentration:.2%} "
                        f"in single position (limit: {max_concentration_pct:.2%})",
                limit_type="concentration",
                current_value=concentration,
                limit_value=max_concentration_pct,
                details={"largest_position": max_position}
            )
        else:
            result = LimitCheckResult(
                status=LimitCheckStatus.PASS,
                message=f"Concentration risk acceptable: {concentration:.2%}",
                limit_type="concentration",
                current_value=concentration,
                limit_value=max_concentration_pct
            )
        
        self._check_history.append(result)
        return result
    
    def get_check_history(self) -> List[LimitCheckResult]:
        """Get history of limit checks."""
        return self._check_history.copy()
