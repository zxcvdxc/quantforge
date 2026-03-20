"""
跨期套利策略 - Calendar Spread Strategy

原理: 利用同一品种不同到期月份期货合约之间的价差进行套利
当近月与远月合约价差偏离历史均值时,预期价差会收敛回归
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from qf_strategy.base import (
    BarData,
    BaseStrategy,
    Signal,
    SignalType,
    StrategyParameter,
    TickData,
)


class CalendarSpread(BaseStrategy):
    """
    跨期套利策略
    
    交易逻辑:
    - 当价差 > 阈值上限时: 卖出近月 + 买入远月 (预期价差收敛)
    - 当价差 < 阈值下限时: 买入近月 + 卖出远月 (预期价差收敛)
    - 当价差回归均值附近时: 平仓获利
    """
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        初始化跨期套利策略
        
        Args:
            params: 策略参数
                - near_symbol: 近月合约代码
                - far_symbol: 远月合约代码
                - lookback_period: 回看周期
                - entry_threshold: 开仓阈值(几倍标准差)
                - exit_threshold: 平仓阈值(几倍标准差)
                - max_history: 最大历史数据条数
        """
        self._spread_history: List[float] = []
        self._position: int = 0  # 0=无仓位, 1=正套(买近卖远), -1=反套(卖近买远)
        self._entry_spread: Optional[float] = None
        super().__init__(name="CalendarSpread", params=params)
    
    def _setup_default_params(self) -> None:
        """设置默认参数"""
        self.params = {
            "near_symbol": StrategyParameter(
                name="near_symbol",
                value="BTC-2403",
                description="近月合约代码"
            ),
            "far_symbol": StrategyParameter(
                name="far_symbol",
                value="BTC-2406", 
                description="远月合约代码"
            ),
            "spread_type": StrategyParameter(
                name="spread_type",
                value="simple",
                description="价差类型: simple(简单价差) 或 ratio(价比)"
            ),
            "lookback_period": StrategyParameter(
                name="lookback_period",
                value=30,
                min_value=10,
                max_value=100,
                step=5,
                description="回看周期"
            ),
            "entry_threshold": StrategyParameter(
                name="entry_threshold",
                value=1.5,
                min_value=0.5,
                max_value=4.0,
                step=0.25,
                description="开仓阈值(标准差倍数)"
            ),
            "exit_threshold": StrategyParameter(
                name="exit_threshold",
                value=0.5,
                min_value=0.1,
                max_value=1.5,
                step=0.1,
                description="平仓阈值(标准差倍数)"
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
        self._spread_history.clear()
        self._position = 0
        self._entry_spread = None
    
    def calculate_spread(self, near_price: float, far_price: float) -> float:
        """
        计算价差
        
        Args:
            near_price: 近月合约价格
            far_price: 远月合约价格
            
        Returns:
            价差
        """
        spread_type = self.get_param("spread_type")
        if spread_type == "ratio":
            # 价比
            if far_price == 0:
                return 0.0
            return near_price / far_price - 1.0
        else:
            # 简单价差
            return near_price - far_price
    
    def get_spread_stats(self) -> Tuple[Optional[float], Optional[float]]:
        """
        获取价差统计量
        
        Returns:
            (均值, 标准差)
        """
        period = int(self.get_param("lookback_period"))
        if len(self._spread_history) < period:
            return None, None
        
        recent_spread = self._spread_history[-period:]
        mean = np.mean(recent_spread)
        std = np.std(recent_spread)
        return mean, std
    
    def check_convergence(self, spread: float, mean: float, std: float) -> bool:
        """
        检查价差是否收敛到均值附近
        
        Args:
            spread: 当前价差
            mean: 历史价差均值
            std: 历史价差标准差
            
        Returns:
            是否收敛
        """
        if std == 0:
            return False
        exit_threshold = float(self.get_param("exit_threshold"))
        zscore = abs((spread - mean) / std)
        return zscore < exit_threshold
    
    def check_divergence(self, spread: float, mean: float, std: float) -> Tuple[bool, str]:
        """
        检查价差是否偏离均值(开仓机会)
        
        Args:
            spread: 当前价差
            mean: 历史价差均值
            std: 历史价差标准差
            
        Returns:
            (是否开仓, 套利类型)
        """
        if std == 0:
            return False, ""
        
        entry_threshold = float(self.get_param("entry_threshold"))
        zscore = (spread - mean) / std
        
        # 价差过高: 买入近月, 卖出远月
        if zscore > entry_threshold and self._position != 1:
            return True, "bull_spread"
        
        # 价差过低: 卖出近月, 买入远月
        if zscore < -entry_threshold and self._position != -1:
            return True, "bear_spread"
        
        return False, ""
    
    def on_bar(self, bar: BarData) -> Optional[Signal]:
        """
        处理K线数据
        
        预期 bar.metadata 中包含:
        - near_price: 近月合约价格
        - far_price: 远月合约价格
        """
        self._add_to_history(bar)
        
        # 获取合约价格
        near_price = bar.metadata.get("near_price", bar.close)
        far_price = bar.metadata.get("far_price", bar.close)
        
        # 计算价差
        spread = self.calculate_spread(near_price, far_price)
        self._spread_history.append(spread)
        
        # 限制历史长度
        max_lookback = int(self.get_param("lookback_period")) * 3
        if len(self._spread_history) > max_lookback:
            self._spread_history = self._spread_history[-max_lookback:]
        
        # 获取价差统计量
        mean, std = self.get_spread_stats()
        if mean is None or std is None:
            return None
        
        signal = None
        
        # 检查平仓条件
        if self._position != 0 and self.check_convergence(spread, mean, std):
            if self._position == 1:
                # 平牛市价差(卖出近月, 买入远月)
                signal = Signal(
                    timestamp=bar.timestamp,
                    symbol=f"{self.get_param('near_symbol')},{self.get_param('far_symbol')}",
                    signal_type=SignalType.CLOSE_LONG,
                    price=near_price,
                    confidence=0.85,
                    metadata={
                        "spread": spread,
                        "mean": mean,
                        "std": std,
                        "zscore": (spread - mean) / std if std > 0 else 0,
                        "position": "bull_spread",
                        "exit_reason": "convergence",
                    }
                )
            elif self._position == -1:
                # 平熊市价差(买入近月, 卖出远月)
                signal = Signal(
                    timestamp=bar.timestamp,
                    symbol=f"{self.get_param('near_symbol')},{self.get_param('far_symbol')}",
                    signal_type=SignalType.CLOSE_SHORT,
                    price=near_price,
                    confidence=0.85,
                    metadata={
                        "spread": spread,
                        "mean": mean,
                        "std": std,
                        "zscore": (spread - mean) / std if std > 0 else 0,
                        "position": "bear_spread",
                        "exit_reason": "convergence",
                    }
                )
            self._position = 0
            self._entry_spread = None
        
        # 检查开仓条件
        elif self._position == 0:
            should_entry, spread_type = self.check_divergence(spread, mean, std)
            if should_entry:
                if spread_type == "bull_spread":
                    # 牛市价差: 买入近月, 卖出远月
                    signal = Signal(
                        timestamp=bar.timestamp,
                        symbol=f"{self.get_param('near_symbol')},{self.get_param('far_symbol')}",
                        signal_type=SignalType.OPEN_LONG,
                        price=near_price,
                        confidence=min(abs((spread - mean) / std) / 2.0, 1.0),
                        metadata={
                            "spread": spread,
                            "mean": mean,
                            "std": std,
                            "zscore": (spread - mean) / std if std > 0 else 0,
                            "spread_type": spread_type,
                            "far_price": far_price,
                        }
                    )
                    self._position = 1
                    self._entry_spread = spread
                    
                elif spread_type == "bear_spread":
                    # 熊市价差: 卖出近月, 买入远月
                    signal = Signal(
                        timestamp=bar.timestamp,
                        symbol=f"{self.get_param('near_symbol')},{self.get_param('far_symbol')}",
                        signal_type=SignalType.OPEN_SHORT,
                        price=near_price,
                        confidence=min(abs((spread - mean) / std) / 2.0, 1.0),
                        metadata={
                            "spread": spread,
                            "mean": mean,
                            "std": std,
                            "zscore": (spread - mean) / std if std > 0 else 0,
                            "spread_type": spread_type,
                            "far_price": far_price,
                        }
                    )
                    self._position = -1
                    self._entry_spread = spread
        
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
    
    def get_spread_history(self) -> List[float]:
        """获取价差历史"""
        return self._spread_history.copy()
    
    def get_current_zscore(self) -> Optional[float]:
        """获取当前价差的Z-Score"""
        if not self._spread_history:
            return None
        mean, std = self.get_spread_stats()
        if mean is None or std is None or std == 0:
            return None
        return (self._spread_history[-1] - mean) / std
