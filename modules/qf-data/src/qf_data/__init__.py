"""
QuantForge Data Collection Module
多源数据采集、清洗、标准化处理
"""

from .collector import DataCollector
from .cleaner import DataCleaner
from .exceptions import (
    DataCollectionError,
    DataSourceError,
    DataFormatError,
    DataCleaningError,
)
from .types import (
    KlineData,
    TickData,
    DataSource,
    SymbolInfo,
    Exchange,
    MarketType,
)

__version__ = "0.1.0"
__all__ = [
    "DataCollector",
    "DataCleaner",
    "DataCollectionError",
    "DataSourceError",
    "DataFormatError",
    "DataCleaningError",
    "KlineData",
    "TickData",
    "DataSource",
    "SymbolInfo",
    "Exchange",
    "MarketType",
]
