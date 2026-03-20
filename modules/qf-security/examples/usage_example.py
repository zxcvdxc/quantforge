"""
Security Integration Example - 安全集成示例

展示如何在QuantForge各模块中使用安全功能
"""

import asyncio
from pathlib import Path
from datetime import datetime

# 导入安全模块
from qf_security import (
    # 加密
    initialize_security,
    SecureConfig,
    encrypt_config,
    decrypt_config,
    
    # 脱敏
    install_log_masker,
    create_masked_logger,
    mask_sensitive_data,
    
    # 访问控制
    RBACManager,
    Permission,
    Role,
    APIKeyPermission,
    require_permission,
    
    # 审计
    init_audit_logger,
    audit_log_event,
    AuditEventType,
)

from qf_security.integration import (
    init_security,
    load_exchange_config,
    audit_trade,
    audit_config_change,
)


# ============ 示例1: 初始化安全系统 ============

def example_init_security():
    """初始化安全系统示例"""
    print("=" * 50)
    print("示例1: 初始化安全系统")
    print("=" * 50)
    
    # 方式1: 初始化安全系统（包含加密配置、RBAC、审计日志）
    secure_config, rbac_manager = init_security(
        audit_log_path=Path("logs/audit.log"),
        enable_log_masking=True,
    )
    
    print("✅ 安全系统初始化完成")
    print(f"   - 加密配置: 已初始化")
    print(f"   - RBAC管理器: 已初始化")
    print(f"   - 审计日志: 已启用")
    print()


# ============ 示例2: 加密配置 ============

def example_encrypt_config():
    """加密配置示例"""
    print("=" * 50)
    print("示例2: 加密交易所配置")
    print("=" * 50)
    
    # 原始配置（包含敏感信息）
    config = {
        "exchanges": {
            "okx": {
                "api_key": "my-secret-api-key-123456",
                "api_secret": "my-secret-api-secret-abcdef",
                "passphrase": "my-passphrase",
                "use_proxy": False,
            },
            "binance": {
                "api_key": "binance-api-key-789012",
                "api_secret": "binance-api-secret-xyzabc",
            }
        },
        "database": {
            "mysql": {
                "host": "localhost",
                "port": 3306,
                "user": "quant",
                "password": "my-db-password",
            },
            "redis": {
                "host": "localhost",
                "port": 6379,
                "password": "redis-secret",
            }
        }
    }
    
    print("原始配置:")
    print(f"   OKX API Key: {config['exchanges']['okx']['api_key']}")
    print(f"   MySQL Password: {config['database']['mysql']['password']}")
    print()
    
    # 创建安全配置实例
    secure_config = SecureConfig()
    
    # 加密配置
    encrypted = secure_config.encrypt_config_values(config)
    
    print("加密后:")
    print(f"   OKX API Key: {encrypted['exchanges']['okx']['api_key'][:20]}...")
    print(f"   MySQL Password: {encrypted['database']['mysql']['password'][:20]}...")
    print()
    
    # 保存到文件
    secure_config.save_encrypted_config(config, "config.encrypted.json")
    print("✅ 配置已加密并保存到: config.encrypted.json")
    print()
    
    # 解密验证
    decrypted = secure_config.load_encrypted_config("config.encrypted.json")
    assert decrypted == config
    print("✅ 解密验证通过")
    print()


# ============ 示例3: 日志脱敏 ============

def example_log_masking():
    """日志脱敏示例"""
    print("=" * 50)
    print("示例3: 日志脱敏")
    print("=" * 50)
    
    # 创建带脱敏功能的logger
    logger = create_masked_logger("example")
    
    # 包含敏感信息的日志
    logger.info("Connecting to OKX with api_key=sk-1234567890abcdef")
    logger.info("Database connection: mysql://user:password123@localhost/db")
    logger.info("Configuration: password=secret_value, token=abc123xyz")
    
    print()
    print("☝️  查看上方输出，敏感信息已被脱敏")
    print()


# ============ 示例4: 访问控制 ============

