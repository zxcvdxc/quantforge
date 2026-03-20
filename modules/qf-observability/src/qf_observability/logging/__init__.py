"""
日志模块 - 结构化日志和敏感数据脱敏
"""

from .json_logger import (
    JSONLogger,
    JSONLogFormatter,
    configure_logging,
    get_logger,
    set_log_level,
    get_context,
    set_context,
    clear_context,
    generate_trace_id,
    generate_span_id,
    log_with_context,
    ContextManager,
    with_context,
)

from .masking import (
    SensitiveDataFilter,
    add_sensitive_pattern,
    remove_sensitive_pattern,
    mask_sensitive_fields,
    mask_api_key,
    mask_password,
    mask_connection_string,
    mask_amount,
    mask_email,
    mask_phone,
    create_masked_logger,
)

__all__ = [
    'JSONLogger',
    'JSONLogFormatter',
    'configure_logging',
    'get_logger',
    'set_log_level',
    'get_context',
    'set_context',
    'clear_context',
    'generate_trace_id',
    'generate_span_id',
    'log_with_context',
    'ContextManager',
    'with_context',
    'SensitiveDataFilter',
    'add_sensitive_pattern',
    'remove_sensitive_pattern',
    'mask_sensitive_fields',
    'mask_api_key',
    'mask_password',
    'mask_connection_string',
    'mask_amount',
    'mask_email',
    'mask_phone',
    'create_masked_logger',
]
