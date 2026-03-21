#!/usr/bin/env python3
"""
OKX连接测试脚本
验证API密钥配置正确性
"""

import os
import sys
from datetime import datetime

# 添加模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules', 'qf-data', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules', 'qf-security', 'src'))

def test_okx_connection():
    """测试OKX API连接"""
    print("=" * 60)
    print("🔍 OKX API 连接测试")
    print("=" * 60)
    
    # 检查环境变量
    api_key = os.getenv('OKX_API_KEY')
    api_secret = os.getenv('OKX_API_SECRET')
    passphrase = os.getenv('OKX_PASSPHRASE')
    server = os.getenv('OKX_SERVER', 'TEST')
    
    print(f"\n📋 配置信息:")
    print(f"  服务器: {'模拟盘 (TEST)' if server == 'TEST' else '实盘 (REAL)'}")
    print(f"  API密钥: {'✅ 已配置' if api_key and api_key != 'your_okx_api_key_here' else '❌ 未配置'}")
    print(f"  API密钥长度: {len(api_key) if api_key else 0} 字符")
    
    # 验证配置
    if not api_key or api_key == 'your_okx_api_key_here':
        print("\n❌ 错误: OKX_API_KEY 未配置")
        print("请在 .env 文件中设置 OKX_API_KEY")
        return False
    
    if not api_secret or api_secret == 'your_okx_api_secret_here':
        print("\n❌ 错误: OKX_API_SECRET 未配置")
        return False
    
    if not passphrase or passphrase == 'your_okx_passphrase_here':
        print("\n❌ 错误: OKX_PASSPHRASE 未配置")
        return False
    
    # 尝试导入并连接
    try:
        print("\n🔌 正在连接OKX...")
        
        # 尝试导入OKX客户端
        try:
            from qf_data import OKXClient
            from qf_security import SecureCredentialManager
            
            # 使用安全凭证管理
            cred_manager = SecureCredentialManager()
            encrypted_key = cred_manager.encrypt(api_key)
            
            client = OKXClient(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                testnet=(server == 'TEST')
            )
            
        except ImportError:
            # 如果安全模块未安装，使用普通客户端
            print("⚠️  qf-security 模块未安装，使用普通连接...")
            from qf_data.exchanges.okx import OKXClient
            
            client = OKXClient(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                testnet=(server == 'TEST')
            )
        
        # 测试获取账户信息
        print("📡 获取账户信息...")
        account_info = client.get_account_balance()
        
        if account_info:
            print(f"\n✅ 连接成功!")
            print(f"  账户类型: {'模拟盘' if server == 'TEST' else '实盘'}")
            
            # 显示账户余额
            if 'data' in account_info and len(account_info['data']) > 0:
                print(f"\n💰 账户余额:")
                for currency in account_info['data'][0].get('details', [])[:5]:
                    ccy = currency.get('ccy', 'Unknown')
                    cash_bal = currency.get('cashBal', '0')
                    print(f"    {ccy}: {cash_bal}")
            
            return True
        else:
            print("\n❌ 获取账户信息失败")
            return False
            
    except Exception as e:
        print(f"\n❌ 连接失败: {str(e)}")
        print("\n可能的原因:")
        print("  1. API密钥不正确")
        print("  2. IP地址未在白名单中")
        print("  3. API密钥权限不足")
        print("  4. 网络连接问题")
        return False

def test_market_data():
    """测试行情数据获取"""
    print("\n" + "=" * 60)
    print("📈 行情数据测试")
    print("=" * 60)
    
    try:
        from qf_data.exchanges.okx import OKXClient
        
        api_key = os.getenv('OKX_API_KEY')
        api_secret = os.getenv('OKX_API_SECRET')
        passphrase = os.getenv('OKX_PASSPHRASE')
        server = os.getenv('OKX_SERVER', 'TEST')
        
        client = OKXClient(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            testnet=(server == 'TEST')
        )
        
        # 获取BTC价格
        print("\n📊 获取 BTC-USDT 行情...")
        ticker = client.get_ticker('BTC-USDT')
        
        if ticker and 'data' in ticker:
            data = ticker['data'][0]
            print(f"  最新价格: {data.get('last', 'N/A')}")
            print(f"  24h最高: {data.get('high24h', 'N/A')}")
            print(f"  24h最低: {data.get('low24h', 'N/A')}")
            print(f"  24h成交量: {data.get('vol24h', 'N/A')}")
            print("\n✅ 行情数据获取成功")
            return True
        else:
            print("\n❌ 获取行情数据失败")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        return False

if __name__ == '__main__':
    print(f"\n🚀 QuantForge OKX 连接测试")
    print(f"⏰ 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 运行测试
    connection_ok = test_okx_connection()
    market_ok = test_market_data() if connection_ok else False
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)
    print(f"  API连接: {'✅ 通过' if connection_ok else '❌ 失败'}")
    print(f"  行情数据: {'✅ 通过' if market_ok else '❌ 失败'}")
    
    if connection_ok and market_ok:
        print("\n🎉 所有测试通过! 可以开始交易。")
        sys.exit(0)
    else:
        print("\n⚠️  测试未通过，请检查配置后重试。")
        sys.exit(1)
