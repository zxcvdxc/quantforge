"""Event-driven backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Protocol, TypeVar, Union
import copy

import numpy as np
import pandas as pd


class EventType(Enum):
    """Types of events in the backtesting system."""
    MARKET_DATA = auto()
    ORDER_SUBMIT = auto()
    ORDER_FILL = auto()
    ORDER_CANCEL = auto()
    POSITION_UPDATE = auto()
    ACCOUNT_UPDATE = auto()


class OrderSide(Enum):
    """Order side - BUY or SELL."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(Enum):
    """Order execution status."""
    PENDING = auto()
    FILLED = auto()
    PARTIALLY_FILLED = auto()
    CANCELLED = auto()
    REJECTED = auto()


@dataclass
class MarketDataEvent:
    """Market data event representing a price update."""
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @property
    def price(self) -> float:
        """Get current price (closing price)."""
        return self.close


@dataclass 
class Order:
    """Trading order."""
    id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0


@dataclass
class Position:
    """Trading position for a symbol."""
    symbol: str
    quantity: float = 0.0
    avg_price: float = 0.0
    
    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0
    
    @property
    def is_flat(self) -> bool:
        """Check if position is flat."""
        return self.quantity == 0
    
    def market_value_at(self, current_price: float) -> float:
        """Calculate market value at given price."""
        return self.quantity * current_price
    
    def update(self, filled_quantity: float, filled_price: float) -> None:
        """Update position with a fill."""
        if self.is_flat:
            self.quantity = filled_quantity
            self.avg_price = filled_price
        elif (self.quantity > 0 and filled_quantity > 0) or (self.quantity < 0 and filled_quantity < 0):
            # Adding to position
            total_value = self.quantity * self.avg_price + filled_quantity * filled_price
            self.quantity += filled_quantity
            self.avg_price = total_value / self.quantity if self.quantity != 0 else 0
        else:
            # Reducing or reversing position
            remaining = self.quantity + filled_quantity
            if abs(remaining) < 1e-10:  # Position closed
                self.quantity = 0.0
                self.avg_price = 0.0
            elif (remaining > 0) != (self.quantity > 0):  # Reversed
                self.quantity = remaining
                self.avg_price = filled_price
            else:  # Reduced but same direction
                self.quantity = remaining
                # Average price unchanged when reducing


@dataclass
class Account:
    """Trading account state."""
    initial_capital: float = 100000.0
    cash: float = 100000.0
    positions: Dict[str, Position] = field(default_factory=dict)
    
    def total_value(self, prices: Dict[str, float] | None = None) -> float:
        """Calculate total account value including positions."""
        if prices is None:
            return self.cash + sum(
                pos.quantity * pos.avg_price  # Use avg price as estimate
                for pos in self.positions.values()
            )
        position_value = sum(
            pos.quantity * prices.get(sym, 0) 
            for sym, pos in self.positions.items()
        )
        return self.cash + position_value
    
    def get_position(self, symbol: str) -> Position:
        """Get or create position for symbol."""
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]


@dataclass
class FillEvent:
    """Order fill event."""
    timestamp: datetime
    order: Order
    filled_quantity: float
    filled_price: float
    commission: float
    slippage: float


class EventHandler(Protocol):
    """Protocol for event handlers."""
    def __call__(self, event: Any, engine: BacktestEngine) -> None: ...


