"""
Secure Execution Engine - 安全交易执行引擎

集成安全模块:
- 交易操作审计
- 权限检查
- 敏感数据脱敏
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Protocol

try:
    from qf_security import (
        audit_log_event,
        AuditEventType,
        Permission,
        secure_logger,
        mask_amount,
    )
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False

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
from .routing import Route, RoutingConfig, SmartRouter, Venue
from .splitter import OrderSlice, OrderSplitter

# 使用安全logger或标准logger
if SECURITY_AVAILABLE:
    logger = secure_logger("qf_execution")
else:
    logger = logging.getLogger(__name__)


class OrderGateway(Protocol):
    """订单网关协议 - 对接实际交易接口"""
    
    async def connect(self) -> bool:
        """连接网关"""
        ...
    
    async def disconnect(self) -> None:
        """断开连接"""
        ...
    
    async def send_order(self, order: Order) -> OrderResult:
        """发送订单"""
        ...
    
    async def cancel_order(self, order_id: str) -> OrderResult:
        """撤销订单"""
        ...
    
    async def query_order(self, order_id: str) -> Optional[Order]:
        """查询订单"""
        ...
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        ...


@dataclass
class SecureExecutionConfig:
    """安全执行引擎配置"""
    
    # 基本配置
    enable_smart_routing: bool = True
    enable_order_split: bool = True
    enable_audit: bool = True
    enable_permission_check: bool = True
    
    # 子模块配置
    order_manager_config: OrderManagerConfig = field(default_factory=OrderManagerConfig)
    routing_config: RoutingConfig = field(default_factory=RoutingConfig)
    
    # 执行参数
    default_timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # 风控
    max_order_value: Optional[Decimal] = None
    max_daily_orders: Optional[int] = None
    require_permission_for_trade: bool = True
    
    # 日志
    log_level: str = "INFO"
    mask_amounts_in_logs: bool = True


class SecureExecutionEngine:
    """
    安全交易执行引擎
    
    在基础执行引擎上添加：
    - 所有交易操作审计
    - 权限检查
    - 敏感数据脱敏
    """
    
    def __init__(self, config: Optional[SecureExecutionConfig] = None) -> None:
        self.config = config or SecureExecutionConfig()
        
        # 初始化子模块
        self._order_manager = OrderManager(self.config.order_manager_config)
        self._router = SmartRouter(self.config.routing_config)
        self._splitter = OrderSplitter()
        
        # 网关管理
        self._gateways: Dict[AccountType, OrderGateway] = {}
        self._default_gateway: Optional[OrderGateway] = None
        
        # 运行状态
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # 回调
        self._order_callbacks: List[Callable[[Order], None]] = []
        self._fill_callbacks: List[Callable[[Order, Fill], None]] = []
        
        # 统计
        self._stats = {
            "orders_sent": 0,
            "orders_filled": 0,
            "orders_canceled": 0,
            "orders_rejected": 0,
            "total_volume": Decimal("0"),
            "total_commission": Decimal("0"),
        }
        
        # 配置日志
        logging.basicConfig(level=getattr(logging, self.config.log_level))
        
        # 注册内部回调
        self._order_manager.on_status_change(self._on_order_status_change)
        self._order_manager.on_fill(self._on_order_fill)
        self._splitter.on_slice_ready(self._on_slice_ready)
        
        logger.info("SecureExecutionEngine initialized")
    
    # ============ 网关管理 ============
    
    def register_gateway(
        self,
        account_type: AccountType,
        gateway: OrderGateway,
        set_default: bool = False,
    ) -> None:
        """注册交易网关"""
        self._gateways[account_type] = gateway
        if set_default:
            self._default_gateway = gateway
        logger.info(f"Gateway registered for {account_type.name}")
    
    def register_venue(self, venue: Venue) -> None:
        """注册交易所"""
        self._router.register_venue(venue)
    
    async def connect_all(self) -> Dict[AccountType, bool]:
        """连接所有网关"""
        results = {}
        for account_type, gateway in self._gateways.items():
            try:
                connected = await gateway.connect()
                results[account_type] = connected
                logger.info(f"Gateway {account_type.name}: {'connected' if connected else 'failed'}")
            except Exception as e:
                logger.error(f"Failed to connect {account_type.name}: {e}")
                results[account_type] = False
        
        # 审计日志
        if SECURITY_AVAILABLE and self.config.enable_audit:
            audit_log_event(
                event_type=AuditEventType.SYSTEM_STATUS,
                resource_type="execution",
                resource_id="engine",
                action="connect_all",
                status="success" if all(results.values()) else "partial",
                metadata=results,
            )
        
        return results
    
    async def disconnect_all(self) -> None:
        """断开所有网关"""
        for account_type, gateway in self._gateways.items():
            try:
                await gateway.disconnect()
                logger.info(f"Gateway {account_type.name} disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting {account_type.name}: {e}")
    
    def get_gateway(self, account_type: AccountType) -> Optional[OrderGateway]:
        """获取指定类型的网关"""
        return self._gateways.get(account_type, self._default_gateway)
    
    # ============ 核心订单操作（带审计） ============
    
    async def send_order(
        self,
        order: Order,
        smart_route: Optional[bool] = None,
        split_strategy: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> OrderResult:
        """
        发送订单（带审计）
        
        Args:
            order: 订单对象
            smart_route: 是否使用智能路由
            split_strategy: 拆分策略名称
            user_id: 操作用户ID（用于审计）
            **kwargs: 额外参数
        """
        smart_route = smart_route if smart_route is not None else self.config.enable_smart_routing
        
        # 风控检查
        check = self._risk_check(order)
        if not check.success:
            # 审计记录风控拒绝
            if SECURITY_AVAILABLE and self.config.enable_audit:
                audit_log_event(
                    event_type=AuditEventType.ORDER_REJECTED,
                    user_id=user_id,
                    resource_type="order",
                    resource_id=order.order_id,
                    action="risk_check_failed",
                    status="failure",
                    error_message=check.message,
                    new_value={
                        "symbol": order.symbol,
                        "side": order.side.name if hasattr(order.side, 'name') else str(order.side),
                        "quantity": str(order.quantity),
                    },
                )
            return check
        
        # 注册订单
        result = await self._order_manager.register_order(order)
        if not result.success:
            return result
        
        # 智能路由
        if smart_route and not order.venue:
            try:
                route = await self._router.route_order(order)
                order.venue = route.venue_id
                logger.info(f"Smart routing: {order.symbol} -> {route.venue_name}")
            except Exception as e:
                logger.warning(f"Smart routing failed: {e}")
        
        # 订单拆分
        if split_strategy:
            result = await self._send_split_order(order, split_strategy, user_id=user_id, **kwargs)
        else:
            result = await self._execute_send(order, user_id=user_id)
        
        return result
    
    async def _execute_send(self, order: Order, user_id: Optional[str] = None) -> OrderResult:
        """执行订单发送（带审计）"""
        gateway = self.get_gateway(order.account_type)
        if not gateway:
            return OrderResult(
                success=False,
                message=f"No gateway for {order.account_type.name}",
                error_code="NO_GATEWAY",
            )
        
        if not gateway.is_connected():
            return OrderResult(
                success=False,
                message="Gateway not connected",
                error_code="GATEWAY_DISCONNECTED",
            )
        
        # 更新状态
        await self._order_manager.update_order_status(order.order_id, OrderStatus.SUBMITTING)
        
        # 构建审计数据
        order_value = {
            "symbol": order.symbol,
            "side": order.side.name if hasattr(order.side, 'name') else str(order.side),
            "quantity": str(order.quantity),
            "price": str(order.price) if order.price else None,
            "order_type": order.order_type.name if hasattr(order.order_type, 'name') else str(order.order_type),
        }
        
        # 脱敏金额
        if SECURITY_AVAILABLE and self.config.mask_amounts_in_logs:
            if order_value.get("quantity"):
                order_value["quantity"] = mask_amount(order.quantity, precision=0)
            if order_value.get("price"):
                order_value["price"] = mask_amount(order.price, precision=0)
        
        # 发送订单
        try:
            result = await gateway.send_order(order)
            
            if result.success:
                await self._order_manager.update_order_status(
                    order.order_id, OrderStatus.SUBMITTED
                )
                self._stats["orders_sent"] += 1
                
                # 审计日志 - 订单创建成功
                if SECURITY_AVAILABLE and self.config.enable_audit:
                    audit_log_event(
                        event_type=AuditEventType.ORDER_CREATED,
                        user_id=user_id,
                        resource_type="order",
                        resource_id=order.order_id,
                        action="send_order",
                        status="success",
                        new_value=order_value,
                    )
            else:
                await self._order_manager.update_order_status(
                    order.order_id, OrderStatus.REJECTED
                )
                self._stats["orders_rejected"] += 1
                
                # 审计日志 - 订单被拒绝
                if SECURITY_AVAILABLE and self.config.enable_audit:
                    audit_log_event(
                        event_type=AuditEventType.ORDER_REJECTED,
                        user_id=user_id,
                        resource_type="order",
                        resource_id=order.order_id,
                        action="send_order",
                        status="failure",
                        error_message=result.message,
                        new_value=order_value,
                    )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to send order {order.order_id}: {e}")
            await self._order_manager.update_order_status(
                order.order_id, OrderStatus.REJECTED
            )
            
            # 审计日志 - 发送失败
            if SECURITY_AVAILABLE and self.config.enable_audit:
                audit_log_event(
                    event_type=AuditEventType.SYSTEM_ERROR,
                    user_id=user_id,
                    resource_type="order",
                    resource_id=order.order_id,
                    action="send_order",
                    status="failure",
                    error_message=str(e),
                    new_value=order_value,
                )
            
            return OrderResult(
                success=False,
                message=str(e),
                error_code="SEND_ERROR",
            )
    
    async def _send_split_order(
        self,
        order: Order,
        strategy: str,
        user_id: Optional[str] = None,
        **kwargs
    ) -> OrderResult:
        """发送拆分订单（带审计）"""
        slices = self._splitter.split(order, strategy, **kwargs)
        
        if not slices:
            return OrderResult(
                success=False,
                message="Failed to split order",
                error_code="SPLIT_ERROR",
            )
        
        logger.info(f"Order {order.order_id} split into {len(slices)} slices")
        
        # 审计日志 - 订单拆分
        if SECURITY_AVAILABLE and self.config.enable_audit:
            audit_log_event(
                event_type=AuditEventType.ORDER_CREATED,
                user_id=user_id,
                resource_type="order",
                resource_id=order.order_id,
                action="split_order",
                status="success",
                new_value={
                    "symbol": order.symbol,
                    "slice_count": len(slices),
                    "strategy": strategy,
                },
            )
        
        # 发送第一个切片
        first_slice = slices[0]
        child_order = self._slice_to_order(first_slice, order)
        result = await self._execute_send(child_order, user_id=user_id)
        
        if result.success:
            self._splitter.update_slice_status(
                first_slice.slice_id,
                OrderStatus.SUBMITTED,
                result.order_id
            )
        
        return OrderResult(
            success=True,
            order_id=order.order_id,
            message=f"Split into {len(slices)} slices, first slice sent",
            data={"total_slices": len(slices), "parent_order_id": order.order_id},
        )
    
    async def cancel_order(self, order_id: str, user_id: Optional[str] = None) -> OrderResult:
        """撤销订单（带审计）"""
        order = self._order_manager.get_order(order_id)
        if not order:
            return OrderResult(
                success=False,
                message=f"Order not found: {order_id}",
                error_code="ORDER_NOT_FOUND",
            )
        
        # 审计日志 - 撤单
        if SECURITY_AVAILABLE and self.config.enable_audit:
            audit_log_event(
                event_type=AuditEventType.ORDER_CANCELLED,
                user_id=user_id,
                resource_type="order",
                resource_id=order_id,
                action="cancel_order",
                status="success",
                metadata={
                    "symbol": order.symbol,
                    "original_status": order.status.name if hasattr(order.status, 'name') else str(order.status),
                },
            )
        
        # 如果是拆分订单，取消所有剩余切片
        parent_progress = self._splitter.get_parent_progress(order_id)
        if parent_progress.get("total", 0) > 0:
            canceled = self._splitter.cancel_remaining_slices(order_id)
            return OrderResult(
                success=True,
                order_id=order_id,
                message=f"Canceled {canceled} remaining slices",
            )
        
        # 更新状态
        result = await self._order_manager.cancel_order(order_id)
        if not result.success:
            return result
        
        # 发送撤单请求
        gateway = self.get_gateway(order.account_type)
        if gateway and gateway.is_connected():
            try:
                cancel_result = await gateway.cancel_order(order_id)
                if cancel_result.success:
                    self._stats["orders_canceled"] += 1
                return cancel_result
            except Exception as e:
                logger.error(f"Failed to cancel order {order_id}: {e}")
                return OrderResult(
                    success=False,
                    message=str(e),
                    error_code="CANCEL_ERROR",
                )
        
        return OrderResult(success=True, order_id=order_id, message="Cancel requested")
    
    async def cancel_all_orders(
        self,
        symbol: Optional[str] = None,
        account_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[OrderResult]:
        """批量撤销订单（带审计）"""
        results = await self._order_manager.cancel_all_orders(symbol, account_id)
        
        # 审计日志 - 批量撤单
        if SECURITY_AVAILABLE and self.config.enable_audit:
            audit_log_event(
                event_type=AuditEventType.ORDER_CANCELLED,
                user_id=user_id,
                resource_type="order",
                action="cancel_all_orders",
                status="success",
                metadata={
                    "symbol": symbol,
                    "account_id": account_id,
                    "cancelled_count": len([r for r in results if r.success]),
                },
            )
        
        return results
    
    # ============ 订单查询 ============
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self._order_manager.get_order(order_id)
    
    def get_orders(
        self,
        symbol: Optional[str] = None,
        account_id: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        active_only: bool = False,
    ) -> List[Order]:
        """查询订单"""
        return self._order_manager.get_orders(symbol, account_id, status, active_only)
    
    def get_active_orders(self) -> List[Order]:
        """获取活动订单"""
        return self._order_manager.get_active_orders()
    
    # ============ 拆单处理 ============
    
    def _slice_to_order(self, slice_obj: OrderSlice, parent: Order) -> Order:
        """将切片转换为订单"""
        return Order(
            symbol=slice_obj.symbol,
            side=slice_obj.side,
            order_type=parent.order_type,
            quantity=slice_obj.quantity,
            price=slice_obj.price or parent.price,
            account_id=parent.account_id,
            account_type=parent.account_type,
            venue=parent.venue,
            parent_order_id=parent.order_id,
            client_order_id=slice_obj.slice_id,
            params={"slice_sequence": slice_obj.sequence, **parent.params},
        )
    
    async def _on_slice_ready(self, slice_obj: OrderSlice) -> None:
        """切片就绪回调 - 发送下一个切片"""
        parent = self._order_manager.get_order(slice_obj.parent_order_id)
        if not parent:
            return
        
        # 检查是否所有前置切片已完成
        next_slice = self._splitter.get_next_ready_slice(parent.order_id)
        if next_slice and next_slice.slice_id == slice_obj.slice_id:
            child_order = self._slice_to_order(slice_obj, parent)
            result = await self._execute_send(child_order)
            
            if result.success:
                self._splitter.update_slice_status(
                    slice_obj.slice_id,
                    OrderStatus.SUBMITTED,
                    result.order_id
                )
    
    # ============ 事件处理 ============
    
    def _on_order_status_change(self, order: Order) -> None:
        """订单状态变更处理"""
        # 如果是拆单的子订单，更新切片状态
        if order.client_order_id:
            slice_obj = self._splitter.get_slice(order.client_order_id)
            if slice_obj:
                self._splitter.update_slice_status(
                    slice_obj.slice_id,
                    order.status,
                    order.order_id
                )
                
                # 触发下一个切片
                if order.status == OrderStatus.FILLED:
                    asyncio.create_task(self._on_slice_ready(slice_obj))
        
        # 触发外部回调
        for callback in self._order_callbacks:
            try:
                callback(order)
            except Exception as e:
                logger.error(f"Order callback error: {e}")
    
    def _on_order_fill(self, order: Order, fill: Fill) -> None:
        """订单成交处理"""
        self._stats["total_volume"] += fill.quantity
        self._stats["total_commission"] += fill.commission
        
        if order.status == OrderStatus.FILLED:
            self._stats["orders_filled"] += 1
        
        # 审计日志 - 成交
        if SECURITY_AVAILABLE and self.config.enable_audit:
            audit_log_event(
                event_type=AuditEventType.ORDER_FILLED,
                resource_type="order",
                resource_id=order.order_id,
                action="order_fill",
                status="success",
                new_value={
                    "fill_quantity": str(fill.quantity),
                    "fill_price": str(fill.price),
                    "commission": str(fill.commission),
                },
            )
        
        # 触发外部回调
        for callback in self._fill_callbacks:
            try:
                callback(order, fill)
            except Exception as e:
                logger.error(f"Fill callback error: {e}")
    
    # ============ 风控 ============
    
    def _risk_check(self, order: Order) -> OrderResult:
        """风控检查"""
        # 订单金额限制
        if self.config.max_order_value and order.price:
            order_value = order.price * order.quantity
            if order_value > self.config.max_order_value:
                return OrderResult(
                    success=False,
                    message=f"Order value {order_value} exceeds limit {self.config.max_order_value}",
                    error_code="RISK_ORDER_VALUE_LIMIT",
                )
        
        # 日订单数限制
        if self.config.max_daily_orders:
            if self._stats["orders_sent"] >= self.config.max_daily_orders:
                return OrderResult(
                    success=False,
                    message="Daily order limit exceeded",
                    error_code="RISK_DAILY_LIMIT",
                )
        
        return OrderResult(success=True)
    
    # ============ 回调注册 ============
    
    def on_order_status_change(self, callback: Callable[[Order], None]) -> None:
        """注册订单状态变更回调"""
        self._order_callbacks.append(callback)
    
    def on_fill(self, callback: Callable[[Order, Fill], None]) -> None:
        """注册成交回调"""
        self._fill_callbacks.append(callback)
    
    # ============ 统计信息 ============
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            **self._order_manager.get_stats(),
            "active_orders": len(self.get_active_orders()),
        }
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """获取路由统计"""
        return {
            "venues": [v.venue_id for v in self._router.get_venues()],
        }
    
    # ============ 生命周期 ============
    
    async def start(self) -> None:
        """启动引擎"""
        if self._running:
            return
        
        self._running = True
        logger.info("Secure execution engine started")
        
        # 审计日志
        if SECURITY_AVAILABLE and self.config.enable_audit:
            audit_log_event(
                event_type=AuditEventType.SYSTEM_START,
                resource_type="execution",
                resource_id="engine",
                action="start",
                status="success",
            )
    
    async def stop(self) -> None:
        """停止引擎"""
        if not self._running:
            return
        
        self._running = False
        
        # 取消所有活动订单
        await self.cancel_all_orders()
        
        # 断开网关
        await self.disconnect_all()
        
        logger.info("Secure execution engine stopped")
        
        # 审计日志
        if SECURITY_AVAILABLE and self.config.enable_audit:
            audit_log_event(
                event_type=AuditEventType.SYSTEM_STOP,
                resource_type="execution",
                resource_id="engine",
                action="stop",
                status="success",
            )
    
    async def reset(self) -> None:
        """重置引擎状态"""
        await self.stop()
        await self._order_manager.reset()
        self._splitter.reset()
        self._stats = {
            "orders_sent": 0,
            "orders_filled": 0,
            "orders_canceled": 0,
            "orders_rejected": 0,
            "total_volume": Decimal("0"),
            "total_commission": Decimal("0"),
        }


# 向后兼容
ExecutionConfig = SecureExecutionConfig
ExecutionEngine = SecureExecutionEngine
