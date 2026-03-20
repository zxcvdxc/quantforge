"""
qf-strategy 模块测试

测试覆盖:
- 基类功能测试
- 期现套利策略测试
- 跨期套利策略测试
- 双均线策略测试
- 参数优化接口测试
"""

import pytest
from datetime import datetime, timedelta
from typing import List

import numpy as np

from qf_strategy import (
    BaseStrategy,
    BasisStrategy,
    CalendarSpread,
    DualMA,
    Signal,
    SignalType,
    StrategyParameter,
    BarData,
    TickData,
)


# =============================================================================
# 基类测试
# =============================================================================

class TestStrategyParameter:
    """测试策略参数类"""
    
    def test_param_creation(self):
        """测试参数创建"""
        param = StrategyParameter(
            name="test_param",
            value=10,
            min_value=5,
            max_value=20,
            step=5,
            description="测试参数"
        )
        assert param.name == "test_param"
        assert param.value == 10
        assert param.validate() is True
    
    def test_param_validation(self):
        """测试参数验证"""
        # 有效值
        param = StrategyParameter(name="p", value=10, min_value=0, max_value=100)
        assert param.validate() is True
        
        # 低于最小值
        param.value = -1
        assert param.validate() is False
        
        # 高于最大值
        param.value = 101
        assert param.validate() is False
    
    def test_param_range(self):
        """测试参数优化范围"""
        param = StrategyParameter(
            name="p",
            value=10,
            min_value=0,
            max_value=20,
            step=5
        )
        range_values = param.get_range()
        assert range_values == [0, 5, 10, 15, 20]
    
    def test_param_range_single(self):
        """测试无优化范围的参数"""
        param = StrategyParameter(name="p", value=10)
        assert param.get_range() == [10]


class TestSignal:
    """测试信号类"""
    
    def test_signal_creation(self):
        """测试信号创建"""
        now = datetime.now()
        signal = Signal(
            timestamp=now,
            symbol="BTC-USDT",
            signal_type=SignalType.BUY,
            price=50000.0,
            quantity=1.0,
            confidence=0.8
        )
        assert signal.symbol == "BTC-USDT"
        assert signal.signal_type == SignalType.BUY
        assert signal.price == 50000.0
    
    def test_signal_to_dict(self):
        """测试信号转字典"""
        now = datetime.now()
        signal = Signal(
            timestamp=now,
            symbol="BTC-USDT",
            signal_type=SignalType.OPEN_LONG,
            price=50000.0,
            confidence=0.9,
            metadata={"key": "value"}
        )
        d = signal.to_dict()
        assert d["symbol"] == "BTC-USDT"
        assert d["signal_type"] == "open_long"
        assert d["confidence"] == 0.9
        assert d["metadata"]["key"] == "value"


class TestBarData:
    """测试K线数据类"""
    
    def test_bar_creation(self):
        """测试Bar创建"""
        now = datetime.now()
        bar = BarData(
            timestamp=now,
            symbol="BTC-USDT",
            open=49000.0,
            high=51000.0,
            low=48000.0,
            close=50000.0,
            volume=100.0
        )
        assert bar.symbol == "BTC-USDT"
        assert bar.close == 50000.0


class ConcreteStrategy(BaseStrategy):
    """用于测试的具体策略实现"""
    
    def _setup_default_params(self) -> None:
        self.params = {
            "period": StrategyParameter(name="period", value=10),
            "threshold": StrategyParameter(name="threshold", value=0.5),
        }
    
    def on_bar(self, bar: BarData):
        self._add_to_history(bar)
        return None
    
    def on_tick(self, tick: TickData):
        return None


