"""
数据类型定义
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum, auto
from typing import Optional, List, Dict, Any
import pandas as pd


class Exchange(Enum):
    """交易所枚举"""
    SSE = "SSE"           # 上海证券交易所
    SZSE = "SZSE"         # 深圳证券交易所
    BSE = "BSE"           # 北京证券交易所
    SHFE = "SHFE"         # 上海期货交易所
    DCE = "DCE"           # 大连商品交易所
    CZCE = "CZCE"         # 郑州商品交易所
    CFFEX = "CFFEX"       # 中国金融期货交易所
    INE = "INE"           # 上海国际能源交易中心
    OKX = "OKX"           # OKX交易所
    BINANCE = "BINANCE"   # Binance交易所


class DataSource(Enum):
    """数据源枚举"""
    TUSHARE = "tushare"
    AKSHARE = "akshare"
    CTP = "ctp"
    OKX = "okx"
    BINANCE = "binance"


class MarketType(Enum):
    """市场类型"""
    STOCK = auto()        # A股
    FUTURES = auto()      # 期货
    CRYPTO = auto()       # 数字货币


@dataclass
class SymbolInfo:
    """标的符号信息"""
    symbol: str
    exchange: Exchange
    market_type: MarketType
    name: Optional[str] = None
    base_asset: Optional[str] = None  # 基础资产（数字货币用）
    quote_asset: Optional[str] = None  # 计价资产（数字货币用）
    price_precision: int = 8
    quantity_precision: int = 8
    min_quantity: Optional[Decimal] = None
    max_quantity: Optional[Decimal] = None


@dataclass
class KlineData:
    """K线数据"""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Optional[Decimal] = None
    trades: Optional[int] = None
    buy_volume: Optional[Decimal] = None
    sell_volume: Optional[Decimal] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
            "quote_volume": float(self.quote_volume) if self.quote_volume else None,
            "trades": self.trades,
            "buy_volume": float(self.buy_volume) if self.buy_volume else None,
            "sell_volume": float(self.sell_volume) if self.sell_volume else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KlineData":
        """从字典创建"""
        return cls(
            timestamp=data["timestamp"] if isinstance(data["timestamp"], datetime) else datetime.fromtimestamp(data["timestamp"] / 1000),
            open=Decimal(str(data["open"])),
            high=Decimal(str(data["high"])),
            low=Decimal(str(data["low"])),
            close=Decimal(str(data["close"])),
            volume=Decimal(str(data["volume"])),
            quote_volume=Decimal(str(data["quote_volume"])) if data.get("quote_volume") else None,
            trades=data.get("trades"),
            buy_volume=Decimal(str(data["buy_volume"])) if data.get("buy_volume") else None,
            sell_volume=Decimal(str(data["sell_volume"])) if data.get("sell_volume") else None,
        )


@dataclass
class TickData:
    """Tick数据"""
    timestamp: datetime
    symbol: str
    price: Decimal
    volume: Decimal
    side: Optional[str] = None  # buy/sell
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    bid_volume: Optional[Decimal] = None
    ask_volume: Optional[Decimal] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "price": float(self.price),
            "volume": float(self.volume),
            "side": self.side,
            "bid_price": float(self.bid_price) if self.bid_price else None,
            "ask_price": float(self.ask_price) if self.ask_price else None,
            "bid_volume": float(self.bid_volume) if self.bid_volume else None,
            "ask_volume": float(self.ask_volume) if self.ask_volume else None,
        }


@dataclass
class OrderBookLevel:
    """订单簿档位"""
    price: Decimal
    volume: Decimal
    count: Optional[int] = None


@dataclass
class OrderBook:
    """订单簿数据"""
    timestamp: datetime
    symbol: str
    bids: List[OrderBookLevel]  # 买单 [价格, 数量, 订单数]
    asks: List[OrderBookLevel]  # 卖单 [价格, 数量, 订单数]
    
    def best_bid(self) -> Optional[OrderBookLevel]:
        """最优买价"""
        return self.bids[0] if self.bids else None
    
    def best_ask(self) -> Optional[OrderBookLevel]:
        """最优卖价"""
        return self.asks[0] if self.asks else None
    
    def mid_price(self) -> Optional[Decimal]:
        """中间价"""
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid and best_ask:
            return (best_bid.price + best_ask.price) / 2
        return None
    
    def spread(self) -> Optional[Decimal]:
        """买卖价差"""
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid and best_ask:
            return best_ask.price - best_bid.price
        return None


# 类型别名
KlineDataFrame = pd.DataFrame  # 包含K线数据的DataFrame
TickDataFrame = pd.DataFrame   # 包含Tick数据的DataFrame
