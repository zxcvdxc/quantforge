#!/usr/bin/env python3
"""
OKX交易示例 - 期现套利策略
使用前确保已配置OKX API密钥
"""

import os
import sys
import asyncio
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules', 'qf-data', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules', 'qf-strategy', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules', 'qf-execution', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules', 'qf-risk', 'src'))

class OKXBasisArbitrage:
    """OKX期现套利策略"""
    
    def __init__(self):
        self.api_key = os.getenv('OKX_API_KEY')
        self.api_secret = os.getenv('OKX_API_SECRET')
        self.passphrase = os.getenv('OKX_PASSPHRASE')
        self.testnet = os.getenv('OKX_SERVER', 'TEST') == 'TEST'
        
        self.symbol_spot = 'BTC-USDT'
        self.symbol_swap = 'BTC-USDT-SWAP'
        self.min_basis = 0.005  # 最小基差0.5%
        self.max_position = 0.1  # 最大持仓0.1 BTC
        
    async def initialize(self):
        """初始化连接"""
        try:
            from qf_data.exchanges.okx import OKXClient
            from qf_execution import ExecutionEngine
            from qf_risk import RiskManager
            
            # 创建OKX客户端
            self.client = OKXClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                passphrase=self.passphrase,
                testnet=self.testnet
            )
            
            # 创建执行引擎
            self.executor = ExecutionEngine()
            
            # 创建风险管理器
            self.risk = RiskManager()
            
            logger.info("✅ 初始化完成")
            logger.info(f"   交易对: {self.symbol_spot} / {self.symbol_swap}")
            logger.info(f"   环境: {'模拟盘' if self.testnet else '实盘'}")
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            raise
    
    async def get_basis(self):
        """获取期现基差"""
        try:
            # 获取现货价格
            spot_ticker = self.client.get_ticker(self.symbol_spot)
            spot_price = float(spot_ticker['data'][0]['last'])
            
            # 获取永续合约价格
            swap_ticker = self.client.get_ticker(self.symbol_swap)
            swap_price = float(swap_ticker['data'][0]['last'])
            
            # 计算基差
            basis = (swap_price - spot_price) / spot_price
            
            return {
                'spot_price': spot_price,
                'swap_price': swap_price,
                'basis': basis,
                'basis_pct': basis * 100
            }
            
        except Exception as e:
            logger.error(f"获取基差失败: {e}")
            return None
    
    async def check_position(self):
        """检查当前持仓"""
        try:
            positions = self.client.get_positions()
            
            spot_pos = 0
            swap_pos = 0
            
            if 'data' in positions:
                for pos in positions['data']:
                    if pos['instId'] == self.symbol_spot:
                        spot_pos = float(pos.get('cashBal', 0))
                    elif pos['instId'] == self.symbol_swap:
                        swap_pos = float(pos.get('pos', 0))
            
            return {'spot': spot_pos, 'swap': swap_pos}
            
        except Exception as e:
            logger.error(f"检查持仓失败: {e}")
            return {'spot': 0, 'swap': 0}
    
    async def execute_arbitrage(self, basis_data):
        """执行套利交易"""
        basis = basis_data['basis']
        
        # 检查风险限额
        if not self.risk.check_order({
            'symbol': self.symbol_spot,
            'quantity': 0.01,  # 最小交易单位
            'side': 'BUY'
        }):
            logger.warning("⚠️ 风险检查未通过，跳过交易")
            return
        
        if basis > self.min_basis:
            # 正基差: 做空合约，买入现货
            logger.info(f"🎯 发现套利机会: 基差 {basis_data['basis_pct']:.4f}%")
            logger.info(f"   现货: {basis_data['spot_price']}")
            logger.info(f"   合约: {basis_data['swap_price']}")
            logger.info("   策略: 做空合约 + 买入现货")
            
            # 注意: 实际交易需要实现下单逻辑
            # 这里仅做示例展示
            
        elif basis < -self.min_basis:
            # 负基差: 做多合约，卖出现货
            logger.info(f"🎯 发现套利机会: 基差 {basis_data['basis_pct']:.4f}%")
            logger.info("   策略: 做多合约 + 卖出现货")
    
    async def run(self):
        """主运行循环"""
        logger.info("🚀 启动OKX期现套利策略...")
        
        await self.initialize()
        
        while True:
            try:
                # 获取基差
                basis_data = await self.get_basis()
                if basis_data:
                    logger.info(
                        f"📊 基差: {basis_data['basis_pct']:+.4f}% | "
                        f"现货: {basis_data['spot_price']:,.2f} | "
                        f"合约: {basis_data['swap_price']:,.2f}"
                    )
                    
                    # 检查是否满足交易条件
                    if abs(basis_data['basis']) > self.min_basis:
                        await self.execute_arbitrage(basis_data)
                
                # 检查持仓
                positions = await self.check_position()
                if positions['spot'] != 0 or positions['swap'] != 0:
                    logger.info(f"💼 持仓: 现货 {positions['spot']:.4f} | 合约 {positions['swap']:.4f}")
                
                # 等待下一次检查
                await asyncio.sleep(5)
                
            except KeyboardInterrupt:
                logger.info("👋 收到停止信号，退出...")
                break
            except Exception as e:
                logger.error(f"运行错误: {e}")
                await asyncio.sleep(5)

async def main():
    """主函数"""
    print("=" * 60)
    print("🚀 QuantForge OKX 期现套利策略")
    print("=" * 60)
    print()
    
    # 检查环境变量
    if not os.getenv('OKX_API_KEY'):
        print("❌ 错误: 未设置 OKX_API_KEY")
        print("请先运行: ./deploy.sh 配置环境变量")
        sys.exit(1)
    
    strategy = OKXBasisArbitrage()
    
    try:
        await strategy.run()
    except Exception as e:
        logger.error(f"策略运行失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())
