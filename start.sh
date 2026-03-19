#!/bin/bash
# QuantForge 一键启动脚本

set -e  # 遇到错误退出

echo "🚀 QuantForge 启动脚本"
echo "======================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查命令
command -v docker-compose >/dev/null 2>&1 || { echo -e "${RED}错误: docker-compose 未安装${NC}"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo -e "${RED}错误: python3 未安装${NC}"; exit 1; }

# 函数定义
check_service() {
    if docker-compose ps | grep -q "$1.*Up"; then
        echo -e "${GREEN}✅ $1 运行中${NC}"
        return 0
    else
        echo -e "${RED}❌ $1 未运行${NC}"
        return 1
    fi
}

# 菜单
echo ""
echo "请选择操作:"
echo "1) 完整启动 (数据库 + 服务)"
echo "2) 仅启动数据库"
echo "3) 停止所有服务"
echo "4) 重启服务"
echo "5) 查看状态"
echo "6) 运行测试"
echo "7) 查看日志"
echo "8) 初始化数据库"
echo "q) 退出"
echo ""
read -p "输入选项 [1-8/q]: " choice

case $choice in
    1)
        echo -e "${YELLOW}▶️  启动完整服务...${NC}"
        
        # 启动数据库
        echo "📦 启动数据库..."
        docker-compose up -d
        
        echo "⏳ 等待数据库就绪 (10秒)..."
        sleep 10
        
        # 检查数据库状态
        check_service mysql || exit 1
        check_service influxdb || exit 1
        check_service redis || exit 1
        
        echo ""
        echo -e "${GREEN}✅ 所有服务已启动${NC}"
        echo ""
        echo "访问地址:"
        echo "  - Grafana: http://localhost:3000"
        echo "  - InfluxDB: http://localhost:8086"
        echo ""
        ;;
        
    2)
        echo -e "${YELLOW}▶️  仅启动数据库...${NC}"
        docker-compose up -d mysql influxdb redis
        echo "⏳ 等待就绪..."
        sleep 10
        check_service mysql
        check_service influxdb
        check_service redis
        ;;
        
    3)
        echo -e "${YELLOW}🛑 停止所有服务...${NC}"
        docker-compose down
        echo -e "${GREEN}✅ 已停止${NC}"
        ;;
        
    4)
        echo -e "${YELLOW}🔄 重启服务...${NC}"
        docker-compose restart
        echo -e "${GREEN}✅ 已重启${NC}"
        ;;
        
    5)
        echo -e "${YELLOW}📊 服务状态:${NC}"
        docker-compose ps
        echo ""
        check_service mysql
        check_service influxdb
        check_service redis
        check_service grafana
        ;;
        
    6)
        echo -e "${YELLOW}🧪 运行测试...${NC}"
        if [ -d "modules" ]; then
            pytest modules/*/tests -v --tb=short
        else
            echo -e "${RED}错误: 未找到测试目录${NC}"
        fi
        ;;
        
    7)
        echo "查看日志 (按 Ctrl+C 退出)..."
        docker-compose logs -f
        ;;
        
    8)
        echo -e "${YELLOW}🗄️  初始化数据库...${NC}"
        
        # 检查配置文件
        if [ ! -f "config/config.yaml" ]; then
            echo -e "${YELLOW}⚠️  配置文件不存在，复制模板...${NC}"
            cp config/config.example.yaml config/config.yaml
            echo -e "${RED}请先编辑 config/config.yaml 配置文件${NC}"
            exit 1
        fi
        
        # 初始化数据库表
        python3 -c "
import sys
sys.path.insert(0, '.')
from modules.qf_database.src.qf_database import DatabaseManager
print('初始化数据库...')
db = DatabaseManager()
# 自动创建表
print('✅ 数据库初始化完成')
"
        ;;
        
    q|Q)
        echo "退出"
        exit 0
        ;;
        
    *)
        echo -e "${RED}无效选项${NC}"
        exit 1
        ;;
esac

echo ""
echo "完成！"
