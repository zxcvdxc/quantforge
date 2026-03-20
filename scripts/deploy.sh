#!/bin/bash
# ============================================================
# QuantForge 部署脚本
# 支持: 本地部署 | Docker部署 | Kubernetes部署
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认配置
ENVIRONMENT="production"
DEPLOY_TARGET="docker"
ACTION="deploy"
SKIP_TESTS=false
SKIP_BUILD=false

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ============================================================
# 帮助信息
# ============================================================
usage() {
    cat << EOF
QuantForge 部署脚本

用法: $0 [选项]

选项:
    -e, --environment    环境 (development|staging|production) [默认: production]
    -t, --target         部署目标 (docker|k8s|local) [默认: docker]
    -a, --action         操作 (deploy|stop|restart|status|logs|test) [默认: deploy]
    --skip-tests         跳过测试
    --skip-build         跳过构建
    -h, --help           显示帮助

示例:
    $0 -e production -t docker -a deploy
    $0 -e development -t local -a test
    $0 -a stop
    $0 -a status
    $0 -a logs -e production

EOF
}

# ============================================================
# 日志函数
# ============================================================
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================
# 检查依赖
# ============================================================
check_dependencies() {
    log_info "检查依赖..."
    
    local deps=("docker" "docker-compose")
    
    if [ "$DEPLOY_TARGET" = "k8s" ]; then
        deps+=("kubectl" "helm")
    fi
    
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            log_error "未找到依赖: $dep"
            exit 1
        fi
    done
    
    log_success "依赖检查通过"
}

# ============================================================
# 初始化密钥
# ============================================================
init_secrets() {
    log_info "初始化密钥..."
    
    mkdir -p "$PROJECT_ROOT/secrets"
    
    # 生成随机密码
    generate_password() {
        openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 24
    }
    
    # 检查密钥文件是否存在
    if [ ! -f "$PROJECT_ROOT/secrets/mysql_root_password.txt" ]; then
        echo "$(generate_password)" > "$PROJECT_ROOT/secrets/mysql_root_password.txt"
        log_info "生成 MySQL root 密码"
    fi
    
    if [ ! -f "$PROJECT_ROOT/secrets/mysql_password.txt" ]; then
        echo "$(generate_password)" > "$PROJECT_ROOT/secrets/mysql_password.txt"
        log_info "生成 MySQL 用户密码"
    fi
    
    if [ ! -f "$PROJECT_ROOT/secrets/influxdb_user.txt" ]; then
        echo "admin" > "$PROJECT_ROOT/secrets/influxdb_user.txt"
        log_info "设置 InfluxDB 用户名"
    fi
    
    if [ ! -f "$PROJECT_ROOT/secrets/influxdb_password.txt" ]; then
        echo "$(generate_password)" > "$PROJECT_ROOT/secrets/influxdb_password.txt"
        log_info "生成 InfluxDB 密码"
    fi
    
    if [ ! -f "$PROJECT_ROOT/secrets/influxdb_token.txt" ]; then
        echo "$(openssl rand -hex 32)" > "$PROJECT_ROOT/secrets/influxdb_token.txt"
        log_info "生成 InfluxDB Token"
    fi
    
    if [ ! -f "$PROJECT_ROOT/secrets/grafana_password.txt" ]; then
        echo "$(generate_password)" > "$PROJECT_ROOT/secrets/grafana_password.txt"
        log_info "生成 Grafana 密码"
    fi
    
    chmod 600 "$PROJECT_ROOT/secrets/"*.txt
    log_success "密钥初始化完成"
}