class BacktestEngine:
    """
    Event-driven backtesting engine.
    
    Simulates realistic trading with slippage, commissions,
    and proper order execution semantics.
    """
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        slippage_model: Any = None,
        commission_model: Any = None,
    ):
        """
        Initialize backtest engine.
        
        Args:
            initial_capital: Starting capital
            slippage_model: Slippage model for order execution
            commission_model: Commission model for fee calculation
        """
        self.initial_capital = initial_capital
        self.account = Account(initial_capital=initial_capital, cash=initial_capital)
        self.slippage_model = slippage_model
        self.commission_model = commission_model
        
        # Event queues and handlers
        self._event_queue: List[Any] = []
        self._market_data_handlers: List[EventHandler] = []
        self._order_handlers: List[EventHandler] = []
        self._fill_handlers: List[EventHandler] = []
        
        # Order management
        self._orders: Dict[str, Order] = {}
        self._order_counter = 0
        
        # History tracking
        self._equity_curve: List[Dict[str, Any]] = []
        self._trades: List[FillEvent] = []
        
        # Current market data
        self._current_data: Dict[str, MarketDataEvent] = {}
        
        # Strategy reference
        self._strategy: Optional[Callable] = None
        
    def reset(self) -> None:
        """Reset engine to initial state."""
        self.account = Account(
            initial_capital=self.initial_capital,
            cash=self.initial_capital
        )
        self._event_queue.clear()
        self._orders.clear()
        self._order_counter = 0
        self._equity_curve.clear()
        self._trades.clear()
        self._current_data.clear()
        
    def register_strategy(self, strategy: Callable) -> None:
        """Register a trading strategy function."""
        self._strategy = strategy
        
    def add_market_data_handler(self, handler: EventHandler) -> None:
        """Add handler for market data events."""
        self._market_data_handlers.append(handler)
        
    def add_order_handler(self, handler: EventHandler) -> None:
        """Add handler for order events."""
        self._order_handlers.append(handler)
        
    def add_fill_handler(self, handler: EventHandler) -> None:
        """Add handler for fill events."""
        self._fill_handlers.append(handler)
        
    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        self._order_counter += 1
        return f"ORD_{self._order_counter:06d}"
        
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Optional[Order]:
        """
        Submit a new order.
        
        Args:
            symbol: Trading symbol
            side: Buy or sell
            quantity: Order quantity
            order_type: Market, limit, or stop order
            limit_price: Limit price for limit orders
            stop_price: Stop price for stop orders
            
        Returns:
            Order object or None if rejected
        """
        if quantity <= 0:
            return None
            
        order = Order(
            id=self._generate_order_id(),
            timestamp=self._get_current_timestamp(),
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
        )
        
        self._orders[order.id] = order
        
        # Process order immediately for market orders
        if order_type == OrderType.MARKET:
            self._execute_market_order(order)
        elif order_type == OrderType.LIMIT:
            self._process_limit_order(order)
            
        return order
    
    def _get_current_timestamp(self) -> datetime:
        """Get current timestamp from market data."""
        if self._current_data:
            return list(self._current_data.values())[0].timestamp
        return datetime.now()
        
    def _execute_market_order(self, order: Order) -> None:
        """Execute a market order."""
        if order.symbol not in self._current_data:
            order.status = OrderStatus.REJECTED
            return
            
        data = self._current_data[order.symbol]
        
        # Calculate fill price with slippage
        base_price = data.close
        slippage = 0.0
        if self.slippage_model:
            slippage = self.slippage_model.calculate_slippage(
                order, base_price, data
            )
        
        # Apply slippage
        if order.side == OrderSide.BUY:
            fill_price = base_price + slippage
        else:
            fill_price = base_price - slippage
            
        # Calculate commission
        commission = 0.0
        if self.commission_model:
            commission = self.commission_model.calculate_commission(
                order, fill_price
            )
            
        # Create fill event
        fill = FillEvent(
            timestamp=data.timestamp,
            order=order,
            filled_quantity=order.quantity,
            filled_price=fill_price,
            commission=commission,
            slippage=slippage,
        )
        
        # Update order
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.filled_price = fill_price
        order.commission = commission
        order.slippage = slippage
        
        # Process fill
        self._process_fill(fill)
        
    def _process_limit_order(self, order: Order) -> None:
        """Process a limit order."""
        # For simplicity, execute immediately if price is acceptable
        if order.symbol not in self._current_data:
            return
            
        data = self._current_data[order.symbol]
        
        if order.limit_price is None:
            return
            
        # Check if limit price is hit
        can_fill = False
        if order.side == OrderSide.BUY and data.low <= order.limit_price:
            can_fill = True
            fill_price = min(order.limit_price, data.close)
        elif order.side == OrderSide.SELL and data.high >= order.limit_price:
            can_fill = True
            fill_price = max(order.limit_price, data.close)
            
        if can_fill:
            slippage = 0.0
            if self.slippage_model:
                slippage = self.slippage_model.calculate_slippage(
                    order, fill_price, data
                )
                if order.side == OrderSide.BUY:
                    fill_price += slippage
                else:
                    fill_price -= slippage
                    
            commission = 0.0
            if self.commission_model:
                commission = self.commission_model.calculate_commission(
                    order, fill_price
                )
                
            fill = FillEvent(
                timestamp=data.timestamp,
                order=order,
                filled_quantity=order.quantity,
                filled_price=fill_price,
                commission=commission,
                slippage=slippage,
            )
            
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.filled_price = fill_price
            order.commission = commission
            order.slippage = slippage
            
            self._process_fill(fill)
    
    def _process_fill(self, fill: FillEvent) -> None:
        """Process an order fill."""
        order = fill.order
        symbol = order.symbol
        
        # Calculate trade value
        trade_value = fill.filled_quantity * fill.filled_price
        
        # Update cash
        if order.side == OrderSide.BUY:
            self.account.cash -= trade_value + fill.commission
        else:
            self.account.cash += trade_value - fill.commission
            
        # Update position
        position = self.account.get_position(symbol)
        if order.side == OrderSide.BUY:
            position.update(fill.filled_quantity, fill.filled_price)
        else:
            position.update(-fill.filled_quantity, fill.filled_price)
            
        # Record trade
        self._trades.append(fill)
        
        # Notify handlers
        for handler in self._fill_handlers:
            handler(fill, self)
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if order_id not in self._orders:
            return False
            
        order = self._orders[order_id]
        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.CANCELLED
            return True
        return False
        
    def cancel_all_orders(self) -> None:
        """Cancel all pending orders."""
        for order in self._orders.values():
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                
    def on_market_data(self, data: MarketDataEvent) -> None:
        """Process incoming market data."""
        self._current_data[data.symbol] = data
        
        # Notify handlers
        for handler in self._market_data_handlers:
            handler(data, self)
            
        # Run strategy if registered
        if self._strategy:
            self._strategy(self, data)
            
        # Record equity
        self._record_equity(data.timestamp)
        
    def _record_equity(self, timestamp: datetime) -> None:
        """Record current equity state."""
        prices = {sym: d.close for sym, d in self._current_data.items()}
        equity = self.account.total_value(prices)
        
        self._equity_curve.append({
            "timestamp": timestamp,
            "equity": equity,
            "cash": self.account.cash,
            "positions": {
                sym: {
                    "quantity": pos.quantity,
                    "avg_price": pos.avg_price,
                }
                for sym, pos in self.account.positions.items()
            },
        })
        
    def run(
        self,
        data: pd.DataFrame,
        strategy: Optional[Callable] = None,
    ) -> pd.DataFrame:
        """
        Run backtest with provided data.
        
        Args:
            data: DataFrame with columns [timestamp, symbol, open, high, low, close, volume]
            strategy: Optional strategy function to use
            
        Returns:
            DataFrame with equity curve
        """
        if strategy:
            self.register_strategy(strategy)
            
        self.reset()
        
        # Ensure data is sorted by timestamp
        data = data.sort_values("timestamp")
        
        # Process each bar
        for _, row in data.iterrows():
            event = MarketDataEvent(
                timestamp=row["timestamp"],
                symbol=row["symbol"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            self.on_market_data(event)
            
        return self.get_equity_curve()
    
    def get_equity_curve(self) -> pd.DataFrame:
        """Get equity curve as DataFrame."""
        if not self._equity_curve:
            return pd.DataFrame()
        return pd.DataFrame(self._equity_curve)
    
    def get_trades(self) -> pd.DataFrame:
        """Get trade history as DataFrame."""
        if not self._trades:
            return pd.DataFrame()
            
        records = []
        for fill in self._trades:
            records.append({
                "timestamp": fill.timestamp,
                "order_id": fill.order.id,
                "symbol": fill.order.symbol,
                "side": fill.order.side.value,
                "quantity": fill.filled_quantity,
                "price": fill.filled_price,
                "commission": fill.commission,
                "slippage": fill.slippage,
            })
        return pd.DataFrame(records)
    
    @property
    def current_equity(self) -> float:
        """Get current account equity."""
        prices = {sym: d.close for sym, d in self._current_data.items()}
        return self.account.total_value(prices)
        
    @property
    def current_cash(self) -> float:
        """Get current cash balance."""
        return self.account.cash
        
    def get_position_quantity(self, symbol: str) -> float:
        """Get current position quantity for symbol."""
        pos = self.account.positions.get(symbol)
        return pos.quantity if pos else 0.0
