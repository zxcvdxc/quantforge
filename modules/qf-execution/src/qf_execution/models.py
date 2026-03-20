"""
Order Models and Status Definitions
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class OrderStatus(Enum):
    """订单状态"""
    PENDING = auto()       # 待发送
    SUBMITTING = auto()    # 提交中
    SUBMITTED = auto()     # 已提交
    PARTIAL_FILLED = auto() # 部分成交
    FILLED = auto()        # 完全成交
    CANCELING = auto()     # 撤销中
    CANCELED = auto()      # 已撤销
    REJECTED = auto()      # 已拒绝
    EXPIRED = auto()       # 已过期


class OrderType(Enum):
    """订单类型"""
    MARKET = auto()        # 市价单
    LIMIT = auto()         # 限价单
    STOP = auto()          # 止损单
    STOP_LIMIT = auto()    # 止损限价单
    ICEBERG = auto()       # 冰山单
    TWAP = auto()          # TWAP订单


class Side(Enum):
    """买卖方向"""
    BUY = auto()
    SELL = auto()


class AccountType(Enum):
    """账户类型"""
    A_STOCK = auto()       # A股
    FUTURES = auto()       # 期货
    CRYPTO = auto()        # 数字货币


@dataclass
class Fill:
    """成交记录"""
    fill_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str = ""
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    filled_at: datetime = field(default_factory=datetime.utcnow)
    commission: Decimal = Decimal("0")
    venue: str = ""


@dataclass
class Order:
    """订单对象"""
    # 基本信息
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    side: Side = Side.BUY
    order_type: OrderType = OrderType.LIMIT
    
    # 价格数量
    price: Optional[Decimal] = None
    quantity: Decimal = Decimal("0")
    filled_quantity: Decimal = field(default=Decimal("0"), repr=False)
    remaining_quantity: Decimal = field(init=False)
    
    # 状态
    status: OrderStatus = field(default=OrderStatus.PENDING, repr=False)
    fills: List[Fill] = field(default_factory=list, repr=False)
    
    # 账户信息
    account_id: str = ""
    account_type: AccountType = AccountType.A_STOCK
    venue: str = ""  # 交易所/券商
    
    # 时间
    created_at: datetime = field(default_factory=datetime.utcnow, repr=False)
    updated_at: datetime = field(default_factory=datetime.utcnow, repr=False)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    
    # 订单参数
    params: Dict[str, Any] = field(default_factory=dict, repr=False)
    
    # 扩展字段
    client_order_id: Optional[str] = None
    parent_order_id: Optional[str] = None  # 父订单ID（用于拆单）
    
    def __post_init__(self) -> None:
        self.remaining_quantity = self.quantity - self.filled_quantity
    
    def update_status(self, status: OrderStatus) -> None:
        """更新订单状态"""
        self.status = status
        self.updated_at = datetime.utcnow()
    
    def add_fill(self, fill: Fill) -> None:
        """添加成交记录"""
        self.fills.append(fill)
        self.filled_quantity += fill.quantity
        self.remaining_quantity = self.quantity - self.filled_quantity
        
        if self.filled_quantity >= self.quantity:
            self.status = OrderStatus.FILLED
            self.filled_at = datetime.utcnow()
        elif self.filled_quantity > 0:
            self.status = OrderStatus.PARTIAL_FILLED
        
        self.updated_at = datetime.utcnow()
    
    def avg_fill_price(self) -> Optional[Decimal]:
        """计算平均成交价格"""
        if not self.fills or self.filled_quantity == 0:
            return None
        total_value = sum(f.price * f.quantity for f in self.fills)
        return total_value / self.filled_quantity
    
    def total_commission(self) -> Decimal:
        """计算总手续费"""
        return sum(f.commission for f in self.fills)
    
    def is_active(self) -> bool:
        """检查订单是否处于活动状态"""
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIAL_FILLED,
        )
    
    def is_complete(self) -> bool:
        """检查订单是否已完成（成交或取消）"""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )


@dataclass
class OrderResult:
    """订单操作结果"""
    success: bool
    order_id: Optional[str] = None
    message: str = ""
    error_code: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