# ============================================================
# 运行测试
# ============================================================
run_tests() {
    if [ "$SKIP_TESTS" = true ]; then
        log_warning "跳过测试"
        return
    fi
    
    log_info "运行测试套件..."
    
    cd "$PROJECT_ROOT"
    
    # 单元测试
    log_info "运行单元测试..."
    python3 -m pytest modules/*/tests/ -v --tb=short || {
        log_error "单元测试失败"
        exit 1
    }
    
    # 集成测试
    log_info "运行集成测试..."
    python3 -m pytest tests/ -v --tb=short || {
        log_warning "部分集成测试失败"
    }
    
    log_success "测试完成"
}

# ============================================================
# 构建镜像
# ============================================================
build_images() {
    if [ "$SKIP_BUILD" = true ]; then
        log_warning "跳过构建"
        return
    fi
    
    log_info "构建 Docker 镜像..."
    
    cd "$PROJECT_ROOT"
    
    # 构建生产镜像
    docker build \
        --target runtime \
        -t quantforge:latest \
        -t quantforge:$(git describe --tags --always 2>/dev/null || echo "latest") \
        .
    
    # 构建压测镜像
    docker build \
        --target stress-test \
        -t quantforge:stress-test \
        .
    
    # 构建混沌测试镜像
    docker build \
        --target chaos-test \
        -t quantforge:chaos-test \
        .
    
    log_success "镜像构建完成"
}

# ============================================================
# Docker 部署
# ============================================================
deploy_docker() {
    log_info "部署到 Docker (环境: $ENVIRONMENT)..."
    
    cd "$PROJECT_ROOT"
    
    # 选择 compose 文件
    if [ "$ENVIRONMENT" = "production" ]; then
        COMPOSE_FILE="docker-compose.prod.yml"
    else
        COMPOSE_FILE="docker-compose.yml"
    fi
    
    # 检查 compose 文件是否存在
    if [ ! -f "$COMPOSE_FILE" ]; then
        log_error "Compose 文件不存在: $COMPOSE_FILE"
        exit 1
    fi
    
    # 启动服务
    log_info "启动服务..."
    docker-compose -f "$COMPOSE_FILE" up -d
    
    # 等待服务就绪
    log_info "等待服务就绪..."
    sleep 10
    
    # 检查健康状态
    check_health
    
    log_success "Docker 部署完成"
}

# ============================================================
# 停止服务
# ============================================================
stop_services() {
    log_info "停止服务..."
    
    cd "$PROJECT_ROOT"
    
    if [ "$ENVIRONMENT" = "production" ]; then
        docker-compose -f docker-compose.prod.yml down
    else
        docker-compose down
    fi
    
    log_success "服务已停止"
}

# ============================================================
# 重启服务
# ============================================================
restart_services() {
    log_info "重启服务..."
    stop_services
    sleep 2
    deploy_docker
}

# ============================================================
# 查看状态
# ============================================================
show_status() {
    log_info "服务状态:"
    
    cd "$PROJECT_ROOT"
    
    if [ "$ENVIRONMENT" = "production" ]; then
        docker-compose -f docker-compose.prod.yml ps
    else
        docker-compose ps
    fi
    
    echo ""
    log_info "资源使用:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
}

# ============================================================
# 查看日志
# ============================================================
show_logs() {
    log_info "查看日志..."
    
    cd "$PROJECT_ROOT"
    
    if [ "$ENVIRONMENT" = "production" ]; then
        docker-compose -f docker-compose.prod.yml logs -f --tail=100
    else
        docker-compose logs -f --tail=100
    fi
}

# ============================================================
# 健康检查
# ============================================================
check_health() {
    log_info "健康检查..."
    
    local services=("qf-mysql" "qf-influxdb" "qf-redis" "qf-data")
    local all_healthy=true
    
    for service in "${services[@]}"; do
        if docker ps --format "{{.Names}}" | grep -q "^${service}$"; then
            local status=$(docker inspect --format='{{.State.Health.Status}}' "$service" 2>/dev/null || echo "unknown")
            
            if [ "$status" = "healthy" ]; then
                log_success "$service: 健康"
            else
                log_warning "$service: 状态 $status"
                all_healthy=false
            fi
        else
            log_error "$service: 未运行"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = true ]; then
        log_success "所有服务健康"
    else
        log_warning "部分服务未就绪"
    fi
}

# ============================================================
# 运行混沌测试
# ============================================================
run_chaos_tests() {
    log_info "运行混沌测试..."
    
    cd "$PROJECT_ROOT"
    
    # 启动混沌测试容器
    docker-compose -f docker-compose.prod.yml --profile chaos up -d chaos-monkey
    
    # 运行测试
    docker exec qf-chaos-monkey python3 tests/chaos/chaos_monkey.py
    
    log_success "混沌测试完成"
}

# ============================================================
# 运行压力测试
# ============================================================
run_stress_tests() {
    log_info "运行压力测试..."
    
    cd "$PROJECT_ROOT"
    
    # 确保服务已启动
    docker-compose -f docker-compose.prod.yml up -d qf-data
    
    # 启动压测
    docker-compose -f docker-compose.prod.yml --profile stress up -d stress-test
    
    # 等待并查看结果
    log_info "压力测试中，查看日志..."
    docker logs -f qf-stress-test
    
    log_success "压力测试完成"
}

# ============================================================
# 备份数据
# ============================================================
backup_data() {
    log_info "备份数据..."
    
    local backup_dir="$PROJECT_ROOT/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    # 备份 MySQL
    docker exec qf-mysql mysqldump -uquant -pquant123 quantforge > "$backup_dir/mysql_backup.sql" 2>/dev/null || {
        log_warning "MySQL 备份失败"
    }
    
    # 备份 InfluxDB
    docker exec qf-influxdb influx backup /tmp/backup > /dev/null 2>&1 || {
        log_warning "InfluxDB 备份失败"
    }
    
    log_success "备份完成: $backup_dir"
}

# ============================================================
# 清理资源
# ============================================================
cleanup() {
    log_info "清理资源..."
    
    # 删除未使用的镜像
    docker image prune -f
    
    # 删除未使用的卷
    docker volume prune -f
    
    # 删除构建缓存
    docker builder prune -f
    
    log_success "清理完成"
}

# ============================================================
# 主函数
# ============================================================
main() {
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -e|--environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -t|--target)
                DEPLOY_TARGET="$2"
                shift 2
                ;;
            -a|--action)
                ACTION="$2"
                shift 2
                ;;
            --skip-tests)
                SKIP_TESTS=true
                shift
                ;;
            --skip-build)
                SKIP_BUILD=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                usage
                exit 1
                ;;
        esac
    done
    
    # 验证参数
    if [[ ! "$ENVIRONMENT" =~ ^(development|staging|production)$ ]]; then
        log_error "无效的环境: $ENVIRONMENT"
        exit 1
    fi
    
    if [[ ! "$DEPLOY_TARGET" =~ ^(docker|k8s|local)$ ]]; then
        log_error "无效的部署目标: $DEPLOY_TARGET"
        exit 1
    fi
    
    log_info "======================================"
    log_info "QuantForge 部署"
    log_info "环境: $ENVIRONMENT"
    log_info "目标: $DEPLOY_TARGET"
    log_info "操作: $ACTION"
    log_info "======================================"
    
    # 执行操作
    case $ACTION in
        deploy)
            check_dependencies
            init_secrets
            run_tests
            build_images
            deploy_docker
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        test)
            run_tests
            ;;
        chaos)
            run_chaos_tests
            ;;
        stress)
            run_stress_tests
            ;;
        backup)
            backup_data
            ;;
        cleanup)
            cleanup
            ;;
        *)
            log_error "无效的操作: $ACTION"
            usage
            exit 1
            ;;
    esac
    
    log_info "======================================"
    log_success "完成!"
    log_info "======================================"
}

# 运行主函数
main "$@"
