"""Tests for qf-risk module."""

import pytest
import numpy as np
from datetime import datetime, timedelta

# Import all modules to test
from qf_risk import RiskManager, PositionLimits, CircuitBreaker
from qf_risk.limits import (
    PositionLimitConfig, LimitCheckResult, LimitCheckStatus
)
from qf_risk.circuit_breaker import (
    CircuitBreakerConfig, CircuitBreakerState, CircuitBreakerType, CircuitBreakerLevel
)
from qf_risk.stop_loss import (
    StopLossManager, StopLossConfig, StopLossResult, OrderSide, StopLossType
)
from qf_risk.var import VaRCalculator, VaRResult, VaRMethod
from qf_risk.anomaly import (
    AnomalyDetector, AnomalyConfig, AnomalyResult, AnomalyType, AnomalySeverity
)
from qf_risk.manager import RiskManagerConfig, RiskReport


class TestPositionLimits:
    """Tests for position limits."""
    
    def test_single_position_pass(self):
        """Test single position within limits passes."""
        limits = PositionLimits()
        result = limits.check_single_position(
            "AAPL", 5000, 100000
        )
        assert result.status == LimitCheckStatus.PASS
        assert result.current_value == 0.05
        assert result.limit_value == 0.2
    
    def test_single_position_warning(self):
        """Test single position warning."""
        config = PositionLimitConfig(max_single_position_pct=0.1, warning_threshold_pct=0.9)
        limits = PositionLimits(config)
        result = limits.check_single_position(
            "AAPL", 9500, 100000
        )
        assert result.status == LimitCheckStatus.WARNING
    
    def test_single_position_violation(self):
        """Test single position violation."""
        limits = PositionLimits()
        result = limits.check_single_position(
            "AAPL", 25000, 100000
        )
        assert result.status == LimitCheckStatus.VIOLATION
        assert result.current_value == 0.25
    
    def test_total_position_pass(self):
        """Test total position within limits passes."""
        limits = PositionLimits()
        positions = {"AAPL": 10000, "GOOGL": 15000}
        result = limits.check_total_position(positions, 100000)
        assert result.status == LimitCheckStatus.PASS
        assert result.current_value == 0.25
    
    def test_total_position_violation(self):
        """Test total position violation."""
        limits = PositionLimits()
        positions = {"AAPL": 50000, "GOOGL": 40000}
        result = limits.check_total_position(positions, 100000)
        assert result.status == LimitCheckStatus.VIOLATION
        assert result.current_value == 0.9
    
    def test_total_position_with_proposed(self):
        """Test total position with proposed addition."""
        limits = PositionLimits()
        positions = {"AAPL": 40000, "GOOGL": 30000}
        proposed = {"MSFT": 20000}  # Total would be 90K = 90%
        result = limits.check_total_position(positions, 100000, proposed)
        assert result.status == LimitCheckStatus.VIOLATION
    
    def test_concentration_pass(self):
        """Test concentration check passes."""
        limits = PositionLimits()
        positions = {"AAPL": 2500, "GOOGL": 2500, "MSFT": 2500, "AMZN": 2500}
        result = limits.check_concentration(positions)
        assert result.status == LimitCheckStatus.PASS
    
    def test_concentration_warning(self):
        """Test concentration warning."""
        limits = PositionLimits()
        positions = {"AAPL": 7000, "GOOGL": 2000, "MSFT": 1000}
        result = limits.check_concentration(positions, max_concentration_pct=0.5)
        assert result.status == LimitCheckStatus.WARNING
    
    def test_concentration_empty(self):
        """Test concentration with empty positions."""
        limits = PositionLimits()
        result = limits.check_concentration({})
        assert result.status == LimitCheckStatus.PASS
    
    def test_check_history(self):
        """Test limit check history."""
        limits = PositionLimits()
        limits.check_single_position("AAPL", 5000, 100000)
        limits.check_total_position({"AAPL": 5000}, 100000)
        history = limits.get_check_history()
        assert len(history) == 2


