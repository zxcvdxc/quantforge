"""
qf-data 使用示例
"""
import asyncio
import pandas as pd
from qf_data import DataCollector, DataCleaner, DataSource


async def example_crypto_data():
    """获取数字货币数据示例"""
    collector = DataCollector()
    
    # 连接OKX
    await collector.connect(DataSource.OKX)
    
    # 获取BTC-USDT K线数据
    df = await collector.get_kline_df(
        symbol="BTC-USDT",
        interval="1h",
        limit=100,
        source=DataSource.OKX
    )
    print("BTC-USDT K线数据:")
    print(df.head())
    
    # 数据清洗
    cleaner = DataCleaner()
    df_clean = cleaner.clean_kline_dataframe(df)
    print("\n清洗后数据:")
    print(df_clean.head())
    
    await collector.disconnect()


async def example_stock_data():
    """获取A股数据示例"""
    collector = DataCollector({
        "tushare": {"token": "your_token_here"}
    })
    
    # 获取平安银行K线数据
    df = await collector.get_kline_df(
        symbol="000001.SZ",
        interval="1d",
        limit=100,
        source=DataSource.TUSHARE
    )
    print("平安银行 K线数据:")
    print(df.head())


async def example_websocket():
    """WebSocket订阅示例"""
    collector = DataCollector()
    
    print("订阅BTC-USDT Tick数据...")
    count = 0
    async for tick in collector.subscribe_tick("BTC-USDT", source=DataSource.OKX):
        print(f"Tick: {tick.price} @ {tick.volume}")
        count += 1
        if count >= 5:
            break


async def example_multi_source():
    """多数据源对比示例"""
    collector = DataCollector()
    
    results = await collector.multi_source_kline(
        symbol="BTC-USDT",
        sources=[DataSource.OKX, DataSource.BINANCE],
        interval="1h",
        limit=10
    )
    
    for source, data in results.items():
        print(f"{source}: {len(data)}条数据")


def example_cleaning():
    """数据清洗示例"""
    # 创建示例数据（包含缺失值和异常值）
    df = pd.DataFrame({
        "open": [100, 101, None, 103, 150],    # 150是异常值
        "high": [102, 103, None, 105, 155],
        "low": [99, 100, None, 102, 148],
        "close": [101, 102, None, 104, 152],
        "volume": [1000, 1500, 1200, None, 5000],
    }, index=pd.date_range("2024-01-01", periods=5, freq="1h"))
    
    cleaner = DataCleaner()
    
    # 清洗数据
    df_clean = cleaner.clean_kline_dataframe(df)
    print("原始数据:")
    print(df)
    print("\n清洗后数据:")
    print(df_clean)
    
    # 数据质量报告
    report = cleaner.validate_data_quality(df)
    print(f"\n数据质量评分: {report['score']}/100")


if __name__ == "__main__":
    # 运行示例
    print("=" * 50)
    print("数字货币数据示例")
    print("=" * 50)
    asyncio.run(example_crypto_data())
    
    print("\n" + "=" * 50)
    print("数据清洗示例")
    print("=" * 50)
    example_cleaning()
