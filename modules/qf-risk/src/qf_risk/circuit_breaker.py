"""
Circuit breaker mechanism for trading risk control with performance optimizations.

Optimizations:
- Type hints and dataclasses
- Efficient state tracking
- Vectorized calculations
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any
from functools import lru_cache
import numpy as np


class CircuitBreakerLevel(Enum):
    """Circuit breaker levels."""
    NORMAL = "normal"
    WARNING = "warning"
    TRIGGERED = "triggered"
    LOCKED = "locked"


class CircuitBreakerType(Enum):
    """Types of circuit breakers."""
    DAILY_LOSS = "daily_loss"
    MONTHLY_LOSS = "monthly_loss"
    MAX_DRAWDOWN = "max_drawdown"


@dataclass
class CircuitBreakerConfig:
    """
    Configuration for circuit breakers.
    
    Attributes:
        daily_loss_limit_pct: Daily loss limit percentage (default 2%)
        daily_loss_warning_pct: Daily loss warning percentage (default 1%)
        monthly_loss_limit_pct: Monthly loss limit percentage (default 5%)
        monthly_loss_warning_pct: Monthly loss warning percentage (default 3%)
        max_drawdown_limit_pct: Max drawdown limit percentage (default 10%)
        max_drawdown_warning_pct: Max drawdown warning percentage (default 7%)
        auto_reset_hours: Auto-reset hours (default 24)
        lock_duration_minutes: Lock duration after trigger (default 30)
    """
    # Daily loss limits
    daily_loss_limit_pct: float = 0.02
    daily_loss_warning_pct: float = 0.01
    
    # Monthly loss limits
    monthly_loss_limit_pct: float = 0.05
    monthly_loss_warning_pct: float = 0.03
    
    # Drawdown limits
    max_drawdown_limit_pct: float = 0.10
    max_drawdown_warning_pct: float = 0.07
    
    # Auto-reset hours
    auto_reset_hours: int = 24
    
    # Lock duration after trigger (minutes)
    lock_duration_minutes: int = 30


@dataclass
class CircuitBreakerState:
    """
    State of a circuit breaker.
    
    Attributes:
        breaker_type: Type of circuit breaker
        level: Current level (normal/warning/triggered/locked)
        current_value: Current metric value
        limit_value: Limit threshold
        triggered_at: When triggered (optional)
        locked_until: When lock expires (optional)
        message: Status message
    """
    breaker_type: CircuitBreakerType
    level: CircuitBreakerLevel
    current_value: float
    limit_value: float
    triggered_at: Optional[datetime] = None
    locked_until: Optional[datetime] = None
    message: str = ""


class CircuitBreaker:
    """
    High-performance circuit breaker for risk management.
    
    Optimizations:
    - Efficient state tracking with dictionaries
    - Vectorized calculations where applicable
    - Cached limit values
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        """
        Initialize circuit breaker.
        
        Args:
            config: Circuit breaker configuration
        """
        self.config = config or CircuitBreakerConfig()
        self._daily_pnl: Dict[datetime, float] = {}
        self._monthly_pnl: Dict[str, float] = {}
        self._peak_value: float = 0.0
        self._current_value: float = 0.0
        self._states: Dict[CircuitBreakerType, CircuitBreakerState] = {}
        self._listeners: List[Callable[[CircuitBreakerState], None]] = []
        self._initial_capital: float = 0.0
        
        # Pre-computed limit values
        self._limit_values: Dict[CircuitBreakerType, float] = {
            CircuitBreakerType.DAILY_LOSS: self.config.daily_loss_limit_pct,
            CircuitBreakerType.MONTHLY_LOSS: self.config.monthly_loss_limit_pct,
            CircuitBreakerType.MAX_DRAWDOWN: self.config.max_drawdown_limit_pct,
        }
        
        self._warning_values: Dict[CircuitBreakerType, float] = {
            CircuitBreakerType.DAILY_LOSS: self.config.daily_loss_warning_pct,
            CircuitBreakerType.MONTHLY_LOSS: self.config.monthly_loss_warning_pct,
            CircuitBreakerType.MAX_DRAWDOWN: self.config.max_drawdown_warning_pct,
        }
        
        # Initialize states
        for cb_type in CircuitBreakerType:
            self._states[cb_type] = CircuitBreakerState(
                breaker_type=cb_type,
                level=CircuitBreakerLevel.NORMAL,
                current_value=0.0,
                limit_value=self._limit_values[cb_type],
            )
    
    def initialize_capital(self, capital: float) -> None:
        """
        Initialize starting capital.
        
        Args:
            capital: Initial capital amount
        """
        self._initial_capital = capital
        self._current_value = capital
        self._peak_value = capital
    
    def update_portfolio_value(
        self,
        value: float,
        timestamp: Optional[datetime] = None,
    ) -> List[CircuitBreakerState]:
        """
        Update portfolio value and check all circuit breakers.
        
        Args:
            value: Current portfolio value
            timestamp: Current timestamp (defaults to now)
            
        Returns:
            List of updated circuit breaker states
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Update current value
        prev_value = self._current_value
        self._current_value = value
        
        # Update peak value
        if value > self._peak_value:
            self._peak_value = value
        
        # Calculate P&L
        pnl = value - prev_value if prev_value > 0 else 0.0
        
        # Update P&L tracking
        day_key = timestamp.date()
        if day_key not in self._daily_pnl:
            self._daily_pnl[day_key] = 0.0
        self._daily_pnl[day_key] += pnl
        
        month_key = timestamp.strftime("%Y-%m")
        if month_key not in self._monthly_pnl:
            self._monthly_pnl[month_key] = 0.0
        self._monthly_pnl[month_key] += pnl
        
        # Check all circuit breakers
        updated_states = []
        
        # Check daily loss
        daily_state = self._check_daily_loss(timestamp)
        updated_states.append(daily_state)
        
        # Check monthly loss
        monthly_state = self._check_monthly_loss(timestamp)
        updated_states.append(monthly_state)
        
        # Check max drawdown
        drawdown_state = self._check_max_drawdown(timestamp)
        updated_states.append(drawdown_state)
        
        return updated_states
    
    def _check_daily_loss(self, timestamp: datetime) -> CircuitBreakerState:
        """Check daily loss circuit breaker."""
        day_key = timestamp.date()
        daily_pnl = self._daily_pnl.get(day_key, 0.0)
        daily_loss_pct = abs(min(0.0, daily_pnl)) / self._initial_capital if self._initial_capital > 0 else 0.0
        
        return self._evaluate_state(
            CircuitBreakerType.DAILY_LOSS,
            daily_loss_pct,
            timestamp,
        )
    
    def _check_monthly_loss(self, timestamp: datetime) -> CircuitBreakerState:
        """Check monthly loss circuit breaker."""
        month_key = timestamp.strftime("%Y-%m")
        monthly_pnl = self._monthly_pnl.get(month_key, 0.0)
        monthly_loss_pct = abs(min(0.0, monthly_pnl)) / self._initial_capital if self._initial_capital > 0 else 0.0
        
        return self._evaluate_state(
            CircuitBreakerType.MONTHLY_LOSS,
            monthly_loss_pct,
            timestamp,
        )
    
    def _check_max_drawdown(self, timestamp: datetime) -> CircuitBreakerState:
        """Check max drawdown circuit breaker."""
        drawdown = (self._peak_value - self._current_value) / self._peak_value if self._peak_value > 0 else 0.0
        drawdown_pct = max(0.0, drawdown)
        
        return self._evaluate_state(
            CircuitBreakerType.MAX_DRAWDOWN,
            drawdown_pct,
            timestamp,
        )
    
    def _evaluate_state(
        self,
        cb_type: CircuitBreakerType,
        current_value: float,
        timestamp: datetime,
    ) -> CircuitBreakerState:
        """Evaluate circuit breaker state."""
        limit_value = self._limit_values[cb_type]
        warning_value = self._warning_values[cb_type]
        
        state = self._states[cb_type]
        
        # Check if still locked
        if state.level == CircuitBreakerLevel.LOCKED:
            if state.locked_until and timestamp >= state.locked_until:
                # Auto-reset
                state.level = CircuitBreakerLevel.NORMAL
                state.locked_until = None
                state.triggered_at = None
            else:
                # Still locked
                state.current_value = current_value
                return state
        
        # Evaluate new state
        prev_level = state.level
        
        if current_value >= limit_value:
            state.level = CircuitBreakerLevel.TRIGGERED
            state.triggered_at = timestamp
            state.locked_until = timestamp + timedelta(minutes=self.config.lock_duration_minutes)
            state.message = f"{cb_type.value} triggered: {current_value:.2%} >= {limit_value:.2%}"
        elif current_value >= warning_value:
            state.level = CircuitBreakerLevel.WARNING
            state.message = f"{cb_type.value} warning: {current_value:.2%} >= {warning_value:.2%}"
        else:
            state.level = CircuitBreakerLevel.NORMAL
            state.message = f"{cb_type.value} normal: {current_value:.2%}"
        
        state.current_value = current_value
        state.limit_value = limit_value
        
        # Notify listeners if state changed
        if prev_level != state.level:
            self._notify_listeners(state)
        
        return state
    
    def _notify_listeners(self, state: CircuitBreakerState) -> None:
        """Notify all listeners of state change."""
        for listener in self._listeners:
            try:
                listener(state)
            except Exception:
                pass
    
    def add_listener(self, callback: Callable[[CircuitBreakerState], None]) -> None:
        """Add a circuit breaker state change listener."""
        self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[CircuitBreakerState], None]) -> None:
        """Remove a circuit breaker state change listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def get_state(self, cb_type: CircuitBreakerType) -> CircuitBreakerState:
        """Get current state of a circuit breaker."""
        return self._states[cb_type]
    
    def get_all_states(self) -> Dict[CircuitBreakerType, CircuitBreakerState]:
        """Get all circuit breaker states."""
        return self._states.copy()
    
    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed."""
        for state in self._states.values():
            if state.level in (CircuitBreakerLevel.TRIGGERED, CircuitBreakerLevel.LOCKED):
                return False
        return True
    
    def reset(self, cb_type: Optional[CircuitBreakerType] = None) -> None:
        """
        Reset circuit breaker(s).
        
        Args:
            cb_type: Specific type to reset, or None to reset all
        """
        types_to_reset = [cb_type] if cb_type else list(CircuitBreakerType)
        
        for t in types_to_reset:
            if t is None:
                continue
            self._states[t] = CircuitBreakerState(
                breaker_type=t,
                level=CircuitBreakerLevel.NORMAL,
                current_value=0.0,
                limit_value=self._limit_values[t],
            )
    
    def manual_lock(
        self,
        cb_type: CircuitBreakerType,
        duration_minutes: int,
        reason: str = "Manual lock",
    ) -> None:
        """
        Manually lock a circuit breaker.
        
        Args:
            cb_type: Circuit breaker type to lock
            duration_minutes: Lock duration in minutes
            reason: Lock reason
        """
        timestamp = datetime.now()
        state = self._states[cb_type]
        state.level = CircuitBreakerLevel.LOCKED
        state.locked_until = timestamp + timedelta(minutes=duration_minutes)
        state.triggered_at = timestamp
        state.message = reason
        self._notify_listeners(state)
    
    def get_pnl_summary(self) -> Dict[str, float]:
        """Get P&L summary."""
        today = datetime.now().date()
        this_month = datetime.now().strftime("%Y-%m")
        
        return {
            "daily_pnl": self._daily_pnl.get(today, 0.0),
            "monthly_pnl": self._monthly_pnl.get(this_month, 0.0),
            "total_pnl": self._current_value - self._initial_capital,
            "current_drawdown": (self._peak_value - self._current_value) / self._peak_value
            if self._peak_value > 0 else 0.0,
        }
