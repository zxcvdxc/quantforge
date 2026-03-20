"""
双均线策略 - Dual Moving Average Strategy

原理: 利用短期均线与长期均线的交叉信号进行趋势跟踪
- 短期均线上穿长期均线(金叉): 买入信号
- 短期均线下穿长期均线(死叉): 卖出信号
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from qf_strategy.base import (
    BarData,
    BaseStrategy,
    Signal,
    SignalType,
    StrategyParameter,
    TickData,
)


class DualMA(BaseStrategy):
    """
    双均线趋势跟踪策略
    
    交易逻辑:
    - 短周期MA上穿长周期MA(金叉): 开多仓
    - 短周期MA下穿长周期MA(死叉): 开空仓或平多仓
    - 支持多种移动平均类型: SMA, EMA
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
        self._closes: List[float] = []
        self._fast_ma_history: List[float] = []
        self._slow_ma_history: List[float] = []
        self._position: int = 0  # 0=无仓位, 1=多头, -1=空头
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
        self._closes.clear()
        self._fast_ma_history.clear()
        self._slow_ma_history.clear()
        self._position = 0
    
    def calculate_ma(self, data: List[float], period: int) -> Optional[float]:
        """
        计算移动平均
        
        Args:
            data: 价格数据
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
    
    def check_ma_cross(self) -> tuple[bool, str]:
        """
        检查均线交叉信号
        
        Returns:
            (是否有信号, 信号类型: "golden_cross"/"death_cross"/"")
        """
        if len(self._fast_ma_history) < 2 or len(self._slow_ma_history) < 2:
            return False, ""
        
        # 前一周期
        prev_fast = self._fast_ma_history[-2]
        prev_slow = self._slow_ma_history[-2]
        
        # 当前周期
        curr_fast = self._fast_ma_history[-1]
        curr_slow = self._slow_ma_history[-1]
        
        # 计算信号阈值
        signal_threshold = float(self.get_param("signal_threshold"))
        
        # 金叉: 短期上穿长期
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            # 确认价差是否超过阈值
            diff_ratio = abs(curr_fast - curr_slow) / curr_slow if curr_slow > 0 else 0
            if diff_ratio >= signal_threshold:
                return True, "golden_cross"
        
        # 死叉: 短期下穿长期
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            diff_ratio = abs(curr_fast - curr_slow) / curr_slow if curr_slow > 0 else 0
            if diff_ratio >= signal_threshold:
                return True, "death_cross"
        
        return False, ""
    
    def on_bar(self, bar: BarData) -> Optional[Signal]:
        """
        处理K线数据
        
        Args:
            bar: K线数据
            
        Returns:
            交易信号或None
        """
        self._add_to_history(bar)
        
        # 记录收盘价
        self._closes.append(bar.close)
        
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
        
        self._fast_ma_history.append(fast_ma)
        self._slow_ma_history.append(slow_ma)
        
        # 限制MA历史长度
        if len(self._fast_ma_history) > max_period:
            self._fast_ma_history = self._fast_ma_history[-max_period:]
            self._slow_ma_history = self._slow_ma_history[-max_period:]
        
        # 检查交叉信号
        has_signal, signal_type = self.check_ma_cross()
        
        if not has_signal:
            return None
        
        signal = None
        
        if signal_type == "golden_cross":
            # 金叉 - 买入/开多
            if self._position <= 0:
                # 如果有空头仓位,先平仓
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
        
        elif signal_type == "death_cross":
            # 死叉 - 卖出/开空
            if self._position >= 0:
                # 如果有多头仓位,先平仓
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
        
        if signal:
            self._record_signal(signal)
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
    
    def get_ma_values(self) -> tuple[Optional[float], Optional[float]]:
        """
        获取当前均线值
        
        Returns:
            (快速MA, 慢速MA)
        """
        if not self._fast_ma_history or not self._slow_ma_history:
            return None, None
        return self._fast_ma_history[-1], self._slow_ma_history[-1]
    
    def get_ma_history(self) -> tuple[List[float], List[float]]:
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
        if not self._fast_ma_history or not self._slow_ma_history:
            return "neutral"
        
        fast = self._fast_ma_history[-1]
        slow = self._slow_ma_history[-1]
        
        if fast > slow:
            return "up"
        elif fast < slow:
            return "down"
        return "neutral"
