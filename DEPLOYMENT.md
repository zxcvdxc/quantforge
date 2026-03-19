# QuantForge 部署与配置指南

## 📋 系统要求

### 硬件配置
| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 4核 | 8核+ |
| 内存 | 8GB | 16GB+ |
| 磁盘 | 100GB SSD | 500GB SSD |
| 网络 | 10Mbps | 100Mbps+ |

### 软件环境
- **操作系统**: macOS 12+ / Ubuntu 20.04+ / Windows 10+
- **Python**: 3.10+
- **Docker**: 24.0+
- **Docker Compose**: 2.20+

---

## 🚀 快速部署

### 步骤1: 克隆项目
```bash
git clone https://github.com/zxcvdxc/quantforge.git
cd quantforge
```

### 步骤2: 启动数据库
```bash
# 一键启动所有基础设施
docker-compose up -d

# 检查状态
docker-compose ps
```

### 步骤3: 安装模块
```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装基础依赖
pip install -r requirements.txt

# 安装模块 (按顺序)
pip install -e modules/qf-database
pip install -e modules/qf-data
```

### 步骤4: 配置API密钥
```bash
# 复制配置文件模板
cp config/config.example.yaml config/config.yaml

# 编辑配置文件
nano config/config.yaml  # 或 vim/code
```

### 步骤5: 运行测试
```bash
# 测试数据库模块
pytest modules/qf-database/tests -v

# 测试数据模块
pytest modules/qf-data/tests -v

# 全部测试
pytest modules/*/tests -v
```

---

## ⚙️ 详细配置

### 1. 数据库配置

#### MySQL (config.yaml)
```yaml
mysql:
  host: localhost
  port: 3306
  database: quantforge
  username: quant
  password: quant123
  pool_size: 10
```

#### InfluxDB (config.yaml)
```yaml
influxdb:
  url: http://localhost:8086
  token: your-token-here
  org: quantforge
  bucket: market_data
```

#### Redis (config.yaml)
```yaml
redis:
  host: localhost
  port: 6379
  db: 0
  password: null
```

### 2. 交易所API配置

#### OKX (数字货币)
```yaml
exchanges:
  okx:
    api_key: "your-okx-api-key"
    api_secret: "your-okx-api-secret"
    passphrase: "your-okx-passphrase"
    server: "REAL"  # 或 "TEST" 测试网
    
    # 可选：代理设置
    proxy:
      http: "http://127.0.0.1:7890"
      https: "http://127.0.0.1:7890"
```

#### Binance (数字货币)
```yaml
  binance:
    api_key: "your-binance-api-key"
    api_secret: "your-binance-api-secret"
    testnet: true  # 使用测试网
```

#### Tushare (A股)
```yaml
  tushare:
    token: "your-tushare-token"
    # 免费版有频率限制，建议购买付费版
```

#### CTP (期货)
```yaml
  ctp:
    # SimNow仿真环境
    broker_id: "9999"
    user_id: "your-simnow-id"
    password: "your-simnow-password"
    
    # 交易服务器
    td_address: "180.168.146.187:10101"
    # 行情服务器
    md_address: "180.168.146.187:10111"
    
    # 实盘环境 (需要替换)
    # td_address: " your-broker-td-address"
    # md_address: "your-broker-md-address"
```

### 3. 资金配置

```yaml
portfolio:
  # 总资金 (人民币)
  total_capital: 1000000
  
  # 风险平价基础配置
  base_allocation:
    a_share: 0.40    # A股 40%
    futures: 0.35    # 期货 35%
    crypto: 0.25     # 数字货币 25%
  
  # 波动率目标
  volatility_target: 0.15  # 15%年化波动率
  
  # 风险控制
  risk_limits:
    max_position_per_symbol: 0.20    # 单品种最大20%
    max_drawdown: 0.15               # 最大回撤15%
    daily_loss_limit: 0.05           # 日亏损上限5%
    
  # 再平衡频率
  rebalance_frequency: "1M"  # 月度
```

### 4. 日志配置

```yaml
logging:
  level: INFO  # DEBUG/INFO/WARNING/ERROR
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  
  handlers:
    file:
      filename: "logs/quantforge.log"
      max_bytes: 10485760  # 10MB
      backup_count: 5
    
    console:
      enabled: true
```

---

## 🔧 高级配置

### Docker Compose 自定义

#### 修改端口映射
```yaml
# docker-compose.yml
services:
  mysql:
    ports:
      - "3307:3306"  # 修改主机端口为3307
  
  grafana:
    ports:
      - "3001:3000"  # 修改主机端口为3001
```

