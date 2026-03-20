"""
qf-portfolio 模块测试

测试覆盖：
- 风险平价算法
- 波动率目标配置
- 凯利公式
- ML权重预测
- PortfolioAllocator核心功能
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_returns_data():
    """生成样本收益率数据"""
    np.random.seed(42)
    n_days = 252
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
    
    # 生成相关收益率
    mean_returns = np.array([0.001, 0.0008, 0.0009, 0.0007, 0.0012])
    volatilities = np.array([0.02, 0.018, 0.015, 0.022, 0.035])
    
    # 相关矩阵
    corr = np.array([
        [1.0, 0.6, 0.5, 0.4, 0.3],
        [0.6, 1.0, 0.55, 0.45, 0.35],
        [0.5, 0.55, 1.0, 0.5, 0.4],
        [0.4, 0.45, 0.5, 1.0, 0.3],
        [0.3, 0.35, 0.4, 0.3, 1.0],
    ])
    
    # 协方差矩阵
    cov = np.outer(volatilities, volatilities) * corr
    
    # 生成收益率
    returns = np.random.multivariate_normal(mean_returns, cov, n_days)
    
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='D')
    df = pd.DataFrame(returns, columns=symbols, index=dates)
    
    return df


@pytest.fixture
def sample_symbols():
    """样本资产列表"""
    return ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]


# =============================================================================
# Test RiskParity
# =============================================================================

class TestRiskParity:
    """测试风险平价"""
    
    def test_calculate_weights(self, sample_symbols, sample_returns_data):
        """测试权重计算"""
        from qf_portfolio.risk_parity import RiskParity
        
        rp = RiskParity()
        weights = rp.calculate_weights(sample_symbols, sample_returns_data)
        
        # 验证结果
        assert isinstance(weights, dict)
        assert len(weights) == len(sample_symbols)
        assert all(s in weights for s in sample_symbols)
        assert all(w >= 0 for w in weights.values())  # 权重非负
        assert abs(sum(weights.values()) - 1.0) < 1e-6  # 权重和为1
    
    def test_risk_contribution(self, sample_symbols, sample_returns_data):
        """测试风险贡献均衡"""
        from qf_portfolio.risk_parity import RiskParity
        
        rp = RiskParity()
        weights = rp.calculate_weights(sample_symbols, sample_returns_data)
        
        # 计算风险贡献
        rc = rp.calculate_risk_contributions(weights, sample_returns_data)
        
        assert isinstance(rc, dict)
        assert len(rc) == len(sample_symbols)
        
        # 风险贡献应该大致相等（风险平价的核心性质）
        rc_values = list(rc.values())
        rc_std = np.std(rc_values)
        rc_mean = np.mean(np.abs(rc_values))
        
        # 标准差相对于均值应该较小
        if rc_mean > 0:
            assert rc_std / rc_mean < 0.5
    
    def test_risk_parity_deviation(self, sample_symbols, sample_returns_data):
        """测试风险平价偏离度"""
        from qf_portfolio.risk_parity import RiskParity
        
        rp = RiskParity()
        
        # 风险平价权重
        rp_weights = rp.calculate_weights(sample_symbols, sample_returns_data)
        deviation = rp.get_risk_parity_deviation(rp_weights, sample_returns_data)
        
        # 等权重作为对比
        equal_weights = {s: 1.0 / len(sample_symbols) for s in sample_symbols}
        equal_deviation = rp.get_risk_parity_deviation(equal_weights, sample_returns_data)
        
        # 风险平价的偏离度应该小于等权重
        assert deviation < equal_deviation
    
    def test_empty_symbols(self):
        """测试空资产列表"""
        from qf_portfolio.risk_parity import RiskParity
        
        rp = RiskParity()
        weights = rp.calculate_weights([])
        
        assert weights == {}
    
    def test_no_data(self, sample_symbols):
        """测试无数据情况"""
        from qf_portfolio.risk_parity import RiskParity
        
        rp = RiskParity()
        weights = rp.calculate_weights(sample_symbols, None)
        
        assert len(weights) == len(sample_symbols)
        assert abs(sum(weights.values()) - 1.0) < 1e-6
    
    def test_inverse_volatility_weights(self, sample_symbols, sample_returns_data):
        """测试逆波动率权重"""
        from qf_portfolio.risk_parity import RiskParity
        
        rp = RiskParity()
        weights = rp.inverse_volatility_weights(sample_symbols, sample_returns_data)
        
        assert len(weights) == len(sample_symbols)
        assert all(w >= 0 for w in weights.values())
        assert abs(sum(weights.values()) - 1.0) < 1e-6
    
    def test_custom_risk_budget(self, sample_symbols, sample_returns_data):
        """测试自定义风险预算"""
        from qf_portfolio.risk_parity import RiskParity
        
        # 自定义风险预算：前两个资产承担更多风险
        risk_budget = {
            "AAPL": 0.3,
            "GOOGL": 0.3,
            "MSFT": 0.15,
            "AMZN": 0.15,
            "TSLA": 0.1,
        }
        
        rp = RiskParity(risk_budget=risk_budget)
        weights = rp.calculate_weights(sample_symbols, sample_returns_data)
        
        # 预算高的资产应该有更高的权重
        assert weights["AAPL"] > weights["TSLA"]
        assert weights["GOOGL"] > weights["TSLA"]


# =============================================================================
# Test VolatilityTargeting
# =============================================================================

class TestVolatilityTargeting:
    """测试波动率目标"""
    
    def test_leverage_adjustment(self, sample_symbols, sample_returns_data):
        """测试杠杆调整"""
        from qf_portfolio.volatility_target import VolatilityTargeting
        
        vt = VolatilityTargeting(target_volatility=0.15)
        weights, leverage = vt.calculate_weights(sample_symbols, sample_returns_data)
        
        assert isinstance(weights, dict)
        assert len(weights) == len(sample_symbols)
        assert isinstance(leverage, float)
        assert 0.5 <= leverage <= 2.0  # 在限制范围内
    
    def test_target_achievement(self, sample_symbols, sample_returns_data):
        """测试目标达成"""
        from qf_portfolio.volatility_target import VolatilityTargeting
        
        target_vol = 0.15
        vt = VolatilityTargeting(target_volatility=target_vol)
        
        weights, leverage = vt.calculate_weights(sample_symbols, sample_returns_data)
        
        # 检查杠杆是否合理
        # 当当前波动率高于目标时，杠杆应该小于1
        # 当当前波动率低于目标时，杠杆应该大于1
        metrics = vt.get_risk_metrics()
        
        assert "target_volatility" in metrics
        assert metrics["target_volatility"] == target_vol
        assert "current_leverage" in metrics
    
    def test_volatility_forecast(self, sample_returns_data):
        """测试波动率预测"""
        from qf_portfolio.volatility_target import VolatilityTargeting
        
        vt = VolatilityTargeting()
        
        # 测试简单预测
        vol_simple = vt.get_volatility_forecast(sample_returns_data, method="simple")
        assert vol_simple > 0
        
        # 测试EWM预测
        vol_ewm = vt.get_volatility_forecast(sample_returns_data, method="ewm")
        assert vol_ewm > 0
        
        # 测试GARCH预测
        vol_garch = vt.get_volatility_forecast(sample_returns_data, method="garch")
        assert vol_garch > 0
    
    def test_volatility_adjusted_weights(self, sample_symbols, sample_returns_data):
        """测试波动率调整权重"""
        from qf_portfolio.volatility_target import VolatilityTargeting
        
        vt = VolatilityTargeting()
        weights = vt.calculate_volatility_adjusted_weights(
            sample_symbols, sample_returns_data
        )
        
        assert len(weights) == len(sample_symbols)
        assert all(w >= 0 for w in weights.values())
        assert abs(sum(weights.values()) - 1.0) < 1e-6
    
    def test_leverage_limits(self, sample_symbols, sample_returns_data):
        """测试杠杆限制"""
        from qf_portfolio.volatility_target import VolatilityTargeting
        
        max_leverage = 1.5
        min_leverage = 0.8
        
        vt = VolatilityTargeting(
            max_leverage=max_leverage,
            min_leverage=min_leverage,
            target_volatility=0.5,  # 高目标以触发杠杆上限
        )
        
        weights, leverage = vt.calculate_weights(sample_symbols, sample_returns_data)
        
        assert leverage <= max_leverage + 1e-6
        assert leverage >= min_leverage - 1e-6
    
    def test_reset(self, sample_symbols, sample_returns_data):
        """测试重置功能"""
        from qf_portfolio.volatility_target import VolatilityTargeting
        
        vt = VolatilityTargeting()
        vt.calculate_weights(sample_symbols, sample_returns_data)
        
        assert len(vt.leverage_history) > 0
        
        vt.reset()
        
        assert vt.current_leverage == 1.0
        assert len(vt.leverage_history) == 0
        assert len(vt.volatility_history) == 0


# =============================================================================
# Test KellyCriterion
# =============================================================================

class TestKellyCriterion:
    """测试凯利公式"""
    
    def test_kelly_fraction(self, sample_returns_data):
        """测试凯利分数计算"""
        from qf_portfolio.kelly import KellyCriterion
        
        kc = KellyCriterion(use_half_kelly=False)
        
        symbol = "AAPL"
        returns = sample_returns_data[symbol]
        
        f = kc.calculate_kelly_fraction(symbol, returns)
        
        assert isinstance(f, float)
        assert -1.0 <= f <= 1.0
    
    def test_half_kelly(self, sample_symbols, sample_returns_data):
        """测试半凯利策略"""
        from qf_portfolio.kelly import KellyCriterion
        
        # 全凯利
        kc_full = KellyCriterion(use_half_kelly=False, kelly_fraction=1.0)
        weights_full = kc_full.calculate_weights(sample_symbols, sample_returns_data)
        
        # 半凯利
        kc_half = KellyCriterion(use_half_kelly=True, kelly_fraction=0.5)
        weights_half = kc_half.calculate_weights(sample_symbols, sample_returns_data)
        
        # 半凯利的权重应该是全凯利的一半（相对比例）
        # 注意：由于归一化，这只是一个近似
        max_full = max(abs(w) for w in weights_full.values())
        max_half = max(abs(w) for w in weights_half.values())
        
        assert max_half <= max_full * 1.5  # 允许一些误差
    
    def test_position_limits(self, sample_symbols, sample_returns_data):
        """测试仓位限制"""
        from qf_portfolio.kelly import KellyCriterion
        
        max_pos = 0.4
        min_pos = 0.0
        
        kc = KellyCriterion(
            max_position=max_pos,
            min_position=min_pos,
            use_half_kelly=False,
            kelly_fraction=1.0,
        )
        
        weights = kc.calculate_weights(sample_symbols, sample_returns_data)
        
        # 验证约束（允许归一化后的微小误差）
        for w in weights.values():
            assert w >= min_pos - 0.01, f"权重 {w} 低于最小值 {min_pos}"
            assert w <= max_pos + 0.01, f"权重 {w} 超过最大值 {max_pos}"
    
    def test_calculate_weights(self, sample_symbols, sample_returns_data):
        """测试权重计算"""
        from qf_portfolio.kelly import KellyCriterion
        
        kc = KellyCriterion()
        weights = kc.calculate_weights(sample_symbols, sample_returns_data)
        
        assert isinstance(weights, dict)
        assert len(weights) == len(sample_symbols)
        assert all(s in weights for s in sample_symbols)
        assert abs(sum(weights.values()) - 1.0) < 1e-6
    
    def test_growth_rate(self, sample_symbols, sample_returns_data):
        """测试增长率计算"""
        from qf_portfolio.kelly import KellyCriterion
        
        kc = KellyCriterion()
        weights = kc.calculate_weights(sample_symbols, sample_returns_data)
        
        growth = kc.calculate_growth_rate(weights, sample_returns_data)
        
        assert isinstance(growth, float)
    
    def test_simple_kelly_with_rates(self, sample_symbols):
        """测试基于胜率的简单凯利"""
        from qf_portfolio.kelly import KellyCriterion
        
        win_rates = {s: 0.55 for s in sample_symbols}
        payoffs = {s: 1.5 for s in sample_symbols}
        
        kc = KellyCriterion(use_half_kelly=False)
        weights = kc.calculate_weights(
            sample_symbols, None, win_rates=win_rates, payoffs=payoffs
        )
        
        assert len(weights) == len(sample_symbols)
        assert abs(sum(weights.values()) - 1.0) < 1e-6
    
    def test_get_kelly_summary(self):
        """测试摘要信息"""
        from qf_portfolio.kelly import KellyCriterion
        
        kc = KellyCriterion(use_half_kelly=True, kelly_fraction=0.5)
        summary = kc.get_kelly_summary()
        
        assert summary["is_half_kelly"] is True
        assert summary["kelly_fraction"] == 0.5


# =============================================================================
# Test MLWeightsPredictor
# =============================================================================

class TestMLWeights:
    """测试ML权重预测"""
    
    def test_predict_weights(self, sample_symbols, sample_returns_data):
        """测试权重预测"""
        from qf_portfolio.ml_weights import MLWeightsPredictor
        
        mlwp = MLWeightsPredictor()
        
        # 先训练模型
        mlwp.fit(sample_returns_data)
        
        # 预测权重
        weights = mlwp.predict_weights(sample_symbols, sample_returns_data)
        
        assert isinstance(weights, dict)
        assert len(weights) > 0
        assert all(w >= 0 for w in weights.values())
    
    def test_momentum_fallback(self, sample_symbols, sample_returns_data):
        """测试动量回退策略"""
        from qf_portfolio.ml_weights import MLWeightsPredictor
        
        mlwp = MLWeightsPredictor()
        
        # 不训练直接预测，应该使用动量回退
        weights = mlwp.predict_weights(sample_symbols, sample_returns_data)
        
        assert isinstance(weights, dict)
        assert len(weights) == len(sample_symbols)
    
    def test_predict_returns(self, sample_symbols, sample_returns_data):
        """测试收益预测"""
        from qf_portfolio.ml_weights import MLWeightsPredictor
        
        mlwp = MLWeightsPredictor()
        mlwp.fit(sample_returns_data)
        
        predictions = mlwp.predict_returns(sample_symbols, sample_returns_data)
        
        assert isinstance(predictions, dict)
        assert all(s in predictions for s in sample_symbols)
        
        for s, (pred, conf) in predictions.items():
            assert isinstance(pred, float)
            assert isinstance(conf, float)
            assert 0 <= conf <= 1
    
    def test_confidence_filter(self, sample_symbols, sample_returns_data):
        """测试置信度过滤"""
        from qf_portfolio.ml_weights import MLWeightsPredictor
        
        mlwp = MLWeightsPredictor(confidence_threshold=0.9)
        mlwp.fit(sample_returns_data)
        
        # 使用置信度过滤
        weights_filtered = mlwp.predict_weights(
            sample_symbols, sample_returns_data, use_confidence_filter=True
        )
        
        # 不使用置信度过滤
        weights_unfiltered = mlwp.predict_weights(
            sample_symbols, sample_returns_data, use_confidence_filter=False
        )
        
        assert len(weights_filtered) > 0
        assert len(weights_unfiltered) > 0
    
    def test_get_feature_importance(self, sample_returns_data):
        """测试特征重要性"""
        from qf_portfolio.ml_weights import MLWeightsPredictor
        
        mlwp = MLWeightsPredictor()
        mlwp.fit(sample_returns_data)
        
        if mlwp.is_fitted:
            importance = mlwp.get_feature_importance()
            assert isinstance(importance, dict)
    
    def test_get_prediction_stats(self, sample_symbols, sample_returns_data):
        """测试预测统计"""
        from qf_portfolio.ml_weights import MLWeightsPredictor
        
        mlwp = MLWeightsPredictor()
        mlwp.fit(sample_returns_data)
        mlwp.predict_weights(sample_symbols, sample_returns_data)
        
        stats = mlwp.get_prediction_stats()
        
        assert isinstance(stats, dict)
        assert "total_predictions" in stats
    
    def test_reset(self, sample_returns_data):
        """测试重置"""
        from qf_portfolio.ml_weights import MLWeightsPredictor
        
        mlwp = MLWeightsPredictor()
        mlwp.fit(sample_returns_data)
        
        assert mlwp.is_fitted
        
        mlwp.reset()
        
        assert not mlwp.is_fitted
        assert len(mlwp.models) == 0


# =============================================================================
# Test PortfolioAllocator
# =============================================================================

class TestPortfolioAllocator:
    """测试组合配置核心"""
    
    def test_init(self):
        """测试初始化"""
        from qf_portfolio.allocator import PortfolioAllocator
        
        allocator = PortfolioAllocator(
            capital=1000000,
            target_volatility=0.15,
        )
        
        assert allocator.capital == 1000000
        assert allocator.target_volatility == 0.15
        assert len(allocator.assets) == 0
    
    def test_add_remove_asset(self):
        """测试添加和移除资产"""
        from qf_portfolio.allocator import PortfolioAllocator
        
        allocator = PortfolioAllocator()
        
        allocator.add_asset("AAPL", min_weight=0.05, max_weight=0.3)
        assert "AAPL" in allocator.assets
        assert allocator.assets["AAPL"].min_weight == 0.05
        assert allocator.assets["AAPL"].max_weight == 0.3
        
        allocator.remove_asset("AAPL")
        assert "AAPL" not in allocator.assets
    
    def test_calculate_equal_weight(self, sample_symbols, sample_returns_data):
        """测试等权重配置"""
        from qf_portfolio.allocator import PortfolioAllocator, AllocationStrategy
        
        allocator = PortfolioAllocator()
        for s in sample_symbols:
            allocator.add_asset(s)
        
        result = allocator.calculate_weights(
            AllocationStrategy.EQUAL_WEIGHT,
            sample_returns_data
        )
        
        assert isinstance(result.weights, dict)
        assert len(result.weights) == len(sample_symbols)
        
        # 等权重
        expected_weight = 1.0 / len(sample_symbols)
        for w in result.weights.values():
            assert abs(w - expected_weight) < 1e-6
    
    def test_calculate_risk_parity(self, sample_symbols, sample_returns_data):
        """测试风险平价配置"""
        from qf_portfolio.allocator import PortfolioAllocator, AllocationStrategy
        
        allocator = PortfolioAllocator()
        for s in sample_symbols:
            allocator.add_asset(s)
        
        result = allocator.calculate_weights(
            AllocationStrategy.RISK_PARITY,
            sample_returns_data
        )
        
        assert isinstance(result.weights, dict)
        assert len(result.weights) == len(sample_symbols)
        assert abs(sum(result.weights.values()) - 1.0) < 1e-6
    
    def test_calculate_volatility_target(self, sample_symbols, sample_returns_data):
        """测试波动率目标配置"""
        from qf_portfolio.allocator import PortfolioAllocator, AllocationStrategy
        
        allocator = PortfolioAllocator(target_volatility=0.15)
        for s in sample_symbols:
            allocator.add_asset(s)
        
        result = allocator.calculate_weights(
            AllocationStrategy.VOLATILITY_TARGET,
            sample_returns_data
        )
        
        assert isinstance(result.weights, dict)
        assert len(result.weights) == len(sample_symbols)
    
    def test_calculate_kelly(self, sample_symbols, sample_returns_data):
        """测试凯利公式配置"""
        from qf_portfolio.allocator import PortfolioAllocator, AllocationStrategy
        
        allocator = PortfolioAllocator()
        for s in sample_symbols:
            allocator.add_asset(s)
        
        result = allocator.calculate_weights(
            AllocationStrategy.KELLY_CRITERION,
            sample_returns_data
        )
        
        assert isinstance(result.weights, dict)
        assert len(result.weights) == len(sample_symbols)
    
    def test_calculate_combined(self, sample_symbols, sample_returns_data):
        """测试组合策略配置"""
        from qf_portfolio.allocator import PortfolioAllocator, AllocationStrategy
        
        allocator = PortfolioAllocator()
        for s in sample_symbols:
            allocator.add_asset(s)
        
        result = allocator.calculate_weights(
            AllocationStrategy.COMBINED,
            sample_returns_data
        )
        
        assert isinstance(result.weights, dict)
        assert len(result.weights) == len(sample_symbols)
        assert abs(sum(result.weights.values()) - 1.0) < 1e-6
    
    def test_weight_constraints(self, sample_symbols, sample_returns_data):
        """测试权重约束"""
        from qf_portfolio.allocator import PortfolioAllocator, AllocationStrategy
        
        allocator = PortfolioAllocator(min_weight=0.05, max_weight=0.4)
        
        for s in sample_symbols:
            allocator.add_asset(s, min_weight=0.05, max_weight=0.4)
        
        result = allocator.calculate_weights(
            AllocationStrategy.EQUAL_WEIGHT,
            sample_returns_data
        )
        
        # 验证约束
        for s, w in result.weights.items():
            assert w >= 0.05 - 1e-6  # 最小权重
            assert w <= 0.4 + 1e-6    # 最大权重
    
    def test_should_rebalance(self):
        """测试再平衡判断"""
        from qf_portfolio.allocator import PortfolioAllocator
        
        allocator = PortfolioAllocator(rebalance_frequency="M")
        
        # 初始状态应该需要再平衡
        assert allocator.should_rebalance() is True
        
        # 设置上次再平衡时间
        allocator.last_rebalance_date = datetime.now()
        assert allocator.should_rebalance() is False
        
        # 设置一个月前
        allocator.last_rebalance_date = datetime.now() - timedelta(days=31)
        assert allocator.should_rebalance() is True
    
    def test_rebalance(self, sample_symbols, sample_returns_data):
        """测试再平衡执行"""
        from qf_portfolio.allocator import PortfolioAllocator
        
        allocator = PortfolioAllocator()
        for s in sample_symbols:
            allocator.add_asset(s)
        
        # 强制再平衡
        result = allocator.rebalance(
            returns_data=sample_returns_data,
            force=True
        )
        
        assert result is not None
        assert result.rebalanced is True
        assert allocator.last_rebalance_date is not None
        assert len(allocator.allocation_history) == 1
    
    def test_get_position_sizes(self, sample_symbols):
        """测试持仓数量计算"""
        from qf_portfolio.allocator import PortfolioAllocator
        
        allocator = PortfolioAllocator(capital=1000000)
        allocator.current_weights = {s: 0.2 for s in sample_symbols}
        
        prices = {s: 100.0 for s in sample_symbols}
        positions = allocator.get_position_sizes(prices)
        
        expected_position = (1000000 * 0.2) / 100.0
        
        for s, pos in positions.items():
            assert abs(pos - expected_position) < 1e-6
    
    def test_get_rebalance_trades(self, sample_symbols):
        """测试再平衡交易计算"""
        from qf_portfolio.allocator import PortfolioAllocator
        
        allocator = PortfolioAllocator(capital=1000000)
        allocator.current_weights = {s: 0.2 for s in sample_symbols}
        
        current_positions = {s: 1000 for s in sample_symbols}
        prices = {s: 200.0 for s in sample_symbols}
        
        trades = allocator.get_rebalance_trades(current_positions, prices)
        
        assert len(trades) == len(sample_symbols)
        
        # 目标持仓 = (1e6 * 0.2) / 200 = 1000
        # 交易应该接近0
        for s, trade in trades.items():
            assert abs(trade) < 1e-6
    
    def test_get_allocation_summary(self, sample_symbols):
        """测试配置摘要"""
        from qf_portfolio.allocator import PortfolioAllocator
        
        allocator = PortfolioAllocator(capital=1000000)
        for s in sample_symbols:
            allocator.add_asset(s)
        
        summary = allocator.get_allocation_summary()
        
        assert summary["capital"] == 1000000
        assert len(summary["assets"]) == len(sample_symbols)
    
    def test_register_strategy(self, sample_symbols, sample_returns_data):
        """测试策略注册"""
        from qf_portfolio.allocator import PortfolioAllocator, AllocationStrategy
        from qf_portfolio.risk_parity import RiskParity
        
        allocator = PortfolioAllocator()
        for s in sample_symbols:
            allocator.add_asset(s)
        
        # 注册自定义策略
        custom_rp = RiskParity(max_iter=500)
        allocator.register_strategy(AllocationStrategy.RISK_PARITY, custom_rp)
        
        result = allocator.calculate_weights(
            AllocationStrategy.RISK_PARITY,
            sample_returns_data
        )
        
        assert result is not None


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """集成测试"""
    
    def test_full_workflow(self, sample_symbols, sample_returns_data):
        """测试完整工作流程"""
        from qf_portfolio import PortfolioAllocator, AllocationStrategy
        
        # 创建配置器
        allocator = PortfolioAllocator(
            capital=1000000,
            target_volatility=0.15,
            rebalance_frequency="M",
        )
        
        # 添加资产
        for symbol in sample_symbols:
            allocator.add_asset(symbol, min_weight=0.05, max_weight=0.4)
        
        # 计算权重
        result = allocator.calculate_weights(
            AllocationStrategy.COMBINED,
            sample_returns_data
        )
        
        assert result is not None
        assert len(result.weights) == len(sample_symbols)
        
        # 执行再平衡
        rebalance_result = allocator.rebalance(
            returns_data=sample_returns_data,
            force=True
        )
        
        assert rebalance_result is not None
        assert allocator.last_rebalance_date is not None
        
        # 获取持仓
        prices = {s: 100.0 for s in sample_symbols}
        positions = allocator.get_position_sizes(prices)
        
        assert len(positions) == len(sample_symbols)
        
        # 获取摘要
        summary = allocator.get_allocation_summary()
        assert summary["capital"] == 1000000
    
    def test_multiple_rebalances(self, sample_symbols, sample_returns_data):
        """测试多次再平衡"""
        from qf_portfolio import PortfolioAllocator
        
        allocator = PortfolioAllocator(rebalance_frequency="D")
        
        for s in sample_symbols:
            allocator.add_asset(s)
        
        # 模拟多次再平衡
        for i in range(3):
            result = allocator.rebalance(
                returns_data=sample_returns_data,
                force=True
            )
            assert result is not None
        
        assert len(allocator.allocation_history) == 3
    
    def test_empty_portfolio(self):
        """测试空组合"""
        from qf_portfolio import PortfolioAllocator
        
        allocator = PortfolioAllocator()
        
        with pytest.raises(ValueError):
            allocator.calculate_weights()


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """边界情况测试"""
    
    def test_single_asset(self, sample_returns_data):
        """测试单资产"""
        from qf_portfolio import PortfolioAllocator
        
        allocator = PortfolioAllocator()
        allocator.add_asset("AAPL")
        
        result = allocator.calculate_weights(
            returns_data=sample_returns_data[["AAPL"]]
        )
        
        assert result.weights["AAPL"] == 1.0
    
    def test_missing_data_columns(self, sample_returns_data):
        """测试缺失数据列"""
        from qf_portfolio.risk_parity import RiskParity
        
        rp = RiskParity()
        
        # 请求不存在的资产
        symbols = ["AAPL", "UNKNOWN"]
        weights = rp.calculate_weights(symbols, sample_returns_data)
        
        assert len(weights) == 2
        assert abs(sum(weights.values()) - 1.0) < 1e-6
    
    def test_zero_volatility(self):
        """测试零波动率情况"""
        from qf_portfolio.volatility_target import VolatilityTargeting
        
        vt = VolatilityTargeting(target_volatility=0.15)
        
        # 创建零波动率数据
        zero_data = pd.DataFrame({
            "A": [0.001] * 100,
            "B": [0.001] * 100,
        })
        
        weights, leverage = vt.calculate_weights(["A", "B"], zero_data)
        
        assert len(weights) == 2
        assert leverage >= vt.min_leverage
    
    def test_negative_returns(self):
        """测试负收益率"""
        from qf_portfolio.kelly import KellyCriterion
        
        kc = KellyCriterion()
        
        # 全负收益率
        negative_returns = pd.Series([-0.01] * 100)
        
        f = kc.calculate_kelly_fraction("TEST", negative_returns)
        
        # 凯利分数应该很小或为负
        assert isinstance(f, float)