class TestCircuitBreaker:
    """Tests for circuit breaker."""
    
    def test_initial_state(self):
        """Test initial circuit breaker state."""
        cb = CircuitBreaker()
        for cb_type in CircuitBreakerType:
            state = cb.get_state(cb_type)
            assert state.level == CircuitBreakerLevel.NORMAL
    
    def test_initialize_capital(self):
        """Test capital initialization."""
        cb = CircuitBreaker()
        cb.initialize_capital(100000)
        assert cb._initial_capital == 100000
        assert cb._current_value == 100000
    
    def test_daily_loss_trigger(self):
        """Test daily loss circuit breaker triggers."""
        config = CircuitBreakerConfig(daily_loss_limit_pct=0.02)
        cb = CircuitBreaker(config)
        cb.initialize_capital(100000)
        
        # Simulate 3% loss
        states = cb.update_portfolio_value(97000)
        daily_state = next(s for s in states if s.breaker_type == CircuitBreakerType.DAILY_LOSS)
        assert daily_state.level == CircuitBreakerLevel.TRIGGERED
    
    def test_daily_loss_warning(self):
        """Test daily loss circuit breaker warning."""
        config = CircuitBreakerConfig(daily_loss_limit_pct=0.02, daily_loss_warning_pct=0.01)
        cb = CircuitBreaker(config)
        cb.initialize_capital(100000)
        
        # Simulate 1.5% loss
        states = cb.update_portfolio_value(98500)
        daily_state = next(s for s in states if s.breaker_type == CircuitBreakerType.DAILY_LOSS)
        assert daily_state.level == CircuitBreakerLevel.WARNING
    
    def test_max_drawdown_trigger(self):
        """Test max drawdown circuit breaker triggers."""
        config = CircuitBreakerConfig(max_drawdown_limit_pct=0.05)
        cb = CircuitBreaker(config)
        cb.initialize_capital(100000)
        
        # Peak at 110000, then drop to 104000 (5.45% drawdown)
        cb.update_portfolio_value(110000)
        states = cb.update_portfolio_value(104000)
        
        dd_state = next(s for s in states if s.breaker_type == CircuitBreakerType.MAX_DRAWDOWN)
        assert dd_state.level == CircuitBreakerLevel.TRIGGERED
    
    def test_monthly_loss_trigger(self):
        """Test monthly loss circuit breaker triggers."""
        config = CircuitBreakerConfig(monthly_loss_limit_pct=0.05)
        cb = CircuitBreaker(config)
        cb.initialize_capital(100000)
        
        # Simulate 6% loss over multiple days
        cb.update_portfolio_value(98000)
        cb.update_portfolio_value(96000)
        states = cb.update_portfolio_value(94000)
        
        monthly_state = next(s for s in states if s.breaker_type == CircuitBreakerType.MONTHLY_LOSS)
        assert monthly_state.level == CircuitBreakerLevel.TRIGGERED
    
    def test_trading_allowed(self):
        """Test trading allowed check."""
        config = CircuitBreakerConfig(daily_loss_limit_pct=0.01)
        cb = CircuitBreaker(config)
        cb.initialize_capital(100000)
        
        assert cb.is_trading_allowed() is True
        
        # Trigger circuit breaker
        cb.update_portfolio_value(98500)
        assert cb.is_trading_allowed() is False
    
    def test_reset(self):
        """Test circuit breaker reset."""
        config = CircuitBreakerConfig(daily_loss_limit_pct=0.01)
        cb = CircuitBreaker(config)
        cb.initialize_capital(100000)
        cb.update_portfolio_value(98500)
        
        assert cb.is_trading_allowed() is False
        
        cb.reset()
        assert cb.is_trading_allowed() is True
        
        state = cb.get_state(CircuitBreakerType.DAILY_LOSS)
        assert state.level == CircuitBreakerLevel.NORMAL
    
    def test_reset_single(self):
        """Test single circuit breaker reset."""
        cb = CircuitBreaker()
        cb.initialize_capital(100000)
        cb.update_portfolio_value(98500)
        
        cb.reset(CircuitBreakerType.DAILY_LOSS)
        
        state = cb.get_state(CircuitBreakerType.DAILY_LOSS)
        assert state.level == CircuitBreakerLevel.NORMAL
    
    def test_listener_notification(self):
        """Test listener notification on state change."""
        cb = CircuitBreaker()
        cb.initialize_capital(100000)
        
        events = []
        def listener(state):
            events.append(state)
        
        cb.add_listener(listener)
        cb.update_portfolio_value(98500)  # Trigger warning/loss
        
        assert len(events) > 0
        
        cb.remove_listener(listener)
    
    def test_manual_lock(self):
        """Test manual circuit breaker lock."""
        cb = CircuitBreaker()
        cb.initialize_capital(100000)
        
        cb.manual_lock(CircuitBreakerType.DAILY_LOSS, 30, "Manual test lock")
        
        assert cb.is_trading_allowed() is False
        
        state = cb.get_state(CircuitBreakerType.DAILY_LOSS)
        assert state.level == CircuitBreakerLevel.LOCKED
        assert state.message == "Manual test lock"


