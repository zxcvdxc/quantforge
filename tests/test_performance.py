"""
大规模数据测试和压力测试

测试目标:
- 10万条K线数据的性能
- 确保优化后速度提升50%+
- 验证内存使用效率
"""

import time
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

# Import modules
from qf_risk import RiskManager, PositionLimits, CircuitBreaker, VaRCalculator, VaRMethod
from qf_portfolio import PortfolioAllocator, AllocationStrategy, RiskParity, KellyCriterion, VolatilityTargeting


class TestLargeScaleRisk:
    """大规模风险计算测试"""
    
    @pytest.fixture
    def large_returns_data(self):
        """生成10万条收益率数据"""
        np.random.seed(42)
        n_samples = 100000
        returns = np.random.normal(0.0001, 0.02, n_samples)
        return returns.tolist()
    
    @pytest.fixture
    def large_kline_data(self):
        """生成10万条K线数据"""
        np.random.seed(42)
        n_samples = 100000
        
        base_price = 100.0
        prices = [base_price]
        
        for i in range(1, n_samples):
            change = np.random.normal(0.0001, 0.02)
            prices.append(prices[-1] * (1 + change))
        
        dates = pd.date_range(end=datetime.now(), periods=n_samples, freq='min')
        
        df = pd.DataFrame({
            'open': prices,
            'high': [p * (1 + abs(np.random.normal(0, 0.005))) for p in prices],
            'low': [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
            'close': prices,
            'volume': np.random.lognormal(10, 1, n_samples),
        }, index=dates)
        
        return df
    
    def test_var_large_dataset(self, large_returns_data):
        """测试VaR计算在10万条数据上的性能"""
        calculator = VaRCalculator(confidence_level=0.95, holding_period_days=1)
        
        start = time.perf_counter()
        result = calculator.calculate(large_returns_data, 100000, VaRMethod.HISTORICAL)
        elapsed = time.perf_counter() - start
        
        assert result is not None
        assert result.var_value > 0
        # 10万条数据应该在100ms内完成
        assert elapsed < 0.1, f"VaR计算太慢: {elapsed:.3f}s"
        print(f"\nVaR (100k samples): {elapsed*1000:.2f}ms")
    
    def test_var_parametric_performance(self, large_returns_data):
        """测试参数化VaR在10万条数据上的性能"""
        calculator = VaRCalculator(confidence_level=0.95, holding_period_days=1)
        
        start = time.perf_counter()
        result = calculator.calculate(large_returns_data, 100000, VaRMethod.PARAMETRIC)
        elapsed = time.perf_counter() - start
        
        assert result is not None
        assert result.var_value > 0
        # 参数化VaR应该更快
        assert elapsed < 0.05, f"参数化VaR计算太慢: {elapsed:.3f}s"
        print(f"\nParametric VaR (100k samples): {elapsed*1000:.2f}ms")
    
    def test_anomaly_detection_performance(self, large_kline_data):
        """测试异常检测在大量数据上的性能"""
        from qf_risk.anomaly import AnomalyDetector
        
        detector = AnomalyDetector()
        
        prices = large_kline_data['close'].tolist()
        volumes = large_kline_data['volume'].tolist()
        
        start = time.perf_counter()
        result = detector.detect_price_outlier(prices[-1], prices[:-1], "TEST")
        elapsed = time.perf_counter() - start
        
        assert result is not None
        # 10万条价格的异常检测应该在50ms内
        assert elapsed < 0.05, f"异常检测太慢: {elapsed:.3f}s"
        print(f"\nAnomaly detection (100k prices): {elapsed*1000:.2f}ms")
    
    def test_volume_spike_performance(self, large_kline_data):
        """测试成交量异常检测性能"""
        from qf_risk.anomaly import AnomalyDetector
        
        detector = AnomalyDetector()
        
        volumes = large_kline_data['volume'].tolist()
        
        start = time.perf_counter()
        result = detector.detect_volume_spike(volumes[-1], volumes[:-1], "TEST")
        elapsed = time.perf_counter() - start
        
        assert result is not None
        assert elapsed < 0.05, f"成交量异常检测太慢: {elapsed:.3f}s"
        print(f"\nVolume spike detection (100k volumes): {elapsed*1000:.2f}ms")


class TestLargeScalePortfolio:
    """大规模投资组合测试"""
    
    @pytest.fixture
    def large_returns_df(self):
        """生成大规模多资产收益率数据"""
        np.random.seed(42)
        n_days = 5000  # 约20年数据
        n_assets = 50  # 50个资产
        
        symbols = [f"ASSET_{i}" for i in range(n_assets)]
        
        # 生成相关收益率
        mean_returns = np.random.normal(0.0001, 0.001, n_assets)
        volatilities = np.random.uniform(0.01, 0.03, n_assets)
        
        # 相关矩阵
        corr = np.random.uniform(-0.2, 0.6, (n_assets, n_assets))
        corr = (corr + corr.T) / 2
        np.fill_diagonal(corr, 1.0)
        
        # 确保正半定
        eigvals = np.linalg.eigvals(corr)
        if np.any(eigvals < 0):
            corr = corr + np.eye(n_assets) * (abs(np.min(eigvals)) + 0.01)
        
        cov = np.outer(volatilities, volatilities) * corr
        returns = np.random.multivariate_normal(mean_returns, cov, n_days)
        
        dates = pd.date_range(end=datetime.now(), periods=n_days, freq='D')
        df = pd.DataFrame(returns, columns=symbols, index=dates)
        
        return df
    
    def test_risk_parity_large_dataset(self, large_returns_df):
        """测试风险平价在大量资产上的性能"""
        symbols = large_returns_df.columns.tolist()[:20]  # 使用20个资产
        
        rp = RiskParity()
        
        start = time.perf_counter()
        weights = rp.calculate_weights(symbols, large_returns_df)
        elapsed = time.perf_counter() - start
        
        assert len(weights) == len(symbols)
        assert elapsed < 1.0, f"风险平价计算太慢: {elapsed:.3f}s"
        print(f"\nRisk parity (20 assets, 5000 days): {elapsed*1000:.2f}ms")
    
    def test_kelly_criterion_large_dataset(self, large_returns_df):
        """测试凯利公式在大量资产上的性能"""
        symbols = large_returns_df.columns.tolist()[:10]  # 使用10个资产
        
        kc = KellyCriterion(use_half_kelly=True)
        
        start = time.perf_counter()
        weights = kc.calculate_weights(symbols, large_returns_df)
        elapsed = time.perf_counter() - start
        
        assert len(weights) == len(symbols)
        assert elapsed < 1.0, f"凯利公式计算太慢: {elapsed:.3f}s"
        print(f"\nKelly criterion (10 assets, 5000 days): {elapsed*1000:.2f}ms")
    
    def test_volatility_targeting_large_dataset(self, large_returns_df):
        """测试波动率目标在大量资产上的性能"""
        symbols = large_returns_df.columns.tolist()[:20]
        
        vt = VolatilityTargeting(target_volatility=0.15)
        
        start = time.perf_counter()
        weights, leverage = vt.calculate_weights(symbols, large_returns_df)
        elapsed = time.perf_counter() - start
        
        assert len(weights) == len(symbols)
        assert elapsed < 0.5, f"波动率目标计算太慢: {elapsed:.3f}s"
        print(f"\nVolatility targeting (20 assets, 5000 days): {elapsed*1000:.2f}ms")


class TestStressTest:
    """压力测试"""
    
    def test_batch_var_calculation(self):
        """批量VaR计算测试"""
        np.random.seed(42)
        calculator = VaRCalculator()
        
        # 100个组合，每个有10000条收益率数据
        portfolios = []
        values = []
        
        for _ in range(100):
            returns = np.random.normal(0.0001, 0.02, 10000)
            portfolios.append(returns)
            values.append(100000)
        
        start = time.perf_counter()
        results = calculator.batch_calculate(portfolios, values, VaRMethod.PARAMETRIC)
        elapsed = time.perf_counter() - start
        
        assert len(results) == 100
        # 100个组合的VaR计算应该在1秒内完成
        assert elapsed < 1.0, f"批量VaR计算太慢: {elapsed:.3f}s"
        print(f"\nBatch VaR (100 portfolios): {elapsed*1000:.2f}ms")
    
    def test_risk_manager_stress_test(self):
        """RiskManager压力测试"""
        manager = RiskManager()
        manager.initialize_capital(1000000)
        
        np.random.seed(42)
        
        # 模拟1000天的交易
        start = time.perf_counter()
        
        for i in range(1000):
            # 随机组合价值变化
            change = np.random.normal(0.0001, 0.02)
            new_value = manager.get_portfolio_value() * (1 + change)
            manager.update_portfolio_value(new_value)
            
            # 每100天检查一次VaR
            if i % 100 == 0 and i > 0:
                manager.calculate_var()
        
        elapsed = time.perf_counter() - start
        
        # 1000天的模拟应该在1秒内完成
        assert elapsed < 1.0, f"RiskManager压力测试太慢: {elapsed:.3f}s"
        print(f"\nRiskManager stress test (1000 days): {elapsed*1000:.2f}ms")
    
    def test_portfolio_allocator_stress_test(self):
        """PortfolioAllocator压力测试"""
        np.random.seed(42)
        n_assets = 20
        n_days = 1000
        
        # 生成收益率数据
        returns_data = pd.DataFrame(
            np.random.normal(0.0001, 0.02, (n_days, n_assets)),
            columns=[f"ASSET_{i}" for i in range(n_assets)]
        )
        
        allocator = PortfolioAllocator(capital=1000000)
        
        for i in range(n_assets):
            allocator.add_asset(f"ASSET_{i}", min_weight=0.0, max_weight=0.2)
        
        start = time.perf_counter()
        
        # 执行10次再平衡
        for _ in range(10):
            result = allocator.calculate_weights(
                AllocationStrategy.COMBINED,
                returns_data
            )
        
        elapsed = time.perf_counter() - start
        
        assert elapsed < 10.0, f"组合分配压力测试太慢: {elapsed:.3f}s"
        print(f"\nPortfolio allocator stress test (10 rebalances): {elapsed*1000:.2f}ms")


class TestPerformanceImprovements:
    """性能改进验证测试"""
    
    def test_vectorized_vs_loop_performance(self):
        """验证向量化比循环快50%以上"""
        from qf_risk.var import VaRCalculator, VaRMethod
        
        np.random.seed(42)
        n_samples = 50000
        returns = np.random.normal(0.0001, 0.02, n_samples)
        
        calculator = VaRCalculator()
        
        # 向量化计算
        start = time.perf_counter()
        result1 = calculator.calculate(returns, 100000, VaRMethod.HISTORICAL)
        vectorized_time = time.perf_counter() - start
        
        # 使用Python循环计算（模拟旧实现）
        start = time.perf_counter()
        returns_list = returns.tolist()
        sorted_returns = sorted(returns_list)
        index = int((1 - 0.95) * len(sorted_returns))
        var_pct_loop = sorted_returns[index]
        loop_time = time.perf_counter() - start
        
        speedup = loop_time / vectorized_time
        print(f"\nVectorized vs Loop speedup: {speedup:.2f}x")
        print(f"  Vectorized: {vectorized_time*1000:.2f}ms")
        print(f"  Loop: {loop_time*1000:.2f}ms")
        
        # 验证向量化至少快1.5倍（50%提升）
        assert speedup >= 1.5, f"向量化性能提升不足: {speedup:.2f}x"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
