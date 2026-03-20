"""
策略基类定义

提供所有策略的抽象基类和通用接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"           # 买入信号
    SELL = "sell"         # 卖出信号
    OPEN_LONG = "open_long"    # 开多仓
    OPEN_SHORT = "open_short"  # 开空仓
    CLOSE_LONG = "close_long"  # 平多仓
    CLOSE_SHORT = "close_short" # 平空仓
    HOLD = "hold"         # 持有
    NO_SIGNAL = "no_signal"  # 无信号


@dataclass
class Signal:
    """交易信号"""
    timestamp: datetime
    symbol: str
    signal_type: SignalType
    price: float
    quantity: Optional[float] = None
    confidence: float = 1.0  # 信号置信度 0-1
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "price": self.price,
            "quantity": self.quantity,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass 
class StrategyParameter:
    """策略参数"""
    name: str
    value: Union[int, float, str, bool]
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    step: Optional[Union[int, float]] = None
    description: str = ""
    
    def validate(self) -> bool:
        """验证参数值是否在有效范围内"""
        if isinstance(self.value, (int, float)):
            if self.min_value is not None and self.value < self.min_value:
                return False
            if self.max_value is not None and self.value > self.max_value:
                return False
        return True
    
    def get_range(self) -> List[Union[int, float]]:
        """获取参数优化范围"""
        if self.step is None or self.min_value is None or self.max_value is None:
            return [self.value]
        
        values = []
        current = self.min_value
        while current <= self.max_value:
            values.append(current)
            current += self.step
        return values


@dataclass
class BarData:
    """K线数据"""
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_series(cls, series: pd.Series) -> "BarData":
        """从 pandas Series 创建"""
        return cls(
            timestamp=series.name if isinstance(series.name, datetime) else pd.to_datetime(series.name),
            symbol=str(series.get("symbol", "")),
            open=float(series.get("open", 0)),
            high=float(series.get("high", 0)),
            low=float(series.get("low", 0)),
            close=float(series.get("close", 0)),
            volume=float(series.get("volume", 0)),
        )


@dataclass
class TickData:
    """Tick数据"""
    timestamp: datetime
    symbol: str
    price: float
    volume: float
    bid: float
    ask: float
    bid_volume: float
    ask_volume: float


class BaseStrategy(ABC):
    """策略抽象基类
    
    所有策略必须继承此类并实现以下方法：
    - on_bar: 处理K线数据
    - on_tick: 处理Tick数据
    """
    
    def __init__(self, name: str = "", params: Optional[Dict[str, Any]] = None):
        """
        初始化策略
        
        Args:
            name: 策略名称
            params: 策略参数字典
        """
        self.name = name or self.__class__.__name__
        self.params: Dict[str, StrategyParameter] = {}
        self._history: List[BarData] = []
        self._signals: List[Signal] = []
        self._is_initialized = False
        
        # 设置默认参数
        self._setup_default_params()
        
        # 更新用户参数
        if params:
            self.update_params(params)
    
    @abstractmethod
    def _setup_default_params(self) -> None:
        """设置默认参数 - 子类必须实现"""
        pass
    
    @abstractmethod
    def on_bar(self, bar: BarData) -> Optional[Signal]:
        """
        处理K线数据
        
        Args:
            bar: K线数据
            
        Returns:
            交易信号或None
        """
        pass
    
    @abstractmethod
    def on_tick(self, tick: TickData) -> Optional[Signal]:
        """
        处理Tick数据
        
        Args:
            tick: Tick数据
            
        Returns:
            交易信号或None
        """
        pass
    
    def initialize(self, **kwargs) -> None:
        """初始化策略状态"""
        self._is_initialized = True
        self._history.clear()
        self._signals.clear()
    
    def update_params(self, params: Dict[str, Any]) -> None:
        """
        更新策略参数
        
        Args:
            params: 参数字典
        """
        for key, value in params.items():
            if key in self.params:
                self.params[key].value = value
    
    def get_param(self, name: str) -> Any:
        """获取参数值"""
        if name in self.params:
            return self.params[name].value
        return None
    
    def set_param(self, name: str, value: Any) -> None:
        """设置参数值"""
        if name in self.params:
            self.params[name].value = value
    
    def get_optimization_params(self) -> Dict[str, List[Union[int, float]]]:
        """
        获取参数优化空间
        
        Returns:
            参数名称到取值列表的映射
        """
        result = {}
        for name, param in self.params.items():
            param_range = param.get_range()
            if len(param_range) > 1:
                result[name] = param_range
        return result
    
    def get_history(self, n: Optional[int] = None) -> List[BarData]:
        """
        获取历史数据
        
        Args:
            n: 获取最近n条数据，None表示获取全部
            
        Returns:
            BarData列表
        """
        if n is None:
            return self._history.copy()
        return self._history[-n:]
    
    def get_signals(self) -> List[Signal]:
        """获取所有生成的信号"""
        return self._signals.copy()
    
    def clear_history(self) -> None:
        """清空历史数据"""
        self._history.clear()
        self._signals.clear()
    
    def reset(self) -> None:
        """重置策略状态"""
        self.clear_history()
        self._is_initialized = False
    
    def _add_to_history(self, bar: BarData) -> None:
        """添加数据到历史"""
        self._history.append(bar)
        # 限制历史数据大小
        max_history = int(self.get_param("max_history") or 10000)
        if len(self._history) > max_history:
            self._history = self._history[-max_history:]
    
    def _record_signal(self, signal: Optional[Signal]) -> None:
        """记录信号"""
        if signal:
            self._signals.append(signal)
    
    def calculate_sma(self, data: List[float], period: int) -> Optional[float]:
        """
        计算简单移动平均
        
        Args:
            data: 价格数据列表
            period: 周期
            
        Returns:
            SMA值或None（数据不足）
        """
        if len(data) < period:
            return None
        return np.mean(data[-period:])
    
    def calculate_ema(self, data: List[float], period: int) -> Optional[float]:
        """
        计算指数移动平均
        
        Args:
            data: 价格数据列表
            period: 周期
            
        Returns:
            EMA值或None（数据不足）
        """
        if len(data) < period:
            return None
        
        alpha = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema
    
    def calculate_std(self, data: List[float], period: int) -> Optional[float]:
        """
        计算标准差
        
        Args:
            data: 价格数据列表
            period: 周期
            
        Returns:
            标准差或None（数据不足）
        """
        if len(data) < period:
            return None
        return np.std(data[-period:])
    
    def calculate_zscore(self, value: float, mean: float, std: float) -> float:
        """
        计算Z-Score
        
        Args:
            value: 当前值
            mean: 平均值
            std: 标准差
            
        Returns:
            Z-Score
        """
        if std == 0:
            return 0
        return (value - mean) / std
    
    def __repr__(self) -> str:
        return f"{self.name}(params={len(self.params)}, history={len(self._history)})"
