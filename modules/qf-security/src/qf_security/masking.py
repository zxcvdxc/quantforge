"""
Masking Module - 敏感数据脱敏模块
提供日志脱敏、金额脱敏等功能
"""

import re
import json
import logging
from typing import Any, Dict, List, Optional, Pattern, Union
from decimal import Decimal
from dataclasses import dataclass, field


# 敏感字段名称模式 (正则表达式)
SENSITIVE_FIELD_PATTERNS = [
    re.compile(r".*password.*", re.IGNORECASE),
    re.compile(r".*secret.*", re.IGNORECASE),
    re.compile(r".*api_key.*", re.IGNORECASE),
    re.compile(r".*api_secret.*", re.IGNORECASE),
    re.compile(r".*private_key.*", re.IGNORECASE),
    re.compile(r".*token.*", re.IGNORECASE),
    re.compile(r".*passphrase.*", re.IGNORECASE),
    re.compile(r".*access_key.*", re.IGNORECASE),
    re.compile(r".*access_secret.*", re.IGNORECASE),
    re.compile(r".*auth.*", re.IGNORECASE),
    re.compile(r".*credential.*", re.IGNORECASE),
    re.compile(r".*mysql_password.*", re.IGNORECASE),
    re.compile(r".*redis_password.*", re.IGNORECASE),
    re.compile(r".*influxdb_token.*", re.IGNORECASE),
]

# 敏感值模式 (正则表达式)
SENSITIVE_VALUE_PATTERNS = [
    # API密钥 (常见格式)
    re.compile(r"[A-Za-z0-9]{32,}"),  # 32位以上字母数字组合
    re.compile(r"[a-f0-9]{64}", re.IGNORECASE),  # 64位十六进制 (常见哈希)
]

# 数据库连接字符串模式
CONNECTION_STRING_PATTERN = re.compile(
    r"((?:mysql|postgresql|mongodb|redis|amqp|http|https)://)"
    r"([^:]+):([^@]+)@"
    r"(.+)",
    re.IGNORECASE,
)


@dataclass
class MaskingConfig:
    """脱敏配置"""
    
    # 是否启用脱敏
    enabled: bool = True
    
    # 是否脱敏金额
    mask_amounts: bool = False
    
    # 金额脱敏阈值 (超过此值的金额脱敏)
    amount_threshold: Decimal = Decimal("10000")
    
    # 金额脱敏精度 (保留几位)
    amount_precision: int = 0
    
    # 自定义敏感字段
    sensitive_fields: List[str] = field(default_factory=list)
    
    # 自定义脱敏规则
    custom_rules: Dict[str, str] = field(default_factory=dict)
    
    # 脱敏替换字符
    mask_char: str = "*"
    
    # 保留前几位
    keep_prefix: int = 4
    
    # 保留后几位
    keep_suffix: int = 4


