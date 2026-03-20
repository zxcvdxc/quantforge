"""Optimized event-driven backtesting engine.

This module provides a high-performance event-driven backtesting engine
with vectorized operations, memory pre-allocation, and signal caching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, TypeVar, Union, NamedTuple
import copy
import numpy as np
import pandas as pd
from collections import deque


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


@dataclass(slots=True)
class MarketDataEvent:
    """Market data event representing a price update.

    Attributes:
        timestamp: Event timestamp
        symbol: Trading symbol
        open: Opening price
        high: High price
        low: Low price
        close: Closing price
        volume: Trading volume
    """
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

    @property
    def typical_price(self) -> float:
        """Calculate typical price (H+L+C)/3."""
        return (self.high + self.low + self.close) / 3.0

    @property
    def price_range(self) -> float:
        """Calculate price range (high - low)."""
        return self.high - self.low


@dataclass(slots=True)
class Order:
    """Trading order.

    Attributes:
        id: Unique order identifier
        timestamp: Order creation timestamp
        symbol: Trading symbol
        side: Buy or sell
        quantity: Order quantity
        order_type: Market, limit, or stop order
        limit_price: Limit price for limit orders
        stop_price: Stop price for stop orders
        status: Current order status
        filled_quantity: Amount already filled
        filled_price: Average fill price
        commission: Total commission paid
        slippage: Total slippage cost
    """
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


@dataclass(slots=True)
class Position:
    """Trading position for a symbol.

    Attributes:
        symbol: Trading symbol
        quantity: Position size (positive=long, negative=short)
        avg_price: Average entry price
    """
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
        return abs(self.quantity) < 1e-10

    @property
    def market_value(self) -> float:
        """Get position market value (approximate)."""
        return self.quantity * self.avg_price

    def market_value_at(self, current_price: float) -> float:
        """Calculate market value at given price."""
        return self.quantity * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L."""
        return self.quantity * (current_price - self.avg_price)

    def update(self, filled_quantity: float, filled_price: float) -> None:
        """Update position with a fill.

        Args:
            filled_quantity: Amount filled (positive=buy, negative=sell)
            filled_price: Fill price
        """
        if self.is_flat:
            self.quantity = filled_quantity
            self.avg_price = filled_price
        elif (self.quantity > 0 and filled_quantity > 0) or (self.quantity < 0 and filled_quantity < 0):
            # Adding to position
            total_value = self.quantity * self.avg_price + filled_quantity * filled_price
            self.quantity += filled_quantity
            self.avg_price = total_value / self.quantity if self.quantity != 0 else 0.0
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


@dataclass(slots=True)
class Account:
    """Trading account state.

    Attributes:
        initial_capital: Starting capital
        cash: Current cash balance
        positions: Dictionary of positions by symbol
    """
    initial_capital: float = 100000.0
    cash: float = 100000.0
    positions: Dict[str, Position] = field(default_factory=dict)

    def total_value(self, prices: Optional[Dict[str, float]] = None) -> float:
        """Calculate total account value including positions.

        Args:
            prices: Current market prices (uses avg_price if None)

        Returns:
            Total account value
        """
        if prices is None:
            return self.cash + sum(
                pos.market_value
                for pos in self.positions.values()
            )
        position_value = sum(
            pos.quantity * prices.get(sym, 0.0)
            for sym, pos in self.positions.items()
        )
        return self.cash + position_value

    def get_position(self, symbol: str) -> Position:
        """Get or create position for symbol."""
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def buying_power(self, prices: Optional[Dict[str, float]] = None) -> float:
        """Calculate available buying power."""
        return self.cash


@dataclass(slots=True)
class FillEvent:
    """Order fill event.

    Attributes:
        timestamp: Fill timestamp
        order: Original order
        filled_quantity: Amount filled
        filled_price: Fill price
        commission: Commission paid
        slippage: Slippage cost
    """
    timestamp: datetime
    order: Order
    filled_quantity: float
    filled_price: float
    commission: float
    slippage: float


class EventHandler(Protocol):
    """Protocol for event handlers."""
    def __call__(self, event: Any, engine: "BacktestEngine") -> None: ...


# Type alias for strategy functions (forward reference)
StrategyCallable = Callable[["BacktestEngine", MarketDataEvent], None]


