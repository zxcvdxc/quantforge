"""
异常定义
"""


class DataCollectionError(Exception):
    """数据采集基础异常"""
    pass


class DataSourceError(DataCollectionError):
    """数据源错误"""
    def __init__(self, message: str, source: str = None, original_error: Exception = None):
        super().__init__(message)
        self.source = source
        self.original_error = original_error


class DataFormatError(DataCollectionError):
    """数据格式错误"""
    pass


class DataCleaningError(DataCollectionError):
    """数据清洗错误"""
    pass


class ConnectionError(DataCollectionError):
    """连接错误"""
    pass


class AuthenticationError(DataCollectionError):
    """认证错误"""
    pass


class RateLimitError(DataCollectionError):
    """请求频率限制错误"""
    pass
