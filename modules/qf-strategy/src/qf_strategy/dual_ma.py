"""双均线策略 - Dual Moving Average Strategy (Optimized)

原理: 利用短期均线与长期均线的交叉信号进行趋势跟踪
- 短期均线上穿长期均线(金叉): 买入信号
- 短期均线下穿长期均线(死叉): 卖出信号

优化:
- 使用向量化NumPy计算
- 信号缓存
- 内存预分配
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

from qf_strategy.base import (
    BarData,
    BaseStrategy,
    Signal,
    SignalType,
    StrategyParameter,
    TickData,
)


class DualMA(BaseStrategy):
    """双均线趋势跟踪策略 - 优化版本
    
    交易逻辑:
    - 短周期MA上穿长周期MA(金叉): 开多仓
    - 短周期MA下穿长周期MA(死叉): 开空仓或平多仓
    - 支持多种移动平均类型: SMA, EMA
    
    Attributes:
        _closes: 收盘价历史 (NumPy数组)
        _fast_ma_history: 快速MA历史
        _slow_ma_history: 慢速MA历史
        _position: 当前仓位状态 (0=无, 1=多头, -1=空头)
    """
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        初始化双均线策略
        
        Args:
            params: 策略参数
                - fast_period: 短期均线周期
                - slow_period: 长期均线周期
                - ma_type: 均线类型 (sma/ema)
                - signal_threshold: 信号确认阈值(避免噪音)
                - max_history: 最大历史数据条数
        """
        # 初始化NumPy数组
        self._closes: NDArray[np.float64] = np.array([], dtype=np.float64)
        self._fast_ma_history: NDArray[np.float64] = np.array([], dtype=np.float64)
        self._slow_ma_history: NDArray[np.float64] = np.array([], dtype=np.float64)
        self._position: int = 0  # 0=无仓位, 1=多头, -1=空头
        
        # 缓存的MA值
        self._cached_fast_ma: Optional[float] = None
        self._cached_slow_ma: Optional[float] = None
        
        super().__init__(name="DualMA", params=params)
    
    def _setup_default_params(self) -> None:
        """设置默认参数"""
        self.params = {
            "fast_period": StrategyParameter(
                name="fast_period",
                value=10,
                min_value=5,
                max_value=50,
                step=5,
                description="短期均线周期"
            ),
            "slow_period": StrategyParameter(
                name="slow_period",
                value=30,
                min_value=20,
                max_value=100,
                step=5,
                description="长期均线周期"
            ),
            "ma_type": StrategyParameter(
                name="ma_type",
                value="sma",
                description="均线类型: sma(简单移动平均) 或 ema(指数移动平均)"
            ),
            "signal_threshold": StrategyParameter(
                name="signal_threshold",
                value=0.0,
                min_value=0.0,
                max_value=0.01,
                step=0.001,
                description="信号确认阈值(价格差比例)"
            ),
            "max_history": StrategyParameter(
                name="max_history",
                value=5000,
                description="最大历史数据条数"
            ),
        }
    
    def initialize(self, **kwargs) -> None:
        """初始化策略状态"""
        super().initialize(**kwargs)
        self._closes = np.array([], dtype=np.float64)
        self._fast_ma_history = np.array([], dtype=np.float64)
        self._slow_ma_history = np.array([], dtype=np.float64)
        self._position = 0
        self._cached_fast_ma = None
        self._cached_slow_ma = None
    
    def calculate_ma(self, data: NDArray[np.float64], period: int) -> Optional[float]:
        """
        计算移动平均 - 使用向量化计算
        
        Args:
            data: 价格数据 (NumPy数组)
            period: 周期
            
        Returns:
            移动平均值或None
        """
        if len(data) < period:
            return None
        
        ma_type = self.get_param("ma_type")
        if ma_type == "ema":
            return self.calculate_ema(data, period)
        else:
            return self.calculate_sma(data, period)
    
    def calculate_ma_series(self, data: NDArray[np.float64], period: int) -> NDArray[np.float64]:
        """
        计算MA序列 - 向量化
        
        Args:
            data: 价格数据
            period: 周期
            
        Returns:
            MA序列
        """
        ma_type = self.get_param("ma_type")
        if ma_type == "ema":
            return self.calculate_ema_series(data, period)
        else:
            return self.calculate_sma_series(data, period)
    
    def check_ma_cross(self) -> Tuple[bool, str]:
        """
        检查均线交叉信号 - 向量化版本
        
        Returns:
            (是否有信号, 信号类型: "golden_cross"/"death_cross"/"")
        """
        if len(self._fast_ma_history) < 2 or len(self._slow_ma_history) < 2:
            return False, ""
        
        # 使用向量化检测
        golden, death = self.detect_crossover(
            self._fast_ma_history,
            self._slow_ma_history
        )
        
        if not golden and not death:
            return False, ""
        
        # 计算信号阈值
        signal_threshold = float(self.get_param("signal_threshold"))
        
        if golden:
            curr_fast = self._fast_ma_history[-1]
            curr_slow = self._slow_ma_history[-1]
            diff_ratio = abs(curr_fast - curr_slow) / curr_slow if curr_slow > 0 else 0
            if diff_ratio >= signal_threshold:
                return True, "golden_cross"
        
        if death:
            curr_fast = self._fast_ma_history[-1]
            curr_slow = self._slow_ma_history[-1]
            diff_ratio = abs(curr_fast - curr_slow) / curr_slow if curr_slow > 0 else 0
            if diff_ratio >= signal_threshold:
                return True, "death_cross"
        
        return False, ""
    
    def on_bar(self, bar: BarData) -> Optional[Signal]:
        """
        处理K线数据 - 优化版本
        
        Args:
            bar: K线数据
            
        Returns:
            交易信号或None
        """
        self._add_to_history(bar)
        
        # 使用NumPy数组存储收盘价
        self._closes = np.append(self._closes, bar.close)
        
        # 限制历史长度
        max_period = int(self.get_param("slow_period")) * 3
        if len(self._closes) > max_period:
            self._closes = self._closes[-max_period:]
        
        # 计算均线
        fast_period = int(self.get_param("fast_period"))
        slow_period = int(self.get_param("slow_period"))
        
        fast_ma = self.calculate_ma(self._closes, fast_period)
        slow_ma = self.calculate_ma(self._closes, slow_period)
        
        if fast_ma is None or slow_ma is None:
            return None
        
        self._fast_ma_history = np.append(self._fast_ma_history, fast_ma)
        self._slow_ma_history = np.append(self._slow_ma_history, slow_ma)
        
        # 限制MA历史长度
        if len(self._fast_ma_history) > max_period:
            self._fast_ma_history = self._fast_ma_history[-max_period:]
            self._slow_ma_history = self._slow_ma_history[-max_period:]
        
        # 缓存当前MA值
        self._cached_fast_ma = fast_ma
        self._cached_slow_ma = slow_ma
        
        # 检查交叉信号
        has_signal, signal_type = self.check_ma_cross()
        
        if not has_signal:
            return None
        
        signal = None
        
        if signal_type == "golden_cross":
            # 金叉 - 买入/开多
            signal = self._handle_golden_cross(bar, fast_ma, slow_ma)
        elif signal_type == "death_cross":
            # 死叉 - 卖出/开空
            signal = self._handle_death_cross(bar, fast_ma, slow_ma)
        
        if signal:
            self._record_signal(signal)
        return signal
    
    def _handle_golden_cross(self, bar: BarData, fast_ma: float, slow_ma: float) -> Optional[Signal]:
        """处理金叉信号"""
        signal = None
        
        if self._position <= 0:
            # 如果有空头仓位，先平仓
            if self._position < 0:
                signal = Signal(
                    timestamp=bar.timestamp,
                    symbol=bar.symbol,
                    signal_type=SignalType.CLOSE_SHORT,
                    price=bar.close,
                    confidence=0.75,
                    metadata={
                        "fast_ma": fast_ma,
                        "slow_ma": slow_ma,
                        "cross_type": "golden_cross",
                        "ma_type": self.get_param("ma_type"),
                    }
                )
                self._record_signal(signal)
            
            # 开多仓
            signal = Signal(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                signal_type=SignalType.OPEN_LONG,
                price=bar.close,
                confidence=0.8,
                metadata={
                    "fast_ma": fast_ma,
                    "slow_ma": slow_ma,
                    "cross_type": "golden_cross",
                    "ma_type": self.get_param("ma_type"),
                }
            )
            self._position = 1
        
        return signal
    
    def _handle_death_cross(self, bar: BarData, fast_ma: float, slow_ma: float) -> Optional[Signal]:
        """处理死叉信号"""
        signal = None
        
        if self._position >= 0:
            # 如果有多头仓位，先平仓
            if self._position > 0:
                signal = Signal(
                    timestamp=bar.timestamp,
                    symbol=bar.symbol,
                    signal_type=SignalType.CLOSE_LONG,
                    price=bar.close,
                    confidence=0.75,
                    metadata={
                        "fast_ma": fast_ma,
                        "slow_ma": slow_ma,
                        "cross_type": "death_cross",
                        "ma_type": self.get_param("ma_type"),
                    }
                )
                self._record_signal(signal)
            
            # 开空仓
            signal = Signal(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                signal_type=SignalType.OPEN_SHORT,
                price=bar.close,
                confidence=0.8,
                metadata={
                    "fast_ma": fast_ma,
                    "slow_ma": slow_ma,
                    "cross_type": "death_cross",
                    "ma_type": self.get_param("ma_type"),
                }
            )
            self._position = -1
        
        return signal
    
    def on_tick(self, tick: TickData) -> Optional[Signal]:
        """处理Tick数据"""
        bar = BarData(
            timestamp=tick.timestamp,
            symbol=tick.symbol,
            open=tick.price,
            high=tick.price,
            low=tick.price,
            close=tick.price,
            volume=tick.volume,
        )
        return self.on_bar(bar)
    
    def get_position(self) -> int:
        """获取当前仓位状态"""
        return self._position
    
    def get_ma_values(self) -> Tuple[Optional[float], Optional[float]]:
        """
        获取当前均线值
        
        Returns:
            (快速MA, 慢速MA)
        """
        return self._cached_fast_ma, self._cached_slow_ma
    
    def get_ma_history(self) -> Tuple[NDArray[np.float64], NDArray[np.float64]]:
        """
        获取均线历史
        
        Returns:
            (快速MA历史, 慢速MA历史)
        """
        return self._fast_ma_history.copy(), self._slow_ma_history.copy()
    
    def get_trend_direction(self) -> str:
        """
        获取当前趋势方向
        
        Returns:
            "up"/"down"/"neutral"
        """
        if self._cached_fast_ma is None or self._cached_slow_ma is None:
            return "neutral"
        
        if self._cached_fast_ma > self._cached_slow_ma:
            return "up"
        elif self._cached_fast_ma < self._cached_slow_ma:
            return "down"
        return "neutral"
    
    def get_ma_spread(self) -> Optional[float]:
        """获取MA差值 (Fast - Slow)"""
        if self._cached_fast_ma is None or self._cached_slow_ma is None:
            return None
        return self._cached_fast_ma - self._cached_slow_ma
    
    def get_ma_spread_ratio(self) -> Optional[float]:
        """获取MA差值比例 (Fast - Slow) / Slow"""
        if self._cached_fast_ma is None or self._cached_slow_ma is None:
            return None
        if self._cached_slow_ma == 0:
            return 0.0
        return (self._cached_fast_ma - self._cached_slow_ma) / self._cached_slow_ma
