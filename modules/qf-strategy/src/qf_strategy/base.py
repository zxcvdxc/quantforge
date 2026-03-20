"""策略基类定义 - 优化版本

提供所有策略的抽象基类和通用接口，包含性能优化:
- NumPy向量化计算
- 信号缓存
- 内存预分配
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Tuple, Protocol, runtime_checkable
from collections import deque
import numpy as np
import pandas as pd
from numpy.typing import NDArray


class SignalType(Enum):
    """信号类型枚举"""
    BUY = "buy"           # 买入信号
    SELL = "sell"         # 卖出信号
    OPEN_LONG = "open_long"    # 开多仓
    OPEN_SHORT = "open_short"  # 开空仓
    CLOSE_LONG = "close_long"  # 平多仓
    CLOSE_SHORT = "close_short" # 平空仓
    HOLD = "hold"         # 持有
    NO_SIGNAL = "no_signal"  # 无信号


@dataclass(slots=True)
class Signal:
    """交易信号
    
    Attributes:
        timestamp: 信号时间戳
        symbol: 交易标的
        signal_type: 信号类型
        price: 触发价格
        quantity: 交易数量
        confidence: 信号置信度 (0-1)
        metadata: 额外元数据
    """
    timestamp: datetime
    symbol: str
    signal_type: SignalType
    price: float
    quantity: Optional[float] = None
    confidence: float = 1.0
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
    
    def is_entry(self) -> bool:
        """检查是否为开仓信号"""
        return self.signal_type in (SignalType.BUY, SignalType.OPEN_LONG, SignalType.OPEN_SHORT)
    
    def is_exit(self) -> bool:
        """检查是否为平仓信号"""
        return self.signal_type in (SignalType.SELL, SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT)


@dataclass(slots=True)
class StrategyParameter:
    """策略参数
    
    Attributes:
        name: 参数名称
        value: 参数值
        min_value: 最小值（用于优化）
        max_value: 最大值（用于优化）
        step: 优化步长
        description: 参数描述
    """
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


@dataclass(slots=True)
class BarData:
    """K线数据
    
    Attributes:
        timestamp: 时间戳
        symbol: 交易标的
        open: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量
        metadata: 额外元数据
    """
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
        ts = series.name if isinstance(series.name, datetime) else pd.to_datetime(series.name)
        return cls(
            timestamp=ts,
            symbol=str(series.get("symbol", "")),
            open=float(series.get("open", 0)),
            high=float(series.get("high", 0)),
            low=float(series.get("low", 0)),
            close=float(series.get("close", 0)),
            volume=float(series.get("volume", 0)),
        )
    
    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> List["BarData"]:
        """从 DataFrame 创建 BarData 列表"""
        bars = []
        for _, row in df.iterrows():
            bars.append(cls(
                timestamp=row.get("timestamp", row.name) if isinstance(row.get("timestamp"), datetime) else pd.to_datetime(row.get("timestamp", row.name)),
                symbol=str(row.get("symbol", "")),
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=float(row.get("volume", 0)),
            ))
        return bars
    
    @property
    def typical_price(self) -> float:
        """典型价格 (H+L+C)/3"""
        return (self.high + self.low + self.close) / 3.0
    
    @property
    def price_range(self) -> float:
        """价格区间"""
        return self.high - self.low
    
    @property
    def body_size(self) -> float:
        """K线实体大小"""
        return abs(self.close - self.open)
    
    @property
    def is_bullish(self) -> bool:
        """是否为阳线"""
        return self.close > self.open
    
    @property
    def is_bearish(self) -> bool:
        """是否为阴线"""
        return self.close < self.open


@dataclass(slots=True)
class TickData:
    """Tick数据
    
    Attributes:
        timestamp: 时间戳
        symbol: 交易标的
        price: 当前价格
        volume: 成交量
        bid: 买一价
        ask: 卖一价
        bid_volume: 买量
        ask_volume: 卖量
    """
    timestamp: datetime
    symbol: str
    price: float
    volume: float
    bid: float
    ask: float
    bid_volume: float
    ask_volume: float
    
    @property
    def spread(self) -> float:
        """买卖价差"""
        return self.ask - self.bid
    
    @property
    def mid_price(self) -> float:
        """中间价"""
        return (self.bid + self.ask) / 2.0


class SignalCache:
    """信号缓存 - 用于优化重复计算"""
    
    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, Any] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key in self._cache:
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None
    
    def set(self, key: str, value: Any) -> None:
        """设置缓存值"""
        if len(self._cache) >= self._max_size:
            # 简单的LRU: 清除一半缓存
            keys = list(self._cache.keys())[:self._max_size//2]
            for k in keys:
                del self._cache[k]
        self._cache[key] = value
    
    def clear(self) -> None:
        """清除缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
    
    @property
    def hit_rate(self) -> float:
        """缓存命中率"""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0


