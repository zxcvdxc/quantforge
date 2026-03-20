"""
可观测性模块使用示例
"""

import asyncio
from datetime import datetime

# ============================================================
# 1. 结构化日志示例
# ============================================================

def logging_example():
    """结构化日志使用示例"""
    from qf_observability.logging import (
        configure_logging,
        get_logger,
        set_context,
        clear_context,
        mask_sensitive_fields,
    )
    
    # 配置日志
    configure_logging(
        name='quantforge',
        level='INFO',
        json_output=True,
    )
    
    # 设置上下文（trace_id会传递到所有后续日志）
    set_context(
        trace_id='abc123def456',
        span_id='span789',
        request_id='req-001',
    )
    
    # 获取日志记录器
    logger = get_logger('trading')
    
    # 记录业务日志
    logger.info('交易开始', symbol='BTC/USD', quantity=1.5)
    logger.info('订单已提交', order_id='ORD-12345', price=50000.0)
    
    # 脱敏敏感数据
    sensitive_data = {
        'username': 'trader1',
        'password': 'secret123',
        'api_key': 'sk-1234567890abcdef',
        'email': 'trader@example.com',
    }
    masked = mask_sensitive_fields(sensitive_data)
    logger.info('用户数据', data=masked)
    
    # 清除上下文
    clear_context()


# ============================================================
# 2. 指标采集示例
# ============================================================

def metrics_example():
    """指标采集使用示例"""
    from qf_observability.metrics import (
        start_metrics_server,
        TradingMetrics,
        TradeRecord,
        LatencyMetrics,
        SystemMetrics,
        get_collector,
    )
    
    # 启动Prometheus指标服务器（访问 http://localhost:9090/metrics）
    start_metrics_server(port=9090)
    
    # 交易指标
    trading = TradingMetrics()
    
    # 记录成功交易
    trade = TradeRecord(
        trade_id='trade-001',
        symbol='BTC/USD',
        side='buy',
        quantity=1.0,
        price=50000.0,
        timestamp=datetime.utcnow(),
        latency_ms=45.5,
        status='success',
    )
    trading.record_trade(trade)
    
    # 记录失败交易
    failed_trade = TradeRecord(
        trade_id='trade-002',
        symbol='ETH/USD',
        side='sell',
        quantity=10.0,
        price=3000.0,
        timestamp=datetime.utcnow(),
        latency_ms=1000.0,  # 超时
        status='failed',
        error='Connection timeout',
    )
    trading.record_trade(failed_trade)
    
    # 查看成功率
    print(f"交易成功率: {trading.get_success_rate() * 100:.2f}%")
    print(f"总交易量: {trading.trade_volume.get()}")
    
    # 延迟指标
    latency = LatencyMetrics()
    latency.record_api_latency(0.05, endpoint='/api/trades')
    latency.record_db_latency(0.02, operation='select')
    latency.record_network_latency(0.03, peer='exchange-1')
    
    # 系统指标
    system = SystemMetrics()
    metrics = system.collect()
    print(f"CPU使用率: {metrics['cpu_percent']:.2f}%")
    print(f"内存使用: {metrics['memory']['percent']:.2f}%")
    
    # 注册系统采集器
    collector = get_collector()
    from qf_observability.metrics import ResourceUsageCollector
    collector.register_collector(ResourceUsageCollector())
    
    # 采集所有指标
    all_metrics = collector.collect_all()
    print(f"采集到的指标: {list(all_metrics.keys())}")


# ============================================================
# 3. 分布式追踪示例
# ============================================================

