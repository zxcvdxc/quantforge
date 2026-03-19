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

## 🧪 测试使用指南

### 运行所有测试
```bash
# 进入模块目录
cd modules/qf-execution

# 运行所有测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ -v --cov=src --cov-report=html
```

### 运行特定测试
```bash
# 测试发送订单
pytest tests/test_execution.py::TestOrderManager::test_send_order -v

# 测试撤单
pytest tests/test_execution.py::TestOrderManager::test_cancel_order -v

# 测试智能路由
pytest tests/test_execution.py::TestExecutionEngine::test_smart_routing -v
```

### 测试用例清单

| 测试类 | 测试用例 | 说明 |
|--------|---------|------|
| TestOrderManager | test_send_order | 订单发送 |
| TestOrderManager | test_cancel_order | 撤单功能 |
| TestOrderManager | test_order_status | 订单状态更新 |
| TestOrderManager | test_partial_fill | 部分成交 |
| TestExecutionEngine | test_smart_routing | 智能路由 |
| TestExecutionEngine | test_best_price | 最优价格选择 |
| TestExecutionEngine | test_order_split | 大单拆分 |
| TestMultiAccount | test_account_switch | 多账户切换 |

## 依赖
- vnpy
- requests
- asyncio
- pytest
- pytest-asyncio
- pytest-cov
