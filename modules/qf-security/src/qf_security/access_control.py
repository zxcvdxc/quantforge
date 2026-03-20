"""
Access Control Module - 访问控制模块
提供基于角色的权限控制 (RBAC)、API密钥权限分级、IP白名单等功能
"""

import re
import functools
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Callable, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from ipaddress import ip_address, ip_network

from .exceptions import (
    PermissionDeniedError,
    IPNotWhitelistedError,
    APIKeyInvalidError,
    APIKeyExpiredError,
)


class Permission(Enum):
    """权限枚举"""
    # 数据权限
    DATA_READ = auto()           # 读取数据
    DATA_WRITE = auto()          # 写入数据
    DATA_DELETE = auto()         # 删除数据
    
    # 交易权限
    TRADE_VIEW = auto()          # 查看持仓/订单
    TRADE_CREATE = auto()        # 创建订单
    TRADE_CANCEL = auto()        # 取消订单
    TRADE_MODIFY = auto()        # 修改订单
    
    # 管理权限
    CONFIG_READ = auto()         # 读取配置
    CONFIG_WRITE = auto()        # 修改配置
    USER_MANAGE = auto()         # 用户管理
    KEY_MANAGE = auto()          # API密钥管理
    AUDIT_VIEW = auto()          # 查看审计日志
    
    # 系统权限
    SYSTEM_STATUS = auto()       # 查看系统状态
    SYSTEM_CONTROL = auto()      # 控制系统 (启停)
    BACKUP_MANAGE = auto()       # 备份管理


class Role(Enum):
    """角色枚举"""
    # 只读角色
    VIEWER = "viewer"
    # 交易员角色
    TRADER = "trader"
    # 管理员角色
    ADMIN = "admin"
    # 系统角色 (内部使用)
    SYSTEM = "system"


# 角色权限映射
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.VIEWER: {
        Permission.DATA_READ,
        Permission.TRADE_VIEW,
        Permission.CONFIG_READ,
        Permission.SYSTEM_STATUS,
    },
    Role.TRADER: {
        Permission.DATA_READ,
        Permission.DATA_WRITE,
        Permission.TRADE_VIEW,
        Permission.TRADE_CREATE,
        Permission.TRADE_CANCEL,
        Permission.TRADE_MODIFY,
        Permission.CONFIG_READ,
        Permission.SYSTEM_STATUS,
    },
    Role.ADMIN: {
        Permission.DATA_READ,
        Permission.DATA_WRITE,
        Permission.DATA_DELETE,
        Permission.TRADE_VIEW,
        Permission.TRADE_CREATE,
        Permission.TRADE_CANCEL,
        Permission.TRADE_MODIFY,
        Permission.CONFIG_READ,
        Permission.CONFIG_WRITE,
        Permission.USER_MANAGE,
        Permission.KEY_MANAGE,
        Permission.AUDIT_VIEW,
        Permission.SYSTEM_STATUS,
        Permission.SYSTEM_CONTROL,
        Permission.BACKUP_MANAGE,
    },
    Role.SYSTEM: set(Permission),  # 系统角色拥有所有权限
}


class APIKeyPermission(Enum):
    """API密钥权限级别"""
    READ_ONLY = "readonly"       # 只读 (查询)
    TRADING = "trading"          # 交易 (查询+交易)
    MANAGE = "manage"            # 管理 (查询+交易+配置)


# API密钥权限映射到角色
APIKEY_PERMISSION_ROLE: Dict[APIKeyPermission, Role] = {
    APIKeyPermission.READ_ONLY: Role.VIEWER,
    APIKeyPermission.TRADING: Role.TRADER,
    APIKeyPermission.MANAGE: Role.ADMIN,
}


@dataclass
class APIKey:
    """API密钥数据结构"""
    
    key_id: str                          # 密钥ID
    key_hash: str                        # 密钥哈希值 (存储用)
    permission: APIKeyPermission         # 权限级别
    role: Role                           # 关联角色
    created_at: datetime                 # 创建时间
    expires_at: Optional[datetime]       # 过期时间
    last_used_at: Optional[datetime]     # 最后使用时间
    usage_count: int = 0                 # 使用次数
    is_active: bool = True               # 是否激活
    allowed_ips: Optional[List[str]] = None  # 允许的IP列表
    rate_limit: Optional[int] = None     # 速率限制 (请求/分钟)
    description: Optional[str] = None    # 描述
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def can_access(self, client_ip: str) -> bool:
        """检查IP是否允许访问"""
        if self.allowed_ips is None or not self.allowed_ips:
            return True
        return IPWhitelist.check_ip(client_ip, self.allowed_ips)
    
    def has_permission(self, permission: Permission) -> bool:
        """检查是否有指定权限"""
        return permission in ROLE_PERMISSIONS.get(self.role, set())


