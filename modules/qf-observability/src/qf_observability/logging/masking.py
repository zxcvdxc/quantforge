"""
敏感数据脱敏模块
提供自动识别和脱敏敏感字段的功能
"""

import re
import json
import hashlib
from typing import Any, Dict, List, Optional, Pattern, Set, Callable
from copy import deepcopy


class SensitiveDataFilter:
    """敏感数据过滤器"""
    
    # Default sensitive field patterns
    DEFAULT_SENSITIVE_FIELDS: Set[str] = {
        'password', 'passwd', 'pwd',
        'secret', 'secret_key', 'api_secret',
        'token', 'access_token', 'refresh_token', 'auth_token',
        'api_key', 'apikey', 'key',
        'private_key', 'privatekey',
        'credit_card', 'creditcard', 'card_number', 'ccv', 'cvv',
        'ssn', 'social_security',
        'email', 'phone', 'mobile',
        'address', 'address_line',
        'account_number', 'accountnumber', 'iban',
        'apikey', 'api_key', 'app_key', 'appkey',
        'authorization', 'auth',
        'cookie', 'session_id', 'sessionid',
        'connection_string', 'conn_string', 'dsn',
    }
    
    # Default patterns for sensitive values
    DEFAULT_PATTERNS: List[Pattern] = [
        # API keys
        re.compile(r'[a-zA-Z0-9]{32,}', re.IGNORECASE),
        # JWT tokens
        re.compile(r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*'),
        # UUIDs that might be keys
        re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE),
    ]
    
    def __init__(
        self,
        sensitive_fields: Optional[Set[str]] = None,
        mask_char: str = '*',
        max_mask_length: int = 8,
        hash_sensitive: bool = False,
    ):
        self.sensitive_fields = sensitive_fields or self.DEFAULT_SENSITIVE_FIELDS.copy()
        self.patterns = self.DEFAULT_PATTERNS.copy()
        self.mask_char = mask_char
        self.max_mask_length = max_mask_length
        self.hash_sensitive = hash_sensitive
        self._custom_filters: List[Callable[[Any], Any]] = []
    
    def add_sensitive_field(self, field: str):
        """添加敏感字段"""
        self.sensitive_fields.add(field.lower())
    
    def remove_sensitive_field(self, field: str):
        """移除敏感字段"""
        self.sensitive_fields.discard(field.lower())
    
    def add_pattern(self, pattern: Pattern):
        """添加敏感值匹配模式"""
        self.patterns.append(pattern)
    
    def remove_pattern(self, pattern: Pattern):
        """移除敏感值匹配模式"""
        if pattern in self.patterns:
            self.patterns.remove(pattern)
    
    def add_custom_filter(self, filter_func: Callable[[Any], Any]):
        """添加自定义过滤器"""
        self._custom_filters.append(filter_func)
    
    def mask_value(self, value: Any, field_name: str = '') -> Any:
        """脱敏单个值"""
        if value is None:
            return None
        
        if isinstance(value, str):
            # Check if field name is sensitive
            if field_name.lower() in self.sensitive_fields:
                return self._mask_string(value)
            
            # Check if value matches sensitive patterns
            for pattern in self.patterns:
                if pattern.search(value):
                    return self._mask_string(value)
            
            # Check for connection strings
            if any(kw in field_name.lower() for kw in ['connection', 'conn', 'dsn', 'url']):
                return mask_connection_string(value)
            
            return value
        
        elif isinstance(value, (int, float)):
            # Check if field name suggests this is sensitive
            if field_name.lower() in self.sensitive_fields:
                return self._mask_number(value)
            return value
        
        elif isinstance(value, dict):
            return self.mask_dict(value)
        
        elif isinstance(value, list):
            return [self.mask_value(item, field_name) for item in value]
        
        return value
    
    def _mask_string(self, value: str) -> str:
        """脱敏字符串"""
        if not value:
            return value
        
        if self.hash_sensitive:
            return f"sha256:{hashlib.sha256(value.encode()).hexdigest()[:16]}"
        
        if len(value) <= 4:
            return self.mask_char * len(value)
        elif len(value) <= 8:
            return value[:2] + self.mask_char * (len(value) - 4) + value[-2:]
        else:
            return value[:4] + self.mask_char * min(len(value) - 8, self.max_mask_length) + value[-4:]
    
    def _mask_number(self, value: Union[int, float]) -> str:
        """脱敏数字"""
        return self.mask_char * min(len(str(value)), self.max_mask_length)
    
    def mask_dict(self, data: Dict[str, Any], parent_key: str = '') -> Dict[str, Any]:
        """脱敏字典"""
        result = {}
        for key, value in data.items():
            full_key = f"{parent_key}.{key}" if parent_key else key
            
            # Check if key is sensitive
            if key.lower() in self.sensitive_fields:
                result[key] = self.mask_value(value, key)
            else:
                result[key] = self.mask_value(value, key)
        
        # Apply custom filters
        for filter_func in self._custom_filters:
            result = filter_func(result)
        
        return result
    
    def mask_json(self, json_str: str) -> str:
        """脱敏JSON字符串"""
        try:
            data = json.loads(json_str)
            masked_data = self.mask_value(data)
            return json.dumps(masked_data)
        except json.JSONDecodeError:
            return json_str
    
    def mask_log_message(self, message: str) -> str:
        """脱敏日志消息"""
        # Mask patterns in message
        masked = message
        for pattern in self.patterns:
            masked = pattern.sub(lambda m: self._mask_string(m.group()), masked)
        return masked


