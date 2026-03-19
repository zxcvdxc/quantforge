# QuantForge - 模块化量化交易系统

## 项目简介
基于vn.py的模块化量化交易系统，支持100万资金动态配置，覆盖A股、期货期权套利、数字货币。

## 模块架构
```
modules/
├── qf-data/        # 数据采集
├── qf-database/    # 数据存储
├── qf-risk/        # 风险管理
├── qf-portfolio/   # 资金配置
├── qf-strategy/    # 策略实现
├── qf-execution/   # 交易执行
├── qf-backtest/    # 回测引擎
└── qf-monitor/     # 监控报警
```

## 快速开始
```bash
# 1. 克隆项目
git clone https://github.com/yourusername/quantforge.git
cd quantforge

# 2. 启动数据库
docker-compose up -d

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行测试
pytest modules/*/tests -v
```

## 开发规范
- 每个模块独立开发
- 测试覆盖率 > 80%
- 所有测试通过才算完成

## 资金配置
- 总资金: 100万人民币
- 调整频率: 月度
- 策略: 动态风险平价 + 波动率目标 + 凯利公式 + ML优化
