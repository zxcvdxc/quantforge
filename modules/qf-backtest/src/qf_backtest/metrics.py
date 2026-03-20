"""Performance metrics calculation for backtesting results."""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import math

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for a backtest."""
    
    # Return metrics
    total_return: float = 0.0  # Total return as decimal
    annualized_return: float = 0.0  # Annualized return as decimal
    
    # Risk metrics
    volatility: float = 0.0  # Annualized volatility
    max_drawdown: float = 0.0  # Maximum drawdown as decimal
    max_drawdown_duration: int = 0  # Max drawdown in days/bars
    
    # Risk-adjusted returns
    sharpe_ratio: float = 0.0  # Sharpe ratio (assuming risk-free rate = 0)
    sortino_ratio: float = 0.0  # Sortino ratio
    calmar_ratio: float = 0.0  # Calmar ratio
    
    # Trade metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0  # Win rate as decimal
    avg_win: float = 0.0  # Average winning trade return
    avg_loss: float = 0.0  # Average losing trade return
    profit_factor: float = 0.0  # Gross profit / Gross loss
    
    # Additional metrics
    avg_trade_return: float = 0.0
    avg_holding_period: float = 0.0
    final_equity: float = 0.0
    initial_capital: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert metrics to dictionary."""
        return {
            "total_return": self.total_return,
            "annualized_return": self.annualized_return,
            "volatility": self.volatility,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_duration": self.max_drawdown_duration,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "profit_factor": self.profit_factor,
            "avg_trade_return": self.avg_trade_return,
            "avg_holding_period": self.avg_holding_period,
            "final_equity": self.final_equity,
            "initial_capital": self.initial_capital,
        }


def calculate_metrics(
    equity_curve: pd.DataFrame,
    trades: Optional[pd.DataFrame] = None,
    initial_capital: Optional[float] = None,
    risk_free_rate: float = 0.0,
    periods_per_year: float = 252.0,
) -> PerformanceMetrics:
    """
    Calculate comprehensive performance metrics.
    
    Args:
        equity_curve: DataFrame with 'timestamp' and 'equity' columns
        trades: Optional DataFrame with trade history
        initial_capital: Initial capital (defaults to first equity value)
        risk_free_rate: Annual risk-free rate as decimal
        periods_per_year: Number of periods per year (252 for daily)
        
    Returns:
        PerformanceMetrics object
    """
    if equity_curve.empty:
        return PerformanceMetrics()
        
    # Get equity values
    equity = equity_curve["equity"].values
    
    if initial_capital is None:
        initial_capital = equity[0]
        
    final_equity = equity[-1]
    
    # Calculate returns
    total_return = (final_equity - initial_capital) / initial_capital
    
    # Daily returns
    returns = np.diff(equity) / equity[:-1]
    
    if len(returns) == 0:
        return PerformanceMetrics(
            total_return=total_return,
            final_equity=final_equity,
            initial_capital=initial_capital,
        )
    
    # Annualized return
    n_periods = len(equity)
    annualized_return = (final_equity / initial_capital) ** (
        periods_per_year / n_periods
    ) - 1
    
    # Volatility (annualized)
    volatility = np.std(returns) * math.sqrt(periods_per_year)
    
    # Maximum drawdown
    max_dd, max_dd_duration = calculate_max_drawdown(equity)
    
    # Sharpe ratio
    excess_returns = returns - risk_free_rate / periods_per_year
    if np.std(returns) > 0:
        sharpe_ratio = (
            np.mean(excess_returns) / np.std(returns)
        ) * math.sqrt(periods_per_year)
    else:
        sharpe_ratio = 0.0
        
    # Sortino ratio (downside deviation)
    downside_returns = returns[returns < 0]
    if len(downside_returns) > 0 and np.std(downside_returns) > 0:
        sortino_ratio = (
            np.mean(excess_returns) / np.std(downside_returns)
        ) * math.sqrt(periods_per_year)
    else:
        sortino_ratio = 0.0
        
    # Calmar ratio
    if max_dd < 0 and max_dd > -1:
        calmar_ratio = annualized_return / abs(max_dd)
    else:
        calmar_ratio = 0.0
        
    # Calculate trade metrics if trades provided
    trade_metrics = _calculate_trade_metrics(trades) if trades is not None else {}
    
    return PerformanceMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        volatility=volatility,
        max_drawdown=max_dd,
        max_drawdown_duration=max_dd_duration,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        final_equity=final_equity,
        initial_capital=initial_capital,
        **trade_metrics,
    )


