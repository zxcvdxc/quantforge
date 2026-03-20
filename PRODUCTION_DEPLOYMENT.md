# ============================================================
# QuantForge 生产部署文档
# v2.0 - 生产就绪版本
# ============================================================

## 📋 目录

1. [快速开始](#快速开始)
2. [系统架构](#系统架构)
3. [部署要求](#部署要求)
4. [部署步骤](#部署步骤)
5. [混沌测试](#混沌测试)
6. [压力测试](#压力测试)
7. [监控告警](#监控告警)
8. [故障排查](#故障排查)
9. [安全最佳实践](#安全最佳实践)

---

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/zxcvdxc/quantforge.git
cd quantforge

# 2. 一键部署（生产环境）
./scripts/deploy.sh -e production -a deploy

# 3. 验证部署
./scripts/deploy.sh -e production -a status
```

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         QuantForge 系统架构                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │  qf-data    │  │qf-strategy  │  │qf-execution │  │ qf-risk │ │
│  │  数据采集    │  │  策略引擎    │  │  交易执行    │  │ 风控模块 │ │
│  │  :8000      │  │  :8001      │  │  :8002      │  │ :8003   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └────┬────┘ │
│         └─────────────────┴─────────────────┴──────────────┘     │
│                              │                                   │
│                    ┌─────────┴─────────┐                        │
│                    │   Redis Cluster   │                        │
│                    │   (缓存/消息队列)  │                        │
│                    └───────────────────┘                        │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   数据存储层                              │   │
│  │  ┌──────────┐  ┌──────────────┐  ┌────────────────┐    │   │
│  │  │  MySQL   │  │   InfluxDB   │  │  Vault (密钥)   │    │   │
│  │  │ 业务数据  │  │  时序数据     │  │                │    │   │
│  │  │ :3306    │  │   :8086      │  │    :8200       │    │   │
│  │  └──────────┘  └──────────────┘  └────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   监控告警层                              │   │
│  │  ┌──────────┐  ┌──────────────┐  ┌────────────────┐    │   │
│  │  │ Grafana  │  │  Prometheus  │  │   AlertManager │    │   │
│  │  │ :3000    │  │   :9090      │  │                │    │   │
│  │  └──────────┘  └──────────────┘  └────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   混沌测试层                              │   │
│  │  ┌──────────┐  ┌──────────────┐  ┌────────────────┐    │   │
│  │  │Chaos Mon.│  │  Stress Test │  │   Locust       │    │   │
│  │  └──────────┘  └──────────────┘  └────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 部署要求

### 硬件配置

| 环境 | CPU | 内存 | 磁盘 | 网络 |
|------|-----|------|------|------|
| 开发 | 4核 | 8GB | 100GB SSD | 10Mbps |
| 测试 | 8核 | 16GB | 200GB SSD | 50Mbps |
| 生产 | 16核+ | 32GB+ | 500GB SSD+ | 100Mbps+ |

### 软件依赖

- Docker 24.0+
- Docker Compose 2.20+
- Python 3.11+
- Git

### 网络要求

- 开放端口: 3000(Grafana), 3306(MySQL), 8086(InfluxDB), 8000-8003(App)
- 访问交易所API: OKX, Binance, Tushare等

---

## 部署步骤

### 1. 环境准备

```bash
# 创建项目目录
mkdir -p /opt/quantforge
cd /opt/quantforge

# 克隆代码
git clone https://github.com/zxcvdxc/quantforge.git .

# 设置权限
chmod +x scripts/*.sh
```

### 2. 配置环境变量

创建 `.env` 文件:

```bash
# 环境
ENVIRONMENT=production

# 数据库密码（部署脚本自动生成）
# 或从Vault获取
VAULT_ADDR=http://localhost:8200
VAULT_TOKEN=your-vault-token

# 交易所API密钥（从Vault或环境变量注入）
OKX_API_KEY=${OKX_API_KEY}
OKX_API_SECRET=${OKX_API_SECRET}
OKX_PASSPHRASE=${OKX_PASSPHRASE}

BINANCE_API_KEY=${BINANCE_API_KEY}
BINANCE_API_SECRET=${BINANCE_API_SECRET}

# 监控告警
ALERT_EMAIL_ENABLED=true
SMTP_SERVER=smtp.gmail.com
SMTP_USERNAME=alerts@yourdomain.com
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
```

### 3. 密钥管理

#### 选项A: 使用Vault（推荐生产环境）

```bash
# 初始化Vault
vault operator init

# 启用KV引擎
vault secrets enable -path=secret kv-v2

# 写入密钥
vault kv put secret/quantforge/mysql password=$(openssl rand -base64 32)
vault kv put secret/quantforge/exchanges/okx \
    api_key=$OKX_API_KEY \
    api_secret=$OKX_API_SECRET \
    passphrase=$OKX_PASSPHRASE
```

#### 选项B: 使用本地密钥文件（开发/测试）

```bash
# 自动生成密钥
./scripts/deploy.sh -e production -a init-secrets
```

### 4. 构建和部署

```bash
# 完整部署（测试+构建+部署）
./scripts/deploy.sh -e production -a deploy

# 仅构建镜像
./scripts/deploy.sh --skip-tests -a deploy

# 使用预构建镜像
export SKIP_BUILD=true
./scripts/deploy.sh -a deploy
```

### 5. 验证部署

```bash
# 检查服务状态
./scripts/deploy.sh -a status

# 健康检查
curl http://localhost:8000/health
curl http://localhost:8001/health

# 查看日志
./scripts/deploy.sh -a logs
```

---

## 混沌测试

### 运行混沌测试

```bash
# 启动所有服务
./scripts/deploy.sh -e production -a deploy

# 运行混沌测试（默认运行1小时）
./scripts/deploy.sh -a chaos

# 或手动运行
docker-compose -f docker-compose.prod.yml --profile chaos up -d chaos-monkey
```

### 混沌测试场景

| 测试类型 | 描述 | 频率 |
|---------|------|------|
| 网络延迟 | 注入50-500ms网络延迟 | 每5分钟 |
| 丢包 | 注入5-20%丢包率 | 每10分钟 |
| 服务Kill | 随机杀死一个服务容器 | 每15分钟 |
| CPU压力 | 施加80% CPU负载 | 每20分钟 |
| 内存压力 | 施加90%内存压力 | 每25分钟 |
| 数据库故障 | 重启/暂停数据库 | 每30分钟 |

### 查看混沌测试报告

```bash
# 查看实时日志
docker logs -f qf-chaos-monkey

# 查看报告
docker exec qf-chaos-monkey cat chaos_report_*.json
```

### 预期结果

- **恢复成功率** > 99%
- **平均恢复时间** < 30秒
- **数据一致性** 100%

---

## 压力测试

### 运行压力测试

```bash
# 运行所有压力测试
./scripts/deploy.sh -a stress

# 或手动配置运行
docker-compose -f docker-compose.prod.yml --profile stress up stress-test
```

### 测试场景配置

```bash
# 订单压力测试: 10万订单/秒
export ORDER_RPS=100000
export ORDER_DURATION=300  # 5分钟

# K线回放: 100万条数据
export KLINE_COUNT=1000000

# 内存泄漏测试: 24小时
export MEMORY_TEST_HOURS=24

# 稳定性测试: 7天
export STABILITY_DAYS=7
```

### 性能基准

| 指标 | 目标 | 警告阈值 | 临界阈值 |
|------|------|---------|---------|
| 订单吞吐量 | 100,000/s | 80,000/s | 60,000/s |
| 平均延迟 | < 50ms | 100ms | 500ms |
| P99延迟 | < 100ms | 200ms | 1000ms |
| 错误率 | < 0.01% | 0.1% | 1% |
| 内存泄漏 | 0 MB/h | 50 MB/h | 100 MB/h |
| CPU使用 | < 70% | 80% | 90% |

### 查看压力测试报告

```bash
docker exec qf-stress-test cat stress_report_*.json | jq .
```

---

## 监控告警

### 访问监控面板

| 服务 | URL | 默认凭证 |
|------|-----|---------|
| Grafana | http://localhost:3000 | admin/(自动生成) |
| Prometheus | http://localhost:9090 | - |

### 关键指标监控

```promql
# 订单处理速率
rate(orders_processed_total[1m])

# 平均延迟
histogram_quantile(0.99, rate(order_latency_bucket[5m]))

# 错误率
rate(orders_failed_total[5m]) / rate(orders_total[5m])

# 内存使用
process_resident_memory_bytes / 1024 / 1024

# CPU使用
rate(process_cpu_seconds_total[5m]) * 100
```

### 告警规则

```yaml
groups:
  - name: quantforge
    rules:
      - alert: HighErrorRate
        expr: rate(orders_failed_total[5m]) / rate(orders_total[5m]) > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "高错误率: {{ $value }}"
          
      - alert: HighLatency
        expr: histogram_quantile(0.99, rate(order_latency_bucket[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
          
      - alert: MemoryLeak
        expr: rate(process_resident_memory_bytes[1h]) > 104857600
        for: 1h
        labels:
          severity: warning
```

---

## 故障排查

### 常见问题

#### 1. 服务启动失败

```bash
# 检查日志
docker logs qf-data
docker logs qf-mysql

# 检查资源
docker stats --no-stream

# 检查端口占用
netstat -tlnp | grep 8000
```

#### 2. 数据库连接失败

```bash
# 检查MySQL状态
docker-compose exec mysql mysqladmin -uquant -p ping

# 检查网络
docker network ls
docker network inspect quantforge_qf-network
```

#### 3. 性能问题

```bash
# 查看性能指标
curl http://localhost:8000/metrics

# 分析火焰图
py-spy record -o profile.svg --pid $(pgrep -f qf-data)

# 内存分析
python -m memory_profiler app.py
```

### 日志分析

```bash
# 聚合日志
docker-compose logs -f --tail=100 | grep ERROR

# 按服务查看
docker-compose logs -f qf-data
docker-compose logs -f qf-strategy

# 导出日志
docker logs qf-data > qf-data.log 2>&1
```

---

## 安全最佳实践

### 1. 密钥管理

- ✅ 使用Vault管理所有密钥
- ✅ 定期轮换API密钥(90天)
- ✅ 启用数据库动态凭证
- ❌ 不要将密钥提交到Git
- ❌ 不要在日志中打印密钥

### 2. 网络安全

```bash
# 配置防火墙
sudo ufw allow from 127.0.0.1 to any port 3306
sudo ufw allow from 127.0.0.1 to any port 8086
sudo ufw allow from 127.0.0.1 to any port 6379

# 启用SSL
# 在config/environments/production.yaml中配置
```

### 3. 容器安全

- 使用非root用户运行容器
- 最小化镜像（多阶段构建）
- 定期扫描漏洞

```bash
# 扫描镜像漏洞
docker scan quantforge:latest
trivy image quantforge:latest
```

### 4. 审计日志

```bash
# 启用审计
docker-compose exec mysql mysql -e "SET GLOBAL general_log = 'ON';"

# 查看审计日志
tail -f /var/log/quantforge/audit.log
```

---

## 维护操作

### 备份

```bash
# 手动备份
./scripts/deploy.sh -a backup

# 自动备份 (添加到crontab)
0 2 * * * /opt/quantforge/scripts/deploy.sh -a backup
```

### 更新

```bash
# 拉取最新代码
git pull origin main

# 重新部署
./scripts/deploy.sh -e production -a deploy

# 零停机更新
docker-compose -f docker-compose.prod.yml up -d --no-deps --build qf-data
```

### 扩容

```bash
# 垂直扩容 (增加资源限制)
# 编辑 docker-compose.prod.yml

deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 8G

# 水平扩容 (多实例)
docker-compose -f docker-compose.prod.yml up -d --scale qf-data=3
```

---

## 附录

### 环境变量参考

| 变量 | 描述 | 必需 |
|------|------|------|
| ENVIRONMENT | 环境 (dev/staging/prod) | 是 |
| VAULT_ADDR | Vault地址 | 否 |
| VAULT_TOKEN | Vault Token | 否 |
| MYSQL_HOST | MySQL主机 | 否 |
| INFLUXDB_URL | InfluxDB地址 | 否 |
| OKX_API_KEY | OKX API Key | 否 |
| LOG_LEVEL | 日志级别 | 否 |

### 端口映射

| 服务 | 内部端口 | 外部端口 |
|------|---------|---------|
| qf-data | 8000 | 8000 |
| qf-strategy | 8000 | 8001 |
| qf-execution | 8000 | 8002 |
| qf-risk | 8000 | 8003 |
| MySQL | 3306 | 3306 |
| InfluxDB | 8086 | 8086 |
| Redis | 6379 | 6379 |
| Grafana | 3000 | 3000 |
| Prometheus | 9090 | 9090 |

### 支持

- 📧 Email: support@quantforge.io
- 💬 Telegram: @quantforge_support
- 🐛 Issues: https://github.com/zxcvdxc/quantforge/issues

---

**部署完成！** 开始你的量化交易之旅 🚀
