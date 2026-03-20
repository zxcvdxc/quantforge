"""
期现套利策略 - Basis Arbitrage Strategy

原理: 利用期货价格与现货价格之间的基差进行套利
当基差偏离历史均值超过一定阈值时，预期基差会收敛回归
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


class BasisStrategy(BaseStrategy):
    """
    期现套利策略
    
    交易逻辑:
    - 当基差 > 阈值上限时: 做空期货 + 买入现货 (预期基差收敛)
    - 当基差 < 阈值下限时: 做多期货 + 卖出现货 (预期基差收敛)
    - 当基差回归均值附近时: 平仓获利
    """
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        初始化期现套利策略
        
        Args:
            params: 策略参数
                - spot_symbol: 现货代码
                - future_symbol: 期货代码  
                - lookback_period: 回看周期(计算历史基差均值和标准差)
                - entry_threshold: 开仓阈值(几倍标准差)
                - exit_threshold: 平仓阈值(几倍标准差)
                - max_history: 最大历史数据条数
        """
        self._basis_history: List[float] = []
        self._position: int = 0  # 0=无仓位, 1=正向套利(多现空期), -1=反向套利(空现多期)
        self._entry_basis: Optional[float] = None  # 开仓时的基差
        super().__init__(name="BasisStrategy", params=params)
    
    def _setup_default_params(self) -> None:
        """设置默认参数"""
        self.params = {
            "spot_symbol": StrategyParameter(
                name="spot_symbol",
                value="BTC-USDT",
                description="现货交易对代码"
            ),
            "future_symbol": StrategyParameter(
                name="future_symbol", 
                value="BTC-USDT-SWAP",
                description="期货交易对代码"
            ),
            "lookback_period": StrategyParameter(
                name="lookback_period",
                value=20,
                min_value=5,
                max_value=100,
                step=5,
                description="回看周期"
            ),
            "entry_threshold": StrategyParameter(
                name="entry_threshold",
                value=2.0,
                min_value=0.5,
                max_value=5.0,
                step=0.5,
                description="开仓阈值(标准差倍数)"
            ),
            "exit_threshold": StrategyParameter(
                name="exit_threshold",
                value=0.5,
                min_value=0.1,
                max_value=2.0,
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
        self._basis_history.clear()
        self._position = 0
        self._entry_basis = None
    
    def calculate_basis(self, spot_price: float, future_price: float) -> float:
        """
        计算基差 = 期货价格 - 现货价格
        
        Args:
            spot_price: 现货价格
            future_price: 期货价格
            
        Returns:
            基差值
        """
        return future_price - spot_price
    
    def calculate_basis_ratio(self, spot_price: float, future_price: float) -> float:
        """
        计算基差率 = (期货价格 - 现货价格) / 现货价格
        
        Args:
            spot_price: 现货价格
            future_price: 期货价格
            
        Returns:
            基差率
        """
        if spot_price == 0:
            return 0.0
        return (future_price - spot_price) / spot_price
    
    def get_basis_stats(self) -> Tuple[Optional[float], Optional[float]]:
        """
        获取基差统计量(均值和标准差)
        
        Returns:
            (均值, 标准差)
        """
        period = int(self.get_param("lookback_period"))
        if len(self._basis_history) < period:
            return None, None
        
        recent_basis = self._basis_history[-period:]
        mean = np.mean(recent_basis)
        std = np.std(recent_basis)
        return mean, std
    
    def check_entry_condition(self, basis: float, mean: float, std: float) -> Tuple[bool, str]:
        """
        检查开仓条件
        
        Args:
            basis: 当前基差
            mean: 历史基差均值
            std: 历史基差标准差
            
        Returns:
            (是否开仓, 信号类型描述)
        """
        if std == 0:
            return False, ""
        
        entry_threshold = float(self.get_param("entry_threshold"))
        zscore = (basis - mean) / std
        
        # 基差过高: 做空期货, 买入现货
        if zscore > entry_threshold and self._position != 1:
            return True, "positive_arbitrage"
        
        # 基差过低: 做多期货, 卖出现货
        if zscore < -entry_threshold and self._position != -1:
            return True, "negative_arbitrage"
        
        return False, ""
    
    def check_exit_condition(self, basis: float, mean: float, std: float) -> bool:
        """
        检查平仓条件
        
        Args:
            basis: 当前基差
            mean: 历史基差均值
            std: 历史基差标准差
            
        Returns:
            是否平仓
        """
        if std == 0 or self._entry_basis is None:
            return False
        
        exit_threshold = float(self.get_param("exit_threshold"))
        zscore = (basis - mean) / std
        
        # 基差回归均值附近,平仓获利
        if abs(zscore) < exit_threshold:
            return True
        
        # 或者基差向不利方向移动超过止损阈值
        if self._position == 1:  # 正向套利
            # 如果基差进一步扩大, 止损
            basis_diff = basis - self._entry_basis
            if basis_diff > std * 1.5:  # 动态止损
                return True
        elif self._position == -1:  # 反向套利
            basis_diff = self._entry_basis - basis
            if basis_diff > std * 1.5:  # 动态止损
                return True
        
        return False
    
    def on_bar(self, bar: BarData) -> Optional[Signal]:
        """
        处理K线数据
        
        预期 bar.metadata 中包含:
        - spot_price: 现货价格
        - future_price: 期货价格
        """
        self._add_to_history(bar)
        
        # 获取期现价格
        spot_price = bar.metadata.get("spot_price", bar.close)
        future_price = bar.metadata.get("future_price", bar.close)
        
        # 计算基差
        basis = self.calculate_basis(spot_price, future_price)
        self._basis_history.append(basis)
        
        # 限制历史长度
        max_lookback = int(self.get_param("lookback_period")) * 3
        if len(self._basis_history) > max_lookback:
            self._basis_history = self._basis_history[-max_lookback:]
        
        # 获取基差统计量
        mean, std = self.get_basis_stats()
        if mean is None or std is None:
            return None
        
        signal = None
        
        # 检查平仓条件
        if self._position != 0 and self.check_exit_condition(basis, mean, std):
            if self._position == 1:
                # 平正向套利仓位
                signal = Signal(
                    timestamp=bar.timestamp,
                    symbol=f"{self.get_param('future_symbol')},{self.get_param('spot_symbol')}",
                    signal_type=SignalType.CLOSE_SHORT,
                    price=future_price,
                    confidence=0.8,
                    metadata={
                        "basis": basis,
                        "mean": mean,
                        "std": std,
                        "zscore": (basis - mean) / std if std > 0 else 0,
                        "position": "positive_arbitrage",
                        "exit_reason": "convergence",
                    }
                )
            elif self._position == -1:
                # 平反向套利仓位
                signal = Signal(
                    timestamp=bar.timestamp,
                    symbol=f"{self.get_param('future_symbol')},{self.get_param('spot_symbol')}",
                    signal_type=SignalType.CLOSE_LONG,
                    price=future_price,
                    confidence=0.8,
                    metadata={
                        "basis": basis,
                        "mean": mean,
                        "std": std,
                        "zscore": (basis - mean) / std if std > 0 else 0,
                        "position": "negative_arbitrage",
                        "exit_reason": "convergence",
                    }
                )
            self._position = 0
            self._entry_basis = None
        
        # 检查开仓条件
        elif self._position == 0:
            should_entry, arb_type = self.check_entry_condition(basis, mean, std)
            if should_entry:
                if arb_type == "positive_arbitrage":
                    # 正向套利: 做空期货, 买入现货
                    signal = Signal(
                        timestamp=bar.timestamp,
                        symbol=f"{self.get_param('future_symbol')},{self.get_param('spot_symbol')}",
                        signal_type=SignalType.OPEN_SHORT,
                        price=future_price,
                        confidence=min(abs((basis - mean) / std) / 2.0, 1.0),
                        metadata={
                            "basis": basis,
                            "mean": mean,
                            "std": std,
                            "zscore": (basis - mean) / std if std > 0 else 0,
                            "arb_type": arb_type,
                            "spot_price": spot_price,
                        }
                    )
                    self._position = 1
                    self._entry_basis = basis
                    
                elif arb_type == "negative_arbitrage":
                    # 反向套利: 做多期货, 卖出现货
                    signal = Signal(
                        timestamp=bar.timestamp,
                        symbol=f"{self.get_param('future_symbol')},{self.get_param('spot_symbol')}",
                        signal_type=SignalType.OPEN_LONG,
                        price=future_price,
                        confidence=min(abs((basis - mean) / std) / 2.0, 1.0),
                        metadata={
                            "basis": basis,
                            "mean": mean,
                            "std": std,
                            "zscore": (basis - mean) / std if std > 0 else 0,
                            "arb_type": arb_type,
                            "spot_price": spot_price,
                        }
                    )
                    self._position = -1
                    self._entry_basis = basis
        
        if signal:
            self._record_signal(signal)
        return signal
    
    def on_tick(self, tick: TickData) -> Optional[Signal]:
        """处理Tick数据 - 期现套利通常基于K线"""
        # 将tick转换为bar进行处理
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
    
    def get_basis_history(self) -> List[float]:
        """获取基差历史"""
        return self._basis_history.copy()
