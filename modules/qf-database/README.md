# qf-database 数据存储模块

## 功能
MySQL + InfluxDB + Redis 统一管理

## 数据库
- MySQL 8.0: 关系数据（合约、账户、交易记录）
- InfluxDB 2.x: 时序数据（K线、Tick）
- Redis: 实时缓存

## API接口
```python
from qf_database import DatabaseManager

db = DatabaseManager()
db.save_kline(data)
```

## 测试
```bash
pytest tests/ -v --cov=qf_database
```

## 依赖
- sqlalchemy >= 2.0.0
- pymysql
- influxdb-client >= 1.36.0
- redis >= 5.0.0
- pytest
- pytest-cov
- pytest-asyncio