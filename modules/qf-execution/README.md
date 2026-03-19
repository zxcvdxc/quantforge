# qf-execution 交易执行模块

## 功能
订单管理、智能路由、多账户对接

## 支持接口
- vn.py CTP (期货)
- vn.py XTP (A股)
- OKX API (数字货币)

## API接口
```python
from qf_execution import ExecutionEngine

engine = ExecutionEngine()
engine.send_order(order)
```

## 测试
```bash
pytest tests/ -v --cov=qf_execution
```