@dataclass
class User:
    """用户数据结构"""
    
    user_id: str                         # 用户ID
    username: str                        # 用户名
    role: Role                           # 角色
    password_hash: Optional[str] = None  # 密码哈希
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    is_active: bool = True
    api_keys: List[APIKey] = field(default_factory=list)
    allowed_ips: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def has_permission(self, permission: Permission) -> bool:
        """检查用户是否有指定权限"""
        return permission in ROLE_PERMISSIONS.get(self.role, set())
    
    def can_access(self, client_ip: str) -> bool:
        """检查用户IP是否允许"""
        if self.allowed_ips is None or not self.allowed_ips:
            return True
        return IPWhitelist.check_ip(client_ip, self.allowed_ips)


class IPWhitelist:
    """IP白名单管理"""
    
    @staticmethod
    def check_ip(client_ip: str, allowed_patterns: List[str]) -> bool:
        """
        检查IP是否在白名单中
        
        支持格式:
        - 精确IP: 192.168.1.1
        - CIDR: 192.168.1.0/24
        - 通配符: 192.168.1.*
        - 范围: 192.168.1.1-192.168.1.100
        """
        try:
            client = ip_address(client_ip)
        except ValueError:
            return False
        
        for pattern in allowed_patterns:
            if IPWhitelist._match_ip(client, pattern):
                return True
        
        return False
    
    @staticmethod
    def _match_ip(client: ip_address, pattern: str) -> bool:
        """匹配单个IP模式"""
        pattern = pattern.strip()
        
        # CIDR 格式
        if "/" in pattern:
            try:
                network = ip_network(pattern, strict=False)
                return client in network
            except ValueError:
                pass
        
        # 通配符格式
        if "*" in pattern:
            return IPWhitelist._match_wildcard(client, pattern)
        
        # 范围格式
        if "-" in pattern:
            return IPWhitelist._match_range(client, pattern)
        
        # 精确IP
        try:
            return client == ip_address(pattern)
        except ValueError:
            pass
        
        return False
    
    @staticmethod
    def _match_wildcard(client: ip_address, pattern: str) -> bool:
        """匹配通配符模式"""
        pattern_parts = pattern.split(".")
        client_parts = str(client).split(".")
        
        if len(pattern_parts) != len(client_parts):
            return False
        
        for p, c in zip(pattern_parts, client_parts):
            if p != "*" and p != c:
                return False
        
        return True
    
    @staticmethod
    def _match_range(client: ip_address, pattern: str) -> bool:
        """匹配IP范围"""
        try:
            start_ip, end_ip = pattern.split("-")
            start = ip_address(start_ip.strip())
            end = ip_address(end_ip.strip())
            
            # 转换为整数进行比较
            client_int = int(client)
            start_int = int(start)
            end_int = int(end)
            
            return start_int <= client_int <= end_int
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_patterns(patterns: List[str]) -> List[str]:
        """验证IP模式列表，返回无效的模式"""
        invalid = []
        for pattern in patterns:
            if not IPWhitelist._is_valid_pattern(pattern):
                invalid.append(pattern)
        return invalid
    
    @staticmethod
    def _is_valid_pattern(pattern: str) -> bool:
        """验证IP模式是否有效"""
        pattern = pattern.strip()
        
        # CIDR
        if "/" in pattern:
            try:
                ip_network(pattern, strict=False)
                return True
            except ValueError:
                pass
        
        # 通配符
        if "*" in pattern:
            return all(p == "*" or p.isdigit() for p in pattern.split("."))
        
        # 范围
        if "-" in pattern:
            try:
                start, end = pattern.split("-")
                ip_address(start.strip())
                ip_address(end.strip())
                return True
            except ValueError:
                pass
        
        # 精确IP
        try:
            ip_address(pattern)
            return True
        except ValueError:
            pass
        
        return False


class RBACManager:
    """
    基于角色的访问控制管理器
    
    提供用户管理、API密钥管理、权限检查等功能
    """
    
    def __init__(self):
        self._users: Dict[str, User] = {}
        self._api_keys: Dict[str, APIKey] = {}
        self._api_key_hashes: Dict[str, str] = {}  # key_hash -> key_id
    
    # ============ 用户管理 ============
    
    def create_user(
        self,
        user_id: str,
        username: str,
        role: Role,
        password_hash: Optional[str] = None,
        allowed_ips: Optional[List[str]] = None,
    ) -> User:
        """创建用户"""
        if user_id in self._users:
            raise ValueError(f"User {user_id} already exists")
        
        user = User(
            user_id=user_id,
            username=username,
            role=role,
            password_hash=password_hash,
            allowed_ips=allowed_ips,
        )
        self._users[user_id] = user
        return user
    
    def get_user(self, user_id: str) -> Optional[User]:
        """获取用户"""
        return self._users.get(user_id)
    
    def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        if user_id in self._users:
            del self._users[user_id]
            return True
        return False
    
    def list_users(self) -> List[User]:
        """列出所有用户"""
        return list(self._users.values())
    
    def update_user_role(self, user_id: str, new_role: Role) -> bool:
        """更新用户角色"""
        user = self._users.get(user_id)
        if user:
            user.role = new_role
            return True
        return False
    
    # ============ API密钥管理 ============
    
    def create_api_key(
        self,
        user_id: str,
        permission: APIKeyPermission,
        expires_in_days: Optional[int] = None,
        allowed_ips: Optional[List[str]] = None,
        rate_limit: Optional[int] = None,
        description: Optional[str] = None,
    ) -> tuple:
        """
        创建API密钥
        
        Returns:
            (APIKey, raw_key) 元组，raw_key只显示一次
        """
        import secrets
        import hashlib
        
        # 生成随机密钥
        raw_key = f"qf_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_id = f"key_{secrets.token_hex(8)}"
        
        # 计算过期时间
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now() + timedelta(days=expires_in_days)
        
        # 确定角色
        role = APIKEY_PERMISSION_ROLE.get(permission, Role.VIEWER)
        
        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            permission=permission,
            role=role,
            created_at=datetime.now(),
            expires_at=expires_at,
            allowed_ips=allowed_ips,
            rate_limit=rate_limit,
            description=description,
        )
        
        self._api_keys[key_id] = api_key
        self._api_key_hashes[key_hash] = key_id
        
        # 关联到用户
        user = self._users.get(user_id)
        if user:
            user.api_keys.append(api_key)
        
        return api_key, raw_key
    
    def validate_api_key(self, raw_key: str, client_ip: Optional[str] = None) -> APIKey:
        """
        验证API密钥
        
        Args:
            raw_key: 原始API密钥
            client_ip: 客户端IP (用于IP白名单检查)
            
        Returns:
            APIKey对象
            
        Raises:
            APIKeyInvalidError: 密钥无效
            APIKeyExpiredError: 密钥已过期
            IPNotWhitelistedError: IP不在白名单中
        """
        import hashlib
        
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_id = self._api_key_hashes.get(key_hash)
        
        if not key_id:
            raise APIKeyInvalidError("Invalid API key")
        
        api_key = self._api_keys.get(key_id)
        if not api_key:
            raise APIKeyInvalidError("Invalid API key")
        
        if not api_key.is_active:
            raise APIKeyInvalidError("API key is deactivated")
        
        if api_key.is_expired():
            raise APIKeyExpiredError("API key has expired")
        
        if client_ip and not api_key.can_access(client_ip):
            raise IPNotWhitelistedError(f"IP {client_ip} not whitelisted")
        
        # 更新使用统计
        api_key.last_used_at = datetime.now()
        api_key.usage_count += 1
        
        return api_key
    
    def revoke_api_key(self, key_id: str) -> bool:
        """撤销API密钥"""
        api_key = self._api_keys.get(key_id)
        if api_key:
            api_key.is_active = False
            return True
        return False
    
    def delete_api_key(self, key_id: str) -> bool:
        """删除API密钥"""
        api_key = self._api_keys.get(key_id)
        if api_key:
            del self._api_keys[key_id]
            if api_key.key_hash in self._api_key_hashes:
                del self._api_key_hashes[api_key.key_hash]
            return True
        return False
    
    def list_api_keys(self, user_id: Optional[str] = None) -> List[APIKey]:
        """列出API密钥"""
        if user_id:
            user = self._users.get(user_id)
            if user:
                return user.api_keys
            return []
        return list(self._api_keys.values())
    
    # ============ 权限检查 ============
    
    def check_permission(
        self,
        user_or_key: Union[User, APIKey],
        permission: Permission,
    ) -> bool:
        """检查权限"""
        return user_or_key.has_permission(permission)
    
    def require_permission(
        self,
        user_or_key: Union[User, APIKey],
        permission: Permission,
    ) -> None:
        """要求必须有权限，否则抛出异常"""
        if not self.check_permission(user_or_key, permission):
            raise PermissionDeniedError(
                f"Permission denied: {permission.name}"
            )


# ============ 装饰器 ============

def require_permission(permission: Permission):
    """
    权限检查装饰器
    
    用于函数级别的权限控制
    
    Example:
        @require_permission(Permission.TRADE_CREATE)
        async def create_order(user: User, order_data: dict):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 从参数中查找用户或API密钥
            user_or_key = None
            for arg in args:
                if isinstance(arg, (User, APIKey)):
                    user_or_key = arg
                    break
            
            if user_or_key is None:
                # 从kwargs查找
                user_or_key = kwargs.get("user") or kwargs.get("api_key")
            
            if user_or_key is None:
                raise PermissionDeniedError("No user or API key provided")
            
            if not user_or_key.has_permission(permission):
                raise PermissionDeniedError(
                    f"Permission denied: {permission.name}"
                )
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_role(role: Role):
    """
    角色检查装饰器
    
    Example:
        @require_role(Role.ADMIN)
        def admin_only_function(user: User):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            user = None
            for arg in args:
                if isinstance(arg, User):
                    user = arg
                    break
            
            if user is None:
                user = kwargs.get("user")
            
            if user is None:
                raise PermissionDeniedError("No user provided")
            
            if user.role != role and user.role != Role.SYSTEM:
                raise PermissionDeniedError(
                    f"Role required: {role.value}"
                )
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_api_key(
    permission: Optional[APIKeyPermission] = None,
    check_ip: bool = True,
):
    """
    API密钥验证装饰器
    
    Example:
        @require_api_key(permission=APIKeyPermission.TRADING)
        async def trading_endpoint(request):
            api_key = request.api_key  # 已验证的API密钥对象
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 这里假设request对象在args或kwargs中
            request = kwargs.get("request")
            if request is None and args:
                request = args[0]
            
            if request is None:
                raise APIKeyInvalidError("No request object provided")
            
            # 获取API密钥 (从header或query param)
            raw_key = getattr(request, "api_key", None)
            if raw_key is None:
                # 尝试从不同属性获取
                headers = getattr(request, "headers", {})
                raw_key = headers.get("X-API-Key") if isinstance(headers, dict) else None
            
            if not raw_key:
                raise APIKeyInvalidError("No API key provided")
            
            # 获取客户端IP
            client_ip = None
            if check_ip:
                client_ip = getattr(request, "client_ip", None)
                if client_ip is None:
                    headers = getattr(request, "headers", {})
                    if isinstance(headers, dict):
                        client_ip = headers.get("X-Forwarded-For", headers.get("X-Real-IP"))
            
            # 验证密钥
            rbac = RBACManager()
            api_key = rbac.validate_api_key(raw_key, client_ip)
            
            # 检查权限级别
            if permission and api_key.permission != permission:
                # 高级权限可以访问低级端点
                permission_order = [
                    APIKeyPermission.READ_ONLY,
                    APIKeyPermission.TRADING,
                    APIKeyPermission.MANAGE,
                ]
                if permission_order.index(api_key.permission) < permission_order.index(permission):
                    raise PermissionDeniedError(
                        f"API key permission insufficient: {api_key.permission.value}"
                    )
            
            # 将验证后的密钥对象注入到函数参数
            kwargs["api_key"] = api_key
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def ip_whitelist(allowed_patterns: List[str]):
    """
    IP白名单装饰器
    
    Example:
        @ip_whitelist(["192.168.1.*", "10.0.0.0/24"])
        def internal_endpoint(request):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            if request is None and args:
                request = args[0]
            
            if request is None:
                raise IPNotWhitelistedError("No request object provided")
            
            # 获取客户端IP
            client_ip = getattr(request, "client_ip", None)
            if client_ip is None:
                headers = getattr(request, "headers", {})
                if isinstance(headers, dict):
                    client_ip = headers.get("X-Forwarded-For", headers.get("X-Real-IP"))
            
            if not client_ip:
                raise IPNotWhitelistedError("Cannot determine client IP")
            
            if not IPWhitelist.check_ip(client_ip, allowed_patterns):
                raise IPNotWhitelistedError(f"IP {client_ip} not whitelisted")
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator
