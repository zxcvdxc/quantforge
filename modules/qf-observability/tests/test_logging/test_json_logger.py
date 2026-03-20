"""
日志模块测试
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from qf_observability.logging import (
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
    SensitiveDataFilter,
    mask_sensitive_fields,
    mask_api_key,
    mask_password,
    mask_connection_string,
    mask_email,
    mask_phone,
)


class TestJSONLogger:
    """JSON日志测试"""
    
    def test_configure_logging(self):
        """测试配置日志"""
        logger = configure_logging(name='test', level='DEBUG')
        assert logger is not None
        
        log = get_logger('test')
        assert log is not None
    
    def test_set_log_level(self):
        """测试设置日志级别"""
        configure_logging(level='INFO')
        set_log_level('DEBUG')
        
        log = get_logger()
        # Just verify it doesn't throw
        log.info('Test message')
    
    def test_context_management(self):
        """测试上下文管理"""
        clear_context()
        
        trace_id = generate_trace_id()
        span_id = generate_span_id()
        
        set_context(trace_id=trace_id, span_id=span_id)
        ctx = get_context()
        
        assert ctx['trace_id'] == trace_id
        assert ctx['span_id'] == span_id
        
        clear_context()
        ctx = get_context()
        assert ctx['trace_id'] == ''
    
    def test_context_manager(self):
        """测试上下文管理器"""
        with ContextManager(trace_id='test-trace', span_id='test-span'):
            ctx = get_context()
            assert ctx['trace_id'] == 'test-trace'
            assert ctx['span_id'] == 'test-span'
        
        # Context should be cleared after exit
        ctx = get_context()
        assert ctx['trace_id'] == ''
    
    def test_with_context_decorator(self):
        """测试上下文装饰器"""
        @with_context(trace_id='decorated-trace')
        def test_func():
            ctx = get_context()
            return ctx['trace_id']
        
        result = test_func()
        assert result == 'decorated-trace'


class TestSensitiveDataFilter:
    """敏感数据过滤器测试"""
    
    def test_mask_password(self):
        """测试密码脱敏"""
        password = 'mySecretPassword123'
        masked = mask_password(password)
        assert '*' in masked
        assert len(masked) > 0
    
    def test_mask_api_key(self):
        """测试API Key脱敏"""
        api_key = 'sk-1234567890abcdef'
        masked = mask_api_key(api_key)
        assert '...' in masked
        assert masked.startswith('sk-1')
        assert masked.endswith('cdef')
    
    def test_mask_connection_string(self):
        """测试连接字符串脱敏"""
        conn_str = 'postgresql://user:password@localhost:5432/dbname'
        masked = mask_connection_string(conn_str)
        assert 'password' not in masked or '***' in masked
    
    def test_mask_email(self):
        """测试邮箱脱敏"""
        email = 'test@example.com'
        masked = mask_email(email)
        assert '@' in masked
        assert '*' in masked
    
    def test_mask_phone(self):
        """测试手机号脱敏"""
        phone = '13800138000'
        masked = mask_phone(phone)
        assert masked.startswith('138')
        assert masked.endswith('8000')
        assert '*' in masked
    
    def test_sensitive_data_filter_dict(self):
        """测试字典脱敏"""
        filter_instance = SensitiveDataFilter()
        
        data = {
            'username': 'testuser',
            'password': 'secret123',
            'api_key': 'key123456789',
            'email': 'test@example.com',
        }
        
        masked = filter_instance.mask_dict(data)
        
        assert masked['username'] == 'testuser'  # Not sensitive
        assert masked['password'] != 'secret123'  # Masked
        assert masked['api_key'] != 'key123456789'  # Masked
        assert masked['email'] != 'test@example.com'  # Masked
    
    def test_mask_sensitive_fields(self):
        """测试通用脱敏函数"""
        data = {
            'user': 'test',
            'secret': 'my-secret-value',
            'normal_field': 'normal',
        }
        
        masked = mask_sensitive_fields(data)
        assert masked['secret'] != 'my-secret-value'
        assert masked['normal_field'] == 'normal'
    
    def test_custom_sensitive_field(self):
        """测试自定义敏感字段"""
        filter_instance = SensitiveDataFilter()
        filter_instance.add_sensitive_field('custom_field')
        
        data = {'custom_field': 'sensitive', 'other': 'normal'}
        masked = filter_instance.mask_dict(data)
        
        assert masked['custom_field'] != 'sensitive'
        assert masked['other'] == 'normal'


class TestLogMaskingIntegration:
    """日志脱敏集成测试"""
    
    def test_log_with_sensitive_data(self, caplog):
        """测试带敏感数据的日志"""
        # This would require more complex setup with actual log capture
        pass
