"""
Order Manager - 订单管理器
负责订单的发送、撤销、查询和状态管理
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set

from .models import (
    AccountType,
    Fill,
    Order,
    OrderResult,
    OrderStatus,
    OrderType,
    Side,
)

logger = logging.getLogger(__name__)


@dataclass
class OrderManagerConfig:
    """订单管理器配置"""
    max_pending_orders: int = 1000
    auto_cancel_on_error: bool = True
    default_timeout: float = 30.0
    enable_audit_log: bool = True


class OrderManager:
    """
    订单管理器
    
    功能：
    - 订单生命周期管理
    - 订单状态跟踪
    - 成交回报处理
    - 订单查询和筛选
    """
    
    def __init__(self, config: Optional[OrderManagerConfig] = None) -> None:
        self.config = config or OrderManagerConfig()
        self._orders: Dict[str, Order] = {}  # order_id -> Order
        self._orders_by_symbol: Dict[str, Set[str]] = defaultdict(set)
        self._orders_by_account: Dict[str, Set[str]] = defaultdict(set)
        self._orders_by_status: Dict[OrderStatus, Set[str]] = defaultdict(set)
        
        # 回调函数
        self._status_callbacks: List[Callable[[Order], None]] = []
        self._fill_callbacks: List[Callable[[Order, Fill], None]] = []
        
        # 统计
        self._stats = {
            "total_orders": 0,
            "filled_orders": 0,
            "canceled_orders": 0,
            "rejected_orders": 0,
        }
        
        self._lock = asyncio.Lock()
    
    # ============ 订单创建 ============
    
    def create_order(
        self,
        symbol: str,
        side: Side,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        account_id: str = "",
        account_type: AccountType = AccountType.A_STOCK,
        venue: str = "",
        **kwargs: Any,
    ) -> Order:
        """
        创建新订单
        
        Args:
            symbol: 交易代码
            side: 买卖方向
            order_type: 订单类型
            quantity: 数量
            price: 价格（市价单可为空）
            account_id: 账户ID
            account_type: 账户类型
            venue: 交易所/券商
            **kwargs: 其他参数
        
        Returns:
            Order: 创建的订单对象
        """
        order = Order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            account_id=account_id,
            account_type=account_type,
            venue=venue,
            params=kwargs,
        )
        return order
    
    async def register_order(self, order: Order) -> OrderResult:
        """
        注册订单到管理器
        
        Args:
            order: 订单对象
        
        Returns:
            OrderResult: 操作结果
        """
        async with self._lock:
            if len(self._orders) >= self.config.max_pending_orders:
                return OrderResult(
                    success=False,
                    message="Max pending orders limit reached",
                    error_code="ORDER_LIMIT_EXCEEDED",
                )
            
            self._orders[order.order_id] = order
            self._orders_by_symbol[order.symbol].add(order.order_id)
            self._orders_by_account[order.account_id].add(order.order_id)
            self._orders_by_status[order.status].add(order.order_id)
            self._stats["total_orders"] += 1
        
        logger.info(f"Order registered: {order.order_id} ({order.symbol})")
        return OrderResult(success=True, order_id=order.order_id)
    
    # ============ 订单状态管理 ============
    
    async def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        **kwargs: Any,
    ) -> OrderResult:
        """
        更新订单状态
        
        Args:
            order_id: 订单ID
            status: 新状态
            **kwargs: 额外信息
        
        Returns:
            OrderResult: 操作结果
        """
        async with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return OrderResult(
                    success=False,
                    message=f"Order not found: {order_id}",
                    error_code="ORDER_NOT_FOUND",
                )
            
            old_status = order.status
            if old_status == status:
                return OrderResult(success=True, order_id=order_id)
            
            # 更新索引
            self._orders_by_status[old_status].discard(order_id)
            self._orders_by_status[status].add(order_id)
            
            # 更新订单
            order.update_status(status)
            
            # 更新时间戳
            if status == OrderStatus.SUBMITTED:
                order.submitted_at = datetime.utcnow()
            
            # 更新统计
            if status == OrderStatus.FILLED:
                self._stats["filled_orders"] += 1
            elif status == OrderStatus.CANCELED:
                self._stats["canceled_orders"] += 1
            elif status == OrderStatus.REJECTED:
                self._stats["rejected_orders"] += 1
            
            # 更新其他字段
            for key, value in kwargs.items():
                if hasattr(order, key):
                    setattr(order, key, value)
        
        # 触发回调
        self._notify_status_change(order)
        
        logger.debug(f"Order {order_id} status: {old_status.name} -> {status.name}")
        return OrderResult(success=True, order_id=order_id)
    
    async def add_fill(
        self,
        order_id: str,
        price: Decimal,
        quantity: Decimal,
        commission: Decimal = Decimal("0"),
        venue: str = "",
    ) -> OrderResult:
        """
        添加成交记录
        
        Args:
            order_id: 订单ID
            price: 成交价格
            quantity: 成交数量
            commission: 手续费
            venue: 交易所
        
        Returns:
            OrderResult: 操作结果
        """
        async with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return OrderResult(
                    success=False,
                    message=f"Order not found: {order_id}",
                    error_code="ORDER_NOT_FOUND",
                )
            
            fill = Fill(
                order_id=order_id,
                price=price,
                quantity=quantity,
                commission=commission,
                venue=venue,
            )
            
            old_status = order.status
            order.add_fill(fill)
            
            # 更新索引
            if old_status != order.status:
                self._orders_by_status[old_status].discard(order_id)
                self._orders_by_status[order.status].add(order_id)
        
        # 触发回调
        self._notify_fill(order, fill)
        
        logger.info(
            f"Fill added: {order_id} {quantity} @ {price} "
            f"(filled: {order.filled_quantity}/{order.quantity})"
        )
        return OrderResult(success=True, order_id=order_id)
    
    # ============ 订单查询 ============
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self._orders.get(order_id)
    
    def get_orders(
        self,
        symbol: Optional[str] = None,
        account_id: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        active_only: bool = False,
    ) -> List[Order]:
        """
        查询订单
        
        Args:
            symbol: 交易代码过滤
            account_id: 账户ID过滤
            status: 状态过滤
            active_only: 只返回活动订单
        
        Returns:
            List[Order]: 订单列表
        """
        order_ids: Set[str] = set()
        
        if symbol:
            order_ids = self._orders_by_symbol.get(symbol, set()).copy()
        elif account_id:
            order_ids = self._orders_by_account.get(account_id, set()).copy()
        elif status:
            order_ids = self._orders_by_status.get(status, set()).copy()
        else:
            order_ids = set(self._orders.keys())
        
        if active_only:
            active_ids = set()
            for s in [OrderStatus.PENDING, OrderStatus.SUBMITTING, 
                      OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED]:
                active_ids.update(self._orders_by_status.get(s, set()))
            order_ids = order_ids & active_ids
        
        return [self._orders[oid] for oid in order_ids if oid in self._orders]
    
    def get_active_orders(self) -> List[Order]:
        """获取所有活动订单"""
        return self.get_orders(active_only=True)
    
    def get_orders_by_symbol(self, symbol: str) -> List[Order]:
        """获取指定代码的所有订单"""
        return self.get_orders(symbol=symbol)
    
    def get_orders_by_account(self, account_id: str) -> List[Order]:
        """获取指定账户的所有订单"""
        return self.get_orders(account_id=account_id)
    
    # ============ 订单撤销 ============
    
    async def cancel_order(self, order_id: str) -> OrderResult:
        """
        撤销订单
        
        Args:
            order_id: 订单ID
        
        Returns:
            OrderResult: 操作结果
        """
        order = self.get_order(order_id)
        if not order:
            return OrderResult(
                success=False,
                message=f"Order not found: {order_id}",
                error_code="ORDER_NOT_FOUND",
            )
        
        if not order.is_active():
            return OrderResult(
                success=False,
                message=f"Order {order_id} is not active (status: {order.status.name})",
                error_code="ORDER_NOT_ACTIVE",
            )
        
        await self.update_order_status(order_id, OrderStatus.CANCELING)
        return OrderResult(success=True, order_id=order_id)
    
    async def cancel_all_orders(
        self,
        symbol: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> List[OrderResult]:
        """
        批量撤销订单
        
        Args:
            symbol: 交易代码过滤
            account_id: 账户ID过滤
        
        Returns:
            List[OrderResult]: 操作结果列表
        """
        orders = self.get_orders(symbol=symbol, account_id=account_id, active_only=True)
        results = []
        for order in orders:
            result = await self.cancel_order(order.order_id)
            results.append(result)
        return results
    
    # ============ 回调注册 ============
    
    def on_status_change(self, callback: Callable[[Order], None]) -> None:
        """注册状态变更回调"""
        self._status_callbacks.append(callback)
    
    def on_fill(self, callback: Callable[[Order, Fill], None]) -> None:
        """注册成交回调"""
        self._fill_callbacks.append(callback)
    
    def _notify_status_change(self, order: Order) -> None:
        """通知状态变更"""
        for callback in self._status_callbacks:
            try:
                callback(order)
            except Exception as e:
                logger.error(f"Status callback error: {e}")
    
    def _notify_fill(self, order: Order, fill: Fill) -> None:
        """通知成交"""
        for callback in self._fill_callbacks:
            try:
                callback(order, fill)
            except Exception as e:
                logger.error(f"Fill callback error: {e}")
    
    # ============ 统计信息 ============
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "active_orders": len(self.get_active_orders()),
            "pending_count": len(self._orders_by_status.get(OrderStatus.PENDING, set())),
            "submitted_count": len(self._orders_by_status.get(OrderStatus.SUBMITTED, set())),
            "partial_filled_count": len(self._orders_by_status.get(OrderStatus.PARTIAL_FILLED, set())),
        }
    
    def clear_completed_orders(self, max_age_hours: float = 24.0) -> int:
        """
        清理已完成订单
        
        Args:
            max_age_hours: 最大保留时间（小时）
        
        Returns:
            int: 清理的订单数量
        """
        now = datetime.utcnow()
        to_remove = []
        
        for order_id, order in self._orders.items():
            if order.is_complete():
                age_hours = (now - order.updated_at).total_seconds() / 3600
                if age_hours >= max_age_hours:
                    to_remove.append(order_id)
        
        for order_id in to_remove:
            self._remove_order(order_id)
        
        return len(to_remove)
    
    def _remove_order(self, order_id: str) -> None:
        """从索引中移除订单"""
        order = self._orders.pop(order_id, None)
        if order:
            self._orders_by_symbol[order.symbol].discard(order_id)
            self._orders_by_account[order.account_id].discard(order_id)
            self._orders_by_status[order.status].discard(order_id)
    
    async def reset(self) -> None:
        """重置管理器状态"""
        async with self._lock:
            self._orders.clear()
            self._orders_by_symbol.clear()
            self._orders_by_account.clear()
            self._orders_by_status.clear()
            self._stats = {
                "total_orders": 0,
                "filled_orders": 0,
                "canceled_orders": 0,
                "rejected_orders": 0,
            }
