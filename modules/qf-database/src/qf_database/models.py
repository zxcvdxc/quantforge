from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass, asdict


@dataclass
class Contract:
    """合约信息"""
    symbol: str
    exchange: str
    name: str
    contract_type: str  # spot, futures, option
    base_asset: str
    quote_asset: str
    price_precision: int = 8
    quantity_precision: int = 8
    min_quantity: Decimal = Decimal("0.0001")
    max_quantity: Decimal = Decimal("100000000")
    status: str = "active"  # active, suspended, delisted
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        # 处理 Decimal 类型
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat() if value else None
        return data


@dataclass
class Trade:
    """交易记录"""
    id: Optional[int] = None
    symbol: str = ""
    exchange: str = ""
    side: str = ""  # buy, sell
    order_type: str = ""  # market, limit
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    fee_asset: str = ""
    status: str = "pending"  # pending, filled, partial, canceled
    order_id: str = ""
    trade_id: str = ""
    account_id: str = ""
    strategy_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat() if value else None
        return data


@dataclass
class Account:
    """账户信息"""
    id: Optional[int] = None
    account_id: str = ""
    exchange: str = ""
    account_type: str = ""  # spot, margin, futures
    asset: str = ""
    free: Decimal = Decimal("0")
    locked: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat() if value else None
        return data


@dataclass
class Kline:
    """K线数据"""
    symbol: str
    exchange: str
    interval: str  # 1m, 5m, 15m, 1h, 4h, 1d
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trades: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = float(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
        return data


@dataclass
class Tick:
    """Tick数据"""
    symbol: str
    exchange: str
    timestamp: datetime
    price: Decimal
    quantity: Decimal
    side: str  # buy, sell
    trade_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = float(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
        return data