class SignalCache:
    """Cache for pre-computed strategy signals.

    Optimizes strategy execution by caching signal calculations
    when the same parameters are used repeatedly.
    """

    def __init__(self, max_size: int = 10000):
        """Initialize signal cache.

        Args:
            max_size: Maximum number of cached signals
        """
        self._cache: Dict[str, Any] = {}
        self._max_size = max_size
        self._access_count: Dict[str, int] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get cached signal."""
        if key in self._cache:
            self._access_count[key] = self._access_count.get(key, 0) + 1
            return self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        """Cache a signal."""
        if len(self._cache) >= self._max_size:
            # Remove least used entry
            if self._cache:
                min_key = min(self._access_count, key=self._access_count.get)
                del self._cache[min_key]
                del self._access_count[min_key]

        self._cache[key] = value
        self._access_count[key] = 1

    def clear(self) -> None:
        """Clear all cached signals."""
        self._cache.clear()
        self._access_count.clear()


class BacktestEngine:
    """Optimized event-driven backtesting engine.

    Features:
    - Vectorized operations for bulk calculations
    - Memory pre-allocation for equity curves
    - Signal caching for repeated calculations
    - Efficient event loop processing

    Attributes:
        initial_capital: Starting capital
        account: Trading account state
        slippage_model: Slippage model for order execution
        commission_model: Commission model for fee calculation
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        slippage_model: Any = None,
        commission_model: Any = None,
        enable_caching: bool = True,
        equity_buffer_size: int = 10000,
    ):
        """Initialize backtest engine.

        Args:
            initial_capital: Starting capital
            slippage_model: Slippage model for order execution
            commission_model: Commission model for fee calculation
            enable_caching: Enable signal caching
            equity_buffer_size: Pre-allocated equity curve buffer size
        """
        self.initial_capital = initial_capital
        self.account = Account(initial_capital=initial_capital, cash=initial_capital)
        self.slippage_model = slippage_model
        self.commission_model = commission_model
        self.enable_caching = enable_caching

        # Event handlers
        self._market_data_handlers: List[EventHandler] = []
        self._order_handlers: List[EventHandler] = []
        self._fill_handlers: List[EventHandler] = []

        # Order management
        self._orders: Dict[str, Order] = {}
        self._order_counter = 0

        # History tracking with pre-allocation
        self._equity_buffer_size = equity_buffer_size
        self._equity_curve: List[Dict[str, Any]] = []
        self._equity_timestamps: List[datetime] = []
        self._equity_values: List[float] = []
        self._trades: List[FillEvent] = []

        # Current market data cache
        self._current_data: Dict[str, MarketDataEvent] = {}
        self._current_prices: Dict[str, float] = {}

        # Strategy reference
        self._strategy: Optional[StrategyCallable] = None

        # Signal cache
        self._signal_cache = SignalCache() if enable_caching else None

        # Pre-allocate equity arrays for vectorized operations
        self._equity_array = np.zeros(equity_buffer_size)
        self._cash_array = np.zeros(equity_buffer_size)
        self._equity_index = 0

    def reset(self) -> None:
        """Reset engine to initial state."""
        self.account = Account(
            initial_capital=self.initial_capital,
            cash=self.initial_capital
        )
        self._orders.clear()
        self._order_counter = 0
        self._equity_curve.clear()
        self._equity_timestamps.clear()
        self._equity_values.clear()
        self._trades.clear()
        self._current_data.clear()
        self._current_prices.clear()
        self._equity_index = 0

        if self._signal_cache:
            self._signal_cache.clear()

    def register_strategy(self, strategy: StrategyCallable) -> None:
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
        """Submit a new order.

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
            return next(iter(self._current_data.values())).timestamp
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
        if order.symbol not in self._current_data:
            return

        data = self._current_data[order.symbol]

        if order.limit_price is None:
            return

        # Check if limit price is hit
        can_fill = False
        fill_price = 0.0

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
        fill_qty = fill.filled_quantity if order.side == OrderSide.BUY else -fill.filled_quantity
        position.update(fill_qty, fill.filled_price)

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
        """Process incoming market data.

        This is the core event processing method. Optimized for speed
        by minimizing attribute lookups and using local references.
        """
        # Cache market data
        self._current_data[data.symbol] = data
        self._current_prices[data.symbol] = data.close

        # Notify handlers
        handlers = self._market_data_handlers
        for handler in handlers:
            handler(data, self)

        # Run strategy if registered
        strategy = self._strategy
        if strategy:
            strategy(self, data)

        # Record equity
        self._record_equity(data.timestamp)

    def _record_equity(self, timestamp: datetime) -> None:
        """Record current equity state with memory pre-allocation."""
        prices = self._current_prices
        equity = self.account.total_value(prices)

        # Use pre-allocated arrays when possible
        idx = self._equity_index
        if idx < self._equity_buffer_size:
            self._equity_array[idx] = equity
            self._cash_array[idx] = self.account.cash

        # Also store in list for flexibility
        self._equity_timestamps.append(timestamp)
        self._equity_values.append(equity)

        self._equity_index += 1

    def run(
        self,
        data: pd.DataFrame,
        strategy: Optional[StrategyCallable] = None,
    ) -> pd.DataFrame:
        """Run backtest with provided data.

        Optimized for speed by:
        - Using vectorized operations where possible
        - Minimizing DataFrame operations
        - Pre-allocating memory

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

        # Pre-allocate arrays based on data size
        n_rows = len(data)
        if n_rows > self._equity_buffer_size:
            self._equity_array = np.zeros(n_rows + 1000)
            self._cash_array = np.zeros(n_rows + 1000)
            self._equity_buffer_size = n_rows + 1000

        # Local references for speed
        on_market_data = self.on_market_data
        MarketDataEventClass = MarketDataEvent

        # Process each bar
        for _, row in data.iterrows():
            event = MarketDataEventClass(
                timestamp=row["timestamp"],
                symbol=row["symbol"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            on_market_data(event)

        return self.get_equity_curve()

    def run_vectorized(
        self,
        data: pd.DataFrame,
        signals: pd.Series,
        position_size: float = 1.0,
    ) -> pd.DataFrame:
        """Run vectorized backtest with pre-computed signals.

        Much faster than event-driven mode for simple strategies.

        Args:
            data: DataFrame with OHLCV data
            signals: Series of signals (1=long, -1=short, 0=flat)
            position_size: Position size per trade

        Returns:
            DataFrame with equity curve
        """
        self.reset()

        close_prices = data["close"].values
        timestamps = data["timestamp"].values

        # Calculate position changes
        position_changes = np.diff(signals.values, prepend=0)

        # Vectorized P&L calculation
        position = np.zeros(len(signals))
        position[0] = signals.iloc[0] * position_size

        for i in range(1, len(signals)):
            if position_changes[i] != 0:
                position[i] = signals.iloc[i] * position_size
            else:
                position[i] = position[i-1]

        # Calculate returns
        price_changes = np.diff(close_prices, prepend=close_prices[0])
        pnl = position[:-1] * price_changes[1:]

        # Cumulative equity
        equity = self.initial_capital + np.cumsum(np.insert(pnl, 0, 0))

        # Create equity curve
        equity_df = pd.DataFrame({
            "timestamp": timestamps,
            "equity": equity,
            "cash": self.initial_capital - np.cumsum(np.abs(np.diff(position, prepend=0)) * close_prices * 0.001),
        })

        return equity_df

    def get_equity_curve(self) -> pd.DataFrame:
        """Get equity curve as DataFrame."""
        if not self._equity_values:
            return pd.DataFrame()

        return pd.DataFrame({
            "timestamp": self._equity_timestamps,
            "equity": self._equity_values,
            "cash": [self.initial_capital] * len(self._equity_values),  # Simplified cash tracking
        })

    def get_equity_array(self) -> np.ndarray:
        """Get equity values as NumPy array (for vectorized analysis)."""
        return self._equity_array[:self._equity_index]

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

    def get_position_summary(self) -> pd.DataFrame:
        """Get summary of all positions."""
        if not self.account.positions:
            return pd.DataFrame()

        records = []
        for symbol, pos in self.account.positions.items():
            current_price = self._current_prices.get(symbol, pos.avg_price)
            records.append({
                "symbol": symbol,
                "quantity": pos.quantity,
                "avg_price": pos.avg_price,
                "current_price": current_price,
                "market_value": pos.market_value_at(current_price),
                "unrealized_pnl": pos.unrealized_pnl(current_price),
            })
        return pd.DataFrame(records)

    @property
    def current_equity(self) -> float:
        """Get current account equity."""
        return self.account.total_value(self._current_prices)

    @property
    def current_cash(self) -> float:
        """Get current cash balance."""
        return self.account.cash

    def get_position_quantity(self, symbol: str) -> float:
        """Get current position quantity for symbol."""
        pos = self.account.positions.get(symbol)
        return pos.quantity if pos else 0.0

    def get_cached_signal(self, key: str) -> Optional[Any]:
        """Get cached signal if caching is enabled."""
        if self._signal_cache:
            return self._signal_cache.get(key)
        return None

    def cache_signal(self, key: str, value: Any) -> None:
        """Cache a signal if caching is enabled."""
        if self._signal_cache:
            self._signal_cache.set(key, value)