def tracing_example():
    """分布式追踪使用示例"""
    from qf_observability.tracing import (
        configure_tracing,
        trace_function,
        get_current_span,
        add_span_attribute,
        add_span_event,
        get_trace_id,
        TraceContext,
        inject_context,
    )
    
    # 配置追踪
    configure_tracing(
        service_name='trading-service',
        service_version='1.0.0',
        console_export=True,  # 开发时输出到控制台
        # otlp_endpoint='http://localhost:4317',  # 生产环境使用OTLP
    )
    
    @trace_function(name='place_order', kind='server')
    def place_order(symbol, quantity, price):
        """下单函数 - 自动追踪"""
        span = get_current_span()
        
        # 添加自定义属性
        add_span_attribute('order.symbol', symbol)
        add_span_attribute('order.quantity', quantity)
        add_span_attribute('order.price', price)
        
        # 记录事件
        add_span_event('validation_complete', {'valid': True})
        
        # 模拟下单逻辑
        result = {'order_id': 'ORD-123', 'status': 'filled'}
        
        add_span_event('order_filled', result)
        
        print(f"Trace ID: {get_trace_id()}")
        return result
    
    # 执行被追踪的函数
    result = place_order('BTC/USD', 1.0, 50000.0)
    print(f"下单结果: {result}")
    
    # 跨服务传递上下文
    headers = inject_context()
    print(f"传递给下游服务的请求头: {headers}")


async def async_tracing_example():
    """异步追踪示例"""
    from qf_observability.tracing import (
        configure_tracing,
        trace_async_function,
        SpanContext,
    )
    
    configure_tracing(
        service_name='async-trading-service',
        console_export=True,
    )
    
    @trace_async_function(name='fetch_market_data')
    async def fetch_market_data(symbols):
        """异步获取市场数据"""
        await asyncio.sleep(0.1)  # 模拟网络请求
        return {s: {'price': 50000.0} for s in symbols}
    
    @trace_async_function(name='process_orders')
    async def process_orders(orders):
        """批量处理订单"""
        with SpanContext(name='batch_processing', attributes={'batch_size': len(orders)}):
            tasks = []
            for order in orders:
                task = process_single_order(order)
                tasks.append(task)
            results = await asyncio.gather(*tasks)
            return results
    
    @trace_async_function(name='process_single_order')
    async def process_single_order(order):
        await asyncio.sleep(0.01)
        return {'order_id': order['id'], 'status': 'processed'}
    
    # 执行
    orders = [{'id': i, 'symbol': 'BTC/USD'} for i in range(5)]
    results = await process_orders(orders)
    print(f"处理结果: {results}")


# ============================================================
# 4. 性能剖析示例
# ============================================================

def profiling_example():
    """性能剖析使用示例"""
    import time
    from qf_observability.profiling import (
        profile_function,
        get_hotspots,
        Timer,
        get_memory_usage,
        MemoryTracker,
    )
    
    @profile_function
    def slow_function(n):
        """需要优化的函数"""
        result = []
        for i in range(n):
            result.append(i ** 2)
        time.sleep(0.1)  # 模拟慢操作
        return sum(result)
    
    @profile_function
    def fast_function(n):
        """优化后的函数"""
        time.sleep(0.01)
        return sum(i ** 2 for i in range(n))
    
    # 执行函数（自动记录性能）
    for _ in range(10):
        slow_function(1000)
        fast_function(1000)
    
    # 查看热点
    hotspots = get_hotspots(top_n=5)
    print("\n性能热点:")
    for hotspot in hotspots:
        print(f"  {hotspot.function_name}: {hotspot.total_time:.3f}s "
              f"({hotspot.percent_of_total:.1f}%)")
    
    # 使用计时器
    with Timer('critical_section'):
        time.sleep(0.05)
        # 关键代码段
    
    # 内存使用
    memory = get_memory_usage()
    print(f"\n内存使用: {memory['rss_mb']:.2f} MB")
    
    # 内存追踪
    with MemoryTracker('data_processing'):
        # 处理大量数据
        large_list = [i for i in range(100000)]
        # ...