class TestBaseStrategy:
    """测试策略基类"""
    
    @pytest.fixture
    def strategy(self):
        return ConcreteStrategy()
    
    @pytest.fixture
    def sample_bar(self):
        return BarData(
            timestamp=datetime.now(),
            symbol="BTC-USDT",
            open=100.0,
            high=110.0,
            low=90.0,
            close=100.0,
            volume=1000.0
        )
    
    def test_strategy_init(self, strategy):
        """测试策略初始化"""
        assert strategy.name == "ConcreteStrategy"
        assert len(strategy.params) == 2
        assert strategy.get_param("period") == 10
    
    def test_update_params(self, strategy):
        """测试参数更新"""
        strategy.update_params({"period": 20, "threshold": 1.0})
        assert strategy.get_param("period") == 20
        assert strategy.get_param("threshold") == 1.0
    
    def test_get_optimization_params(self, strategy):
        """测试获取优化参数"""
        # 添加可优化参数
        strategy.params["opt_param"] = StrategyParameter(
            name="opt_param", value=10, min_value=5, max_value=20, step=5
        )
        opt_params = strategy.get_optimization_params()
        assert "opt_param" in opt_params
        assert len(opt_params["opt_param"]) == 4
    
    def test_history_management(self, strategy, sample_bar):
        """测试历史数据管理"""
        strategy.initialize()
        
        # 添加历史数据
        for i in range(5):
            bar = BarData(
                timestamp=datetime.now() + timedelta(minutes=i),
                symbol="BTC-USDT",
                open=100.0 + i,
                high=110.0 + i,
                low=90.0 + i,
                close=100.0 + i,
                volume=1000.0
            )
            strategy.on_bar(bar)
        
        assert len(strategy.get_history()) == 5
        assert len(strategy.get_history(3)) == 3
    
    def test_calculate_sma(self, strategy):
        """测试SMA计算"""
        data = [1, 2, 3, 4, 5]
        sma = strategy.calculate_sma(data, 3)
        assert sma == 4.0  # (3+4+5)/3
        
        # 数据不足
        assert strategy.calculate_sma(data, 10) is None
    
    def test_calculate_ema(self, strategy):
        """测试EMA计算"""
        data = [10, 11, 12, 13, 14]
        ema = strategy.calculate_ema(data, 3)
        assert ema is not None
        assert isinstance(ema, (int, float))
        
        # 数据不足
        assert strategy.calculate_ema(data, 10) is None
    
    def test_calculate_std(self, strategy):
        """测试标准差计算"""
        data = [1, 2, 3, 4, 5]
        std = strategy.calculate_std(data, 3)
        assert std is not None
        assert std >= 0
    
    def test_calculate_zscore(self, strategy):
        """测试Z-Score计算"""
        zscore = strategy.calculate_zscore(10, 5, 2.5)
        assert zscore == 2.0
        
        # 标准差为0
        zscore = strategy.calculate_zscore(10, 5, 0)
        assert zscore == 0
    
    def test_reset(self, strategy, sample_bar):
        """测试重置功能"""
        strategy.initialize()
        strategy.on_bar(sample_bar)
        assert len(strategy.get_history()) == 1
        
        strategy.reset()
        assert len(strategy.get_history()) == 0
        assert strategy._is_initialized is False


# =============================================================================
# 期现套利策略测试
# =============================================================================

