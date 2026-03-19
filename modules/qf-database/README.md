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

## 🧪 测试使用指南

### 运行所有测试
```bash
# 进入模块目录
cd modules/qf-database

# 运行所有测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ -v --cov=src --cov-report=html

# 生成XML报告（CI/CD使用）
pytest tests/ -v --cov=src --cov-report=xml
```

### 运行特定测试文件
```bash
# 测试MySQL功能
pytest tests/test_database.py::TestMySQLManager -v

# 测试InfluxDB功能
pytest tests/test_database.py::TestInfluxDBManager -v

# 测试Redis功能
pytest tests/test_database.py::TestRedisManager -v

# 测试扩展功能
pytest tests/test_extended.py -v

# 测试边界情况
pytest tests/test_final.py -v
```

### 运行特定测试用例
```bash
# 测试数据库连接
pytest tests/test_database.py::TestMySQLManager::test_connection -v

# 测试K线保存
pytest tests/test_database.py::TestInfluxDBManager::test_save_kline -v

# 测试Redis缓存
pytest tests/test_database.py::TestRedisManager::test_cache_tick -v
```

### 测试覆盖率检查
```bash
# 终端显示覆盖率
pytest tests/ -v --cov=src --cov-report=term-missing

# 生成HTML报告（浏览器打开 htmlcov/index.html）
pytest tests/ -v --cov=src --cov-report=html

# 只显示覆盖率低于80%的文件
pytest tests/ --cov=src --cov-fail-under=80
```

### 调试测试
```bash
# 失败时进入PDB调试
pytest tests/ -v --pdb

# 只运行上次失败的测试
pytest tests/ -v --lf

# 显示最慢的10个测试
pytest tests/ -v --durations=10
```

### 测试数据准备
```bash
# 确保Docker数据库已启动
docker-compose up -d mysql influxdb redis

# 等待数据库就绪
sleep 10

# 运行测试
pytest tests/ -v
```

### 测试输出示例
```
============================= test session starts =============================
platform darwin -- Python 3.10.0, pytest-7.4.0, pluggy-1.0.0
rootdir: /path/to/quantforge-modules/modules/qf-database
plugins: cov-4.1.0, asyncio-0.21.0
collected 144 items

tests/test_database.py::TestMySQLManager::test_connection PASSED         [  0%]
tests/test_database.py::TestMySQLManager::test_save_contract PASSED      [  1%]
...
tests/test_final.py::TestRedisManager::test_cache_tick PASSED            [100%]

============================= 144 passed in 15.23s ============================
```

## 测试结构
```
tests/
├── test_database.py      # 基础测试 (46个)
│   ├── TestMySQLManager      # MySQL测试
│   ├── TestInfluxDBManager   # InfluxDB测试
│   └── TestRedisManager      # Redis测试
├── test_extended.py      # 扩展测试 (62个)
└── test_final.py         # 边界测试 (36个)
```

## 依赖
```bash
pip install -r requirements.txt
# 或
pip install sqlalchemy>=2.0.0 pymysql influxdb-client>=1.36.0 redis>=5.0.0
pip install pytest pytest-cov pytest-asyncio
```

## 配置
测试前确保 `config/config.yaml` 中数据库配置正确：
```yaml
database:
  mysql:
    host: localhost
    port: 3306
    database: quantforge_test  # 测试数据库
    username: quant
    password: quant123
```
