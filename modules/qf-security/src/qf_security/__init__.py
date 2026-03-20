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
    generate_master_key,
    save_master_key,
    initialize_security,
    rotate_key,
)

from .masking import (
    LogMasker,
    mask_sensitive_data,
    mask_api_key,
    mask_password,
    mask_connection_string,
    mask_amount,
    mask_string,
    mask_dict_values,
    install_log_masker,
    create_masked_logger,
    MaskingConfig,
)

from .access_control import (
    RBACManager,
    Permission,
    Role,
    APIKeyPermission,
    IPWhitelist,
    require_permission,
    require_role,
    User,
    APIKey,
)

from .audit import (
    AuditLogger,
    AuditEvent,
    AuditEventType,
    AuditLevel,
    audit_log,
    audit_log_event,
    init_audit_logger,
    get_audit_logger,
)

from .exceptions import (
    SecurityError,
    EncryptionError,
    DecryptionError,
    AccessDeniedError,
    PermissionDeniedError,
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
    "generate_master_key",
    "save_master_key",
    "initialize_security",
    "rotate_key",
    # Masking
    "LogMasker",
    "mask_sensitive_data",
    "mask_api_key",
    "mask_password",
    "mask_connection_string",
    "mask_amount",
    "mask_string",
    "mask_dict_values",
    "install_log_masker",
    "create_masked_logger",
    "MaskingConfig",
    # Access Control
    "RBACManager",
    "Permission",
    "Role",
    "APIKeyPermission",
    "IPWhitelist",
    "require_permission",
    "require_role",
    "User",
    "APIKey",
    # Audit
    "AuditLogger",
    "AuditEvent",
    "AuditEventType",
    "AuditLevel",
    "audit_log",
    "audit_log_event",
    "init_audit_logger",
    "get_audit_logger",
    # Exceptions
    "SecurityError",
    "EncryptionError",
    "DecryptionError",
    "AccessDeniedError",
    "PermissionDeniedError",
    "InvalidTokenError",
    "KeyRotationError",
]
