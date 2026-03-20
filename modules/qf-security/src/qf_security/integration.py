"""
Security Integration Module - 安全集成模块
为其他QuantForge模块提供安全功能的便捷集成
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from functools import wraps

from qf_security import (
    SecureConfig,
    install_log_masker,
    create_masked_logger,
    MaskingConfig,
    init_audit_logger,
    audit_log_event,
    AuditEventType,
    RBACManager,
    Permission,
    require_permission,
)


# 全局安全配置实例
_global_secure_config: Optional[SecureConfig] = None
_global_rbac_manager: Optional[RBACManager] = None


def init_security(
    master_key: Optional[str] = None,
    config_path: Optional[Path] = None,
    audit_log_path: Optional[Path] = None,
    enable_log_masking: bool = True,
) -> tuple:
    """
    初始化QuantForge安全系统
    
    Args:
        master_key: 主密钥，若为None则从环境获取
        config_path: 加密配置文件路径
        audit_log_path: 审计日志路径
        enable_log_masking: 是否启用日志脱敏
        
    Returns:
        (SecureConfig, RBACManager) 元组
    """
    global _global_secure_config, _global_rbac_manager
    
    # 初始化安全配置
    _global_secure_config = SecureConfig(
        master_key=master_key,
        encrypted_config_path=config_path,
    )
    
    # 初始化RBAC管理器
    _global_rbac_manager = RBACManager()
    
    # 初始化审计日志
    if audit_log_path:
        init_audit_logger(log_file=audit_log_path)
    
    # 安装日志脱敏
    if enable_log_masking:
        install_log_masker()
    
    return _global_secure_config, _global_rbac_manager


def get_secure_config() -> SecureConfig:
    """获取全局安全配置"""
    if _global_secure_config is None:
        raise RuntimeError("Security not initialized. Call init_security() first.")
    return _global_secure_config


def get_rbac_manager() -> RBACManager:
    """获取全局RBAC管理器"""
    if _global_rbac_manager is None:
        raise RuntimeError("Security not initialized. Call init_security() first.")
    return _global_rbac_manager


def load_exchange_config(exchange_name: str) -> Dict[str, Any]:
    """
    加载交易所配置（自动解密）
    
    Args:
        exchange_name: 交易所名称 (okx, binance, ctp等)
        
    Returns:
        解密后的配置字典
    """
    config = get_secure_config()
    
    # 尝试从加密配置加载
    try:
        full_config = config.load_encrypted_config()
        exchange_config = full_config.get("exchanges", {}).get(exchange_name, {})
    except Exception:
        # 如果失败，尝试从环境变量加载
        exchange_config = _load_exchange_config_from_env(exchange_name)
    
    return exchange_config


def _load_exchange_config_from_env(exchange_name: str) -> Dict[str, Any]:
    """从环境变量加载交易所配置"""
    prefix = f"QF_{exchange_name.upper()}_"
    
    config = {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            config_key = key[len(prefix):].lower()
            config[config_key] = value
    
    return config


def secure_logger(name: str) -> logging.Logger:
    """
    创建安全的logger（带脱敏功能）
    
    Args:
        name: logger名称
        
    Returns:
        配置好的logger
    """
    return create_masked_logger(name)


def audit_trade(
    action: str,
    symbol: Optional[str] = None,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    side: Optional[str] = None,
    order_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    记录交易审计日志
    
    Args:
        action: 动作描述
        symbol: 交易对
        quantity: 数量
        price: 价格
        side: 方向
        order_id: 订单ID
        user_id: 用户ID
        metadata: 额外元数据
    """
    # 映射动作到事件类型
    event_type_map = {
        "create": AuditEventType.ORDER_CREATED,
        "cancel": AuditEventType.ORDER_CANCELLED,
        "modify": AuditEventType.ORDER_MODIFIED,
        "fill": AuditEventType.ORDER_FILLED,
        "reject": AuditEventType.ORDER_REJECTED,
    }
    
    event_type = event_type_map.get(action.lower(), AuditEventType.ORDER_CREATED)
    
    new_value = {}
    if symbol:
        new_value["symbol"] = symbol
    if quantity is not None:
        new_value["quantity"] = quantity
    if price is not None:
        new_value["price"] = price
    if side:
        new_value["side"] = side
    
    audit_log_event(
        event_type=event_type,
        user_id=user_id,
        resource_type="order",
        resource_id=order_id,
        action=action,
        new_value=new_value,
        metadata=metadata or {},
    )


