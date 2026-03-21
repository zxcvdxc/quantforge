#!/bin/bash
# QuantForge 完整部署脚本 - 一键启动OKX交易
# 使用前请填写 .env 文件中的API密钥

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   QuantForge 部署脚本 - OKX交易就绪   ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查.env文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env 文件不存在，创建模板...${NC}"
    cat > .env << 'EOF'
# ==========================================
# QuantForge 环境变量配置
# ⚠️  请填写以下配置后重新运行部署脚本
# ==========================================

# === 数据库配置 ===
MYSQL_ROOT_PASSWORD=quantforge_root_123
MYSQL_DATABASE=quantforge
MYSQL_USER=quant
MYSQL_PASSWORD=quant_123

# === InfluxDB配置 ===
INFLUXDB_ADMIN_TOKEN=quantforge_token_change_me

# === OKX API配置 (必填) ===
# 请在 https://www.okx.com/account/my-api 创建API密钥
OKX_API_KEY=your_okx_api_key_here
OKX_API_SECRET=your_okx_api_secret_here
OKX_PASSPHRASE=your_okx_passphrase_here
OKX_SERVER=TEST  # TEST或REAL，建议先用TEST测试

# === Binance API配置 (可选) ===
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true

# === Tushare配置 (A股数据，可选) ===
TUSHARE_TOKEN=your_tushare_token

# === CTP期货配置 (可选) ===
CTP_BROKER_ID=9999
CTP_USER_ID=your_simnow_id
CTP_PASSWORD=your_simnow_password
CTP_TD_ADDRESS=180.168.146.187:10101
CTP_MD_ADDRESS=180.168.146.187:10111

# === 安全配置 ===
# 加密密钥 (运行 python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 生成)
ENCRYPTION_KEY=your_encryption_key_here

# === 监控报警配置 (可选) ===
# 邮件报警
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
ALERT_EMAIL=alert@example.com

# 企业微信报警
WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_key

# 钉钉报警
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=your_token

# === 系统配置 ===
TZ=Asia/Shanghai
PYTHONUNBUFFERED=1
LOG_LEVEL=INFO
EOF
    echo -e "${YELLOW}✅ 已创建 .env 模板文件${NC}"
    echo -e "${RED}❌ 请先编辑 .env 文件，填写OKX API密钥后再运行此脚本${NC}"
    echo ""
    echo "编辑命令: nano .env 或 vim .env"
    exit 1
fi

# 检查关键配置是否已填写
if grep -q "your_okx_api_key_here" .env; then
    echo -e "${RED}❌ 错误: OKX API密钥未配置${NC}"
    echo -e "${YELLOW}请编辑 .env 文件，填写以下配置:${NC}"
    echo "  - OKX_API_KEY"
    echo "  - OKX_API_SECRET"
    echo "  - OKX_PASSPHRASE"
    echo ""
    echo "OKX API密钥获取: https://www.okx.com/account/my-api"
    exit 1
fi

echo -e "${GREEN}✅ 环境变量检查通过${NC}"
echo ""

# 功能选择
echo "请选择部署操作:"
echo "1) 完整部署 (数据库 + 服务 + OKX连接测试)"
echo "2) 仅启动数据库"
echo "3) 仅启动OKX交易服务"
echo "4) 停止所有服务"
echo "5) 查看服务状态"
echo "6) 运行OKX连接测试"
echo "7) 查看交易日志"
echo "q) 退出"
echo ""
read -p "输入选项 [1-7/q]: " choice

