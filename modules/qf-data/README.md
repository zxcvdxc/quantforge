# qf-data 数据采集模块

## 功能
多源数据接入、清洗、标准化处理

## 支持数据源
- A股: Tushare, AKShare
- 期货: CTP行情
- 数字货币: OKX, Binance

## API接口
```python
from qf_data import DataCollector

collector = DataCollector()
data = collector.get_kline(symbol="BTC-USDT", interval="1m", limit=1000)
```

## 安装
```bash
pip install -e .
```

## 测试
```bash
pytest tests/ -v --cov=qf_data --cov-report=html
```

## 依赖
- requests
- aiohttp
- websockets
- pandas
- numpy
