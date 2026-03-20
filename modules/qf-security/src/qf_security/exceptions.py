"""
Security Module Exceptions - 安全模块异常定义
"""


class SecurityError(Exception):
    """安全模块基础异常"""
    pass


class EncryptionError(SecurityError):
    """加密错误"""
    pass


class DecryptionError(SecurityError):
    """解密错误"""
    pass


class AccessDeniedError(SecurityError):
    """访问被拒绝"""
    pass


class InvalidTokenError(SecurityError):
    """无效令牌"""
    pass


class KeyRotationError(SecurityError):
    """密钥轮换错误"""
    pass


class PermissionDeniedError(AccessDeniedError):
    """权限不足"""
    pass


class IPNotWhitelistedError(AccessDeniedError):
    """IP不在白名单中"""
    pass


class APIKeyInvalidError(AccessDeniedError):
    """API密钥无效"""
    pass


class APIKeyExpiredError(AccessDeniedError):
    """API密钥已过期"""
    pass


class AuditLogError(SecurityError):
    """审计日志错误"""
    pass
