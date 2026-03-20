# qf-security - QuantForge 安全模块

QuantForge 安全模块提供完整的交易安全解决方案，包括：

- 🔐 **API密钥加密存储** - Fernet对称加密 + PBKDF2密钥派生
- 🎭 **敏感数据脱敏** - 日志脱敏、金额脱敏、连接字符串脱敏
- 🛡️ **访问控制** - RBAC角色权限控制、API密钥分级、IP白名单
- 📝 **审计日志** - 交易操作记录、配置变更审计、权限变更记录

## 快速开始

### 1. 安装

```bash
cd modules/qf-security
pip install -e .
```

### 2. 初始化安全系统

```python
from qf_security import initialize_security, SecureConfig

# 方式1: 生成随机主密钥
master_key = initialize_security()

# 方式2: 从密码派生
master_key = initialize_security(password="your-secure-password")
```

### 3. 加密配置

```python
from qf_security import SecureConfig

# 创建安全配置实例
secure_config = SecureConfig()

# 原始配置
config = {
    "okx": {
        "api_key": "your-api-key",
        "api_secret": "your-api-secret",
        "passphrase": "your-passphrase",
    },
    "mysql": {
        "password": "your-db-password",
    }
}

# 加密配置
encrypted = secure_config.encrypt_config_values(config)
print(encrypted)
# {
#   "okx": {
#     "api_key": "ENC:gAAAAAB...",
#     "api_secret": "ENC:gAAAAAB...",
#     "passphrase": "ENC:gAAAAAB...",
#   }
# }

# 保存到文件
secure_config.save_encrypted_config(config, "config.encrypted.json")

# 从文件加载并解密
loaded_config = secure_config.load_encrypted_config("config.encrypted.json")
```

### 4. 日志脱敏

```python
from qf_security import install_log_masker, create_masked_logger

# 方式1: 为现有logger添加脱敏
import logging
logger = logging.getLogger()
install_log_masker(logger)

# 方式2: 创建新的脱敏logger
logger = create_masked_logger("my_logger")

# 敏感信息会被自动脱敏
logger.info("Connecting with password=secret123")
# 输出: Connecting with password=********

logger.info("API Key: sk-1234567890abcdef")
# 输出: API Key: sk-12**************cdef
```

### 5. 访问控制

```python
from qf_security import (
    RBACManager, Permission, Role, APIKeyPermission,
    require_permission, require_role
)

# 创建RBAC管理器
rbac = RBACManager()

# 创建用户
user = rbac.create_user(
    user_id="user_001",
    username="trader1",
    role=Role.TRADER,
    allowed_ips=["192.168.1.*", "10.0.0.0/24"]
)

# 检查权限
if user.has_permission(Permission.TRADE_CREATE):
    print("User can create orders")

# 创建API密钥
api_key, raw_key = rbac.create_api_key(
    user_id="user_001",
    permission=APIKeyPermission.TRADING,
    expires_in_days=90,
    allowed_ips=["192.168.1.100"]
)

# 验证API密钥
try:
    validated_key = rbac.validate_api_key(raw_key, client_ip="192.168.1.100")
    print(f"Key validated: {validated_key.key_id}")
except Exception as e:
    print(f"Validation failed: {e}")

# 使用装饰器保护函数
@require_permission(Permission.TRADE_CREATE)
def create_order(user, order_data):
    pass

@require_role(Role.ADMIN)
def admin_function(user):
    pass
```

### 6. 审计日志

```python
from qf_security import (
    init_audit_logger, audit_log_event,
    AuditEventType, AuditLevel
)
from datetime import datetime

# 初始化审计日志
init_audit_logger(log_file="logs/audit.log")

# 记录事件
audit_log_event(
    event_type=AuditEventType.ORDER_CREATED,
    user_id="user_001",
    resource_type="order",
    resource_id="order_123",
    new_value={"symbol": "BTC-USDT", "side": "buy", "quantity": 1.0},
    client_ip="192.168.1.100"
)

# 记录配置变更
audit_log_event(
    event_type=AuditEventType.CONFIG_UPDATED,
    user_id="admin_001",
    resource_type="exchange_config",
    resource_id="okx",
    old_value={"timeout": 30},
    new_value={"timeout": 60},
)

# 记录登录
audit_log_event(
    event_type=AuditEventType.LOGIN_SUCCESS,
    user_id="user_001",
    client_ip="192.168.1.100",
    metadata={"user_agent": "Mozilla/5.0..."}
)
```

## 架构设计

```
qf_security/
├── encryption.py      # 加密模块 (Fernet + PBKDF2)
├── masking.py         # 脱敏模块
├── access_control.py  # 访问控制 (RBAC)
├── audit.py          # 审计日志
└── exceptions.py      # 异常定义
```

## 安全特性

### 1. API密钥加密

- 使用Fernet对称加密 (AES-128-CBC + HMAC-SHA256)
- 密钥通过PBKDF2派生，480,000次迭代 (OWASP推荐)
- 支持环境变量和密钥文件双模式
- 密钥轮换支持

### 2. 敏感数据脱敏

- 自动识别敏感字段 (password, secret, api_key等)
- 支持自定义脱敏规则
- 金额脱敏 (可配置阈值和精度)
- 数据库连接字符串脱敏

### 3. 访问控制

- 基于角色的权限控制 (RBAC)
- 3种内置角色: viewer, trader, admin
- API密钥三级权限: readonly, trading, manage
- IP白名单支持 (CIDR、通配符、范围)

### 4. 审计日志

- 20+种审计事件类型
- 支持文件和数据库存储
- 变更追踪 (old_value/new_value)
- 请求追踪和会话管理

## 测试

```bash
# 运行测试
pytest tests/ -v

# 运行带覆盖率
pytest tests/ --cov=qf_security --cov-report=html
```

## 许可证

MIT License