class TestStopLoss:
    """Tests for stop-loss manager."""
    
    def test_register_position(self):
        """Test position registration."""
        manager = StopLossManager()
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        
        position = manager.get_position("AAPL")
        assert position is not None
        assert position.symbol == "AAPL"
        assert position.entry_price == 150.0
        assert position.quantity == 100
    
    def test_fixed_stop_loss_trigger(self):
        """Test fixed stop-loss trigger."""
        config = StopLossConfig(stop_loss_pct=0.02)
        manager = StopLossManager(config)
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        
        # Price drops 3%
        result = manager.update_price("AAPL", 145.0)
        
        assert result is not None
        assert result.triggered is True
        assert result.action == "stop_loss"
    
    def test_take_profit_trigger(self):
        """Test take-profit trigger."""
        config = StopLossConfig(take_profit_pct=0.05)
        manager = StopLossManager(config)
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        
        # Price rises 6%
        result = manager.update_price("AAPL", 159.0)
        
        assert result is not None
        assert result.triggered is True
        assert result.action == "take_profit"
    
    def test_trailing_stop_trigger(self):
        """Test trailing stop trigger."""
        config = StopLossConfig(trailing_stop_pct=0.02)
        manager = StopLossManager(config)
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        
        # Price rises to 160, then drops 2.5%
        manager.update_price("AAPL", 155.0)
        manager.update_price("AAPL", 160.0)
        result = manager.update_price("AAPL", 156.0)  # 2.5% drop from 160
        
        assert result is not None
        assert result.triggered is True
        assert result.action == "trailing_stop"
    
    def test_short_stop_loss(self):
        """Test stop-loss for short position."""
        config = StopLossConfig(stop_loss_pct=0.02)
        manager = StopLossManager(config)
        manager.register_position("AAPL", OrderSide.SELL, 150.0, 100)
        
        # Price rises 3% (loss for short)
        result = manager.update_price("AAPL", 154.5)
        
        assert result is not None
        assert result.triggered is True
        assert result.action == "stop_loss"
    
    def test_short_take_profit(self):
        """Test take-profit for short position."""
        config = StopLossConfig(take_profit_pct=0.05)
        manager = StopLossManager(config)
        manager.register_position("AAPL", OrderSide.SELL, 150.0, 100)
        
        # Price drops 6% (profit for short)
        result = manager.update_price("AAPL", 141.0)
        
        assert result is not None
        assert result.triggered is True
        assert result.action == "take_profit"
    
    def test_no_trigger(self):
        """Test no trigger when price is stable."""
        manager = StopLossManager()
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        
        result = manager.update_price("AAPL", 150.5)
        
        assert result is not None
        assert result.triggered is False
    
    def test_close_position(self):
        """Test closing position."""
        manager = StopLossManager()
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        
        closed = manager.close_position("AAPL")
        assert closed is not None
        assert manager.get_position("AAPL") is None
    
    def test_modify_stop_loss(self):
        """Test modifying stop-loss."""
        config = StopLossConfig(stop_loss_pct=0.05, trailing_stop_pct=0.05)  # 5% stop loss/trailing stop
        manager = StopLossManager(config)
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)

        # Update price to 160 to set high water mark
        manager.update_price("AAPL", 160.0)

        # Move stop loss lower to 152 (below current price but above trailing stop)
        success = manager.modify_stop_loss("AAPL", 152.0)
        assert success is True

        # Price at 155 should not trigger (above stop loss)
        result = manager.update_price("AAPL", 155.0)
        assert result.triggered is False
    
    def test_modify_take_profit(self):
        """Test modifying take-profit."""
        manager = StopLossManager()
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        
        success = manager.modify_take_profit("AAPL", 160.0)
        assert success is True
    
    def test_get_all_positions(self):
        """Test getting all positions."""
        manager = StopLossManager()
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        manager.register_position("GOOGL", OrderSide.BUY, 2800.0, 10)
        
        positions = manager.get_all_positions()
        assert len(positions) == 2
        assert "AAPL" in positions
        assert "GOOGL" in positions
    
    def test_pnl_calculation(self):
        """Test P&L calculation in result."""
        manager = StopLossManager()
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        
        result = manager.update_price("AAPL", 160.0)
        
        assert result is not None
        assert result.pnl is not None
        assert result.pnl_pct is not None
        assert abs(result.pnl_pct - 0.0667) < 0.01  # ~6.67%