def audit_config_change(
    config_name: str,
    old_value: Any,
    new_value: Any,
    user_id: Optional[str] = None,
) -> None:
    """
    记录配置变更审计日志
    
    Args:
        config_name: 配置名称
        old_value: 原值
        new_value: 新值
        user_id: 用户ID
    """
    audit_log_event(
        event_type=AuditEventType.CONFIG_UPDATED,
        user_id=user_id,
        resource_type="config",
        resource_id=config_name,
        old_value=old_value,
        new_value=new_value,
    )


def secure_decorator(permission: Optional[Permission] = None):
    """
    综合安全装饰器
    
    组合权限检查、审计日志和异常处理
    
    Args:
        permission: 所需权限
        
    Example:
        @secure_decorator(permission=Permission.TRADE_CREATE)
        async def create_order(user, order_data):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 权限检查
            if permission:
                user = kwargs.get("user") or (args[0] if args else None)
                if user and hasattr(user, "has_permission"):
                    if not user.has_permission(permission):
                        raise PermissionDeniedError(f"Permission required: {permission}")
            
            # 执行函数
            try:
                result = await func(*args, **kwargs)
                
                # 记录成功审计日志
                audit_log_event(
                    event_type=AuditEventType.SYSTEM_STATUS,
                    action=func.__name__,
                    status="success",
                    metadata={"args": str(args), "kwargs": str(kwargs)},
                )
                
                return result
            except Exception as e:
                # 记录失败审计日志
                audit_log_event(
                    event_type=AuditEventType.SYSTEM_ERROR,
                    action=func.__name__,
                    status="failure",
                    error_message=str(e),
                    metadata={"args": str(args), "kwargs": str(kwargs)},
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 权限检查
            if permission:
                user = kwargs.get("user") or (args[0] if args else None)
                if user and hasattr(user, "has_permission"):
                    if not user.has_permission(permission):
                        from qf_security import PermissionDeniedError
                        raise PermissionDeniedError(f"Permission required: {permission}")
            
            # 执行函数
            try:
                result = func(*args, **kwargs)
                
                # 记录成功审计日志
                audit_log_event(
                    event_type=AuditEventType.SYSTEM_STATUS,
                    action=func.__name__,
                    status="success",
                )
                
                return result
            except Exception as e:
                # 记录失败审计日志
                audit_log_event(
                    event_type=AuditEventType.SYSTEM_ERROR,
                    action=func.__name__,
                    status="failure",
                    error_message=str(e),
                )
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


class SecureDataSource:
    """
    安全数据源包装器
    
    为数据源提供统一的安全包装：
    - 配置自动解密
    - 操作审计
    - 错误脱敏
    """
    
    def __init__(self, name: str, source_class: type, config_key: str):
        self.name = name
        self.source_class = source_class
        self.config_key = config_key
        self._source = None
        self._logger = secure_logger(f"datasource.{name}")
    
    def _get_source(self):
        """延迟初始化数据源"""
        if self._source is None:
            config = load_exchange_config(self.config_key)
            self._source = self.source_class(config)
            self._logger.info(f"Initialized secure {self.name} data source")
        return self._source
    
    def __getattr__(self, name: str):
        """代理属性访问"""
        source = self._get_source()
        attr = getattr(source, name)
        
        # 如果是方法，包装审计
        if callable(attr):
            @wraps(attr)
            def wrapper(*args, **kwargs):
                try:
                    result = attr(*args, **kwargs)
                    audit_log_event(
                        event_type=AuditEventType.DATA_READ,
                        resource_type=self.name,
                        action=name,
                        status="success",
                    )
                    return result
                except Exception as e:
                    self._logger.error(f"{name} failed: {e}")
                    audit_log_event(
                        event_type=AuditEventType.DATA_READ,
                        resource_type=self.name,
                        action=name,
                        status="failure",
                        error_message=str(e),
                    )
                    raise
            return wrapper
        
        return attr


# 便捷函数：为现有模块添加安全功能
def patch_module_security(module_name: str) -> None:
    """
    为现有模块添加安全补丁
    
    这是临时方案，推荐在模块内部直接集成安全功能
    
    Args:
        module_name: 模块名称
    """
    logger = secure_logger(f"patch.{module_name}")
    logger.info(f"Applying security patches to {module_name}")
    
    # 这里可以添加具体的补丁逻辑
    # 例如：替换配置加载函数、添加审计日志等