case $choice in
    1)
        echo -e "${BLUE}▶️  开始完整部署...${NC}"
        
        # 1. 加载环境变量
        echo -e "${BLUE}📋 加载环境变量...${NC}"
        export $(cat .env | grep -v '^#' | xargs)
        
        # 2. 检查Docker
        if ! command -v docker-compose &> /dev/null; then
            echo -e "${RED}❌ 错误: docker-compose 未安装${NC}"
            exit 1
        fi
        
        # 3. 启动数据库
        echo -e "${BLUE}🐳 启动数据库服务...${NC}"
        docker-compose -f docker-compose.yml up -d mysql influxdb redis
        
        echo -e "${BLUE}⏳ 等待数据库就绪 (15秒)...${NC}"
        sleep 15
        
        # 4. 检查数据库健康
        echo -e "${BLUE}🏥 检查数据库健康状态...${NC}"
        if docker-compose ps | grep -q "mysql.*Up"; then
            echo -e "${GREEN}  ✅ MySQL 运行中${NC}"
        else
            echo -e "${RED}  ❌ MySQL 启动失败${NC}"
            docker-compose logs mysql | tail -20
            exit 1
        fi
        
        if docker-compose ps | grep -q "influxdb.*Up"; then
            echo -e "${GREEN}  ✅ InfluxDB 运行中${NC}"
        else
            echo -e "${RED}  ❌ InfluxDB 启动失败${NC}"
            exit 1
        fi
        
        if docker-compose ps | grep -q "redis.*Up"; then
            echo -e "${GREEN}  ✅ Redis 运行中${NC}"
        else
            echo -e "${RED}  ❌ Redis 启动失败${NC}"
            exit 1
        fi
        
        # 5. 初始化数据库
        echo -e "${BLUE}🗄️  初始化数据库表...${NC}"
        python3 scripts/init_database.py || echo -e "${YELLOW}⚠️  数据库初始化可能已执行过${NC}"
        
        # 6. 安装模块
        echo -e "${BLUE}📦 安装Python模块...${NC}"
        for module in qf-data qf-database qf-security qf-reliability qf-observability qf-risk qf-portfolio qf-strategy qf-execution qf-backtest qf-monitor; do
            if [ -d "modules/$module" ]; then
                echo "  安装 $module..."
                pip3 install -e modules/$module -q 2>/dev/null || true
            fi
        done
        
        # 7. OKX连接测试
        echo -e "${BLUE}🔗 测试OKX连接...${NC}"
        python3 scripts/test_okx_connection.py || {
            echo -e "${RED}❌ OKX连接测试失败，请检查API密钥${NC}"
            exit 1
        }
        
        # 8. 启动交易服务
        echo -e "${BLUE}🚀 启动OKX交易服务...${NC}"
        docker-compose -f docker-compose.yml up -d quantforge-trading
        
        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}   ✅ 部署完成！OKX交易服务已启动   ${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo "服务访问:"
        echo "  - Grafana监控:  http://localhost:3000 (admin/admin)"
        echo "  - InfluxDB:     http://localhost:8086"
        echo "  - 交易日志:     docker-compose logs -f quantforge-trading"
        echo ""
        echo "常用命令:"
        echo "  查看状态: ./deploy.sh"
        echo "  停止服务: ./deploy.sh (选4)"
        echo "  查看日志: ./deploy.sh (选7)"
        ;;
        
    2)
        echo -e "${BLUE}🐳 启动数据库...${NC}"
        docker-compose up -d mysql influxdb redis grafana
        echo -e "${GREEN}✅ 数据库已启动${NC}"
        echo "  - MySQL:      localhost:3306"
        echo "  - InfluxDB:   localhost:8086"
        echo "  - Redis:      localhost:6379"
        echo "  - Grafana:    http://localhost:3000"
        ;;
        
    3)
        echo -e "${BLUE}🚀 启动OKX交易服务...${NC}"
        export $(cat .env | grep -v '^#' | xargs)
        docker-compose up -d quantforge-trading
        echo -e "${GREEN}✅ OKX交易服务已启动${NC}"
        echo "查看日志: docker-compose logs -f quantforge-trading"
        ;;
        
    4)
        echo -e "${BLUE}🛑 停止所有服务...${NC}"
        docker-compose down
        echo -e "${GREEN}✅ 服务已停止${NC}"
        ;;
        
    5)
        echo -e "${BLUE}📊 服务状态:${NC}"
        docker-compose ps
        ;;
        
    6)
        echo -e "${BLUE}🔗 测试OKX连接...${NC}"
        export $(cat .env | grep -v '^#' | xargs)
        python3 scripts/test_okx_connection.py
        ;;
        
    7)
        echo -e "${BLUE}📜 查看交易日志 (按 Ctrl+C 退出)...${NC}"
        docker-compose logs -f quantforge-trading
        ;;
        
    q|Q)
        echo "退出"
        exit 0
        ;;
        
    *)
        echo -e "${RED}❌ 无效选项${NC}"
        exit 1
        ;;
esac

echo ""
echo "完成！"
