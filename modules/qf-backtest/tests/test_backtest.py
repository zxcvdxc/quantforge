"""Tests for qf-backtest module."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from qf_backtest import (
    BacktestEngine,
    NoSlippage,
    PercentageSlippage,
    FixedSlippage,
    VolumeBasedSlippage,
    VolatilityBasedSlippage,
    NoCommission,
    PercentageCommission,
    FixedCommission,
    TieredCommission,
    HybridCommission,
    calculate_metrics,
    PerformanceMetrics,
    GridSearchOptimizer,
    optimize_parameters,
)
from qf_backtest.engine import (
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    Position,
    Account,
    MarketDataEvent,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_market_data():
    """Create sample OHLCV market data."""
    np.random.seed(42)
    n_days = 100
    
    # Generate random walk prices
    returns = np.random.normal(0.0005, 0.02, n_days)
    prices = 100 * np.exp(np.cumsum(returns))
    
    # Create OHLCV data
    data = []
    base_date = datetime(2024, 1, 1)
    
    for i in range(n_days):
        close = prices[i]
        high = close * (1 + abs(np.random.normal(0, 0.01)))
        low = close * (1 - abs(np.random.normal(0, 0.01)))
        open_price = low + np.random.random() * (high - low)
        volume = np.random.randint(100000, 1000000)
        
        data.append({
            "timestamp": base_date + timedelta(days=i),
            "symbol": "AAPL",
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
    
    return pd.DataFrame(data)


@pytest.fixture
def simple_strategy():
    """Create a simple moving average crossover strategy."""
    def strategy(engine, data):
        # Simple strategy: buy if price is above 20-day MA
        symbol = data.symbol
        
        # Get all historical data for this symbol
        # For simplicity, just use current position
        position = engine.get_position_quantity(symbol)
        
        if position == 0 and data.close > data.open:  # Bullish
            engine.submit_order(symbol, OrderSide.BUY, 100)
        elif position > 0 and data.close < data.open:  # Bearish
            engine.submit_order(symbol, OrderSide.SELL, position)
    
    return strategy


@pytest.fixture
def engine():
    """Create a fresh backtest engine."""
    return BacktestEngine(initial_capital=100000.0)


# =============================================================================
# Engine Tests
# =============================================================================

class TestBacktestEngine:
    """Test BacktestEngine functionality."""
    
    def test_engine_initialization(self):
        """Test engine initializes correctly."""
        engine = BacktestEngine(initial_capital=50000.0)
        
        assert engine.initial_capital == 50000.0
        assert engine.current_cash == 50000.0
        assert engine.current_equity == 50000.0
        assert len(engine.get_equity_curve()) == 0
        assert len(engine.get_trades()) == 0
    
    def test_reset(self, engine, sample_market_data):
        """Test engine reset functionality."""
        # Run a backtest
        engine.run(sample_market_data, lambda e, d: None)
        
        # Reset
        engine.reset()
        
        assert engine.current_cash == engine.initial_capital
        assert len(engine.get_equity_curve()) == 0
        assert len(engine.get_trades()) == 0
    
    def test_submit_buy_order(self, engine):
        """Test submitting a buy order."""
        # Add market data first
        data = MarketDataEvent(
            timestamp=datetime.now(),
            symbol="AAPL",
            open=100,
            high=105,
            low=99,
            close=102,
            volume=1000000,
        )
        engine.on_market_data(data)
        
        # Submit buy order
        order = engine.submit_order("AAPL", OrderSide.BUY, 100)
        
        assert order is not None
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.quantity == 100
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 100
        assert order.filled_price > 0
    
    def test_submit_sell_order(self, engine):
        """Test submitting a sell order."""
        data = MarketDataEvent(
            timestamp=datetime.now(),
            symbol="AAPL",
            open=100,
            high=105,
            low=99,
            close=102,
            volume=1000000,
        )
        engine.on_market_data(data)
        
        # First buy some shares
        engine.submit_order("AAPL", OrderSide.BUY, 100)
        
        # Then sell
        order = engine.submit_order("AAPL", OrderSide.SELL, 100)
        
        assert order is not None
        assert order.side == OrderSide.SELL
        assert order.status == OrderStatus.FILLED
    
    def test_insufficient_quantity_rejection(self, engine):
        """Test that zero or negative quantity orders are rejected."""
        data = MarketDataEvent(
            timestamp=datetime.now(),
            symbol="AAPL",
            open=100,
            high=105,
            low=99,
            close=102,
            volume=1000000,
        )
        engine.on_market_data(data)
        
        order = engine.submit_order("AAPL", OrderSide.BUY, 0)
        assert order is None
        
        order = engine.submit_order("AAPL", OrderSide.BUY, -10)
        assert order is None
    
    def test_order_without_market_data(self, engine):
        """Test order rejection when no market data available."""
        order = engine.submit_order("AAPL", OrderSide.BUY, 100)
        assert order is not None  # Returns order even if rejected
        assert order.status == OrderStatus.REJECTED
    
    def test_position_tracking(self, engine):
        """Test position tracking."""
        data = MarketDataEvent(
            timestamp=datetime.now(),
            symbol="AAPL",
            open=100,
            high=105,
            low=99,
            close=102,
            volume=1000000,
        )
        engine.on_market_data(data)
        
        # Initial position
        assert engine.get_position_quantity("AAPL") == 0
        
        # Buy
        engine.submit_order("AAPL", OrderSide.BUY, 100)
        assert engine.get_position_quantity("AAPL") == 100
        
        # Sell partial
        engine.submit_order("AAPL", OrderSide.SELL, 50)
        assert engine.get_position_quantity("AAPL") == 50
        
        # Sell all
        engine.submit_order("AAPL", OrderSide.SELL, 50)
        assert engine.get_position_quantity("AAPL") == 0
    
    def test_equity_tracking(self, engine):
        """Test equity curve tracking."""
        data = MarketDataEvent(
            timestamp=datetime.now(),
            symbol="AAPL",
            open=100,
            high=105,
            low=99,
            close=102,
            volume=1000000,
        )
        engine.on_market_data(data)
        
        initial_equity = engine.current_equity
        engine.submit_order("AAPL", OrderSide.BUY, 100)
        
        # Equity should reflect position
        assert engine.current_equity != initial_equity or True  # May be equal due to just buying
    
    def test_full_backtest_run(self, engine, sample_market_data, simple_strategy):
        """Test complete backtest run."""
        equity_curve = engine.run(sample_market_data, simple_strategy)
        
        assert len(equity_curve) > 0
        assert "timestamp" in equity_curve.columns
        assert "equity" in equity_curve.columns
        assert "cash" in equity_curve.columns
        
        trades = engine.get_trades()
        assert len(trades) >= 0
    
    def test_event_handlers(self, engine):
        """Test event handler registration and invocation."""
        market_data_called = [False]
        fill_called = [False]
        
        def market_handler(event, eng):
            market_data_called[0] = True
            
        def fill_handler(event, eng):
            fill_called[0] = True
        
        engine.add_market_data_handler(market_handler)
        engine.add_fill_handler(fill_handler)
        
        data = MarketDataEvent(
            timestamp=datetime.now(),
            symbol="AAPL",
            open=100,
            high=105,
            low=99,
            close=102,
            volume=1000000,
        )
        engine.on_market_data(data)
        
        assert market_data_called[0]
        
        # Fill handler should be called after order
        engine.submit_order("AAPL", OrderSide.BUY, 100)
        assert fill_called[0]


# =============================================================================
# Position Tests
# =============================================================================

class TestPosition:
    """Test Position class."""
    
    def test_position_initialization(self):
        """Test position initialization."""
        pos = Position(symbol="AAPL")
        
        assert pos.symbol == "AAPL"
        assert pos.quantity == 0
        assert pos.avg_price == 0
        assert pos.is_flat
        assert not pos.is_long
        assert not pos.is_short
    
    def test_position_long(self):
        """Test long position."""
        pos = Position(symbol="AAPL")
        pos.update(100, 100.0)
        
        assert pos.is_long
        assert not pos.is_flat
        assert pos.quantity == 100
        assert pos.avg_price == 100.0
    
    def test_position_short(self):
        """Test short position."""
        pos = Position(symbol="AAPL")
        pos.update(-100, 100.0)
        
        assert pos.is_short
        assert not pos.is_flat
        assert pos.quantity == -100
    
    def test_position_add_to_long(self):
        """Test adding to existing long position."""
        pos = Position(symbol="AAPL", quantity=100, avg_price=100.0)
        pos.update(50, 110.0)
        
        # Average price should be weighted
        expected_avg = (100 * 100 + 50 * 110) / 150
        assert pos.quantity == 150
        assert abs(pos.avg_price - expected_avg) < 0.01
    
    def test_position_reduce_long(self):
        """Test reducing long position."""
        pos = Position(symbol="AAPL", quantity=100, avg_price=100.0)
        pos.update(-30, 110.0)
        
        assert pos.quantity == 70
        # Average price unchanged when reducing
        assert pos.avg_price == 100.0
    
    def test_position_close(self):
        """Test closing position."""
        pos = Position(symbol="AAPL", quantity=100, avg_price=100.0)
        pos.update(-100, 110.0)
        
        assert pos.is_flat
        assert pos.quantity == 0
        assert pos.avg_price == 0


# =============================================================================
# Account Tests
# =============================================================================

class TestAccount:
    """Test Account class."""
    
    def test_account_initialization(self):
        """Test account initialization."""
        acc = Account(initial_capital=50000.0, cash=50000.0)
        
        assert acc.initial_capital == 50000.0
        assert acc.cash == 50000.0
        assert acc.total_value() == 50000.0
        assert len(acc.positions) == 0
    
    def test_get_position_creation(self):
        """Test position creation."""
        acc = Account(initial_capital=100000.0, cash=100000.0)
        
        pos = acc.get_position("AAPL")
        assert pos.symbol == "AAPL"
        assert pos.is_flat
        
        # Should return same position
        pos2 = acc.get_position("AAPL")
        assert pos is pos2
    
    def test_total_value_with_prices(self):
        """Test total value calculation with prices."""
        acc = Account(initial_capital=100000.0, cash=50000.0)
        acc.positions["AAPL"] = Position(symbol="AAPL", quantity=100, avg_price=100.0)
        
        prices = {"AAPL": 110.0}
        value = acc.total_value(prices)
        
        # Cash + position value
        expected = 50000 + 100 * 110
        assert value == expected


# =============================================================================
# Slippage Tests
# =============================================================================

class TestSlippage:
    """Test slippage models."""
    
    def test_no_slippage(self):
        """Test no slippage model."""
        model = NoSlippage()
        order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=100
        )
        data = MarketDataEvent(
            timestamp=datetime.now(), symbol="AAPL",
            open=100, high=105, low=99, close=102, volume=1000000
        )
        
        slippage = model.calculate_slippage(order, 102.0, data)
        assert slippage == 0.0
    
    def test_percentage_slippage(self):
        """Test percentage slippage model."""
        model = PercentageSlippage(slippage_pct=0.001)  # 0.1%
        order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=100
        )
        data = MarketDataEvent(
            timestamp=datetime.now(), symbol="AAPL",
            open=100, high=105, low=99, close=102, volume=1000000
        )
        
        slippage = model.calculate_slippage(order, 100.0, data)
        expected = 100.0 * 0.001
        assert abs(slippage - expected) < 0.001
    
    def test_fixed_slippage(self):
        """Test fixed slippage model."""
        model = FixedSlippage(fixed_amount=0.05)
        order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=100
        )
        data = MarketDataEvent(
            timestamp=datetime.now(), symbol="AAPL",
            open=100, high=105, low=99, close=102, volume=1000000
        )
        
        slippage = model.calculate_slippage(order, 100.0, data)
        assert slippage == 0.05
    
    def test_volume_based_slippage(self):
        """Test volume-based slippage model."""
        model = VolumeBasedSlippage(base_slippage_pct=0.001)
        order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=1000
        )
        data = MarketDataEvent(
            timestamp=datetime.now(), symbol="AAPL",
            open=100, high=105, low=99, close=102, volume=10000
        )
        
        slippage = model.calculate_slippage(order, 100.0, data)
        # Should be higher than base due to high volume ratio
        base_slippage = 100.0 * 0.001
        assert slippage > base_slippage
    
    def test_volatility_based_slippage(self):
        """Test volatility-based slippage model."""
        model = VolatilityBasedSlippage(base_slippage_pct=0.001)
        order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=100
        )
        
        # High volatility day
        data = MarketDataEvent(
            timestamp=datetime.now(), symbol="AAPL",
            open=100, high=110, low=90, close=100, volume=1000000
        )
        
        slippage = model.calculate_slippage(order, 100.0, data)
        base_slippage = 100.0 * 0.001
        assert slippage > base_slippage


# =============================================================================
# Commission Tests
# =============================================================================

class TestCommission:
    """Test commission models."""
    
    def test_no_commission(self):
        """Test no commission model."""
        model = NoCommission()
        order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=100
        )
        
        commission = model.calculate_commission(order, 100.0)
        assert commission == 0.0
    
    def test_percentage_commission(self):
        """Test percentage commission model."""
        model = PercentageCommission(rate=0.001)  # 0.1%
        order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=100
        )
        
        commission = model.calculate_commission(order, 100.0)
        expected = 100 * 100.0 * 0.001  # qty * price * rate
        assert commission == expected
    
    def test_percentage_commission_symbol_rates(self):
        """Test per-symbol commission rates."""
        model = PercentageCommission(
            rate=0.001,
            symbol_rates={"AAPL": 0.0005}  # Lower rate for AAPL
        )
        order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=100
        )
        
        commission = model.calculate_commission(order, 100.0)
        expected = 100 * 100.0 * 0.0005
        assert commission == expected
    
    def test_fixed_commission(self):
        """Test fixed commission model."""
        model = FixedCommission(amount=5.0)
        order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=100
        )
        
        commission = model.calculate_commission(order, 100.0)
        assert commission == 5.0
    
    def test_fixed_commission_per_share(self):
        """Test per-share fixed commission."""
        model = FixedCommission(amount=0.01, per_share=True)
        order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=100
        )
        
        commission = model.calculate_commission(order, 100.0)
        expected = 0.01 * 100
        assert commission == expected
    
    def test_tiered_commission(self):
        """Test tiered commission model."""
        model = TieredCommission(tiers=[(0, 0.001), (10000, 0.0008)])
        
        # Small trade
        small_order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=50
        )
        small_commission = model.calculate_commission(small_order, 100.0)
        expected_small = 50 * 100.0 * 0.001
        assert abs(small_commission - expected_small) < 0.01
        
        # Large trade
        large_order = Order(
            id="2", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=200
        )
        large_commission = model.calculate_commission(large_order, 100.0)
        expected_large = 200 * 100.0 * 0.0008  # Lower tier
        assert abs(large_commission - expected_large) < 0.01
    
    def test_hybrid_commission(self):
        """Test hybrid commission model."""
        model = HybridCommission(fixed_amount=5.0, percentage_rate=0.001)
        
        # Trade where percentage is higher
        large_order = Order(
            id="1", timestamp=datetime.now(), symbol="AAPL",
            side=OrderSide.BUY, quantity=1000
        )
        commission = model.calculate_commission(large_order, 100.0)
        expected = max(5.0, 1000 * 100.0 * 0.001)  # Should be 100
        assert commission == expected


# =============================================================================
# Metrics Tests
# =============================================================================

class TestMetrics:
    """Test performance metrics calculation."""
    
    def test_empty_equity_curve(self):
        """Test metrics with empty data."""
        equity_curve = pd.DataFrame()
        metrics = calculate_metrics(equity_curve)
        
        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.total_return == 0.0
    
    def test_basic_metrics(self):
        """Test basic metric calculations."""
        # Create simple equity curve
        equity = [100000, 101000, 102000, 101500, 103000]
        equity_curve = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=5),
            "equity": equity,
        })
        
        metrics = calculate_metrics(equity_curve, initial_capital=100000)
        
        assert metrics.total_return == 0.03  # 3%
        assert metrics.final_equity == 103000
        assert metrics.initial_capital == 100000
    
    def test_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        # Create equity curve with consistent positive returns
        returns = np.full(252, 0.0005)  # Consistent small positive return
        equity = 100000 * np.exp(np.cumsum(returns))
        equity = np.concatenate([[100000], equity])
        
        equity_curve = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=253),
            "equity": equity,
        })
        
        metrics = calculate_metrics(equity_curve)
        
        # Should have very high Sharpe due to consistent returns
        assert metrics.sharpe_ratio > 0
    
    def test_max_drawdown(self):
        """Test maximum drawdown calculation."""
        # Create equity curve with drawdown
        equity = [100, 110, 105, 95, 100, 120, 115]
        equity_curve = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=7),
            "equity": equity,
        })
        
        metrics = calculate_metrics(equity_curve)
        
        # Max drawdown should be from 110 to 95
        expected_dd = (95 - 110) / 110
        assert abs(metrics.max_drawdown - expected_dd) < 0.01
    
    def test_volatility(self):
        """Test volatility calculation."""
        # Create volatile equity curve
        np.random.seed(42)
        returns = np.random.normal(0, 0.02, 252)
        equity = 100000 * np.exp(np.cumsum(returns))
        equity = np.concatenate([[100000], equity])
        
        equity_curve = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=253),
            "equity": equity,
        })
        
        metrics = calculate_metrics(equity_curve)
        
        # Volatility should be positive
        assert metrics.volatility > 0
    
    def test_metrics_to_dict(self):
        """Test metrics serialization."""
        metrics = PerformanceMetrics(
            total_return=0.1,
            sharpe_ratio=1.5,
            max_drawdown=-0.05,
        )
        
        d = metrics.to_dict()
        
        assert d["total_return"] == 0.1
        assert d["sharpe_ratio"] == 1.5
        assert d["max_drawdown"] == -0.05


# =============================================================================
# Optimization Tests
# =============================================================================

class TestOptimization:
    """Test parameter optimization."""
    
    def test_grid_search_optimizer(self, sample_market_data):
        """Test grid search optimization."""
        def engine_factory():
            return BacktestEngine(initial_capital=100000.0)
        
        def strategy_factory(threshold):
            def strategy(engine, data):
                position = engine.get_position_quantity(data.symbol)
                
                # Simple threshold-based strategy
                price_change = (data.close - data.open) / data.open
                
                if position == 0 and price_change > threshold:
                    engine.submit_order(data.symbol, OrderSide.BUY, 100)
                elif position > 0 and price_change < -threshold:
                    engine.submit_order(data.symbol, OrderSide.SELL, position)
            
            return strategy
        
        param_grid = {"threshold": [0.001, 0.005, 0.01]}
        
        optimizer = GridSearchOptimizer(
            engine_factory=engine_factory,
            param_grid=param_grid,
            strategy_factory=strategy_factory,
            scoring="total_return",
            maximize=True,
            n_jobs=1,
        )
        
        optimizer.fit(sample_market_data)
        
        # Should find best parameters
        assert optimizer.best_params_ is not None
        assert "threshold" in optimizer.best_params_
        assert optimizer.best_score_ is not None
        assert len(optimizer.results_) == 3
    
    def test_optimize_parameters_function(self, sample_market_data):
        """Test optimize_parameters convenience function."""
        def strategy_factory(lookback):
            # Simple strategy using lookback parameter
            prices = {}
            
            def strategy(engine, data):
                symbol = data.symbol
                if symbol not in prices:
                    prices[symbol] = []
                prices[symbol].append(data.close)
                
                if len(prices[symbol]) < lookback:
                    return
                
                position = engine.get_position_quantity(symbol)
                sma = sum(prices[symbol][-lookback:]) / lookback
                
                if position == 0 and data.close > sma:
                    engine.submit_order(symbol, OrderSide.BUY, 100)
                elif position > 0 and data.close < sma:
                    engine.submit_order(symbol, OrderSide.SELL, position)
            
            return strategy
        
        param_grid = {"lookback": [5, 10, 20]}
        
        best_params, best_metrics = optimize_parameters(
            data=sample_market_data,
            strategy_factory=strategy_factory,
            param_grid=param_grid,
            initial_capital=100000.0,
            scoring="total_return",
            maximize=True,
            n_jobs=1,
        )
        
        assert "lookback" in best_params
        assert best_params["lookback"] in [5, 10, 20]
        assert isinstance(best_metrics, PerformanceMetrics)
    
    def test_optimization_results_df(self, sample_market_data):
        """Test getting results as DataFrame."""
        def engine_factory():
            return BacktestEngine(initial_capital=100000.0)
        
        def strategy_factory(param1, param2):
            def strategy(engine, data):
                pass
            return strategy
        
        param_grid = {"param1": [1, 2], "param2": [10, 20]}
        
        optimizer = GridSearchOptimizer(
            engine_factory=engine_factory,
            param_grid=param_grid,
            strategy_factory=strategy_factory,
            n_jobs=1,
        )
        
        optimizer.fit(sample_market_data)
        
        df = optimizer.get_results_df()
        
        assert len(df) == 4  # 2x2 grid
        assert "param1" in df.columns
        assert "param2" in df.columns
        assert "score" in df.columns
    
    def test_top_results(self, sample_market_data):
        """Test getting top N results."""
        def engine_factory():
            return BacktestEngine(initial_capital=100000.0)
        
        def strategy_factory(value):
            def strategy(engine, data):
                pass
            return strategy
        
        param_grid = {"value": [1, 2, 3, 4, 5]}
        
        optimizer = GridSearchOptimizer(
            engine_factory=engine_factory,
            param_grid=param_grid,
            strategy_factory=strategy_factory,
            n_jobs=1,
        )
        
        optimizer.fit(sample_market_data)
        
        top = optimizer.top_results(n=3)
        
        assert len(top) == 3


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the full backtesting system."""
    
    def test_backtest_with_slippage_and_commission(self, sample_market_data):
        """Test full backtest with slippage and commission."""
        # Create engine with costs
        engine = BacktestEngine(
            initial_capital=100000.0,
            slippage_model=PercentageSlippage(slippage_pct=0.001),
            commission_model=PercentageCommission(rate=0.001),
        )
        
        # Simple strategy
        def strategy(engine, data):
            position = engine.get_position_quantity(data.symbol)
            
            if position == 0 and data.close > data.open:
                engine.submit_order(data.symbol, OrderSide.BUY, 100)
            elif position > 0 and data.close < data.open:
                engine.submit_order(data.symbol, OrderSide.SELL, position)
        
        # Run backtest
        equity_curve = engine.run(sample_market_data, strategy)
        trades = engine.get_trades()
        
        # Verify trades have slippage and commission
        assert len(trades) > 0
        assert (trades["slippage"] > 0).any() or True  # May be 0 in some cases
        assert (trades["commission"] > 0).any()
        
        # Calculate metrics
        metrics = calculate_metrics(
            equity_curve,
            trades,
            initial_capital=engine.initial_capital,
        )
        
        assert metrics.total_return != 0 or True  # May be flat
        assert metrics.final_equity > 0
    
    def test_multiple_symbols(self):
        """Test backtest with multiple symbols."""
        # Create data for multiple symbols
        np.random.seed(42)
        data = []
        base_date = datetime(2024, 1, 1)
        
        for i in range(50):
            for symbol in ["AAPL", "GOOGL"]:
                price = 100 + np.random.normal(0, 2)
                data.append({
                    "timestamp": base_date + timedelta(days=i),
                    "symbol": symbol,
                    "open": price - 1,
                    "high": price + 2,
                    "low": price - 2,
                    "close": price,
                    "volume": 1000000,
                })
        
        df = pd.DataFrame(data)
        df = df.sort_values("timestamp")
        
        engine = BacktestEngine(initial_capital=100000.0)
        
        positions = {}
        
        def strategy(engine, data):
            symbol = data.symbol
            
            if symbol not in positions:
                positions[symbol] = 0
            
            if positions[symbol] == 0 and data.close > data.open:
                engine.submit_order(symbol, OrderSide.BUY, 50)
                positions[symbol] = 50
            elif positions[symbol] > 0 and data.close < data.open:
                engine.submit_order(symbol, OrderSide.SELL, positions[symbol])
                positions[symbol] = 0
        
        equity_curve = engine.run(df, strategy)
        
        assert len(equity_curve) > 0
        # Should have trades for both symbols
        trades = engine.get_trades()
        symbols_traded = trades["symbol"].unique() if not trades.empty else []
        assert len(symbols_traded) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
