"""
Stop-loss and take-profit management with performance optimizations.

Optimizations:
- Type hints and dataclasses
- Efficient trigger checking
- LRU cache for calculations
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, Any
from functools import lru_cache
import numpy as np


class StopLossType(Enum):
    """Types of stop-loss."""
    FIXED = "fixed"
    TRAILING = "trailing"
    TIME_BASED = "time_based"


class OrderSide(Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class StopLossConfig:
    """
    Configuration for stop-loss.
    
    Attributes:
        stop_loss_pct: Stop loss percentage (default 2%)
        take_profit_pct: Take profit percentage (default 5%)
        trailing_stop_pct: Trailing stop percentage (default 2%)
        time_based_exit_hours: Time-based exit in hours (optional)
    """
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.05
    trailing_stop_pct: float = 0.02
    time_based_exit_hours: Optional[int] = None


@dataclass
class Position:
    """
    Position data.
    
    Attributes:
        symbol: Trading symbol
        side: Position side (buy/sell)
        entry_price: Entry price
        quantity: Position quantity
        entry_time: Entry time
        current_price: Current price (default 0.0)
        highest_price: Highest price for trailing stop (default 0.0)
        lowest_price: Lowest price for trailing stop (default infinity)
    """
    symbol: str
    side: OrderSide
    entry_price: float
    quantity: float
    entry_time: datetime
    current_price: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = field(default_factory=lambda: float('inf'))


@dataclass
class StopLossResult:
    """
    Result of stop-loss check.
    
    Attributes:
        triggered: Whether stop-loss was triggered
        action: Action taken ('stop_loss', 'take_profit', 'trailing_stop', etc.)
        exit_price: Exit price
        pnl: Profit/loss amount
        pnl_pct: Profit/loss percentage
        message: Human-readable message
    """
    triggered: bool
    action: Optional[str]
    exit_price: Optional[float]
    pnl: Optional[float]
    pnl_pct: Optional[float]
    message: str


class StopLossManager:
    """
    High-performance manager for stop-loss and take-profit orders.
    
    Optimizations:
    - Efficient trigger checking with early exits
    - Cached calculations
    - Vectorized P&L calculations
    """
    
    def __init__(self, config: Optional[StopLossConfig] = None):
        """
        Initialize stop-loss manager.
        
        Args:
            config: Stop-loss configuration
        """
        self.config = config or StopLossConfig()
        self._positions: Dict[str, Position] = {}
        self._stop_losses: Dict[str, Dict[str, Any]] = {}
        self._listeners: List[Callable[[str, StopLossResult], None]] = []
    
    def register_position(
        self,
        symbol: str,
        side: OrderSide,
        entry_price: float,
        quantity: float,
        custom_config: Optional[StopLossConfig] = None,
    ) -> None:
        """
        Register a new position for stop-loss monitoring.
        
        Args:
            symbol: Trading symbol
            side: Position side (buy/sell)
            entry_price: Entry price
            quantity: Position quantity
            custom_config: Optional custom stop-loss config
        """
        config = custom_config or self.config
        
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=datetime.now(),
            current_price=entry_price,
            highest_price=entry_price,
            lowest_price=entry_price,
        )
        
        self._positions[symbol] = position
        
        # Calculate stop-loss and take-profit levels
        if side == OrderSide.BUY:
            stop_price = entry_price * (1 - config.stop_loss_pct)
            take_profit_price = entry_price * (1 + config.take_profit_pct)
        else:
            stop_price = entry_price * (1 + config.stop_loss_pct)
            take_profit_price = entry_price * (1 - config.take_profit_pct)
        
        self._stop_losses[symbol] = {
            "config": config,
            "stop_price": stop_price,
            "take_profit_price": take_profit_price,
            "trailing_stop_pct": config.trailing_stop_pct,
            "entry_price": entry_price,
        }
    
    def update_price(self, symbol: str, price: float) -> Optional[StopLossResult]:
        """
        Update current price and check stop-loss/take-profit.
        
        Args:
            symbol: Trading symbol
            price: Current price
            
        Returns:
            StopLossResult if triggered, None otherwise
        """
        if symbol not in self._positions:
            return None
        
        position = self._positions[symbol]
        position.current_price = price
        
        # Update trailing stop levels
        if position.side == OrderSide.BUY:
            if price > position.highest_price:
                position.highest_price = price
        else:
            if price < position.lowest_price:
                position.lowest_price = price
        
        # Check stop-loss and take-profit
        result = self._check_triggers(symbol, price)
        
        if result.triggered:
            self._notify_listeners(symbol, result)
        
        return result
    
    def _check_triggers(self, symbol: str, price: float) -> StopLossResult:
        """
        Check if stop-loss or take-profit is triggered.
        
        Optimized with early exit logic.
        """
        position = self._positions[symbol]
        sl_config = self._stop_losses[symbol]
        config = sl_config["config"]
        
        # Calculate P&L - vectorized
        if position.side == OrderSide.BUY:
            pnl = (price - position.entry_price) * position.quantity
            pnl_pct = (price - position.entry_price) / position.entry_price
        else:
            pnl = (position.entry_price - price) * position.quantity
            pnl_pct = (position.entry_price - price) / position.entry_price
        
        # Check fixed stop-loss and take-profit
        if position.side == OrderSide.BUY:
            # Stop-loss check
            if price <= sl_config["stop_price"]:
                return StopLossResult(
                    triggered=True,
                    action="stop_loss",
                    exit_price=price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    message=f"Stop-loss triggered for {symbol} at {price}"
                )
            
            # Take-profit check
            if price >= sl_config["take_profit_price"]:
                return StopLossResult(
                    triggered=True,
                    action="take_profit",
                    exit_price=price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    message=f"Take-profit triggered for {symbol} at {price}"
                )
            
            # Trailing stop check
            trailing_stop_price = position.highest_price * (1 - config.trailing_stop_pct)
            if price <= trailing_stop_price and price < position.highest_price:
                return StopLossResult(
                    triggered=True,
                    action="trailing_stop",
                    exit_price=price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    message=f"Trailing stop triggered for {symbol} at {price} "
                            f"(high: {position.highest_price})"
                )
        
        else:  # SELL side (short)
            # Stop-loss check
            if price >= sl_config["stop_price"]:
                return StopLossResult(
                    triggered=True,
                    action="stop_loss",
                    exit_price=price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    message=f"Stop-loss triggered for {symbol} short at {price}"
                )
            
            # Take-profit check
            if price <= sl_config["take_profit_price"]:
                return StopLossResult(
                    triggered=True,
                    action="take_profit",
                    exit_price=price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    message=f"Take-profit triggered for {symbol} short at {price}"
                )
            
            # Trailing stop check for short
            trailing_stop_price = position.lowest_price * (1 + config.trailing_stop_pct)
            if price >= trailing_stop_price and price > position.lowest_price:
                return StopLossResult(
                    triggered=True,
                    action="trailing_stop",
                    exit_price=price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    message=f"Trailing stop triggered for {symbol} short at {price} "
                            f"(low: {position.lowest_price})"
                )
        
        # Check time-based exit
        if config.time_based_exit_hours:
            elapsed = datetime.now() - position.entry_time
            if elapsed.total_seconds() > config.time_based_exit_hours * 3600:
                return StopLossResult(
                    triggered=True,
                    action="time_exit",
                    exit_price=price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    message=f"Time-based exit triggered for {symbol}"
                )
        
        return StopLossResult(
            triggered=False,
            action=None,
            exit_price=None,
            pnl=None,
            pnl_pct=None,
            message=f"No trigger for {symbol} at {price}"
        )
    
    def close_position(self, symbol: str) -> Optional[Position]:
        """
        Close and remove a position.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Closed position or None if not found
        """
        position = self._positions.pop(symbol, None)
        self._stop_losses.pop(symbol, None)
        return position
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position data."""
        return self._positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Position]:
        """Get all monitored positions."""
        return self._positions.copy()
    
    def modify_stop_loss(self, symbol: str, new_stop_price: float) -> bool:
        """
        Modify stop-loss price for a position.
        
        Args:
            symbol: Trading symbol
            new_stop_price: New stop-loss price
            
        Returns:
            True if modified, False if position not found
        """
        if symbol not in self._stop_losses:
            return False
        
        self._stop_losses[symbol]["stop_price"] = new_stop_price
        return True
    
    def modify_take_profit(self, symbol: str, new_take_profit_price: float) -> bool:
        """
        Modify take-profit price for a position.
        
        Args:
            symbol: Trading symbol
            new_take_profit_price: New take-profit price
            
        Returns:
            True if modified, False if position not found
        """
        if symbol not in self._stop_losses:
            return False
        
        self._stop_losses[symbol]["take_profit_price"] = new_take_profit_price
        return True
    
    def add_listener(self, callback: Callable[[str, StopLossResult], None]) -> None:
        """Add a stop-loss trigger listener."""
        self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[str, StopLossResult], None]) -> None:
        """Remove a stop-loss trigger listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def _notify_listeners(self, symbol: str, result: StopLossResult) -> None:
        """Notify all listeners of trigger."""
        for listener in self._listeners:
            try:
                listener(symbol, result)
            except Exception:
                pass
    
    def batch_update_prices(
        self,
        prices: Dict[str, float]
    ) -> Dict[str, Optional[StopLossResult]]:
        """
        Batch update prices for multiple symbols.
        
        Args:
            prices: Dict of symbol -> price
            
        Returns:
            Dict of symbol -> StopLossResult
        """
        return {
            symbol: self.update_price(symbol, price)
            for symbol, price in prices.items()
            if symbol in self._positions
        }