async def async_profiling_example():
    """异步性能剖析示例"""
    from qf_observability.profiling import (
        profile_async_function,
        get_async_task_monitor,
        get_async_task_stats,
        create_monitored_task,
    )
    
    monitor = get_async_task_monitor()
    monitor.reset()
    
    @profile_async_function
    async def async_work(task_id):
        await asyncio.sleep(0.1)
        return f"Task {task_id} completed"
    
    # 创建受监控的任务
    tasks = []
    for i in range(5):
        task = create_monitored_task(
            async_work(i),
            name=f'worker_{i}'
        )
        tasks.append(task)
    
    # 等待所有任务
    results = await asyncio.gather(*tasks)
    print(f"任务结果: {results}")
    
    # 获取统计
    stats = get_async_task_stats()
    print(f"\n异步任务统计:")
    print(f"  创建: {stats['stats']['total_created']}")
    print(f"  完成: {stats['stats']['total_completed']}")
    print(f"  失败: {stats['stats']['total_failed']}")
    print(f"  平均耗时: {stats['stats']['avg_duration_ms']:.2f}ms")


# ============================================================
# 5. 综合使用示例
# ============================================================

class ObservableTradingService:
    """可观测的交易服务"""
    
    def __init__(self):
        from qf_observability.logging import get_logger
        from qf_observability.metrics import TradingMetrics, LatencyMetrics
        from qf_observability.tracing import get_tracer
        
        self.logger = get_logger('TradingService')
        self.trading_metrics = TradingMetrics()
        self.latency_metrics = LatencyMetrics()
        self.tracer = get_tracer()
    
    async def execute_trade(self, symbol, quantity, side):
        """执行交易 - 全链路可观测"""
        from qf_observability.tracing import SpanContext, add_span_attribute
        from qf_observability.logging import set_context
        from qf_observability.metrics import TradeRecord
        import time
        
        start_time = time.time()
        
        with SpanContext(name='execute_trade', attributes={
            'trade.symbol': symbol,
            'trade.quantity': quantity,
            'trade.side': side,
        }):
            # 设置日志上下文
            from qf_observability.tracing import get_trace_id
            set_context(trace_id=get_trace_id())
            
            self.logger.info('开始执行交易', symbol=symbol, quantity=quantity)
            
            try:
                # 模拟交易逻辑
                await asyncio.sleep(0.05)
                
                # 记录延迟
                latency_ms = (time.time() - start_time) * 1000
                self.latency_metrics.record_operation_latency('trade_execution', latency_ms / 1000)
                
                # 记录交易
                trade = TradeRecord(
                    trade_id=f'trade-{int(time.time())}',
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=50000.0,
                    timestamp=datetime.utcnow(),
                    latency_ms=latency_ms,
                    status='success',
                )
                self.trading_metrics.record_trade(trade)
                
                self.logger.info('交易执行成功', latency_ms=latency_ms)
                
                return {'status': 'success', 'trade_id': trade.trade_id}
                
            except Exception as e:
                self.logger.error('交易执行失败', error=str(e))
                
                # 记录失败
                trade = TradeRecord(
                    trade_id=f'trade-{int(time.time())}',
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=0.0,
                    timestamp=datetime.utcnow(),
                    latency_ms=(time.time() - start_time) * 1000,
                    status='failed',
                    error=str(e),
                )
                self.trading_metrics.record_trade(trade)
                
                raise


# ============================================================
# 运行示例
# ============================================================

def run_all_examples():
    """运行所有示例"""
    print("=" * 60)
    print("1. 结构化日志示例")
    print("=" * 60)
    logging_example()
    
    print("\n" + "=" * 60)
    print("2. 指标采集示例")
    print("=" * 60)
    metrics_example()
    
    print("\n" + "=" * 60)
    print("3. 分布式追踪示例")
    print("=" * 60)
    tracing_example()
    
    print("\n" + "=" * 60)
    print("4. 性能剖析示例")
    print("=" * 60)
    profiling_example()
    
    print("\n" + "=" * 60)
    print("示例运行完成!")
    print("=" * 60)


if __name__ == '__main__':
    run_all_examples()
    
    # 运行异步示例
    print("\n异步示例...")
    asyncio.run(async_tracing_example())
    asyncio.run(async_profiling_example())
    
    # 运行综合示例
    print("\n综合示例...")
    service = ObservableTradingService()
    asyncio.run(service.execute_trade('BTC/USD', 1.0, 'buy'))
