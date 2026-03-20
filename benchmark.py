"""Performance benchmark for qf-backtest and qf-strategy modules."""

import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate_test_data(n_bars: int = 10000, n_symbols: int = 1) -> pd.DataFrame:
    """Generate test market data."""
    np.random.seed(42)
    
    records = []
    base_price = 50000.0
    
    for symbol_idx in range(n_symbols):
        symbol = f"BTC-{symbol_idx}"
        price = base_price + symbol_idx * 1000
        
        for i in range(n_bars):
            timestamp = datetime(2024, 1, 1) + timedelta(minutes=i)
            
            # Random walk with trend
            returns = np.random.normal(0.0001, 0.01)
            price *= (1 + returns)
            
            # Generate OHLC
            open_price = price * (1 + np.random.normal(0, 0.001))
            high_price = price * (1 + abs(np.random.normal(0, 0.005)))
            low_price = price * (1 - abs(np.random.normal(0, 0.005)))
            close_price = price
            volume = np.random.uniform(100, 1000)
            
            records.append({
                "timestamp": timestamp,
                "symbol": symbol,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            })
    
    return pd.DataFrame(records)


def benchmark_backtest_engine(data: pd.DataFrame) -> float:
    """Benchmark backtest engine performance."""
    import sys
    sys.path.insert(0, '/Users/zxcv/.openclaw/workspace/quantforge-modules/modules/qf-backtest/src')
    from qf_backtest import BacktestEngine
    from qf_backtest.engine import OrderSide
    
    def simple_strategy(engine, data):
        """Simple strategy that buys after 3 up bars, sells after 3 down bars."""
        symbol = data.symbol
        
        # Get or initialize state
        if not hasattr(engine, '_state'):
            engine._state = {}
        if symbol not in engine._state:
            engine._state[symbol] = {'consecutive_up': 0, 'consecutive_down': 0}
        
        state = engine._state[symbol]
        
        # Check direction
        if data.close > data.open:
            state['consecutive_up'] += 1
            state['consecutive_down'] = 0
        elif data.close < data.open:
            state['consecutive_down'] += 1
            state['consecutive_up'] = 0
        
        position = engine.get_position_quantity(symbol)
        
        # Trading logic
        if state['consecutive_up'] >= 3 and position <= 0:
            if position < 0:
                engine.submit_order(symbol, OrderSide.BUY, abs(position))
            engine.submit_order(symbol, OrderSide.BUY, 1.0)
        elif state['consecutive_down'] >= 3 and position >= 0:
            if position > 0:
                engine.submit_order(symbol, OrderSide.SELL, position)
            engine.submit_order(symbol, OrderSide.SELL, 1.0)
    
    engine = BacktestEngine(initial_capital=100000.0)
    
    start_time = time.perf_counter()
    equity = engine.run(data, simple_strategy)
    end_time = time.perf_counter()
    
    elapsed = end_time - start_time
    bars_per_second = len(data) / elapsed
    
    print(f"  Backtest Engine:")
    print(f"    Bars processed: {len(data)}")
    print(f"    Elapsed time: {elapsed:.4f}s")
    print(f"    Bars/second: {bars_per_second:,.0f}")
    print(f"    Final equity: ${equity['equity'].iloc[-1]:,.2f}")
    print(f"    Trades executed: {len(engine.get_trades())}")
    
    return elapsed


def benchmark_strategy_signal_generation(data: pd.DataFrame) -> float:
    """Benchmark strategy signal generation."""
    import sys
    sys.path.insert(0, '/Users/zxcv/.openclaw/workspace/quantforge-modules/modules/qf-strategy/src')
    sys.path.insert(0, '/Users/zxcv/.openclaw/workspace/quantforge-modules/modules/qf-backtest/src')
    from qf_strategy import DualMA
    from qf_strategy.base import BarData
    
    strategy = DualMA(params={"fast_period": 10, "slow_period": 30})
    strategy.initialize()
    
    start_time = time.perf_counter()
    
    for _, row in data.iterrows():
        bar = BarData(
            timestamp=row["timestamp"],
            symbol=row["symbol"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        strategy.on_bar(bar)
    
    end_time = time.perf_counter()
    
    elapsed = end_time - start_time
    signals_per_second = len(data) / elapsed
    
    print(f"\n  Strategy Signal Generation:")
    print(f"    Bars processed: {len(data)}")
    print(f"    Elapsed time: {elapsed:.4f}s")
    print(f"    Signals/second: {signals_per_second:,.0f}")
    print(f"    Total signals: {len(strategy.get_signals())}")
    
    return elapsed


def benchmark_vectorized_backtest(data: pd.DataFrame) -> float:
    """Benchmark vectorized backtest performance."""
    import sys
    sys.path.insert(0, '/Users/zxcv/.openclaw/workspace/quantforge-modules/modules/qf-backtest/src')
    from qf_backtest import BacktestEngine
    
    start_time = time.perf_counter()
    
    # Vectorized SMA calculation
    fast_period = 10
    slow_period = 30
    
    close_prices = data["close"].values
    
    # Calculate SMAs using convolution (vectorized)
    fast_sma = np.convolve(close_prices, np.ones(fast_period)/fast_period, mode='valid')
    slow_sma = np.convolve(close_prices, np.ones(slow_period)/slow_period, mode='valid')
    
    # Align arrays
    offset = slow_period - fast_period
    fast_sma_aligned = fast_sma[offset:]
    
    # Generate signals vectorized
    golden_cross = (fast_sma_aligned[:-1] <= slow_sma[:-1]) & (fast_sma_aligned[1:] > slow_sma[1:])
    death_cross = (fast_sma_aligned[:-1] >= slow_sma[:-1]) & (fast_sma_aligned[1:] < slow_sma[1:])
    
    end_time = time.perf_counter()
    
    elapsed = end_time - start_time
    
    print(f"\n  Vectorized Backtest (NumPy):")
    print(f"    Bars processed: {len(data)}")
    print(f"    Elapsed time: {elapsed:.4f}s")
    print(f"    Operations/second: {len(data) / elapsed:,.0f}")
    print(f"    Golden crosses: {np.sum(golden_cross)}")
    print(f"    Death crosses: {np.sum(death_cross)}")
    
    return elapsed


def run_benchmarks():
    """Run all benchmarks."""
    print("=" * 60)
    print("QuantForge Performance Benchmark")
    print("=" * 60)
    
    # Generate test data
    print("\nGenerating test data...")
    data = generate_test_data(n_bars=50000, n_symbols=1)
    print(f"  Total bars: {len(data)}")
    print(f"  Date range: {data['timestamp'].iloc[0]} to {data['timestamp'].iloc[-1]}")
    
    # Run benchmarks
    print("\n" + "-" * 60)
    print("Running benchmarks...")
    print("-" * 60)
    
    backtest_time = benchmark_backtest_engine(data)
    signal_time = benchmark_strategy_signal_generation(data)
    vectorized_time = benchmark_vectorized_backtest(data)
    
    # Summary
    print("\n" + "=" * 60)
    print("Benchmark Summary")
    print("=" * 60)
    print(f"\nBacktest Engine:      {backtest_time:.4f}s")
    print(f"Signal Generation:    {signal_time:.4f}s")
    print(f"Vectorized (NumPy):   {vectorized_time:.4f}s")
    
    if vectorized_time > 0:
        speedup = backtest_time / vectorized_time
        print(f"\nVectorized speedup:   {speedup:.1f}x")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    run_benchmarks()
