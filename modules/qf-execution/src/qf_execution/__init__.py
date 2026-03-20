"""
QuantForge Execution Module - Order Management and Smart Routing
"""

from .engine import ExecutionConfig, ExecutionEngine, OrderGateway
from .models import (
    AccountType,
    Fill,
    Order,
    OrderResult,
    OrderStatus,
    OrderType,
    Side,
)
from .order_manager import OrderManager, OrderManagerConfig
from .routing import (
    MarketDepth,
    PriceLevel,
    Route,
    RoutingConfig,
    RoutingError,
    SimplePriceFeed,
    SmartRouter,
    Venue,
    VenueStatus,
)
from .splitter import (
    EqualSplitter,
    IcebergOrder,
    OrderSlice,
    OrderSplitter,
    SplitConfig,
    TWAPOrder,
    VWAPOrder,
)

__version__ = "0.1.0"
__all__ = [
    # Engine
    "ExecutionEngine",
    "ExecutionConfig",
    "OrderGateway",
    # Models
    "Order",
    "Fill",
    "OrderStatus",
    "OrderType",
    "Side",
    "AccountType",
    "OrderResult",
    # Order Manager
    "OrderManager",
    "OrderManagerConfig",
    # Routing
    "SmartRouter",
    "Route",
    "Venue",
    "VenueStatus",
    "MarketDepth",
    "PriceLevel",
    "RoutingConfig",
    "RoutingError",
    "SimplePriceFeed",
    # Splitter
    "OrderSplitter",
    "OrderSlice",
    "IcebergOrder",
    "TWAPOrder",
    "VWAPOrder",
    "EqualSplitter",
    "SplitConfig",
]