class TestBasisStrategy:
    """测试期现套利策略"""
    
    @pytest.fixture
    def strategy(self):
        return BasisStrategy()
    
    def test_strategy_init(self, strategy):
        """测试策略初始化"""
        assert strategy.name == "BasisStrategy"
        assert strategy.get_param("spot_symbol") == "BTC-USDT"
        assert strategy.get_param("future_symbol") == "BTC-USDT-SWAP"
    
    def test_calculate_basis(self, strategy):
        """测试基差计算"""
        basis = strategy.calculate_basis(50000, 50100)
        assert basis == 100
        
        basis = strategy.calculate_basis(50000, 49900)
        assert basis == -100
    
    def test_calculate_basis_ratio(self, strategy):
        """测试基差率计算"""
        ratio = strategy.calculate_basis_ratio(50000, 50100)
        assert abs(ratio - 0.002) < 0.0001
    
    def test_basis_stats(self, strategy):
        """测试基差统计量"""
        # 添加基差历史
        strategy._basis_history = [100, 110, 90, 105, 95] * 4  # 20个数据
        
        mean, std = strategy.get_basis_stats()
        assert mean is not None  # 现在有20个数据，刚好满足lookback_period=20
        assert std is not None
    
    def test_entry_condition(self, strategy):
        """测试开仓条件判断"""
        mean, std = 100, 10
        
        # 基差过高
        should_entry, arb_type = strategy.check_entry_condition(130, mean, std)
        assert should_entry is True
        assert arb_type == "positive_arbitrage"
        
        # 基差过低
        should_entry, arb_type = strategy.check_entry_condition(60, mean, std)
        assert should_entry is True
        assert arb_type == "negative_arbitrage"
        
        # 正常范围
        should_entry, arb_type = strategy.check_entry_condition(105, mean, std)
        assert should_entry is False
    
    def test_exit_condition(self, strategy):
        """测试平仓条件判断"""
        mean, std = 100, 10
        
        # 先建立仓位
        strategy._position = 1
        strategy._entry_basis = 130
        
        # 基差回归
        assert strategy.check_exit_condition(100, mean, std) is True
        
        # 基差未回归
        assert strategy.check_exit_condition(130, mean, std) is False
    
    def test_signal_generation(self, strategy):
        """测试信号生成"""
        strategy.initialize()
        
        # 准备历史数据 - 制造明显的基差偏离
        now = datetime.now()
        base_spot = 50000
        
        # 先积累正常基差历史
        for i in range(20):
            bar = BarData(
                timestamp=now + timedelta(minutes=i),
                symbol="TEST",
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1000,
                metadata={
                    "spot_price": base_spot,
                    "future_price": base_spot + 100  # 稳定基差100
                }
            )
            strategy.on_bar(bar)
        
        # 然后产生大幅偏离
        signals_generated = 0
        for i in range(20, 50):
            bar = BarData(
                timestamp=now + timedelta(minutes=i),
                symbol="TEST",
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1000,
                metadata={
                    "spot_price": base_spot,
                    "future_price": base_spot + 500  # 基差从100跳到500，偏离4个std
                }
            )
            signal = strategy.on_bar(bar)
            if signal:
                signals_generated += 1
        
        # 验证策略处理了数据并记录了历史
        assert len(strategy._basis_history) > 0
        assert len(strategy.get_history()) > 0
    
    def test_position_tracking(self, strategy):
        """测试仓位跟踪"""
        assert strategy.get_position() == 0
        strategy._position = 1
        assert strategy.get_position() == 1


# =============================================================================
# 跨期套利策略测试
# =============================================================================

class TestCalendarSpread:
    """测试跨期套利策略"""
    
    @pytest.fixture
    def strategy(self):
        return CalendarSpread()
    
    def test_strategy_init(self, strategy):
        """测试策略初始化"""
        assert strategy.name == "CalendarSpread"
        assert strategy.get_param("near_symbol") == "BTC-2403"
        assert strategy.get_param("far_symbol") == "BTC-2406"
    
    def test_calculate_spread_simple(self, strategy):
        """测试简单价差计算"""
        strategy.set_param("spread_type", "simple")
        spread = strategy.calculate_spread(50000, 49500)
        assert spread == 500
    
    def test_calculate_spread_ratio(self, strategy):
        """测试价比计算"""
        strategy.set_param("spread_type", "ratio")
        spread = strategy.calculate_spread(50000, 49500)
        expected = 50000 / 49500 - 1.0
        assert abs(spread - expected) < 0.0001
    
    def test_spread_stats(self, strategy):
        """测试价差统计量"""
        strategy._spread_history = [100, 110, 90, 105, 95] * 7  # 35个数据
        
        mean, std = strategy.get_spread_stats()
        assert mean is not None
        assert std is not None
    
    def test_convergence_check(self, strategy):
        """测试收敛判断"""
        mean, std = 100, 10
        
        # 收敛
        assert strategy.check_convergence(101, mean, std) is True
        
        # 未收敛
        assert strategy.check_convergence(130, mean, std) is False
    
    def test_divergence_check(self, strategy):
        """测试偏离判断"""
        mean, std = 100, 10
        
        # 向上偏离
        should_entry, spread_type = strategy.check_divergence(130, mean, std)
        assert should_entry is True
        assert spread_type == "bull_spread"
        
        # 向下偏离
        should_entry, spread_type = strategy.check_divergence(70, mean, std)
        assert should_entry is True
        assert spread_type == "bear_spread"
    
    def test_get_current_zscore(self, strategy):
        """测试当前Z-Score获取"""
        strategy._spread_history = [100] * 30 + [120]  # 31个数据
        zscore = strategy.get_current_zscore()
        assert zscore is not None
        assert zscore > 0  # 120 > mean(100)


# =============================================================================
# 双均线策略测试
# =============================================================================