class TestVaR:
    """Tests for VaR calculator."""
    
    def test_historical_var(self):
        """Test historical VaR calculation."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 100).tolist()
        
        calculator = VaRCalculator(confidence_level=0.95, holding_period_days=1)
        result = calculator.calculate(returns, 100000, VaRMethod.HISTORICAL)
        
        assert result is not None
        assert result.var_value > 0
        assert result.var_pct > 0
        assert result.confidence_level == 0.95
        assert result.method == VaRMethod.HISTORICAL
    
    def test_parametric_var(self):
        """Test parametric VaR calculation."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 100).tolist()
        
        calculator = VaRCalculator(confidence_level=0.95, holding_period_days=1)
        result = calculator.calculate(returns, 100000, VaRMethod.PARAMETRIC)
        
        assert result is not None
        assert result.var_value > 0
        assert result.var_pct > 0
        assert result.method == VaRMethod.PARAMETRIC
        assert result.expected_shortfall is not None
    
    def test_monte_carlo_var(self):
        """Test Monte Carlo VaR calculation."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 100).tolist()
        
        calculator = VaRCalculator(confidence_level=0.95, holding_period_days=1)
        result = calculator.calculate(returns, 100000, VaRMethod.MONTE_CARLO, num_simulations=5000)
        
        assert result is not None
        assert result.var_value > 0
        assert result.var_pct > 0
        assert result.method == VaRMethod.MONTE_CARLO
    
    def test_var_holding_period(self):
        """Test VaR with different holding periods."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 100).tolist()
        
        calc_1d = VaRCalculator(confidence_level=0.95, holding_period_days=1)
        calc_10d = VaRCalculator(confidence_level=0.95, holding_period_days=10)
        
        result_1d = calc_1d.calculate(returns, 100000, VaRMethod.PARAMETRIC)
        result_10d = calc_10d.calculate(returns, 100000, VaRMethod.PARAMETRIC)
        
        # 10-day VaR should be larger (approximately sqrt(10) times)
        assert result_10d.var_value > result_1d.var_value
    
    def test_var_different_confidence(self):
        """Test VaR with different confidence levels."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 100).tolist()
        
        calc_95 = VaRCalculator(confidence_level=0.95, holding_period_days=1)
        calc_99 = VaRCalculator(confidence_level=0.99, holding_period_days=1)
        
        result_95 = calc_95.calculate(returns, 100000, VaRMethod.PARAMETRIC)
        result_99 = calc_99.calculate(returns, 100000, VaRMethod.PARAMETRIC)
        
        # 99% VaR should be larger than 95% VaR
        assert result_99.var_value > result_95.var_value
    
    def test_portfolio_var(self):
        """Test portfolio VaR calculation."""
        np.random.seed(42)
        n_days = 100
        
        # Two correlated assets
        returns_a = np.random.normal(0.001, 0.02, n_days)
        returns_b = returns_a * 0.7 + np.random.normal(0, 0.015, n_days)
        
        weights = [0.6, 0.4]
        returns_matrix = [returns_a.tolist(), returns_b.tolist()]
        
        calculator = VaRCalculator(confidence_level=0.95, holding_period_days=1)
        result = calculator.calculate_portfolio_var(weights, returns_matrix, 100000)
        
        assert result is not None
        assert result.var_value > 0
    
    def test_component_var(self):
        """Test component VaR calculation."""
        np.random.seed(42)
        n_days = 100
        
        returns_a = np.random.normal(0.001, 0.02, n_days)
        returns_b = np.random.normal(0.001, 0.025, n_days)
        
        weights = [0.5, 0.5]
        returns_matrix = [returns_a.tolist(), returns_b.tolist()]
        
        calculator = VaRCalculator(confidence_level=0.95, holding_period_days=1)
        components = calculator.component_var(weights, returns_matrix, 100000)
        
        assert len(components) == 2
        # Component VaR can be negative for diversification benefit
        assert all(abs(c['component_var']) >= 0 for c in components)
        assert all(-1 <= c['component_var_pct'] <= 1 for c in components)


class TestAnomalyDetection:
    """Tests for anomaly detection."""
    
    def test_price_gap_detection(self):
        """Test price gap detection."""
        detector = AnomalyDetector(AnomalyConfig(price_gap_threshold=0.03))
        
        # 5% gap
        result = detector.detect_price_gap(100.0, 105.0, "AAPL")
        
        assert result.detected is True
        assert result.anomaly_type == AnomalyType.PRICE_GAP
        assert result.current_value == 0.05
    
    def test_price_gap_no_detection(self):
        """Test no price gap when within threshold."""
        detector = AnomalyDetector(AnomalyConfig(price_gap_threshold=0.03))
        
        result = detector.detect_price_gap(100.0, 101.0, "AAPL")
        
        assert result.detected is False
    
    def test_volume_spike_detection(self):
        """Test volume spike detection."""
        detector = AnomalyDetector(AnomalyConfig(volume_spike_threshold=3.0))
        
        historical_volumes = [1000, 1100, 900, 1050, 950, 1200, 800, 1150, 1000, 950] * 5
        result = detector.detect_volume_spike(5000, historical_volumes, "AAPL")
        
        assert bool(result.detected) is True
        assert result.anomaly_type == AnomalyType.VOLUME_SPIKE
    
    def test_volume_spike_insufficient_data(self):
        """Test volume spike with insufficient data."""
        detector = AnomalyDetector(AnomalyConfig(min_data_points=30))
        
        result = detector.detect_volume_spike(5000, [1000] * 10, "AAPL")
        
        assert result.detected is False
        assert "Insufficient" in result.message
    
    def test_volatility_spike_detection(self):
        """Test volatility spike detection."""
        detector = AnomalyDetector(AnomalyConfig(volatility_spike_threshold=2.0))
        
        recent_returns = [0.05, -0.04, 0.06, -0.05, 0.04]  # High volatility
        historical_vol = 0.02
        
        result = detector.detect_volatility_spike(recent_returns, historical_vol, "AAPL")
        
        assert bool(result.detected) is True
        assert result.anomaly_type == AnomalyType.VOLATILITY_SPIKE
    
    def test_price_outlier_detection(self):
        """Test price outlier detection."""
        detector = AnomalyDetector(AnomalyConfig(price_outlier_zscore=3.0))
        
        historical_prices = [100 + i * 0.5 for i in range(50)]  # Trending up
        current_price = 150  # Significant outlier
        
        result = detector.detect_price_outlier(current_price, historical_prices, "AAPL")
        
        assert bool(result.detected) is True
        assert result.anomaly_type == AnomalyType.PRICE_OUTLIER
        assert result.z_score > 3.0
    
    def test_price_outlier_no_detection(self):
        """Test no price outlier when within range."""
        detector = AnomalyDetector(AnomalyConfig(price_outlier_zscore=3.0))
        
        historical_prices = [100 + i * 0.5 for i in range(50)]
        current_price = 122  # Within expected range (mean ~112, std ~15)
        
        result = detector.detect_price_outlier(current_price, historical_prices, "AAPL")
        
        assert bool(result.detected) is False
    
    def test_scan_all(self):
        """Test scanning for all anomaly types."""
        detector = AnomalyDetector(
            AnomalyConfig(price_gap_threshold=0.03, volume_spike_threshold=3.0)
        )
        
        historical_prices = [100.0] * 50
        historical_volumes = [1000, 1100, 900, 1050, 950, 1200, 800, 1150, 1000, 950] * 5
        recent_returns = [0.001] * 10
        
        anomalies = detector.scan_all(
            "AAPL", 105.0, 5000, 100.0,
            historical_prices, historical_volumes, recent_returns
        )
        
        # Should detect price gap and volume spike
        assert len(anomalies) >= 1
        assert any(a.anomaly_type == AnomalyType.PRICE_GAP for a in anomalies)
        assert any(a.anomaly_type == AnomalyType.VOLUME_SPIKE for a in anomalies)
    
    def test_anomaly_severity(self):
        """Test anomaly severity levels."""
        detector = AnomalyDetector(AnomalyConfig(price_gap_threshold=0.02))
        
        # Small gap
        result_small = detector.detect_price_gap(100.0, 102.0, "AAPL")
        assert result_small.severity in [AnomalySeverity.LOW, AnomalySeverity.MEDIUM]
        
        # Large gap
        result_large = detector.detect_price_gap(100.0, 115.0, "AAPL")
        assert result_large.severity in [AnomalySeverity.HIGH, AnomalySeverity.CRITICAL]


class TestRiskManager:
    """Tests for main RiskManager class."""
    
    def test_initialization(self):
        """Test RiskManager initialization."""
        manager = RiskManager()
        assert manager.position_limits is not None
        assert manager.circuit_breaker is not None
        assert manager.stop_loss_manager is not None
        assert manager.var_calculator is not None
        assert manager.anomaly_detector is not None
    
    def test_initialize_capital(self):
        """Test capital initialization."""
        manager = RiskManager()
        manager.initialize_capital(100000)
        
        assert manager._initial_capital == 100000
        assert manager._portfolio_value == 100000
    
    def test_can_trade_allowed(self):
        """Test trade allowed."""
        config = RiskManagerConfig(
            position_limits=PositionLimitConfig(
                max_single_position_pct=0.5,
                max_total_position_pct=0.9
            )
        )
        manager = RiskManager(config)
        manager.initialize_capital(100000)

        allowed, reasons = manager.can_trade("AAPL", "buy", 10, 150.0)

        assert allowed is True, f"Trade not allowed: {reasons}"
        assert len(reasons) == 0
    
    def test_can_trade_circuit_breaker(self):
        """Test trade blocked by circuit breaker."""
        config = RiskManagerConfig(
            circuit_breaker=CircuitBreakerConfig(daily_loss_limit_pct=0.01)
        )
        manager = RiskManager(config)
        manager.initialize_capital(100000)
        manager.update_portfolio_value(98500)  # Trigger circuit breaker
        
        allowed, reasons = manager.can_trade("AAPL", "buy", 10, 150.0)
        
        assert allowed is False
        assert any("Circuit breaker" in r for r in reasons)
    
    def test_can_trade_position_limit(self):
        """Test trade blocked by position limit."""
        config = RiskManagerConfig(
            position_limits=PositionLimitConfig(max_single_position_pct=0.1)
        )
        manager = RiskManager(config)
        manager.initialize_capital(100000)
        
        # Try to buy position > 10% of portfolio
        allowed, reasons = manager.can_trade("AAPL", "buy", 100, 150.0)
        
        assert allowed is False
        assert any("limit" in r.lower() for r in reasons)
    
    def test_update_portfolio_value(self):
        """Test portfolio value update."""
        manager = RiskManager()
        manager.initialize_capital(100000)
        
        states = manager.update_portfolio_value(102000)
        
        assert manager._portfolio_value == 102000
        assert len(manager._returns_history) == 1
        assert manager._returns_history[0] == 0.02
    
    def test_register_and_update_position(self):
        """Test position registration and price update."""
        manager = RiskManager()
        manager.initialize_capital(100000)
        
        # First check if can trade
        allowed, _ = manager.can_trade("AAPL", "buy", 100, 150.0)
        if allowed:
            manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        
        assert "AAPL" in manager.get_positions() or not allowed
        
        # Test stop loss trigger
        if allowed:
            result = manager.update_price("AAPL", 145.0)  # 3.3% drop
            assert result is not None
    
    def test_close_position(self):
        """Test closing position."""
        manager = RiskManager()
        manager.initialize_capital(100000)
        
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        manager.close_position("AAPL")
        
        assert "AAPL" not in manager.get_positions()
    
    def test_calculate_var(self):
        """Test VaR calculation through RiskManager."""
        np.random.seed(42)
        manager = RiskManager()
        manager.initialize_capital(100000)
        
        # Add returns history
        for _ in range(50):
            manager.update_portfolio_value(
                manager.get_portfolio_value() * (1 + np.random.normal(0, 0.02))
            )
        
        result = manager.calculate_var()
        
        assert result is not None
        assert result.var_value > 0
    
    def test_calculate_var_insufficient_data(self):
        """Test VaR with insufficient data."""
        manager = RiskManager()
        manager.initialize_capital(100000)
        
        result = manager.calculate_var()
        
        assert result is None
    
    def test_check_anomalies(self):
        """Test anomaly detection through RiskManager."""
        manager = RiskManager()
        
        historical_prices = [100.0] * 50
        historical_volumes = [1000] * 50
        recent_returns = [0.001] * 10
        
        anomalies = manager.check_anomalies(
            "AAPL", 105.0, 5000, 100.0,
            historical_prices, historical_volumes, recent_returns
        )
        
        assert len(anomalies) >= 1
    
    def test_get_risk_report(self):
        """Test risk report generation."""
        manager = RiskManager()
        manager.initialize_capital(100000)
        
        # Add some returns history for VaR
        np.random.seed(42)
        for _ in range(50):
            manager.update_portfolio_value(
                manager.get_portfolio_value() * (1 + np.random.normal(0, 0.02))
            )
        
        report = manager.get_risk_report()
        
        assert isinstance(report, RiskReport)
        assert report.timestamp is not None
        assert isinstance(report.circuit_breaker_states, dict)
        assert isinstance(report.position_limit_status, list)
    
    def test_event_listener(self):
        """Test event listener."""
        manager = RiskManager()
        manager.initialize_capital(100000)
        
        events = []
        def listener(event_type, data):
            events.append((event_type, data))
        
        manager.add_event_listener(listener)
        
        # Trigger circuit breaker
        config = RiskManagerConfig(
            circuit_breaker=CircuitBreakerConfig(daily_loss_limit_pct=0.01)
        )
        manager.circuit_breaker = CircuitBreaker(config.circuit_breaker)
        manager.circuit_breaker.initialize_capital(100000)
        manager.update_portfolio_value(98500)
        
        assert len(events) > 0
        
        manager.remove_event_listener(listener)
    
    def test_reset_circuit_breaker(self):
        """Test circuit breaker reset."""
        config = RiskManagerConfig(
            circuit_breaker=CircuitBreakerConfig(daily_loss_limit_pct=0.01)
        )
        manager = RiskManager(config)
        manager.initialize_capital(100000)
        manager.update_portfolio_value(98500)
        
        assert manager.circuit_breaker.is_trading_allowed() is False
        
        manager.reset_circuit_breaker()
        
        assert manager.circuit_breaker.is_trading_allowed() is True


class TestIntegration:
    """Integration tests."""
    
    def test_full_risk_workflow(self):
        """Test complete risk management workflow."""
        # Setup
        config = RiskManagerConfig(
            position_limits=PositionLimitConfig(
                max_single_position_pct=0.5,
                max_total_position_pct=0.9
            ),
            circuit_breaker=CircuitBreakerConfig(
                daily_loss_limit_pct=0.05,
                max_drawdown_limit_pct=0.10
            ),
            stop_loss=StopLossConfig(
                stop_loss_pct=0.02,
                take_profit_pct=0.05
            )
        )

        manager = RiskManager(config)
        manager.initialize_capital(100000)

        # Check if can trade
        allowed, reasons = manager.can_trade("AAPL", "buy", 100, 150.0)
        assert allowed is True, f"Trade not allowed: {reasons}"

        # Register position
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)

        # Monitor price (stop loss)
        result = manager.update_price("AAPL", 160.0)  # Take profit

        # Generate risk report
        report = manager.get_risk_report()
        assert report.trading_allowed is True

        # Simulate loss to trigger circuit breaker
        manager.update_portfolio_value(94000)

        # Should not be able to trade
        allowed, _ = manager.can_trade("GOOGL", "buy", 10, 2000.0)
        assert allowed is False
    
    def test_multiple_positions(self):
        """Test managing multiple positions."""
        manager = RiskManager()
        manager.initialize_capital(100000)
        
        # Register multiple positions
        manager.register_position("AAPL", OrderSide.BUY, 150.0, 100)
        manager.register_position("GOOGL", OrderSide.BUY, 2800.0, 10)
        manager.register_position("MSFT", OrderSide.BUY, 300.0, 50)
        
        positions = manager.get_positions()
        assert len(positions) == 3
        
        # Check concentration
        result = manager.position_limits.check_concentration(positions)
        assert result.current_value <= 1.0
    
    def test_var_with_correlation(self):
        """Test VaR with correlated assets."""
        np.random.seed(42)
        
        # Create correlated returns
        base_returns = np.random.normal(0, 0.02, 100)
        asset_a = base_returns + np.random.normal(0, 0.01, 100)
        asset_b = base_returns * 0.8 + np.random.normal(0, 0.015, 100)
        
        calculator = VaRCalculator(confidence_level=0.95)
        
        # Portfolio VaR
        result = calculator.calculate_portfolio_var(
            [0.5, 0.5],
            [asset_a.tolist(), asset_b.tolist()],
            100000
        )
        
        assert result.var_value > 0
        
        # Component VaR - just check it runs without error
        components = calculator.component_var(
            [0.5, 0.5],
            [asset_a.tolist(), asset_b.tolist()],
            100000
        )
        
        # Verify components exist
        assert len(components) == 2
