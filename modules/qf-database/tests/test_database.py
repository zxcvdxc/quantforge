"""
qf-database 模块测试
"""
import pytest


class TestMySQLManager:
    """测试MySQL管理"""
    
    def test_connection(self):
        """测试连接"""
        pass
    
    def test_save_contract(self):
        """测试保存合约"""
        pass
    
    def test_query_trade(self):
        """测试查询交易"""
        pass


class TestInfluxDBManager:
    """测试InfluxDB管理"""
    
    def test_save_kline(self):
        """测试保存K线"""
        pass
    
    def test_query_range(self):
        """测试范围查询"""
        pass


class TestRedisManager:
    """测试Redis管理"""
    
    def test_cache_tick(self):
        """测试缓存Tick"""
        pass