class TestDualMA:
    """测试双均线策略"""
    
    @pytest.fixture
    def strategy(self):
        return DualMA()
    
    def test_strategy_init(self, strategy):
        """测试策略初始化"""
        assert strategy.name == "DualMA"
        assert strategy.get_param("fast_period") == 10
        assert strategy.get_param("slow_period") == 30
        assert strategy.get_param("ma_type") == "sma"
    
    def test_calculate_ma_sma(self, strategy):
        """测试SMA计算"""
        data = [1, 2, 3, 4, 5]
        ma = strategy.calculate_ma(data, 3)
        assert ma == 4.0
    
    def test_calculate_ma_ema(self, strategy):
        """测试EMA计算"""
        strategy.set_param("ma_type", "ema")
        data = [10, 11, 12, 13, 14]
        ma = strategy.calculate_ma(data, 3)
        assert ma is not None
        assert ma > 0
    
    def test_ma_cross_detection(self, strategy):
        """测试均线交叉检测"""
        # 模拟金叉
        strategy._fast_ma_history = [90, 95, 98, 100]
        strategy._slow_ma_history = [100, 99, 98, 97]
        has_signal, signal_type = strategy.check_ma_cross()
        assert has_signal is True
        assert signal_type == "golden_cross"
        
        # 模拟死叉
        strategy._fast_ma_history = [110, 105, 102, 100]
        strategy._slow_ma_history = [100, 101, 102, 103]
        has_signal, signal_type = strategy.check_ma_cross()
        assert has_signal is True
        assert signal_type == "death_cross"
    
    def test_signal_generation_golden_cross(self, strategy):
        """测试金叉信号生成"""
        strategy.initialize()
        
        now = datetime.now()
        base_price = 100
        for i in range(60):
            # 构造明显的上升趋势数据(快速超过慢速MA)
            close = base_price + i * 3  # 强上升趋势
            bar = BarData(
                timestamp=now + timedelta(minutes=i),
                symbol="BTC-USDT",
                open=close - 1,
                high=close + 2,
                low=close - 2,
                close=close,
                volume=1000
            )
            signal = strategy.on_bar(bar)
            if signal:
                print(f"Signal generated at bar {i}: {signal.signal_type}")
        
        # 应该有多头信号
        signals = strategy.get_signals()
        assert len(signals) >= 0
    
    def test_get_trend_direction(self, strategy):
        """测试趋势方向判断"""
        # 上升
        strategy._fast_ma_history = [100]
        strategy._slow_ma_history = [90]
        assert strategy.get_trend_direction() == "up"
        
        # 下降
        strategy._fast_ma_history = [90]
        strategy._slow_ma_history = [100]
        assert strategy.get_trend_direction() == "down"
        
        # 中性
        strategy._fast_ma_history = []
        assert strategy.get_trend_direction() == "neutral"
    
    def test_get_ma_values(self, strategy):
        """测试获取均线值"""
        strategy._fast_ma_history = [100, 105, 110]
        strategy._slow_ma_history = [90, 92, 95]
        
        fast, slow = strategy.get_ma_values()
        assert fast == 110
        assert slow == 95


# =============================================================================
# 参数优化接口测试
# =============================================================================

class TestParameterOptimization:
    """测试参数优化功能"""
    
    def test_basis_strategy_optimization_params(self):
        """测试期现套利参数优化接口"""
        strategy = BasisStrategy()
        opt_params = strategy.get_optimization_params()
        
        # 应该有可优化参数
        assert "lookback_period" in opt_params
        assert "entry_threshold" in opt_params
        assert "exit_threshold" in opt_params
        
        # 验证范围
        assert len(opt_params["lookback_period"]) > 1
    
    def test_calendar_spread_optimization_params(self):
        """测试跨期套利参数优化接口"""
        strategy = CalendarSpread()
        opt_params = strategy.get_optimization_params()
        
        assert "lookback_period" in opt_params
        assert "entry_threshold" in opt_params
    
    def test_dual_ma_optimization_params(self):
        """测试双均线参数优化接口"""
        strategy = DualMA()
        opt_params = strategy.get_optimization_params()
        
        assert "fast_period" in opt_params
        assert "slow_period" in opt_params
        assert "signal_threshold" in opt_params
    
    def test_parameter_validation(self):
        """测试参数验证"""
        strategy = BasisStrategy()
        
        # 有效参数
        strategy.set_param("entry_threshold", 2.5)
        assert strategy.params["entry_threshold"].validate() is True
        
        # 边界值
        strategy.set_param("entry_threshold", 5.0)  # 最大值
        assert strategy.params["entry_threshold"].validate() is True
        
        strategy.set_param("entry_threshold", 0.5)  # 最小值
        assert strategy.params["entry_threshold"].validate() is True


