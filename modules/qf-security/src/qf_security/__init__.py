"""
QuantForge Security Module - 安全模块
提供加密存储、访问控制、审计日志等安全功能
"""

from .encryption import (
    SecureConfig,
    FernetEncryption,
    KeyDerivation,
    encrypt_config,
    decrypt_config,
    get_master_key,
    rotate_key,
)

from .masking import (
    LogMasker,
    mask_sensitive_data,
    mask_api_key,
    mask_password,
    mask_connection_string,
    mask_amount,
)

from .access_control import (
    RBACManager,
    Permission,
    Role,
    APIKeyPermission,
    IPWhitelist,
    require_permission,
    require_role,
)

from .audit import (
    AuditLogger,
    AuditEvent,
    AuditEventType,
    audit_log,
)

from .exceptions import (
    SecurityError,
    EncryptionError,
    DecryptionError,
    AccessDeniedError,
    InvalidTokenError,
    KeyRotationError,
)

__version__ = "1.0.0"

__all__ = [
    # Encryption
    "SecureConfig",
    "FernetEncryption",
    "KeyDerivation",
    "encrypt_config",
    "decrypt_config",
    "get_master_key",
    "rotate_key",
    # Masking
    "LogMasker",
    "mask_sensitive_data",
    "mask_api_key",
    "mask_password",
    "mask_connection_string",
    "mask_amount",
    # Access Control
    "RBACManager",
    "Permission",
    "Role",
    "APIKeyPermission",
    "IPWhitelist",
    "require_permission",
    "require_role",
    # Audit
    "AuditLogger",
    "AuditEvent",
    "AuditEventType",
    "audit_log",
    # Exceptions
    "SecurityError",
    "EncryptionError",
    "DecryptionError",
    "AccessDeniedError",
    "InvalidTokenError",
    "KeyRotationError",
]