class LogMasker(logging.Filter):
    """
    日志脱敏过滤器
    
    用法:
        handler = logging.StreamHandler()
        handler.addFilter(LogMasker())
        logger.addHandler(handler)
    """
    
    def __init__(self, config: Optional[MaskingConfig] = None, name: str = ""):
        super().__init__(name)
        self.config = config or MaskingConfig()
    
    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录，脱敏敏感信息"""
        if not self.config.enabled:
            return True
        
        # 脱敏消息
        if isinstance(record.msg, str):
            record.msg = self.mask_message(record.msg)
        
        # 脱敏参数
        if record.args:
            record.args = self.mask_args(record.args)
        
        return True
    
    def mask_message(self, message: str) -> str:
        """脱敏消息内容"""
        # 脱敏API密钥
        message = mask_api_key(message, self.config.mask_char)
        
        # 脱敏密码
        message = mask_password(message, self.config.mask_char)
        
        # 脱敏连接字符串
        message = mask_connection_string(message, self.config.mask_char)
        
        # 脱敏JSON中的敏感字段
        message = self._mask_json_in_message(message)
        
        return message
    
    def mask_args(self, args: tuple) -> tuple:
        """脱敏参数"""
        return tuple(
            self.mask_message(str(arg)) if isinstance(arg, str) else arg
            for arg in args
        )
    
    def _mask_json_in_message(self, message: str) -> str:
        """尝试脱敏消息中的JSON"""
        try:
            # 尝试解析为JSON
            data = json.loads(message)
            masked_data = mask_sensitive_data(data, self.config)
            return json.dumps(masked_data, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            # 不是JSON，返回原消息
            return message


def mask_string(
    value: str,
    keep_prefix: int = 4,
    keep_suffix: int = 4,
    mask_char: str = "*",
) -> str:
    """
    脱敏字符串
    
    Args:
        value: 原始字符串
        keep_prefix: 保留前几位
        keep_suffix: 保留后几位
        mask_char: 脱敏字符
        
    Returns:
        脱敏后的字符串
        
    Example:
        >>> mask_string("1234567890")
        '1234****7890'
    """
    if not value:
        return value
    
    length = len(value)
    
    if length <= keep_prefix + keep_suffix:
        # 字符串太短，全部脱敏
        return mask_char * length
    
    prefix = value[:keep_prefix]
    suffix = value[-keep_suffix:] if keep_suffix > 0 else ""
    middle_length = length - keep_prefix - keep_suffix
    middle = mask_char * min(middle_length, 16)  # 最多显示16个脱敏字符
    
    return f"{prefix}{middle}{suffix}"


def mask_api_key(value: str, mask_char: str = "*") -> str:
    """
    脱敏API密钥
    
    Example:
        >>> mask_api_key("sk-1234567890abcdef")
        'sk-12**************cdef'
    """
    # 常见API密钥格式
    patterns = [
        # OpenAI格式: sk-...
        (re.compile(r"(sk-)([a-zA-Z0-9]{20,})"), 2),
        # 通用格式: 包含api_key=或apikey=
        (re.compile(r"(api[_-]?key[=:]\s*)([a-zA-Z0-9]{16,})", re.IGNORECASE), 2),
        # 通用格式: 包含secret=
        (re.compile(r"(secret[=:]\s*)([a-zA-Z0-9]{16,})", re.IGNORECASE), 2),
    ]
    
    for pattern, group in patterns:
        def replace(match):
            prefix = match.group(1)
            key = match.group(group)
            masked_key = mask_string(key, keep_prefix=4, keep_suffix=4, mask_char=mask_char)
            return f"{prefix}{masked_key}"
        
        value = pattern.sub(replace, value)
    
    return value


def mask_password(value: str, mask_char: str = "*") -> str:
    """
    脱敏密码
    
    Example:
        >>> mask_password("password=secret123")
        'password=********'
    """
    patterns = [
        # password=...
        (re.compile(r"(password[=:]\s*)([^\s&,;]+)", re.IGNORECASE), 2),
        # passwd=...
        (re.compile(r"(passwd[=:]\s*)([^\s&,;]+)", re.IGNORECASE), 2),
        # pwd=...
        (re.compile(r"(pwd[=:]\s*)([^\s&,;]+)", re.IGNORECASE), 2),
    ]
    
    for pattern, group in patterns:
        def replace(match):
            prefix = match.group(1)
            return f"{prefix}{mask_char * 8}"
        
        value = pattern.sub(replace, value)
    
    return value


def mask_connection_string(value: str, mask_char: str = "*") -> str:
    """
    脱敏数据库连接字符串
    
    Example:
        >>> mask_connection_string("mysql://user:pass@localhost:3306/db")
        'mysql://user:****@localhost:3306/db'
    """
    def replace(match):
        protocol = match.group(1)
        username = match.group(2)
        password = match.group(3)
        rest = match.group(4)
        return f"{protocol}{username}:{mask_char * 4}@{rest}"
    
    return CONNECTION_STRING_PATTERN.sub(replace, value)


def mask_amount(
    value: Union[Decimal, float, int, str],
    precision: int = 0,
    threshold: Optional[Decimal] = None,
) -> str:
    """
    脱敏金额
    
    Args:
        value: 金额值
        precision: 保留精度，0表示取整，-1表示脱敏
        threshold: 脱敏阈值，低于此值不脱敏
        
    Returns:
        脱敏后的金额字符串
        
    Example:
        >>> mask_amount(12345.67, precision=0)
        '12345'
        >>> mask_amount(12345.67, precision=-1)
        '*****'
    """
    if isinstance(value, str):
        try:
            value = Decimal(value)
        except:
            return value
    
    if threshold is not None and Decimal(str(value)) < threshold:
        return str(value)
    
    if precision == -1:
        # 完全脱敏
        return "*****"
    elif precision == 0:
        # 取整
        return str(int(Decimal(str(value))))
    else:
        # 保留指定精度
        return f"{Decimal(str(value)):.{precision}f}"


def is_sensitive_field(field_name: str, config: Optional[MaskingConfig] = None) -> bool:
    """判断字段名是否为敏感字段"""
    patterns = SENSITIVE_FIELD_PATTERNS.copy()
    
    if config and config.sensitive_fields:
        patterns.extend([
            re.compile(rf".*{re.escape(field)}.*", re.IGNORECASE)
            for field in config.sensitive_fields
        ])
    
    return any(pattern.match(field_name) for pattern in patterns)


def mask_sensitive_data(
    data: Any,
    config: Optional[MaskingConfig] = None,
    _visited: Optional[set] = None,
) -> Any:
    """
    递归脱敏敏感数据
    
    Args:
        data: 任意数据类型
        config: 脱敏配置
        _visited: 内部使用，防止循环引用
        
    Returns:
        脱敏后的数据
    """
    if _visited is None:
        _visited = set()
    
    config = config or MaskingConfig()
    
    if not config.enabled:
        return data
    
    # 防止循环引用
    if id(data) in _visited:
        return data
    
    if isinstance(data, dict):
        _visited.add(id(data))
        result = {}
        for key, value in data.items():
            if is_sensitive_field(key, config):
                # 敏感字段脱敏
                if isinstance(value, str):
                    result[key] = mask_string(
                        value,
                        keep_prefix=config.keep_prefix,
                        keep_suffix=config.keep_suffix,
                        mask_char=config.mask_char,
                    )
                else:
                    result[key] = config.mask_char * 8
            else:
                # 递归处理
                result[key] = mask_sensitive_data(value, config, _visited)
        return result
    
    elif isinstance(data, list):
        _visited.add(id(data))
        return [mask_sensitive_data(item, config, _visited) for item in data]
    
    elif isinstance(data, tuple):
        _visited.add(id(data))
        return tuple(mask_sensitive_data(item, config, _visited) for item in data)
    
    elif isinstance(data, str):
        # 检查是否是连接字符串
        if CONNECTION_STRING_PATTERN.match(data):
            return mask_connection_string(data, config.mask_char)
        return data
    
    elif isinstance(data, (Decimal, float, int)):
        # 检查是否需要脱敏金额
        if config.mask_amounts:
            return mask_amount(data, config.amount_precision, config.amount_threshold)
        return data
    
    return data


def mask_dict_values(
    data: Dict[str, Any],
    sensitive_keys: List[str],
    keep_prefix: int = 4,
    keep_suffix: int = 4,
    mask_char: str = "*",
) -> Dict[str, Any]:
    """
    对字典中指定键的值进行脱敏
    
    Args:
        data: 输入字典
        sensitive_keys: 需要脱敏的键列表
        keep_prefix: 保留前几位
        keep_suffix: 保留后几位
        mask_char: 脱敏字符
        
    Returns:
        脱敏后的字典
    """
    result = {}
    for key, value in data.items():
        if key in sensitive_keys and isinstance(value, str):
            result[key] = mask_string(value, keep_prefix, keep_suffix, mask_char)
        elif isinstance(value, dict):
            result[key] = mask_dict_values(value, sensitive_keys, keep_prefix, keep_suffix, mask_char)
        elif isinstance(value, list):
            result[key] = [
                mask_dict_values(item, sensitive_keys, keep_prefix, keep_suffix, mask_char)
                if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def install_log_masker(
    logger: Optional[logging.Logger] = None,
    config: Optional[MaskingConfig] = None,
) -> None:
    """
    安装日志脱敏过滤器
    
    Args:
        logger: 指定logger，若为None则应用到根logger
        config: 脱敏配置
    """
    if logger is None:
        logger = logging.getLogger()
    
    masker = LogMasker(config)
    logger.addFilter(masker)


def create_masked_logger(
    name: str,
    level: int = logging.INFO,
    config: Optional[MaskingConfig] = None,
) -> logging.Logger:
    """
    创建带脱敏功能的logger
    
    Args:
        name: logger名称
        level: 日志级别
        config: 脱敏配置
        
    Returns:
        配置好的logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 添加控制台处理器
    handler = logging.StreamHandler()
    handler.setLevel(level)
    
    # 添加脱敏过滤器
    masker = LogMasker(config)
    handler.addFilter(masker)
    
    # 设置格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger
