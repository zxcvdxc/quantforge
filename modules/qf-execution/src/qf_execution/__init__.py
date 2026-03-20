"""
QuantForge Execution Module - Order Management and Smart Routing

高性能交易执行模块，提供订单管理、智能路由、订单拆分、批量处理等功能。
"""

from .batch_processor import (
    BatchConfig,
    BatchOrderProcessor,
    BatchResult,
    OrderRateLimiter,
    PriorityOrder,
)
from .connection_pool import (
    AsyncTaskPool,
    ConnectionConfig,
    ConnectionPool,
    ConnectionState,
    ConnectionStats,
    PooledConnection,
)
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

__version__ = "0.2.0"
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
    # Connection Pool
    "ConnectionPool",
    "ConnectionConfig",
    "PooledConnection",
    "ConnectionState",
    "ConnectionStats",
    "AsyncTaskPool",
    # Batch Processor
    "BatchOrderProcessor",
    "BatchConfig",
    "BatchResult",
    "PriorityOrder",
    "OrderRateLimiter",
]
