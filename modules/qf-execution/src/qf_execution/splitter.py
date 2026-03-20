"""
Order Splitter - 订单拆分模块
支持冰山订单、TWAP等高级订单类型
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Callable, Iterator, List, Optional, Protocol

from .models import Order, OrderStatus, OrderType, Side

logger = logging.getLogger(__name__)


@dataclass
class OrderSlice:
    """订单切片"""
    slice_id: str
    parent_order_id: str
    sequence: int  # 第几个切片
    total_slices: int
    
    symbol: str = ""
    side: Side = Side.BUY
    quantity: Decimal = Decimal("0")
    price: Optional[Decimal] = None
    
    # 时间
    scheduled_time: Optional[datetime] = None
    send_after: Optional[datetime] = None
    
    # 状态
    status: OrderStatus = field(default=OrderStatus.PENDING)
    child_order_id: Optional[str] = None
    
    def __post_init__(self) -> None:
        if self.slice_id is None:
            import uuid
            self.slice_id = str(uuid.uuid4())


@dataclass
class SplitConfig:
    """拆分配置"""
    min_slice_size: Decimal = Decimal("1")
    max_slice_size: Optional[Decimal] = None
    randomize_size: bool = False  # 随机化切片大小
    randomize_timing: bool = False  # 随机化发送时间
    price_adjustment_ticks: int = 0  # 价格调整（tick数）


class SplitStrategy(ABC):
    """拆分策略基类"""
    
    def __init__(self, config: Optional[SplitConfig] = None) -> None:
        self.config = config or SplitConfig()
    
    @abstractmethod
    def split(
        self,
        order: Order,
        **kwargs
    ) -> List[OrderSlice]:
        """拆分订单"""
        pass
    
    def _create_slices(
        self,
        order: Order,
        quantities: List[Decimal],
        prices: Optional[List[Optional[Decimal]]] = None,
        schedule_times: Optional[List[Optional[datetime]]] = None,
    ) -> List[OrderSlice]:
        """创建切片列表"""
        import uuid
        
        slices = []
        total = len(quantities)
        
        for i, qty in enumerate(quantities):
            slice_obj = OrderSlice(
                slice_id=str(uuid.uuid4()),
                parent_order_id=order.order_id,
                sequence=i + 1,
                total_slices=total,
                symbol=order.symbol,
                side=order.side,
                quantity=qty,
                price=prices[i] if prices else order.price,
                scheduled_time=schedule_times[i] if schedule_times else None,
            )
            slices.append(slice_obj)
        
        return slices


class EqualSplitter(SplitStrategy):
    """等分拆分策略"""
    
    def __init__(
        self,
        num_slices: int,
        config: Optional[SplitConfig] = None,
    ) -> None:
        super().__init__(config)
        self.num_slices = num_slices
    
    def split(self, order: Order, **kwargs) -> List[OrderSlice]:
        """等分订单"""
        qty_per_slice = (order.quantity / self.num_slices).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )
        
        quantities = [qty_per_slice] * self.num_slices
        # 调整最后一个切片的数量以匹配总额
        quantities[-1] = order.quantity - sum(quantities[:-1])
        
        return self._create_slices(order, quantities)


class IcebergOrder(SplitStrategy):
    """
    冰山订单策略
    
    大单拆分成小单，每次只显示/display_qty的数量，
    成交后自动发送下一个切片。
    """
    
    def __init__(
        self,
        display_qty: Decimal,
        config: Optional[SplitConfig] = None,
    ) -> None:
        super().__init__(config)
        self.display_qty = display_qty
    
    def split(self, order: Order, **kwargs) -> List[OrderSlice]:
        """
        拆分冰山订单
        
        Args:
            order: 原始订单
            **kwargs: 可以包含 variance (随机变化量)
        """
        variance = kwargs.get("variance", Decimal("0"))
        remaining = order.quantity
        quantities = []
        
        while remaining > 0:
            # 应用随机变化
            if variance > 0 and len(quantities) > 0:
                import random
                v = variance * self.display_qty
                display = self.display_qty + Decimal(random.uniform(-float(v), float(v)))
                display = max(self.config.min_slice_size, display)
            else:
                display = self.display_qty
            
            qty = min(display, remaining)
            quantities.append(qty)
            remaining -= qty
        
        return self._create_slices(order, quantities)


class TWAPOrder(SplitStrategy):
    """
    TWAP (Time-Weighted Average Price) 订单策略
    
    在指定时间范围内均匀执行订单
    """
    
    def __init__(
        self,
        duration_seconds: float,
        num_slices: int,
        config: Optional[SplitConfig] = None,
    ) -> None:
        super().__init__(config)
        self.duration_seconds = duration_seconds
        self.num_slices = num_slices
    
    def split(
        self,
        order: Order,
        start_time: Optional[datetime] = None,
        **kwargs
    ) -> List[OrderSlice]:
        """
        拆分TWAP订单
        
        Args:
            order: 原始订单
            start_time: 开始时间（默认当前时间）
        """
        start = start_time or datetime.utcnow()
        interval = self.duration_seconds / self.num_slices
        
        # 计算数量
        qty_per_slice = (order.quantity / self.num_slices).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )
        quantities = [qty_per_slice] * self.num_slices
        quantities[-1] = order.quantity - sum(quantities[:-1])
        
        # 计算时间
        schedule_times = [
            start + timedelta(seconds=interval * i)
            for i in range(self.num_slices)
        ]
        
        # 价格调整
        prices = None
        if self.config.price_adjustment_ticks != 0:
            tick_size = kwargs.get("tick_size", Decimal("0.01"))
            base_price = order.price or Decimal("0")
            prices = [
                base_price + Decimal(self.config.price_adjustment_ticks) * tick_size * i
                for i in range(self.num_slices)
            ]
        
        return self._create_slices(order, quantities, prices, schedule_times)


class VWAPOrder(SplitStrategy):
    """
    VWAP (Volume-Weighted Average Price) 订单策略
    
    根据历史成交量分布来安排切片
    """
    
    def __init__(
        self,
        duration_seconds: float,
        volume_profile: List[float],
        config: Optional[SplitConfig] = None,
    ) -> None:
        super().__init__(config)
        self.duration_seconds = duration_seconds
        self.volume_profile = volume_profile  # 成交量分布（归一化）
    
    def split(
        self,
        order: Order,
        start_time: Optional[datetime] = None,
        **kwargs
    ) -> List[OrderSlice]:
        """
        拆分VWAP订单
        
        Args:
            order: 原始订单
            start_time: 开始时间
        """
        start = start_time or datetime.utcnow()
        num_slices = len(self.volume_profile)
        
        # 根据成交量分布计算数量
        total_volume = sum(self.volume_profile)
        quantities = [
            (order.quantity * Decimal(v) / Decimal(total_volume)).quantize(
                Decimal("0.01"), rounding=ROUND_DOWN
            )
            for v in self.volume_profile
        ]
        # 调整最后一个以确保总额正确
        quantities[-1] = order.quantity - sum(quantities[:-1])
        
        # 计算时间
        interval = self.duration_seconds / num_slices
        schedule_times = [
            start + timedelta(seconds=interval * i)
            for i in range(num_slices)
        ]
        
        return self._create_slices(order, quantities, schedule_times=schedule_times)


class PercentageOfVolume(SplitStrategy):
    """
    POV (Percentage of Volume) 策略
    
    按照市场成交量的固定百分比来执行
    """
    
    def __init__(
        self,
        pov_ratio: float,
        max_participation: float = 0.1,
        config: Optional[SplitConfig] = None,
    ) -> None:
        super().__init__(config)
        self.pov_ratio = pov_ratio  # 参与比例
        self.max_participation = max_participation  # 最大参与比例
    
    def split(
        self,
        order: Order,
        market_volumes: List[Decimal],
        **kwargs
    ) -> List[OrderSlice]:
        """
        拆分POV订单
        
        Args:
            order: 原始订单
            market_volumes: 各时间段的市场成交量预估
        """
        quantities = []
        remaining = order.quantity
        
        for market_vol in market_volumes:
            target_qty = min(
                market_vol * Decimal(str(self.pov_ratio)),
                market_vol * Decimal(str(self.max_participation)),
                remaining
            )
            if target_qty < self.config.min_slice_size:
                break
            
            quantities.append(target_qty)
            remaining -= target_qty
            
            if remaining <= 0:
                break
        
        # 如果还有剩余，加到最后一个切片
        if remaining > 0 and quantities:
            quantities[-1] += remaining
        elif remaining > 0:
            quantities.append(remaining)
        
        return self._create_slices(order, quantities)


class OrderSplitter:
    """
    订单拆分器
    
    负责：
    - 根据策略拆分订单
    - 管理切片生命周期
    - 协调切片发送
    """
    
    def __init__(self) -> None:
        self._slices: dict[str, OrderSlice] = {}
        self._parent_slices: dict[str, List[str]] = {}  # parent_id -> [slice_ids]
        self._strategies: dict[str, type[SplitStrategy]] = {
            "equal": EqualSplitter,
            "iceberg": IcebergOrder,
            "twap": TWAPOrder,
            "vwap": VWAPOrder,
            "pov": PercentageOfVolume,
        }
        self._on_slice_ready: Optional[Callable[[OrderSlice], None]] = None
    
    def register_strategy(
        self,
        name: str,
        strategy_class: type[SplitStrategy]
    ) -> None:
        """注册自定义拆分策略"""
        self._strategies[name] = strategy_class
    
    def split(
        self,
        order: Order,
        strategy: str = "equal",
        **kwargs
    ) -> List[OrderSlice]:
        """
        拆分订单
        
        Args:
            order: 原始订单
            strategy: 策略名称
            **kwargs: 策略参数
        
        Returns:
            List[OrderSlice]: 切片列表
        """
        strategy_class = self._strategies.get(strategy)
        if not strategy_class:
            raise ValueError(f"Unknown strategy: {strategy}")
        
        # 创建策略实例
        if strategy == "equal":
            num_slices = kwargs.get("num_slices", 4)
            splitter = strategy_class(num_slices)
        elif strategy == "iceberg":
            display_qty = kwargs.get("display_qty", order.quantity / 10)
            splitter = strategy_class(display_qty)
        elif strategy == "twap":
            duration = kwargs.get("duration_seconds", 300)
            num_slices = kwargs.get("num_slices", 5)
            splitter = strategy_class(duration, num_slices)
        elif strategy == "vwap":
            duration = kwargs.get("duration_seconds", 300)
            profile = kwargs.get("volume_profile", [0.1] * 10)
            splitter = strategy_class(duration, profile)
        elif strategy == "pov":
            ratio = kwargs.get("pov_ratio", 0.05)
            splitter = strategy_class(ratio)
        else:
            splitter = strategy_class()
        
        # 执行拆分
        slices = splitter.split(order, **kwargs)
        
        # 注册切片
        for slice_obj in slices:
            self._slices[slice_obj.slice_id] = slice_obj
        
        self._parent_slices[order.order_id] = [s.slice_id for s in slices]
        
        logger.info(
            f"Order {order.order_id} split into {len(slices)} slices "
            f"using {strategy} strategy"
        )
        
        return slices
    
    def get_slice(self, slice_id: str) -> Optional[OrderSlice]:
        """获取切片"""
        return self._slices.get(slice_id)
    
    def get_slices_by_parent(self, parent_order_id: str) -> List[OrderSlice]:
        """获取父订单的所有切片"""
        slice_ids = self._parent_slices.get(parent_order_id, [])
        return [self._slices[sid] for sid in slice_ids if sid in self._slices]
    
    def update_slice_status(
        self,
        slice_id: str,
        status: OrderStatus,
        child_order_id: Optional[str] = None
    ) -> None:
        """更新切片状态"""
        slice_obj = self._slices.get(slice_id)
        if slice_obj:
            slice_obj.status = status
            if child_order_id:
                slice_obj.child_order_id = child_order_id
    
    def get_next_ready_slice(self, parent_order_id: str) -> Optional[OrderSlice]:
        """获取下一个就绪的切片（按顺序）"""
        slices = self.get_slices_by_parent(parent_order_id)
        
        for s in slices:
            if s.status == OrderStatus.PENDING:
                # 检查前置切片是否已完成
                prev_slices = [ps for ps in slices if ps.sequence < s.sequence]
                if all(ps.status in [OrderStatus.FILLED, OrderStatus.CANCELED] 
                       for ps in prev_slices):
                    return s
        
        return None
    
    def is_parent_complete(self, parent_order_id: str) -> bool:
        """检查父订单是否全部完成"""
        slices = self.get_slices_by_parent(parent_order_id)
        if not slices:
            return True
        return all(s.status.is_complete() if hasattr(s.status, 'is_complete') 
                   else s.status in [OrderStatus.FILLED, OrderStatus.CANCELED, 
                                     OrderStatus.REJECTED, OrderStatus.EXPIRED]
                   for s in slices)
    
    def get_parent_progress(self, parent_order_id: str) -> dict:
        """获取父订单执行进度"""
        slices = self.get_slices_by_parent(parent_order_id)
        total = len(slices)
        
        if total == 0:
            return {"total": 0, "completed": 0, "progress": 0.0}
        
        completed = sum(1 for s in slices if s.status == OrderStatus.FILLED)
        
        return {
            "total": total,
            "completed": completed,
            "progress": completed / total,
            "slices": [
                {
                    "slice_id": s.slice_id,
                    "sequence": s.sequence,
                    "status": s.status.name if hasattr(s.status, 'name') else str(s.status),
                    "quantity": str(s.quantity),
                }
                for s in slices
            ]
        }
    
    def on_slice_ready(self, callback: Callable[[OrderSlice], None]) -> None:
        """注册切片就绪回调"""
        self._on_slice_ready = callback
    
    def notify_slice_ready(self, slice_obj: OrderSlice) -> None:
        """通知切片就绪"""
        if self._on_slice_ready:
            self._on_slice_ready(slice_obj)
    
    def cancel_remaining_slices(self, parent_order_id: str) -> int:
        """
        取消父订单的剩余切片
        
        Returns:
            int: 取消的切片数量
        """
        slices = self.get_slices_by_parent(parent_order_id)
        canceled = 0
        
        for s in slices:
            if s.status in [OrderStatus.PENDING, OrderStatus.SUBMITTING]:
                s.status = OrderStatus.CANCELED
                canceled += 1
        
        return canceled
    
    def reset(self) -> None:
        """重置状态"""
        self._slices.clear()
        self._parent_slices.clear()