class BaseStrategy(ABC):
    """策略抽象基类 - 优化版本
    
    所有策略必须继承此类并实现以下方法：
    - on_bar: 处理K线数据
    - on_tick: 处理Tick数据
    
    性能优化:
    - 使用NumPy数组存储价格历史
    - 信号缓存避免重复计算
    - 内存预分配减少GC压力
    
    Attributes:
        name: 策略名称
        params: 参数字典
        _history: 历史K线数据
        _signals: 生成的信号列表
        _is_initialized: 是否已初始化
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
        
        # 优化的价格历史存储 (使用NumPy数组)
        self._close_prices: NDArray[np.float64] = np.array([], dtype=np.float64)
        self._high_prices: NDArray[np.float64] = np.array([], dtype=np.float64)
        self._low_prices: NDArray[np.float64] = np.array([], dtype=np.float64)
        self._volumes: NDArray[np.float64] = np.array([], dtype=np.float64)
        
        # 信号缓存
        self._signal_cache = SignalCache()
        
        # 内存预分配配置
        self._buffer_size = 10000
        self._price_buffer: NDArray[np.float64] = np.zeros(self._buffer_size)
        self._buffer_index = 0
        
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
        self._close_prices = np.array([], dtype=np.float64)
        self._high_prices = np.array([], dtype=np.float64)
        self._low_prices = np.array([], dtype=np.float64)
        self._volumes = np.array([], dtype=np.float64)
        self._signal_cache.clear()
        self._buffer_index = 0
    
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
        self._close_prices = np.array([], dtype=np.float64)
        self._high_prices = np.array([], dtype=np.float64)
        self._low_prices = np.array([], dtype=np.float64)
        self._volumes = np.array([], dtype=np.float64)
        self._buffer_index = 0
    
    def reset(self) -> None:
        """重置策略状态"""
        self.clear_history()
        self._signals.clear()
        self._is_initialized = False
        self._signal_cache.clear()
    
    def _add_to_history(self, bar: BarData) -> None:
        """添加数据到历史 - 优化版本"""
        self._history.append(bar)
        
        # 使用NumPy数组存储价格 (更快访问)
        self._close_prices = np.append(self._close_prices, bar.close)
        self._high_prices = np.append(self._high_prices, bar.high)
        self._low_prices = np.append(self._low_prices, bar.low)
        self._volumes = np.append(self._volumes, bar.volume)
        
        # 限制历史数据大小
        max_history = int(self.get_param("max_history") or 10000)
        if len(self._history) > max_history:
            self._history = self._history[-max_history:]
            self._close_prices = self._close_prices[-max_history:]
            self._high_prices = self._high_prices[-max_history:]
            self._low_prices = self._low_prices[-max_history:]
            self._volumes = self._volumes[-max_history:]
    
    def _record_signal(self, signal: Optional[Signal]) -> None:
        """记录信号"""
        if signal:
            self._signals.append(signal)
    
    # ============== 向量化技术指标计算 ==============
    
    def calculate_sma(self, data: Union[List[float], NDArray[np.float64]], period: int) -> Optional[float]:
        """
        计算简单移动平均 - 使用NumPy优化
        
        Args:
            data: 价格数据
            period: 周期
            
        Returns:
            SMA值或None（数据不足）
        """
        arr = np.asarray(data)
        if len(arr) < period:
            return None
        return float(np.mean(arr[-period:]))
    
    def calculate_sma_series(self, data: NDArray[np.float64], period: int) -> NDArray[np.float64]:
        """
        计算SMA序列 - 向量化版本
        
        Args:
            data: 价格数组
            period: 周期
            
        Returns:
            SMA数组
        """
        if len(data) < period:
            return np.array([])
        # 使用卷积计算移动平均
        weights = np.ones(period) / period
        return np.convolve(data, weights, mode='valid')
    
    def calculate_ema(self, data: Union[List[float], NDArray[np.float64]], period: int) -> Optional[float]:
        """
        计算指数移动平均 - 使用NumPy优化
        
        Args:
            data: 价格数据
            period: 周期
            
        Returns:
            EMA值或None（数据不足）
        """
        arr = np.asarray(data)
        if len(arr) < period:
            return None
        
        alpha = 2 / (period + 1)
        ema = arr[0]
        for price in arr[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return float(ema)
    
    def calculate_ema_series(self, data: NDArray[np.float64], period: int) -> NDArray[np.float64]:
        """
        计算EMA序列 - 向量化版本
        
        Args:
            data: 价格数组
            period: 周期
            
        Returns:
            EMA数组
        """
        if len(data) < period:
            return np.array([])
        
        alpha = 2 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        
        return ema
    
    def calculate_std(self, data: Union[List[float], NDArray[np.float64]], period: int) -> Optional[float]:
        """
        计算标准差 - 使用NumPy优化
        
        Args:
            data: 价格数据
            period: 周期
            
        Returns:
            标准差或None（数据不足）
        """
        arr = np.asarray(data)
        if len(arr) < period:
            return None
        return float(np.std(arr[-period:], ddof=1))
    
    def calculate_std_series(self, data: NDArray[np.float64], period: int) -> NDArray[np.float64]:
        """计算标准差序列 - 向量化版本"""
        if len(data) < period:
            return np.array([])
        
        result = np.full(len(data) - period + 1, np.nan)
        for i in range(period - 1, len(data)):
            result[i - period + 1] = np.std(data[i - period + 1:i + 1], ddof=1)
        return result
    
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
            return 0.0
        return (value - mean) / std
    
    def calculate_zscore_series(self, data: NDArray[np.float64], period: int) -> NDArray[np.float64]:
        """计算Z-Score序列 - 向量化版本"""
        if len(data) < period:
            return np.array([])
        
        sma = self.calculate_sma_series(data, period)
        std = self.calculate_std_series(data, period)
        
        valid_len = min(len(sma), len(std))
        data_aligned = data[-valid_len:]
        
        zscores = np.zeros(valid_len)
        for i in range(valid_len):
            if std[i] != 0:
                zscores[i] = (data_aligned[i] - sma[i]) / std[i]
        return zscores
    
    def calculate_rsi(self, data: Union[List[float], NDArray[np.float64]], period: int = 14) -> Optional[float]:
        """
        计算RSI (相对强弱指标)
        
        Args:
            data: 价格数据
            period: 周期 (默认14)
            
        Returns:
            RSI值或None
        """
        arr = np.asarray(data)
        if len(arr) < period + 1:
            return None
        
        # 计算价格变化
        deltas = np.diff(arr)
        
        # 分离上涨和下跌
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # 计算平均上涨和下跌
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    def calculate_macd(
        self,
        data: NDArray[np.float64],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> Tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        """
        计算MACD - 向量化版本
        
        Args:
            data: 价格数组
            fast: 快速EMA周期
            slow: 慢速EMA周期
            signal: 信号线周期
            
        Returns:
            (MACD线, 信号线, 柱状图)
        """
        ema_fast = self.calculate_ema_series(data, fast)
        ema_slow = self.calculate_ema_series(data, slow)
        
        # 对齐长度
        min_len = min(len(ema_fast), len(ema_slow))
        ema_fast = ema_fast[-min_len:]
        ema_slow = ema_slow[-min_len:]
        
        macd_line = ema_fast - ema_slow
        signal_line = self.calculate_ema_series(macd_line, signal)
        
        # 对齐
        hist_len = min(len(macd_line), len(signal_line))
        macd_line = macd_line[-hist_len:]
        signal_line = signal_line[-hist_len:]
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def calculate_bollinger_bands(
        self,
        data: NDArray[np.float64],
        period: int = 20,
        std_dev: float = 2.0,
    ) -> Tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        """
        计算布林带 - 向量化版本
        
        Args:
            data: 价格数组
            period: 周期
            std_dev: 标准差倍数
            
        Returns:
            (上轨, 中轨, 下轨)
        """
        middle = self.calculate_sma_series(data, period)
        std = self.calculate_std_series(data, period)
        
        # 对齐
        min_len = min(len(middle), len(std))
        middle = middle[-min_len:]
        std = std[-min_len:]
        
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        
        return upper, middle, lower
    
    def detect_crossover(
        self,
        fast: NDArray[np.float64],
        slow: NDArray[np.float64],
    ) -> Tuple[bool, bool]:
        """
        检测交叉信号 - 向量化版本
        
        Args:
            fast: 快速线
            slow: 慢速线
            
        Returns:
            (金叉, 死叉)
        """
        if len(fast) < 2 or len(slow) < 2:
            return False, False
        
        # 金叉: 前一时段fast<=slow，当前fast>slow
        golden = (fast[-2] <= slow[-2]) and (fast[-1] > slow[-1])
        
        # 死叉: 前一时段fast>=slow，当前fast<slow
        death = (fast[-2] >= slow[-2]) and (fast[-1] < slow[-1])
        
        return golden, death
    
    def get_cached_indicator(self, key: str) -> Optional[Any]:
        """获取缓存的技术指标"""
        return self._signal_cache.get(key)
    
    def cache_indicator(self, key: str, value: Any) -> None:
        """缓存技术指标"""
        self._signal_cache.set(key, value)
    
    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        return self._signal_cache.hit_rate
    
    def __repr__(self) -> str:
        return f"{self.name}(params={len(self.params)}, history={len(self._history)})"
