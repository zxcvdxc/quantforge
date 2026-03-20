"""
Execution Module Tests
测试订单生命周期、智能路由、订单拆分
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import sys
sys.path.insert(0, 'src')

from qf_execution import (
    AccountType,
    ExecutionConfig,
    ExecutionEngine,
    IcebergOrder,
    MarketDepth,
    Order,
    OrderManager,
    OrderManagerConfig,
    OrderResult,
    OrderSlice,
    OrderSplitter,
    OrderStatus,
    OrderType,
    PriceLevel,
    Route,
    RoutingConfig,
    RoutingError,
    Side,
    SimplePriceFeed,
    SmartRouter,
    TWAPOrder,
    Venue,
    VenueStatus,
)


# ============ Fixtures ============

@pytest.fixture
def sample_order():
    """创建示例订单"""
    return Order(
        symbol="600519.SH",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("100"),
        price=Decimal("1500.00"),
        account_id="test_account",
        account_type=AccountType.A_STOCK,
        venue="xtp",
    )


@pytest.fixture
def sample_venue():
    """创建示例交易所"""
    return Venue(
        venue_id="xtp",
        name="XTP A股",
        account_type=AccountType.A_STOCK,
        maker_fee_rate=Decimal("0.0001"),
        taker_fee_rate=Decimal("0.0002"),
        min_order_size=Decimal("100"),
        max_order_size=Decimal("1000000"),
    )


@pytest.fixture
def order_manager():
    """创建订单管理器"""
    return OrderManager()


@pytest.fixture
def smart_router(sample_venue):
    """创建智能路由器"""
    import asyncio
    router = SmartRouter()
    router.register_venue(sample_venue)
    
    # 设置价格源
    price_feed = SimplePriceFeed()
    depth = MarketDepth(
        symbol="600519.SH",
        bids=[PriceLevel(price=Decimal("1499.00"), quantity=Decimal("500"), venue="xtp")],
        asks=[PriceLevel(price=Decimal("1500.00"), quantity=Decimal("500"), venue="xtp")],
        venue="xtp",
    )
    price_feed.set_depth("600519.SH", "xtp", depth)
    router.set_price_feed(price_feed)
    
    # 直接更新缓存
    asyncio.run(router.update_depth("600519.SH", depth))
    
    return router


@pytest.fixture
def order_splitter():
    """创建订单拆分器"""
    return OrderSplitter()


@pytest.fixture
def execution_engine():
    """创建执行引擎"""
    config = ExecutionConfig(
        enable_smart_routing=True,
        enable_order_split=True,
    )
    return ExecutionEngine(config)


# ============ Order Model Tests ============

class TestOrderModel:
    """订单模型测试"""
    
    def test_order_creation(self):
        """测试订单创建"""
        order = Order(
            symbol="000001.SZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1000"),
            price=Decimal("10.50"),
        )
        
        assert order.symbol == "000001.SZ"
        assert order.side == Side.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == Decimal("1000")
        assert order.price == Decimal("10.50")
        assert order.status == OrderStatus.PENDING
        assert order.filled_quantity == Decimal("0")
        assert order.remaining_quantity == Decimal("1000")
    
    def test_order_str_repr(self):
        """测试订单的字符串表示"""
        order = Order(symbol="000001.SZ", side=Side.BUY, quantity=Decimal("100"))
        # 测试 repr 不报错
        repr(order)
    
    def test_order_total_commission(self):
        """测试总手续费计算"""
        from qf_execution.models import Fill
        order = Order(symbol="000001.SZ", side=Side.BUY, quantity=Decimal("1000"))
        
        # 无成交时
        assert order.total_commission() == Decimal("0")
        
        # 添加成交
        order.add_fill(Fill(
            order_id=order.order_id,
            price=Decimal("10.00"),
            quantity=Decimal("500"),
            commission=Decimal("5.00"),
        ))
        order.add_fill(Fill(
            order_id=order.order_id,
            price=Decimal("11.00"),
            quantity=Decimal("500"),
            commission=Decimal("5.50"),
        ))
        
        assert order.total_commission() == Decimal("10.50")
    
    def test_order_add_fill(self):
        """测试添加成交记录"""
        order = Order(
            symbol="000001.SZ",
            side=Side.BUY,
            quantity=Decimal("1000"),
        )
        
        # 第一次部分成交
        from qf_execution.models import Fill
        fill1 = Fill(
            order_id=order.order_id,
            price=Decimal("10.50"),
            quantity=Decimal("300"),
            commission=Decimal("3.15"),
        )
        order.add_fill(fill1)
        
        assert order.status == OrderStatus.PARTIAL_FILLED
        assert order.filled_quantity == Decimal("300")
        assert order.remaining_quantity == Decimal("700")
        assert len(order.fills) == 1
        
        # 第二次部分成交
        fill2 = Fill(
            order_id=order.order_id,
            price=Decimal("10.51"),
            quantity=Decimal("700"),
            commission=Decimal("7.36"),
        )
        order.add_fill(fill2)
        
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == Decimal("1000")
        assert order.remaining_quantity == Decimal("0")
        assert len(order.fills) == 2
    
    def test_order_avg_fill_price(self):
        """测试平均成交价格计算"""
        from qf_execution.models import Fill
        order = Order(
            symbol="000001.SZ",
            side=Side.BUY,
            quantity=Decimal("1000"),
        )
        
        # 无成交
        assert order.avg_fill_price() is None
        
        # 添加成交
        order.add_fill(Fill(
            order_id=order.order_id,
            price=Decimal("10.00"),
            quantity=Decimal("500"),
        ))
        order.add_fill(Fill(
            order_id=order.order_id,
            price=Decimal("11.00"),
            quantity=Decimal("500"),
        ))
        
        avg_price = order.avg_fill_price()
        assert avg_price == Decimal("10.50")
    
    def test_order_is_active(self):
        """测试订单活动状态判断"""
        order = Order(symbol="000001.SZ", side=Side.BUY, quantity=Decimal("100"))
        
        # PENDING 是活动状态
        order.status = OrderStatus.PENDING
        assert order.is_active() is True
        
        # SUBMITTED 是活动状态
        order.status = OrderStatus.SUBMITTED
        assert order.is_active() is True
        
        # PARTIAL_FILLED 是活动状态
        order.status = OrderStatus.PARTIAL_FILLED
        assert order.is_active() is True
        
        # FILLED 不是活动状态
        order.status = OrderStatus.FILLED
        assert order.is_active() is False
        
        # CANCELED 不是活动状态
        order.status = OrderStatus.CANCELED
        assert order.is_active() is False


# ============ Order Manager Tests ============

class TestOrderManager:
    """订单管理器测试"""
    
    @pytest.mark.asyncio
    async def test_create_and_register_order(self, order_manager):
        """测试创建和注册订单"""
        order = order_manager.create_order(
            symbol="600519.SH",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),
            price=Decimal("1500"),
        )
        
        result = await order_manager.register_order(order)
        
        assert result.success is True
        assert result.order_id == order.order_id
        assert order_manager.get_order(order.order_id) == order
    
    @pytest.mark.asyncio
    async def test_update_order_status(self, order_manager, sample_order):
        """测试更新订单状态"""
        await order_manager.register_order(sample_order)
        
        result = await order_manager.update_order_status(
            sample_order.order_id, OrderStatus.SUBMITTED
        )
        
        assert result.success is True
        assert sample_order.status == OrderStatus.SUBMITTED
    
    @pytest.mark.asyncio
    async def test_add_fill(self, order_manager, sample_order):
        """测试添加成交记录"""
        await order_manager.register_order(sample_order)
        await order_manager.update_order_status(
            sample_order.order_id, OrderStatus.SUBMITTED
        )
        
        result = await order_manager.add_fill(
            sample_order.order_id,
            price=Decimal("1500"),
            quantity=Decimal("100"),
            commission=Decimal("30"),
        )
        
        assert result.success is True
        assert sample_order.status == OrderStatus.FILLED
        assert sample_order.filled_quantity == Decimal("100")
    
    @pytest.mark.asyncio
    async def test_cancel_order(self, order_manager, sample_order):
        """测试撤销订单"""
        await order_manager.register_order(sample_order)
        await order_manager.update_order_status(
            sample_order.order_id, OrderStatus.SUBMITTED
        )
        
        result = await order_manager.cancel_order(sample_order.order_id)
        
        assert result.success is True
        assert sample_order.status == OrderStatus.CANCELING
    
    @pytest.mark.asyncio
    async def test_get_orders_by_filter(self, order_manager):
        """测试按条件查询订单"""
        # 创建多个订单
        orders = []
        for i in range(5):
            order = order_manager.create_order(
                symbol=f"STOCK{i}.SH",
                side=Side.BUY if i % 2 == 0 else Side.SELL,
                order_type=OrderType.LIMIT,
                quantity=Decimal("100"),
                price=Decimal("10"),
                account_id=f"account{i % 2}",
            )
            await order_manager.register_order(order)
            orders.append(order)
        
        # 按交易代码查询
        symbol_orders = order_manager.get_orders(symbol="STOCK0.SH")
        assert len(symbol_orders) == 1
        
        # 按账户查询
        account_orders = order_manager.get_orders(account_id="account0")
        assert len(account_orders) == 3  # index 0, 2, 4
        
        # 查询活动订单
        await order_manager.update_order_status(orders[0].order_id, OrderStatus.FILLED)
        active_orders = order_manager.get_orders(active_only=True)
        assert len(active_orders) == 4
    
    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, order_manager):
        """测试批量撤销订单"""
        # 创建订单
        for i in range(3):
            order = order_manager.create_order(
                symbol="TEST.SH",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("100"),
                price=Decimal("10"),
            )
            await order_manager.register_order(order)
            await order_manager.update_order_status(order.order_id, OrderStatus.SUBMITTED)
        
        # 撤销所有
        results = await order_manager.cancel_all_orders()
        
        assert len(results) == 3
        assert all(r.success for r in results)
    
    def test_get_stats(self, order_manager):
        """测试统计信息"""
        stats = order_manager.get_stats()
        
        assert "total_orders" in stats
        assert "filled_orders" in stats
        assert "canceled_orders" in stats
        assert "rejected_orders" in stats


# ============ Smart Router Tests ============

class TestSmartRouter:
    """智能路由器测试"""
    
    @pytest.mark.asyncio
    async def test_register_venue(self):
        """测试注册交易所"""
        router = SmartRouter()
        venue = Venue(
            venue_id="test",
            name="Test Venue",
            account_type=AccountType.A_STOCK,
        )
        
        router.register_venue(venue)
        venues = router.get_venues()
        
        assert len(venues) == 1
        assert venues[0].venue_id == "test"
    
    @pytest.mark.asyncio
    async def test_route_order_best_price(self, smart_router, sample_order):
        """测试最优价格路由"""
        route = await smart_router.route_order(sample_order)
        
        assert isinstance(route, Route)
        assert route.venue_id == "xtp"
        assert route.expected_price > 0
        assert route.confidence > 0
    
    @pytest.mark.asyncio
    async def test_route_order_no_venue(self, sample_order):
        """测试无可用地���所时的路由"""
        router = SmartRouter()
        # 不注册任何交易所
        
        with pytest.raises(RoutingError):
            await router.route_order(sample_order)
    
    @pytest.mark.asyncio
    async def test_get_best_price(self, smart_router):
        """测试获取最优价格"""
        best_bid = smart_router.get_best_price("600519.SH", Side.SELL)
        best_ask = smart_router.get_best_price("600519.SH", Side.BUY)
        
        assert best_bid == Decimal("1499.00")
        assert best_ask == Decimal("1500.00")
    
    @pytest.mark.asyncio
    async def test_compare_venues(self, smart_router):
        """测试交易所比较"""
        comparison = smart_router.compare_venues("600519.SH")
        
        assert len(comparison) >= 1
        assert "venue_id" in comparison[0]
        assert "bid" in comparison[0]
        assert "ask" in comparison[0]
    
    @pytest.mark.asyncio
    async def test_route_split_order(self, smart_router, sample_order):
        """测试拆单路由"""
        routes = await smart_router.route_split_order(sample_order, slices=3)
        
        assert len(routes) == 3
        assert all(isinstance(r, Route) for r in routes)


# ============ Order Splitter Tests ============

class TestOrderSplitter:
    """订单拆分器测试"""
    
    def test_equal_split(self, order_splitter):
        """测试等分拆分"""
        order = Order(
            symbol="000001.SZ",
            side=Side.BUY,
            quantity=Decimal("1000"),
            price=Decimal("10"),
        )
        
        slices = order_splitter.split(order, strategy="equal", num_slices=4)
        
        assert len(slices) == 4
        assert sum(s.quantity for s in slices) == Decimal("1000")
        assert all(s.parent_order_id == order.order_id for s in slices)
    
    def test_iceberg_split(self, order_splitter):
        """测试冰山单拆分"""
        order = Order(
            symbol="000001.SZ",
            side=Side.BUY,
            quantity=Decimal("10000"),
            price=Decimal("10"),
        )
        
        slices = order_splitter.split(order, strategy="iceberg", display_qty=Decimal("1000"))
        
        assert len(slices) == 10
        assert all(s.quantity <= Decimal("1000") for s in slices)
    
    def test_twap_split(self, order_splitter):
        """测试TWAP拆分"""
        order = Order(
            symbol="000001.SZ",
            side=Side.BUY,
            quantity=Decimal("1000"),
            price=Decimal("10"),
        )
        
        slices = order_splitter.split(
            order,
            strategy="twap",
            duration_seconds=300,
            num_slices=5
        )
        
        assert len(slices) == 5
        assert all(s.scheduled_time is not None for s in slices)
    
    def test_get_slices_by_parent(self, order_splitter):
        """测试获取父订单切片"""
        order = Order(
            symbol="000001.SZ",
            side=Side.BUY,
            quantity=Decimal("1000"),
        )
        
        slices = order_splitter.split(order, strategy="equal", num_slices=3)
        retrieved = order_splitter.get_slices_by_parent(order.order_id)
        
        assert len(retrieved) == 3
        assert set(s.slice_id for s in slices) == set(s.slice_id for s in retrieved)
    
    def test_parent_progress(self, order_splitter):
        """测试父订单进度"""
        order = Order(
            symbol="000001.SZ",
            side=Side.BUY,
            quantity=Decimal("1000"),
        )
        
        slices = order_splitter.split(order, strategy="equal", num_slices=4)
        
        # 更新部分切片状态
        order_splitter.update_slice_status(slices[0].slice_id, OrderStatus.FILLED)
        order_splitter.update_slice_status(slices[1].slice_id, OrderStatus.FILLED)
        
        progress = order_splitter.get_parent_progress(order.order_id)
        
        assert progress["total"] == 4
        assert progress["completed"] == 2
        assert progress["progress"] == 0.5
    
    def test_cancel_remaining_slices(self, order_splitter):
        """测试取消剩余切片"""
        order = Order(
            symbol="000001.SZ",
            side=Side.BUY,
            quantity=Decimal("1000"),
        )
        
        slices = order_splitter.split(order, strategy="equal", num_slices=4)
        
        # 完成第一个
        order_splitter.update_slice_status(slices[0].slice_id, OrderStatus.FILLED)
        
        # 取消剩余
        canceled = order_splitter.cancel_remaining_slices(order.order_id)
        
        assert canceled == 3


# ============ Execution Engine Tests ============

class TestExecutionEngine:
    """执行引擎测试"""
    
    @pytest.mark.asyncio
    async def test_send_order(self, execution_engine, sample_order):
        """测试发送订单"""
        # 创建模拟网关
        mock_gateway = AsyncMock()
        mock_gateway.is_connected.return_value = True
        mock_gateway.send_order.return_value = OrderResult(
            success=True, order_id=sample_order.order_id
        )
        
        execution_engine.register_gateway(
            AccountType.A_STOCK, mock_gateway, set_default=True
        )
        
        result = await execution_engine.send_order(sample_order, smart_route=False)
        
        assert result.success is True
        mock_gateway.send_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cancel_order(self, execution_engine, sample_order):
        """测试撤销订单"""
        mock_gateway = AsyncMock()
        mock_gateway.is_connected.return_value = True
        mock_gateway.send_order.return_value = OrderResult(
            success=True, order_id=sample_order.order_id
        )
        mock_gateway.cancel_order.return_value = OrderResult(
            success=True, order_id=sample_order.order_id
        )
        
        execution_engine.register_gateway(
            AccountType.A_STOCK, mock_gateway, set_default=True
        )
        
        # 先发送订单
        await execution_engine.send_order(sample_order, smart_route=False)
        
        # 再撤销
        result = await execution_engine.cancel_order(sample_order.order_id)
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_get_order(self, execution_engine, sample_order):
        """测试查询订单"""
        mock_gateway = AsyncMock()
        mock_gateway.is_connected.return_value = True
        mock_gateway.send_order.return_value = OrderResult(
            success=True, order_id=sample_order.order_id
        )
        
        execution_engine.register_gateway(
            AccountType.A_STOCK, mock_gateway, set_default=True
        )
        
        await execution_engine.send_order(sample_order, smart_route=False)
        
        retrieved = execution_engine.get_order(sample_order.order_id)
        
        assert retrieved is not None
        assert retrieved.symbol == sample_order.symbol
    
    @pytest.mark.asyncio
    async def test_order_with_smart_routing(self, execution_engine, sample_order, sample_venue):
        """测试智能路由下单"""
        mock_gateway = AsyncMock()
        mock_gateway.is_connected.return_value = True
        mock_gateway.send_order.return_value = OrderResult(
            success=True, order_id="routed_order_id"
        )
        
        execution_engine.register_gateway(
            AccountType.A_STOCK, mock_gateway, set_default=True
        )
        execution_engine.register_venue(sample_venue)
        
        # 设置价格源
        price_feed = SimplePriceFeed()
        depth = MarketDepth(
            symbol="600519.SH",
            bids=[PriceLevel(price=Decimal("1499"), quantity=Decimal("500"), venue="xtp")],
            asks=[PriceLevel(price=Decimal("1500"), quantity=Decimal("500"), venue="xtp")],
            venue="xtp",
        )
        price_feed.set_depth("600519.SH", "xtp", depth)
        execution_engine._router.set_price_feed(price_feed)
        
        # 不清除venue，让智能路由选择
        sample_order.venue = ""
        
        result = await execution_engine.send_order(sample_order, smart_route=True)
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_send_split_order(self, execution_engine, sample_order):
        """测试拆分订单发送"""
        mock_gateway = AsyncMock()
        mock_gateway.is_connected.return_value = True
        mock_gateway.send_order.return_value = OrderResult(
            success=True, order_id="slice_order_id"
        )
        
        execution_engine.register_gateway(
            AccountType.A_STOCK, mock_gateway, set_default=True
        )
        
        result = await execution_engine.send_order(
            sample_order,
            smart_route=False,
            split_strategy="equal",
            num_slices=4,
        )
        
        assert result.success is True
        assert result.data["total_slices"] == 4
    
    @pytest.mark.asyncio
    async def test_get_stats(self, execution_engine):
        """测试获取统计信息"""
        stats = execution_engine.get_stats()
        
        assert "orders_sent" in stats
        assert "orders_filled" in stats
        assert "total_volume" in stats
    
    @pytest.mark.asyncio
    async def test_callbacks(self, execution_engine, sample_order):
        """测试回调功能"""
        order_updates = []
        fills = []
        
        def on_order(order):
            order_updates.append(order)
        
        def on_fill(order, fill):
            fills.append((order, fill))
        
        execution_engine.on_order_status_change(on_order)
        execution_engine.on_fill(on_fill)
        
        # 发送订单并模拟成交
        mock_gateway = AsyncMock()
        mock_gateway.is_connected.return_value = True
        mock_gateway.send_order.return_value = OrderResult(
            success=True, order_id=sample_order.order_id
        )
        
        execution_engine.register_gateway(
            AccountType.A_STOCK, mock_gateway, set_default=True
        )
        
        await execution_engine.send_order(sample_order, smart_route=False)
        
        # 模拟成交
        await execution_engine._order_manager.add_fill(
            sample_order.order_id,
            price=Decimal("1500"),
            quantity=Decimal("100"),
        )
        
        assert len(order_updates) >= 1
        assert len(fills) == 1


# ============ Integration Tests ============

class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_order_lifecycle(self):
        """测试完整订单生命周期"""
        # 创建引擎
        engine = ExecutionEngine()
        
        # 创建模拟网关
        mock_gateway = AsyncMock()
        mock_gateway.is_connected.return_value = True
        mock_gateway.send_order.return_value = OrderResult(
            success=True, order_id="lifecycle_order"
        )
        mock_gateway.cancel_order.return_value = OrderResult(
            success=True, order_id="lifecycle_order"
        )
        
        engine.register_gateway(AccountType.A_STOCK, mock_gateway, set_default=True)
        
        # 1. 创建订单
        order = Order(
            symbol="000001.SZ",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1000"),
            price=Decimal("10.50"),
            account_type=AccountType.A_STOCK,
        )
        
        # 2. 发送订单
        result = await engine.send_order(order, smart_route=False)
        assert result.success is True
        assert order.status == OrderStatus.SUBMITTED
        
        # 3. 查询订单
        retrieved = engine.get_order(order.order_id)
        assert retrieved is not None
        
        # 4. 部分成交
        await engine._order_manager.add_fill(
            order.order_id,
            price=Decimal("10.50"),
            quantity=Decimal("500"),
            commission=Decimal("5.25"),
        )
        assert order.status == OrderStatus.PARTIAL_FILLED
        assert order.filled_quantity == Decimal("500")
        
        # 5. 完全成交
        await engine._order_manager.add_fill(
            order.order_id,
            price=Decimal("10.50"),
            quantity=Decimal("500"),
            commission=Decimal("5.25"),
        )
        assert order.status == OrderStatus.FILLED
        
        # 检查统计
        stats = engine.get_stats()
        assert stats["orders_filled"] == 1
        assert stats["total_volume"] == Decimal("1000")
        
        await engine.reset()
    
    @pytest.mark.asyncio
    async def test_multi_account_support(self):
        """测试多账户支持"""
        engine = ExecutionEngine()
        
        # 为不同账户类型注册网关
        stock_gateway = AsyncMock()
        stock_gateway.is_connected.return_value = True
        stock_gateway.send_order.return_value = OrderResult(success=True, order_id="stock_order")
        
        futures_gateway = AsyncMock()
        futures_gateway.is_connected.return_value = True
        futures_gateway.send_order.return_value = OrderResult(success=True, order_id="futures_order")
        
        crypto_gateway = AsyncMock()
        crypto_gateway.is_connected.return_value = True
        crypto_gateway.send_order.return_value = OrderResult(success=True, order_id="crypto_order")
        
        engine.register_gateway(AccountType.A_STOCK, stock_gateway)
        engine.register_gateway(AccountType.FUTURES, futures_gateway)
        engine.register_gateway(AccountType.CRYPTO, crypto_gateway)
        
        # A股订单
        stock_order = Order(
            symbol="600519.SH",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),
            price=Decimal("1500"),
            account_type=AccountType.A_STOCK,
        )
        
        # 期货订单
        futures_order = Order(
            symbol="IF2506",
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            price=Decimal("3500"),
            account_type=AccountType.FUTURES,
        )
        
        # 数字货币订单
        crypto_order = Order(
            symbol="BTC-USDT",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("60000"),
            account_type=AccountType.CRYPTO,
        )
        
        # 发送订单
        await engine.send_order(stock_order, smart_route=False)
        await engine.send_order(futures_order, smart_route=False)
        await engine.send_order(crypto_order, smart_route=False)
        
        # 验证每个网关都被调用
        stock_gateway.send_order.assert_called_once()
        futures_gateway.send_order.assert_called_once()
        crypto_gateway.send_order.assert_called_once()
        
        await engine.reset()


class TestAdditionalCoverage:
    """额外覆盖率测试"""
    
    def test_venue_calculate_fee(self):
        """测试交易所费用计算"""
        venue = Venue(
            venue_id="test",
            name="Test",
            account_type=AccountType.A_STOCK,
            maker_fee_rate=Decimal("0.001"),
            taker_fee_rate=Decimal("0.002"),
        )
        
        maker_fee = venue.calculate_fee(Decimal("100"), Decimal("10"), is_maker=True)
        taker_fee = venue.calculate_fee(Decimal("100"), Decimal("10"), is_maker=False)
        
        assert maker_fee == Decimal("1.000")
        assert taker_fee == Decimal("2.000")
    
    def test_market_depth(self):
        """测试市场深度"""
        depth = MarketDepth(
            symbol="TEST",
            bids=[
                PriceLevel(price=Decimal("100"), quantity=Decimal("10"), venue="v1"),
                PriceLevel(price=Decimal("99"), quantity=Decimal("20"), venue="v1"),
            ],
            asks=[
                PriceLevel(price=Decimal("101"), quantity=Decimal("15"), venue="v1"),
                PriceLevel(price=Decimal("102"), quantity=Decimal("25"), venue="v1"),
            ],
            venue="v1",
        )
        
        assert depth.get_best_bid().price == Decimal("100")
        assert depth.get_best_ask().price == Decimal("101")
        assert depth.get_spread() == Decimal("1")
        assert depth.get_mid_price() == Decimal("100.5")
    
    def test_market_depth_empty(self):
        """测试空市场深度"""
        depth = MarketDepth(symbol="TEST", venue="v1")
        
        assert depth.get_best_bid() is None
        assert depth.get_best_ask() is None
        assert depth.get_spread() is None
        assert depth.get_mid_price() is None
    
    def test_price_level(self):
        """测试价格档位"""
        level = PriceLevel(price=Decimal("100"), quantity=Decimal("10"), venue="v1")
        assert level.value == Decimal("1000")
    
    @pytest.mark.asyncio
    async def test_order_manager_order_not_found(self):
        """测试订单不存在的情况"""
        om = OrderManager()
        
        # 测试更新不存在的订单
        result = await om.update_order_status("nonexistent", OrderStatus.SUBMITTED)
        assert result.success is False
        assert "not found" in result.message
        
        # 测试添加成交到不存在的订单
        result = await om.add_fill("nonexistent", Decimal("10"), Decimal("100"))
        assert result.success is False
    
    @pytest.mark.asyncio
    async def test_order_manager_cancel_not_active(self):
        """测试取消非活动订单"""
        om = OrderManager()
        order = om.create_order(
            symbol="TEST",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),
        )
        await om.register_order(order)
        await om.update_order_status(order.order_id, OrderStatus.FILLED)
        
        result = await om.cancel_order(order.order_id)
        assert result.success is False
        assert "not active" in result.message
    
    def test_order_manager_clear_completed(self):
        """测试清理已完成订单"""
        om = OrderManager()
        
        # 创建并填充订单
        order = om.create_order(
            symbol="TEST",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100")
        )
        import asyncio
        asyncio.run(om.register_order(order))
        asyncio.run(om.update_order_status(order.order_id, OrderStatus.FILLED))
        
        # 修改时间戳使其过期
        order.updated_at = order.updated_at - timedelta(hours=25)
        
        count = om.clear_completed_orders(max_age_hours=24)
        assert count == 1
    
    @pytest.mark.asyncio
    async def test_smart_router_fetch_depths(self):
        """测试获取市场深度"""
        router = SmartRouter()
        venue = Venue(venue_id="v1", name="Venue1", account_type=AccountType.A_STOCK)
        router.register_venue(venue)
        
        price_feed = SimplePriceFeed()
        depth = MarketDepth(
            symbol="TEST",
            bids=[PriceLevel(price=Decimal("100"), quantity=Decimal("10"), venue="v1")],
            asks=[PriceLevel(price=Decimal("101"), quantity=Decimal("10"), venue="v1")],
            venue="v1",
        )
        price_feed.set_depth("TEST", "v1", depth)
        router.set_price_feed(price_feed)
        
        depths = await router.fetch_all_depths("TEST")
        assert len(depths) == 1
    
    def test_smart_router_no_candidates(self):
        """测试无候选交易所"""
        router = SmartRouter()
        
        order = Order(
            symbol="TEST",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),
            account_type=AccountType.A_STOCK,
        )
        
        # 没有注册任何交易所
        with pytest.raises(RoutingError):
            import asyncio
            asyncio.run(router.route_order(order))
    
    def test_order_splitter_vwap(self):
        """测试VWAP拆分"""
        splitter = OrderSplitter()
        order = Order(
            symbol="TEST",
            side=Side.BUY,
            quantity=Decimal("1000"),
        )
        
        volume_profile = [0.1, 0.2, 0.3, 0.2, 0.2]
        slices = splitter.split(
            order,
            strategy="vwap",
            duration_seconds=300,
            volume_profile=volume_profile,
        )
        
        assert len(slices) == 5
        assert sum(s.quantity for s in slices) == Decimal("1000")
    
    def test_order_splitter_pov(self):
        """测试POV拆分"""
        splitter = OrderSplitter()
        order = Order(
            symbol="TEST",
            side=Side.BUY,
            quantity=Decimal("1000"),
        )
        
        market_volumes = [Decimal("500"), Decimal("600"), Decimal("700")]
        slices = splitter.split(
            order,
            strategy="pov",
            pov_ratio=0.1,
            market_volumes=market_volumes,
        )
        
        assert len(slices) > 0
        assert sum(s.quantity for s in slices) == Decimal("1000")
    
    def test_order_splitter_unknown_strategy(self):
        """测试未知策略"""
        splitter = OrderSplitter()
        order = Order(symbol="TEST", side=Side.BUY, quantity=Decimal("100"))
        
        with pytest.raises(ValueError):
            splitter.split(order, strategy="unknown")
    
    def test_order_splitter_is_parent_complete(self):
        """测试父订单完成状态"""
        splitter = OrderSplitter()
        order = Order(symbol="TEST", side=Side.BUY, quantity=Decimal("1000"))
        
        slices = splitter.split(order, strategy="equal", num_slices=3)
        
        # 初始状态
        assert splitter.is_parent_complete(order.order_id) is False
        
        # 完成所有切片
        for s in slices:
            splitter.update_slice_status(s.slice_id, OrderStatus.FILLED)
        
        assert splitter.is_parent_complete(order.order_id) is True
    
    def test_order_splitter_reset(self):
        """测试拆分器重置"""
        splitter = OrderSplitter()
        order = Order(symbol="TEST", side=Side.BUY, quantity=Decimal("100"))
        
        splitter.split(order, strategy="equal", num_slices=2)
        assert len(splitter.get_slices_by_parent(order.order_id)) == 2
        
        splitter.reset()
        assert len(splitter.get_slices_by_parent(order.order_id)) == 0
    
    @pytest.mark.asyncio
    async def test_execution_engine_risk_check(self):
        """测试执行引擎风控"""
        config = ExecutionConfig(max_order_value=Decimal("1000"))
        engine = ExecutionEngine(config)
        
        # 超过金额限制的订单
        order = Order(
            symbol="TEST",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),
            price=Decimal("20"),  # 总价值2000，超过限制
            account_type=AccountType.A_STOCK,
        )
        
        result = await engine.send_order(order, smart_route=False)
        assert result.success is False
        assert "limit" in result.message.lower() or "RISK" in result.error_code
        
        await engine.reset()
    
    @pytest.mark.asyncio
    async def test_execution_engine_no_gateway(self):
        """测试无网关情况"""
        engine = ExecutionEngine()
        
        order = Order(
            symbol="TEST",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),
            account_type=AccountType.A_STOCK,
        )
        
        # 没有注册网关
        result = await engine.send_order(order, smart_route=False)
        assert result.success is False
        assert "gateway" in result.message.lower() or "NO_GATEWAY" in result.error_code
        
        await engine.reset()
    
    @pytest.mark.asyncio
    async def test_execution_engine_gateway_not_connected(self):
        """测试网关未连接"""
        engine = ExecutionEngine()
        
        mock_gateway = AsyncMock()
        mock_gateway.is_connected = MagicMock(return_value=False)
        engine.register_gateway(AccountType.A_STOCK, mock_gateway, set_default=True)
        
        order = Order(
            symbol="TEST",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),
            account_type=AccountType.A_STOCK,
        )
        
        result = await engine.send_order(order, smart_route=False)
        # 订单会被注册但发送会失败
        assert result.success is False
        
        await engine.reset()
    
    @pytest.mark.asyncio
    async def test_execution_engine_get_order_not_found(self):
        """测试获取不存在的订单"""
        engine = ExecutionEngine()
        
        result = engine.get_order("nonexistent")
        assert result is None
        
        await engine.reset()
    
    @pytest.mark.asyncio
    async def test_execution_engine_routing_stats(self):
        """测试路由统计"""
        engine = ExecutionEngine()
        
        # 注册交易所
        venue = Venue(venue_id="v1", name="Venue1", account_type=AccountType.A_STOCK)
        engine.register_venue(venue)
        
        stats = engine.get_routing_stats()
        assert "venues" in stats
        assert "v1" in stats["venues"]
        
        await engine.reset()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