def calculate_max_drawdown(equity: np.ndarray) -> Tuple[float, int]:
    """
    Calculate maximum drawdown and its duration.
    
    Args:
        equity: Array of equity values
        
    Returns:
        (max_drawdown, max_duration) as (decimal, periods)
    """
    if len(equity) == 0:
        return 0.0, 0
        
    # Running maximum
    running_max = np.maximum.accumulate(equity)
    
    # Drawdown at each point
    drawdowns = (equity - running_max) / running_max
    
    # Maximum drawdown
    max_drawdown = np.min(drawdowns)
    
    # Find drawdown durations
    in_drawdown = drawdowns < 0
    max_duration = 0
    current_duration = 0
    
    for is_dd in in_drawdown:
        if is_dd:
            current_duration += 1
            max_duration = max(max_duration, current_duration)
        else:
            current_duration = 0
            
    return max_drawdown, max_duration


def _calculate_trade_metrics(trades: pd.DataFrame) -> dict:
    """Calculate metrics from trade history."""
    if trades.empty:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "avg_trade_return": 0.0,
        }
        
    total_trades = len(trades)
    
    # Calculate PnL for each trade
    # For simplicity, assume each trade entry has a corresponding exit
    # In practice, you'd match entries and exits
    
    # Calculate returns from trade prices
    if "price" in trades.columns and "quantity" in trades.columns:
        trade_values = trades["price"] * trades["quantity"]
        
        # Group by symbol and side to calculate net position changes
        # This is a simplified calculation
        gross_profit = 0.0
        gross_loss = 0.0
        winning_count = 0
        losing_count = 0
        
        # Simple heuristic: if we have both buy and sell for same symbol
        symbols = trades["symbol"].unique()
        
        for symbol in symbols:
            sym_trades = trades[trades["symbol"] == symbol]
            
            # Calculate weighted average prices
            buys = sym_trades[sym_trades["side"] == "buy"]
            sells = sym_trades[sym_trades["side"] == "sell"]
            
            if len(buys) > 0 and len(sells) > 0:
                avg_buy = (buys["price"] * buys["quantity"]).sum() / buys["quantity"].sum()
                avg_sell = (sells["price"] * sells["quantity"]).sum() / sells["quantity"].sum()
                
                # Assume we close positions
                matched_qty = min(buys["quantity"].sum(), sells["quantity"].sum())
                pnl = (avg_sell - avg_buy) * matched_qty
                
                if pnl > 0:
                    gross_profit += pnl
                    winning_count += 1
                else:
                    gross_loss += abs(pnl)
                    losing_count += 1
        
        win_rate = winning_count / total_trades if total_trades > 0 else 0.0
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else float("inf")
        )
        
        return {
            "total_trades": total_trades,
            "winning_trades": winning_count,
            "losing_trades": losing_count,
            "win_rate": win_rate,
            "avg_win": gross_profit / winning_count if winning_count > 0 else 0.0,
            "avg_loss": -gross_loss / losing_count if losing_count > 0 else 0.0,
            "profit_factor": profit_factor,
            "avg_trade_return": (gross_profit - gross_loss) / total_trades if total_trades > 0 else 0.0,
        }
    
    return {
        "total_trades": total_trades,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "profit_factor": 0.0,
        "avg_trade_return": 0.0,
    }


def calculate_cagr(
    start_value: float,
    end_value: float,
    years: float,
) -> float:
    """
    Calculate Compound Annual Growth Rate.
    
    Args:
        start_value: Starting value
        end_value: Ending value
        years: Number of years
        
    Returns:
        CAGR as decimal
    """
    if start_value <= 0 or years <= 0:
        return 0.0
    return (end_value / start_value) ** (1 / years) - 1


def calculate_var(
    returns: np.ndarray,
    confidence: float = 0.95,
) -> float:
    """
    Calculate Value at Risk.
    
    Args:
        returns: Array of returns
        confidence: Confidence level (e.g., 0.95 for 95%)
        
    Returns:
        VaR as decimal
    """
    if len(returns) == 0:
        return 0.0
    return np.percentile(returns, (1 - confidence) * 100)


def calculate_cvar(
    returns: np.ndarray,
    confidence: float = 0.95,
) -> float:
    """
    Calculate Conditional Value at Risk (Expected Shortfall).
    
    Args:
        returns: Array of returns
        confidence: Confidence level
        
    Returns:
        CVaR as decimal
    """
    if len(returns) == 0:
        return 0.0
    var = calculate_var(returns, confidence)
    return np.mean(returns[returns <= var])