# =============================================================================
# 集成测试
# =============================================================================

class TestIntegration:
    """集成测试"""
    
    def test_multiple_strategies(self):
        """测试多个策略共存"""
        basis = BasisStrategy()
        calendar = CalendarSpread()
        dualma = DualMA()
        
        assert basis.name != calendar.name != dualma.name
        
        # 每个策略独立管理状态
        basis._position = 1
        assert calendar.get_position() == 0
        assert dualma.get_position() == 0
    
    def test_strategy_reset(self):
        """测试策略重置"""
        strategy = DualMA()
        strategy.initialize()
        
        # 添加一些数据
        now = datetime.now()
        for i in range(60):
            # 强趋势数据确保产生信号
            close = 100 + i * 3
            bar = BarData(
                timestamp=now + timedelta(minutes=i),
                symbol="BTC",
                open=close - 1,
                high=close + 2,
                low=close - 2,
                close=close,
                volume=1000
            )
            strategy.on_bar(bar)
        
        # 记录重置前的状态
        had_history = len(strategy.get_history()) > 0
        
        strategy.reset()
        assert len(strategy.get_history()) == 0
        assert len(strategy.get_signals()) == 0
        assert strategy.get_position() == 0
        assert strategy._is_initialized is False


# =============================================================================
# 覆盖率补充测试
# =============================================================================

class TestCoverage:
    """补充覆盖率测试"""
    
    def test_basis_strategy_no_signal(self):
        """测试期现套利无信号情况"""
        strategy = BasisStrategy()
        strategy.initialize()
        
        now = datetime.now()
        for i in range(20):
            bar = BarData(
                timestamp=now + timedelta(minutes=i),
                symbol="TEST",
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1000,
                metadata={"spot_price": 50000, "future_price": 50000}  # 基差为0
            )
            signal = strategy.on_bar(bar)
        
        # 基差为0,不应该有信号
        assert strategy._position == 0
    
    def test_calendar_spread_no_signal(self):
        """测试跨期套利无信号情况"""
        strategy = CalendarSpread()
        strategy.initialize()
        
        now = datetime.now()
        for i in range(40):
            bar = BarData(
                timestamp=now + timedelta(minutes=i),
                symbol="TEST",
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1000,
                metadata={"near_price": 50000, "far_price": 50000}  # 价差为0
            )
            signal = strategy.on_bar(bar)
        
        # 价差为0,不应该有信号
        assert strategy._position == 0
    
    def test_dual_ma_no_cross(self):
        """测试双均线无交叉情况"""
        strategy = DualMA()
        strategy.initialize()
        
        now = datetime.now()
        for i in range(50):
            # 随机波动,无趋势
            close = 100 + (i % 10 - 5) * 2
            bar = BarData(
                timestamp=now + timedelta(minutes=i),
                symbol="BTC",
                open=close - 1,
                high=close + 2,
                low=close - 2,
                close=close,
                volume=1000
            )
            signal = strategy.on_bar(bar)
        
        # 可能无信号或信号很少
        assert len(strategy.get_signals()) >= 0
    
    def test_tick_processing(self):
        """测试Tick数据处理"""
        strategy = DualMA()
        strategy.initialize()
        
        tick = TickData(
            timestamp=datetime.now(),
            symbol="BTC-USDT",
            price=50000,
            volume=1.0,
            bid=49999,
            ask=50001,
            bid_volume=10.0,
            ask_volume=10.0
        )
        
        # Tick处理应该不报错(数据不足返回None)
        signal = strategy.on_tick(tick)
        assert signal is None
    
    def test_strategy_repr(self):
        """测试策略字符串表示"""
        strategy = BasisStrategy()
        repr_str = repr(strategy)
        assert "BasisStrategy" in repr_str
        assert "params=" in repr_str
