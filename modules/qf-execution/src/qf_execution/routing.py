"""
Smart Router - 智能路由模块
负责最优交易所/路径选择，支持多交易所价格比较
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Protocol

from .models import (
    AccountType,
    Order,
    OrderType,
    Side,
)

logger = logging.getLogger(__name__)


class VenueStatus(Enum):
    """交易所状态"""
    AVAILABLE = auto()
    DEGRADED = auto()   # 性能下降
    UNAVAILABLE = auto()
    MAINTENANCE = auto()


@dataclass
class Venue:
    """交易所/券商配置"""
    venue_id: str
    name: str
    account_type: AccountType
    
    # 费用配置
    maker_fee_rate: Decimal = Decimal("0.001")  # 挂单费率
    taker_fee_rate: Decimal = Decimal("0.001")  # 吃单费率
    
    # 交易限制
    min_order_size: Decimal = Decimal("0.01")
    max_order_size: Decimal = Decimal("1000000")
    price_tick: Decimal = Decimal("0.01")
    qty_step: Decimal = Decimal("0.01")
    
    # 状态
    status: VenueStatus = VenueStatus.AVAILABLE
    latency_ms: float = 0.0
    
    # 扩展配置
    config: Dict = field(default_factory=dict)
    
    def calculate_fee(self, price: Decimal, qty: Decimal, is_maker: bool = False) -> Decimal:
        """计算交易费用"""
        fee_rate = self.maker_fee_rate if is_maker else self.taker_fee_rate
        return price * qty * fee_rate


@dataclass
class PriceLevel:
    """价格档位"""
    price: Decimal
    quantity: Decimal
    venue: str = ""
    
    @property
    def value(self) -> Decimal:
        """总价值"""
        return self.price * self.quantity


@dataclass
class MarketDepth:
    """市场深度"""
    symbol: str
    timestamp: float = 0.0
    bids: List[PriceLevel] = field(default_factory=list)  # 从高到低
    asks: List[PriceLevel] = field(default_factory=list)  # 从低到高
    venue: str = ""
    
    def get_best_bid(self) -> Optional[PriceLevel]:
        """获取最优买价"""
        return self.bids[0] if self.bids else None
    
    def get_best_ask(self) -> Optional[PriceLevel]:
        """获取最优卖价"""
        return self.asks[0] if self.asks else None
    
    def get_spread(self) -> Optional[Decimal]:
        """获取买卖价差"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid and best_ask:
            return best_ask.price - best_bid.price
        return None
    
    def get_mid_price(self) -> Optional[Decimal]:
        """获取中间价"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid and best_ask:
            return (best_bid.price + best_ask.price) / 2
        return best_bid.price if best_bid else best_ask.price if best_ask else None


@dataclass
class Route:
    """路由决策结果"""
    venue_id: str
    venue_name: str
    expected_price: Decimal
    expected_cost: Decimal  # 包含手续费
    confidence: float = 1.0  # 信心指数 0-1
    reason: str = ""
    alternatives: List[Dict] = field(default_factory=list)


class PriceFeed(Protocol):
    """价格源协议"""
    
    async def get_depth(self, symbol: str, venue: str) -> Optional[MarketDepth]:
        ...
    
    async def get_price(self, symbol: str, venue: str) -> Optional[Decimal]:
        ...


@dataclass
class RoutingConfig:
    """路由配置"""
    # 策略
    strategy: str = "best_price"  # best_price, lowest_fee, best_execution
    
    # 延迟权重
    latency_weight: float = 0.2
    price_weight: float = 0.5
    fee_weight: float = 0.3
    
    # 阈值
    min_confidence: float = 0.7
    max_latency_ms: float = 500.0
    
    # 多交易所配置
    enable_multi_venue: bool = True
    min_venue_count: int = 1
    max_venue_count: int = 3
    
    # 智能路由
    enable_smart_split: bool = True
    min_qty_for_split: Decimal = Decimal("100")


class SmartRouter:
    """
    智能路由器
    
    功能：
    - 多交易所价格比较
    - 最优执行路径选择
    - 考虑手续费和延迟
    - 支持订单拆分路由
    """
    
    def __init__(self, config: Optional[RoutingConfig] = None) -> None:
        self.config = config or RoutingConfig()
        self._venues: Dict[str, Venue] = {}
        self._price_feed: Optional[PriceFeed] = None
        self._depth_cache: Dict[str, MarketDepth] = {}  # symbol:venue -> depth
        self._last_update: Dict[str, float] = {}  # symbol:venue -> timestamp
        self._cache_ttl_seconds: float = 5.0
    
    def register_venue(self, venue: Venue) -> None:
        """注册交易所"""
        self._venues[venue.venue_id] = venue
        logger.info(f"Venue registered: {venue.venue_id} ({venue.name})")
    
    def unregister_venue(self, venue_id: str) -> None:
        """注销交易所"""
        if venue_id in self._venues:
            del self._venues[venue_id]
            logger.info(f"Venue unregistered: {venue_id}")
    
    def set_price_feed(self, price_feed: PriceFeed) -> None:
        """设置价格源"""
        self._price_feed = price_feed
    
    def get_venues(self, account_type: Optional[AccountType] = None) -> List[Venue]:
        """获取交易所列表"""
        venues = list(self._venues.values())
        if account_type:
            venues = [v for v in venues if v.account_type == account_type]
        return [v for v in venues if v.status == VenueStatus.AVAILABLE]
    
    async def update_depth(self, symbol: str, depth: MarketDepth) -> None:
        """更新市场深度缓存"""
        key = f"{symbol}:{depth.venue}"
        self._depth_cache[key] = depth
        self._last_update[key] = time.time()
    
    def get_cached_depth(self, symbol: str, venue_id: str) -> Optional[MarketDepth]:
        """获取缓存的市场深度"""
        key = f"{symbol}:{venue_id}"
        depth = self._depth_cache.get(key)
        if depth:
            last_update = self._last_update.get(key, 0)
            age = time.time() - last_update
            if age < self._cache_ttl_seconds:
                return depth
        return None
    
    async def fetch_all_depths(self, symbol: str) -> List[MarketDepth]:
        """获取所有交易所的市场深度"""
        depths = []
        for venue_id in self._venues:
            # 先查缓存
            depth = self.get_cached_depth(symbol, venue_id)
            if depth:
                depths.append(depth)
            elif self._price_feed:
                # 从价格源获取
                try:
                    depth = await self._price_feed.get_depth(symbol, venue_id)
                    if depth:
                        await self.update_depth(symbol, depth)
                        depths.append(depth)
                except Exception as e:
                    logger.warning(f"Failed to fetch depth for {symbol} @ {venue_id}: {e}")
        return depths
    
    async def route_order(
        self,
        order: Order,
        preferred_venues: Optional[List[str]] = None,
    ) -> Route:
        """
        为订单选择最优路由
        
        Args:
            order: 订单对象
            preferred_venues: 优先考虑的交易所列表
        
        Returns:
            Route: 路由决策
        """
        symbol = order.symbol
        side = order.side
        qty = order.quantity
        
        # 获取候选交易所
        candidates = self._get_candidates(order, preferred_venues)
        if not candidates:
            raise RoutingError(f"No available venue for {symbol}")
        
        # 获取市场深度
        depths = await self.fetch_all_depths(symbol)
        depth_by_venue = {d.venue: d for d in depths if d.venue in candidates}
        
        # 评估每个交易所
        scores: List[tuple] = []
        for venue_id, venue in candidates.items():
            depth = depth_by_venue.get(venue_id)
            if not depth:
                continue
            
            score, expected_price, expected_cost = self._evaluate_venue(
                venue, depth, side, qty, order.order_type
            )
            scores.append((venue_id, score, expected_price, expected_cost))
        
        if not scores:
            raise RoutingError(f"No price data for {symbol}")
        
        # 排序并选择最优
        scores.sort(key=lambda x: x[1], reverse=True)
        best_venue_id, best_score, best_price, best_cost = scores[0]
        best_venue = candidates[best_venue_id]
        
        # 构建备选方案
        alternatives = [
            {
                "venue_id": vid,
                "expected_price": price,
                "expected_cost": cost,
                "score": score,
            }
            for vid, score, price, cost in scores[1:]
        ]
        
        return Route(
            venue_id=best_venue_id,
            venue_name=best_venue.name,
            expected_price=best_price,
            expected_cost=best_cost,
            confidence=min(best_score, 1.0),
            reason=f"Best price with optimal execution cost",
            alternatives=alternatives[:3],
        )
    
    def _get_candidates(
        self,
        order: Order,
        preferred_venues: Optional[List[str]] = None,
    ) -> Dict[str, Venue]:
        """获取候选交易所"""
        candidates = {}
        
        venue_ids = preferred_venues or list(self._venues.keys())
        
        for venue_id in venue_ids:
            venue = self._venues.get(venue_id)
            if not venue:
                continue
            if venue.status != VenueStatus.AVAILABLE:
                continue
            if venue.account_type != order.account_type:
                continue
            if venue.latency_ms > self.config.max_latency_ms:
                continue
            # 检查数量限制
            if order.quantity < venue.min_order_size or order.quantity > venue.max_order_size:
                continue
            
            candidates[venue_id] = venue
        
        return candidates
    
    def _evaluate_venue(
        self,
        venue: Venue,
        depth: MarketDepth,
        side: Side,
        qty: Decimal,
        order_type: OrderType,
    ) -> tuple[float, Decimal, Decimal]:
        """
        评估交易所
        
        Returns:
            (score, expected_price, expected_cost)
        """
        # 获取执行价格
        if side == Side.BUY:
            best_level = depth.get_best_ask()
            # 估算滑点
            available_qty = sum(a.quantity for a in depth.asks)
        else:
            best_level = depth.get_best_bid()
            available_qty = sum(b.quantity for b in depth.bids)
        
        if not best_level:
            return 0.0, Decimal("0"), Decimal("0")
        
        expected_price = best_level.price
        
        # 计算滑点影响
        slippage = Decimal("0")
        if available_qty > 0:
            fill_ratio = min(qty / available_qty, Decimal("1"))
            slippage = fill_ratio * Decimal("0.001")  # 0.1% max slippage
        
        if side == Side.BUY:
            expected_price = expected_price * (1 + slippage)
        else:
            expected_price = expected_price * (1 - slippage)
        
        # 计算总成本（含手续费）
        is_maker = order_type != OrderType.MARKET
        fee = venue.calculate_fee(expected_price, qty, is_maker)
        expected_cost = expected_price * qty + fee
        
        # 计算评分
        # 价格评分（越低越好，买入时）
        mid_price = depth.get_mid_price() or expected_price
        if side == Side.BUY:
            price_score = float(mid_price / expected_price) if expected_price > 0 else 0.0
        else:
            price_score = float(expected_price / mid_price) if mid_price > 0 else 0.0
        
        # 延迟评分
        latency_score = max(0.0, 1.0 - venue.latency_ms / self.config.max_latency_ms)
        
        # 费用评分（相对于交易额）
        fee_rate = float(fee / (expected_price * qty)) if expected_price * qty > 0 else 0.0
        fee_score = max(0.0, 1.0 - fee_rate * 100)
        
        # 综合评分
        total_score = (
            price_score * float(self.config.price_weight) +
            latency_score * float(self.config.latency_weight) +
            fee_score * float(self.config.fee_weight)
        )
        
        return total_score, expected_price, expected_cost
    
    async def route_split_order(
        self,
        order: Order,
        slices: int,
    ) -> List[Route]:
        """
        为拆单选择多个路由
        
        Args:
            order: 原始订单
            slices: 拆分数
        
        Returns:
            List[Route]: 每个切片的路由决策
        """
        if slices <= 1:
            route = await self.route_order(order)
            return [route]
        
        qty_per_slice = order.quantity / slices
        
        # 获取候选交易所
        candidates = self._get_candidates(order)
        depths = await self.fetch_all_depths(order.symbol)
        
        routes = []
        for i in range(slices):
            # 选择当前最优的交易所
            best_route = None
            best_score = -1
            
            for depth in depths:
                if depth.venue not in candidates:
                    continue
                
                venue = candidates[depth.venue]
                score, price, cost = self._evaluate_venue(
                    venue, depth, order.side, qty_per_slice, order.order_type
                )
                
                if score > best_score:
                    best_score = score
                    best_route = Route(
                        venue_id=venue.venue_id,
                        venue_name=venue.name,
                        expected_price=price,
                        expected_cost=cost,
                        confidence=score,
                        reason=f"Slice {i+1}/{slices}",
                    )
            
            if best_route:
                routes.append(best_route)
            else:
                raise RoutingError(f"No route available for slice {i+1}")
        
        return routes
    
    def get_best_price(self, symbol: str, side: Side) -> Optional[Decimal]:
        """获取最优价格（不考虑手续费）"""
        depths = [d for d in self._depth_cache.values() if d.symbol == symbol]
        
        if side == Side.BUY:
            # 买入：找最低卖价
            best = None
            for depth in depths:
                ask = depth.get_best_ask()
                if ask and (best is None or ask.price < best):
                    best = ask.price
            return best
        else:
            # 卖出：找最高买价
            best = None
            for depth in depths:
                bid = depth.get_best_bid()
                if bid and (best is None or bid.price > best):
                    best = bid.price
            return best
    
    def compare_venues(self, symbol: str) -> List[Dict]:
        """比较各交易所的价格和费用"""
        depths = [d for d in self._depth_cache.values() if d.symbol == symbol]
        
        comparison = []
        for depth in depths:
            venue = self._venues.get(depth.venue)
            if not venue:
                continue
            
            comparison.append({
                "venue_id": venue.venue_id,
                "venue_name": venue.name,
                "bid": depth.get_best_bid().price if depth.get_best_bid() else None,
                "ask": depth.get_best_ask().price if depth.get_best_ask() else None,
                "spread": depth.get_spread(),
                "maker_fee": venue.maker_fee_rate,
                "taker_fee": venue.taker_fee_rate,
                "latency_ms": venue.latency_ms,
            })
        
        return comparison


class RoutingError(Exception):
    """路由错误"""
    pass


# 简单的内存价格源实现
class SimplePriceFeed:
    """简单价格源（用于测试）"""
    
    def __init__(self) -> None:
        self._prices: Dict[str, Decimal] = {}
        self._depths: Dict[str, MarketDepth] = {}
    
    def set_price(self, symbol: str, venue: str, price: Decimal) -> None:
        """设置价格"""
        key = f"{symbol}:{venue}"
        self._prices[key] = price
    
    def set_depth(self, symbol: str, venue: str, depth: MarketDepth) -> None:
        """设置市场深度"""
        key = f"{symbol}:{venue}"
        self._depths[key] = depth
    
    async def get_depth(self, symbol: str, venue: str) -> Optional[MarketDepth]:
        key = f"{symbol}:{venue}"
        return self._depths.get(key)
    
    async def get_price(self, symbol: str, venue: str) -> Optional[Decimal]:
        key = f"{symbol}:{venue}"
        return self._prices.get(key)