def example_access_control():
    """访问控制示例"""
    print("=" * 50)
    print("示例4: 访问控制 (RBAC)")
    print("=" * 50)
    
    # 创建RBAC管理器
    rbac = RBACManager()
    
    # 创建用户
    trader = rbac.create_user(
        user_id="trader_001",
        username="Trader One",
        role=Role.TRADER,
        allowed_ips=["192.168.1.100", "10.0.0.0/24"]
    )
    
    admin = rbac.create_user(
        user_id="admin_001",
        username="Admin One",
        role=Role.ADMIN,
    )
    
    # 检查权限
    print("权限检查:")
    print(f"   Trader can trade: {trader.has_permission(Permission.TRADE_CREATE)}")
    print(f"   Trader can manage users: {trader.has_permission(Permission.USER_MANAGE)}")
    print(f"   Admin can manage users: {admin.has_permission(Permission.USER_MANAGE)}")
    print()
    
    # 创建API密钥
    api_key, raw_key = rbac.create_api_key(
        user_id="trader_001",
        permission=APIKeyPermission.TRADING,
        expires_in_days=90,
        allowed_ips=["192.168.1.100"],
    )
    
    print(f"API密钥创建:")
    print(f"   Key ID: {api_key.key_id}")
    print(f"   Permission: {api_key.permission.value}")
    print(f"   Expires: {api_key.expires_at}")
    print()
    
    # 验证API密钥
    try:
        validated = rbac.validate_api_key(raw_key, client_ip="192.168.1.100")
        print(f"✅ API密钥验证通过: {validated.key_id}")
    except Exception as e:
        print(f"❌ 验证失败: {e}")
    print()


# ============ 示例5: 审计日志 ============

def example_audit_logging():
    """审计日志示例"""
    print("=" * 50)
    print("示例5: 审计日志")
    print("=" * 50)
    
    # 初始化审计日志
    init_audit_logger(log_file=Path("logs/audit_example.log"))
    
    # 记录交易操作
    audit_log_event(
        event_type=AuditEventType.ORDER_CREATED,
        user_id="trader_001",
        resource_type="order",
        resource_id="order_123",
        new_value={
            "symbol": "BTC-USDT",
            "side": "buy",
            "quantity": 1.5,
            "price": 50000.0,
        },
        client_ip="192.168.1.100"
    )
    print("✅ 订单创建已记录")
    
    # 记录配置变更
    audit_log_event(
        event_type=AuditEventType.CONFIG_UPDATED,
        user_id="admin_001",
        resource_type="risk_config",
        resource_id="max_position",
        old_value={"value": 100},
        new_value={"value": 200},
    )
    print("✅ 配置变更已记录")
    
    # 使用便捷函数记录交易
    audit_trade(
        action="fill",
        symbol="BTC-USDT",
        quantity=1.5,
        price=50000.0,
        side="buy",
        order_id="order_123",
        user_id="trader_001",
    )
    print("✅ 成交记录已记录")
    print()


# ============ 示例6: 综合安全使用 ============

async def example_secure_trading():
    """安全交易示例"""
    print("=" * 50)
    print("示例6: 综合安全使用")
    print("=" * 50)
    
    # 1. 初始化安全系统
    secure_config, rbac = init_security()
    
    # 2. 创建用户
    trader = rbac.create_user(
        user_id="trader_001",
        username="Trader One",
        role=Role.TRADER,
    )
    
    # 3. 加载交易所配置（自动解密）
    try:
        exchange_config = load_exchange_config("okx")
        print(f"交易所配置加载成功: {list(exchange_config.keys())}")
    except Exception as e:
        print(f"配置加载失败: {e}")
        exchange_config = {"api_key": "demo", "api_secret": "demo"}
    
    # 4. 模拟交易操作
    print("\n模拟交易流程:")
    
    # 检查权限
    if trader.has_permission(Permission.TRADE_CREATE):
        print("✅ 权限检查通过，可以创建订单")
        
        # 模拟订单创建
        order_data = {
            "symbol": "BTC-USDT",
            "side": "buy",
            "quantity": 1.0,
            "price": 50000.0,
        }
        
        # 记录审计
        audit_trade(
            action="create",
            user_id=trader.user_id,
            **order_data
        )
        print(f"✅ 订单已创建并记录审计日志")
        print(f"   Symbol: {order_data['symbol']}")
        print(f"   Quantity: {order_data['quantity']}")
    else:
        print("❌ 权限不足")
    
    print()


# ============ 运行所有示例 ============

def main():
    """主函数"""
    print("\n")
    print("╔" + "═" * 48 + "╗")
    print("║" + " " * 10 + "QuantForge 安全模块示例" + " " * 13 + "║")
    print("╚" + "═" * 48 + "╝")
    print("\n")
    
    # 运行示例
    try:
        example_init_security()
    except Exception as e:
        print(f"初始化示例跳过: {e}\n")
    
    try:
        example_encrypt_config()
    except Exception as e:
        print(f"加密示例跳过: {e}\n")
    
    example_log_masking()
    example_access_control()
    
    try:
        example_audit_logging()
    except Exception as e:
        print(f"审计日志示例跳过: {e}\n")
    
    try:
        asyncio.run(example_secure_trading())
    except Exception as e:
        print(f"综合示例跳过: {e}\n")
    
    print("=" * 50)
    print("所有示例运行完成!")
    print("=" * 50)
    print("\n更多信息请查看:")
    print("  - modules/qf-security/README.md")
    print("  - modules/qf-security/tests/test_security.py")
    print()


if __name__ == "__main__":
    main()