#### 数据持久化路径
```yaml
services:
  mysql:
    volumes:
      - /your/custom/path/mysql:/var/lib/mysql
  
  influxdb:
    volumes:
      - /your/custom/path/influxdb:/var/lib/influxdb2
```

### 环境变量配置

创建 `.env` 文件：
```bash
# 数据库
MYSQL_ROOT_PASSWORD=your-strong-password
MYSQL_DATABASE=quantforge
MYSQL_USER=quant
MYSQL_PASSWORD=your-strong-password

# InfluxDB
INFLUXDB_ADMIN_TOKEN=your-influx-token

# 交易所API (敏感信息建议放这里)
OKX_API_KEY=xxx
OKX_API_SECRET=xxx
OKX_PASSPHRASE=xxx
```

然后在 docker-compose.yml 中使用：
```yaml
services:
  mysql:
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
```

---

## 🧪 验证部署

### 1. 检查服务状态
```bash
# 查看所有服务
docker-compose ps

# 查看日志
docker-compose logs -f mysql
docker-compose logs -f influxdb
docker-compose logs -f redis
```

### 2. 测试数据库连接
```bash
# MySQL
docker-compose exec mysql mysql -uquant -pquant123 -e "SHOW DATABASES;"

# InfluxDB
curl http://localhost:8086/health

# Redis
docker-compose exec redis redis-cli ping
```

### 3. 运行集成测试
```bash
# 测试数据流
python3 -c "
from qf_data import DataCollector
from qf_database import DatabaseManager

# 采集数据
collector = DataCollector()
data = collector.get_kline('BTC-USDT', '1m', 100)

# 存储数据
db = DatabaseManager()
db.save_kline(data)

print('✅ 数据流测试通过')
"
```

---

## 🚀 启动交易

### 方式1: 命令行启动
```bash
# 启动数据服务
python3 -m modules.qf_data.service &

# 启动数据库服务
python3 -m modules.qf_database.service &

# 启动策略
python3 strategies/main.py
```

### 方式2: 使用启动脚本
```bash
# 一键启动全部
./scripts/start_all.sh

# 或分步启动
./scripts/start_database.sh
./scripts/start_data.sh
./scripts/start_trading.sh
```

### 方式3: Docker 全流程 (推荐生产环境)
```bash
# 构建镜像
docker-compose -f docker-compose.prod.yml build

# 启动服务
docker-compose -f docker-compose.prod.yml up -d
```

---

## 📊 监控面板

### Grafana 访问
- URL: http://localhost:3000
- 用户名: admin
- 密码: admin (首次登录后修改)

### 导入预设仪表板
1. 登录 Grafana
2. 左侧菜单 → Dashboards → Import
3. 上传 `config/grafana/dashboard.json`

---

## 🔒 安全配置

### 1. 修改默认密码
```bash
# MySQL
docker-compose exec mysql mysql -uroot -p -e "ALTER USER 'quant'@'%' IDENTIFIED BY 'new-strong-password';"

# InfluxDB
# 通过 Web UI: http://localhost:8086
```

### 2. 防火墙设置
```bash
# 仅允许本地访问数据库
sudo ufw allow from 127.0.0.1 to any port 3306
sudo ufw allow from 127.0.0.1 to any port 8086
sudo ufw allow from 127.0.0.1 to any port 6379
```

### 3. API密钥安全
- 永远不要提交 `.env` 到Git
- 定期轮换API密钥
- 使用IP白名单（交易所支持）

---

## 🐛 故障排查

### 问题1: MySQL连接失败
```bash
# 检查服务状态
docker-compose ps mysql

# 查看日志
docker-compose logs mysql | tail -50

# 重置数据（谨慎）
docker-compose down -v
docker-compose up -d mysql
```

### 问题2: 数据采集超时
```bash
# 检查网络
ping api.okx.com

# 检查代理
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
```

### 问题3: 内存不足
```bash
# 限制Docker内存
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 或在docker-compose中设置
services:
  mysql:
    deploy:
      resources:
        limits:
          memory: 2G
```

---

## 📞 技术支持

遇到问题？
1. 查看日志: `docker-compose logs -f [service]`
2. 运行诊断: `python3 scripts/diagnose.py`
3. 提交Issue: https://github.com/zxcvdxc/quantforge/issues

---

**部署完成！** 开始你的量化交易之旅 🚀