# Global filter instance
_global_filter = SensitiveDataFilter()


def add_sensitive_pattern(pattern: str):
    """添加敏感字段模式"""
    _global_filter.add_sensitive_field(pattern)


def remove_sensitive_pattern(pattern: str):
    """移除敏感字段模式"""
    _global_filter.remove_sensitive_field(pattern)


def mask_sensitive_fields(data: Any, field_names: Optional[List[str]] = None) -> Any:
    """脱敏敏感字段"""
    if field_names:
        for field in field_names:
            _global_filter.add_sensitive_field(field)
    
    return _global_filter.mask_value(data)


def mask_api_key(key: str) -> str:
    """脱敏API Key"""
    if not key or len(key) < 8:
        return '*' * len(key) if key else ''
    return f"{key[:4]}...{key[-4:]}"


def mask_password(password: str) -> str:
    """脱敏密码"""
    if not password:
        return ''
    return '*' * min(len(password), 8)


def mask_connection_string(conn_str: str) -> str:
    """脱敏连接字符串"""
    if not conn_str:
        return ''
    
    # Handle common connection string formats
    # MongoDB, PostgreSQL, MySQL, etc.
    
    # Mask password in URLs
    import urllib.parse
    try:
        parsed = urllib.parse.urlparse(conn_str)
        if parsed.password:
            masked_password = mask_password(parsed.password)
            netloc = f"{parsed.username}:{masked_password}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            
            # Reconstruct URL
            return urllib.parse.urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))
    except:
        pass
    
    # Handle key=value format
    patterns = [
        (r'(password|pwd|passwd)=([^\s;]+)', r'\1=***'),
        (r'(secret|api_key|apikey)=([^\s;]+)', r'\1=***'),
        (r'(token|auth_token)=([^\s;]+)', r'\1=***'),
    ]
    
    result = conn_str
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def mask_amount(amount: Union[int, float], show_last: int = 2) -> str:
    """脱敏金额"""
    if amount is None:
        return '***'
    
    amount_str = str(amount)
    if len(amount_str) <= show_last + 2:
        return '*' * len(amount_str)
    
    return '*' * (len(amount_str) - show_last) + amount_str[-show_last:]


def mask_email(email: str) -> str:
    """脱敏邮箱"""
    if not email or '@' not in email:
        return email
    
    local, domain = email.rsplit('@', 1)
    if len(local) <= 2:
        masked_local = local[0] + '*' if len(local) == 2 else '*'
    else:
        masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
    
    domain_parts = domain.split('.')
    masked_domain = domain_parts[0][0] + '***' if domain_parts[0] else ''
    masked_domain += '.' + '.'.join(domain_parts[1:])
    
    return f"{masked_local}@{masked_domain}"


def mask_phone(phone: str) -> str:
    """脱敏手机号"""
    if not phone:
        return ''
    
    # Remove non-digit characters
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) < 7:
        return '*' * len(digits)
    
    # Keep first 3 and last 4 digits
    return digits[:3] + '*' * (len(digits) - 7) + digits[-4:]


def create_masked_logger(logger, filter_instance: Optional[SensitiveDataFilter] = None):
    """为现有日志记录器添加脱敏功能"""
    filter_inst = filter_instance or _global_filter
    
    class MaskedLogger:
        def __init__(self, wrapped_logger):
            self._logger = wrapped_logger
        
        def _mask_args(self, args):
            if isinstance(args, tuple) and len(args) == 1:
                args = args[0]
            
            if isinstance(args, dict):
                return filter_inst.mask_dict(args)
            elif isinstance(args, str):
                return filter_inst.mask_log_message(args)
            return args
        
        def debug(self, msg, *args, **kwargs):
            self._logger.debug(self._mask_args(msg), *args, **kwargs)
        
        def info(self, msg, *args, **kwargs):
            self._logger.info(self._mask_args(msg), *args, **kwargs)
        
        def warning(self, msg, *args, **kwargs):
            self._logger.warning(self._mask_args(msg), *args, **kwargs)
        
        def error(self, msg, *args, **kwargs):
            self._logger.error(self._mask_args(msg), *args, **kwargs)
        
        def critical(self, msg, *args, **kwargs):
            self._logger.critical(self._mask_args(msg), *args, **kwargs)
        
        def exception(self, msg, *args, **kwargs):
            self._logger.exception(self._mask_args(msg), *args, **kwargs)
        
        def bind(self, **kwargs):
            masked_kwargs = filter_inst.mask_dict(kwargs)
            return MaskedLogger(self._logger.bind(**masked_kwargs))
    
    return MaskedLogger(logger)
