"""Main Risk Manager class for unified risk management."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
import logging

from .limits import PositionLimits, PositionLimitConfig, LimitCheckResult, LimitCheckStatus
from .circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerState, CircuitBreakerType
)
from .stop_loss import StopLossManager, StopLossConfig, StopLossResult, OrderSide
from .var import VaRCalculator, VaRResult, VaRMethod
from .anomaly import AnomalyDetector, AnomalyConfig, AnomalyResult


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RiskManagerConfig:
    """Configuration for RiskManager."""
    position_limits: Optional[PositionLimitConfig] = None
    circuit_breaker: Optional[CircuitBreakerConfig] = None
    stop_loss: Optional[StopLossConfig] = None
    anomaly: Optional[AnomalyConfig] = None
    var_confidence_level: float = 0.95
    var_holding_period_days: int = 1


@dataclass
class RiskReport:
    """Comprehensive risk report."""
    timestamp: datetime
    trading_allowed: bool
    circuit_breaker_states: Dict[CircuitBreakerType, CircuitBreakerState]
    position_limit_status: List[LimitCheckResult]
    var_result: Optional[VaRResult]
    active_stop_losses: int
    anomalies: List[AnomalyResult]
    warnings: List[str]
    errors: List[str]


class RiskManager:
    """Unified risk manager for trading systems."""
    
    def __init__(self, config: Optional[RiskManagerConfig] = None):
        """Initialize risk manager.
        
        Args:
            config: Risk manager configuration
        """
        self.config = config or RiskManagerConfig()
        
        # Initialize sub-modules
        self.position_limits = PositionLimits(self.config.position_limits)
        self.circuit_breaker = CircuitBreaker(self.config.circuit_breaker)
        self.stop_loss_manager = StopLossManager(self.config.stop_loss)
        self.var_calculator = VaRCalculator(
            confidence_level=self.config.var_confidence_level,
            holding_period_days=self.config.var_holding_period_days
        )
        self.anomaly_detector = AnomalyDetector(self.config.anomaly)
        
        # Portfolio state
        self._portfolio_value: float = 0.0
        self._initial_capital: float = 0.0
        self._positions: Dict[str, float] = {}
        self._returns_history: List[float] = []
        
        # Callbacks
        self._risk_event_callbacks: List[Callable[[str, Any], None]] = []
        
        logger.info("RiskManager initialized")
    
    def initialize_capital(self, capital: float) -> None:
        """Initialize portfolio capital.
        
        Args:
            capital: Initial capital amount
        """
        self._initial_capital = capital
        self._portfolio_value = capital
        self.circuit_breaker.initialize_capital(capital)
        logger.info(f"RiskManager initialized with capital: {capital:,.2f}")
    
    def can_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float
    ) -> tuple[bool, List[str]]:
        """Check if a trade is allowed.
        
        Args:
            symbol: Trading symbol
            side: Trade side ('buy' or 'sell')
            quantity: Trade quantity
            price: Trade price
            
        Returns:
            Tuple of (allowed, reasons)
        """
        reasons = []
        
        # Check circuit breakers
        if not self.circuit_breaker.is_trading_allowed():
            states = self.circuit_breaker.get_all_states()
            for cb_type, state in states.items():
                if state.level.value in ('triggered', 'locked'):
                    reasons.append(f"Circuit breaker active: {cb_type.value}")
            return False, reasons
        
        # Calculate proposed position change
        notional_value = quantity * price
        proposed_addition = {symbol: notional_value} if side.lower() == 'buy' else {}
        
        # Check single position limit
        current_position = self._positions.get(symbol, 0.0)
        single_result = self.position_limits.check_single_position(
            symbol, current_position, self._portfolio_value, notional_value
        )
        if single_result.status == LimitCheckStatus.VIOLATION:
            reasons.append(f"Single position limit: {single_result.message}")
        
        # Check total position limit
        total_result = self.position_limits.check_total_position(
            self._positions, self._portfolio_value, proposed_addition
        )
        if total_result.status == LimitCheckStatus.VIOLATION:
            reasons.append(f"Total position limit: {total_result.message}")
        
        # Check concentration
        test_positions = self._positions.copy()
        if side.lower() == 'buy':
            test_positions[symbol] = test_positions.get(symbol, 0.0) + notional_value
        else:
            test_positions[symbol] = test_positions.get(symbol, 0.0) - notional_value
        
        concentration_result = self.position_limits.check_concentration(test_positions)
        if concentration_result.status == LimitCheckStatus.WARNING:
            reasons.append(f"Concentration warning: {concentration_result.message}")
        
        allowed = len(reasons) == 0
        return allowed, reasons
    
    def update_portfolio_value(self, value: float, timestamp: Optional[datetime] = None) -> List[CircuitBreakerState]:
        """Update portfolio value and check circuit breakers.
        
        Args:
            value: Current portfolio value
            timestamp: Optional timestamp
            
        Returns:
            Updated circuit breaker states
        """
        # Calculate return
        if self._portfolio_value > 0:
            daily_return = (value - self._portfolio_value) / self._portfolio_value
            self._returns_history.append(daily_return)
            # Keep only last 252 days
            if len(self._returns_history) > 252:
                self._returns_history = self._returns_history[-252:]
        
        self._portfolio_value = value
        states = self.circuit_breaker.update_portfolio_value(value, timestamp)
        
        # Notify if any breaker triggered
        for state in states:
            if state.level.value in ('triggered', 'locked', 'warning'):
                self._notify_event('circuit_breaker', state)
        
        return states
    
    def register_position(
        self,
        symbol: str,
        side: OrderSide,
        entry_price: float,
        quantity: float
    ) -> None:
        """Register a position for stop-loss monitoring.
        
        Args:
            symbol: Trading symbol
            side: Position side
            entry_price: Entry price
            quantity: Quantity
        """
        self.stop_loss_manager.register_position(symbol, side, entry_price, quantity)
        notional = entry_price * quantity
        self._positions[symbol] = self._positions.get(symbol, 0.0) + notional
        logger.info(f"Position registered: {symbol} {side.value} {quantity} @ {entry_price}")
    
    def update_price(self, symbol: str, price: float) -> Optional[StopLossResult]:
        """Update price and check stop-loss/take-profit.
        
        Args:
            symbol: Trading symbol
            price: Current price
            
        Returns:
            StopLossResult if triggered, None otherwise
        """
        result = self.stop_loss_manager.update_price(symbol, price)
        
        if result and result.triggered:
            # Update internal position tracking
            if result.action in ('stop_loss', 'take_profit', 'trailing_stop'):
                self._positions.pop(symbol, None)
            self._notify_event('stop_loss_triggered', result)
        
        return result
    
    def close_position(self, symbol: str) -> None:
        """Close and remove a position.
        
        Args:
            symbol: Trading symbol
        """
        self.stop_loss_manager.close_position(symbol)
        self._positions.pop(symbol, None)
    
    def calculate_var(
        self,
        portfolio_value: Optional[float] = None,
        method: VaRMethod = VaRMethod.HISTORICAL
    ) -> Optional[VaRResult]:
        """Calculate portfolio VaR.
        
        Args:
            portfolio_value: Portfolio value (uses current if not provided)
            method: VaR calculation method
            
        Returns:
            VaRResult or None if insufficient data
        """
        value = portfolio_value or self._portfolio_value
        
        if len(self._returns_history) < 30:
            logger.warning(f"Insufficient returns data for VaR: {len(self._returns_history)} days")
            return None
        
        return self.var_calculator.calculate(self._returns_history, value, method)
    
    def check_anomalies(
        self,
        symbol: str,
        current_price: float,
        current_volume: float,
        prev_close: float,
        historical_prices: List[float],
        historical_volumes: List[float],
        recent_returns: List[float]
    ) -> List[AnomalyResult]:
        """Check for market anomalies.
        
        Args:
            symbol: Trading symbol
            current_price: Current price
            current_volume: Current volume
            prev_close: Previous closing price
            historical_prices: Historical prices
            historical_volumes: Historical volumes
            recent_returns: Recent returns
            
        Returns:
            List of detected anomalies
        """
        anomalies = self.anomaly_detector.scan_all(
            symbol, current_price, current_volume, prev_close,
            historical_prices, historical_volumes, recent_returns
        )
        
        for anomaly in anomalies:
            self._notify_event('anomaly_detected', anomaly)
        
        return anomalies
    
    def get_risk_report(self) -> RiskReport:
        """Generate comprehensive risk report.
        
        Returns:
            RiskReport with all risk metrics
        """
        warnings = []
        errors = []
        
        # Circuit breaker status
        cb_states = self.circuit_breaker.get_all_states()
        for cb_type, state in cb_states.items():
            if state.level.value == 'warning':
                warnings.append(f"{cb_type.value}: {state.message}")
            elif state.level.value in ('triggered', 'locked'):
                errors.append(f"{cb_type.value}: {state.message}")
        
        # Position limits
        limit_results = []
        concentration_result = self.position_limits.check_concentration(self._positions)
        limit_results.append(concentration_result)
        if concentration_result.status == LimitCheckStatus.WARNING:
            warnings.append(concentration_result.message)
        
        # VaR
        var_result = self.calculate_var() if len(self._returns_history) >= 30 else None
        
        # Active stop-losses
        active_sl = len(self.stop_loss_manager.get_all_positions())
        
        return RiskReport(
            timestamp=datetime.now(),
            trading_allowed=self.circuit_breaker.is_trading_allowed(),
            circuit_breaker_states=cb_states,
            position_limit_status=limit_results,
            var_result=var_result,
            active_stop_losses=active_sl,
            anomalies=[],  # Would need current market data
            warnings=warnings,
            errors=errors
        )
    
    def add_event_listener(self, callback: Callable[[str, Any], None]) -> None:
        """Add risk event listener.
        
        Args:
            callback: Function to call on risk events
        """
        self._risk_event_callbacks.append(callback)
    
    def remove_event_listener(self, callback: Callable[[str, Any], None]) -> None:
        """Remove risk event listener."""
        if callback in self._risk_event_callbacks:
            self._risk_event_callbacks.remove(callback)
    
    def _notify_event(self, event_type: str, data: Any) -> None:
        """Notify all listeners of risk event."""
        for callback in self._risk_event_callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.error(f"Error in risk event callback: {e}")
    
    def reset_circuit_breaker(self, cb_type: Optional[CircuitBreakerType] = None) -> None:
        """Reset circuit breaker(s).
        
        Args:
            cb_type: Specific type to reset, or None for all
        """
        self.circuit_breaker.reset(cb_type)
        logger.info(f"Circuit breaker reset: {cb_type.value if cb_type else 'all'}")
    
    def get_positions(self) -> Dict[str, float]:
        """Get current positions."""
        return self._positions.copy()
    
    def get_portfolio_value(self) -> float:
        """Get current portfolio value."""
        return self._portfolio_value
    
    def get_returns_history(self) -> List[float]:
        """Get returns history."""
        return self._returns_history.copy()
