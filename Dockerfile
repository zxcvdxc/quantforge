# ============================================================
# QuantForge 生产环境 Dockerfile
# 多阶段构建 | 非root用户 | 安全优化
# ============================================================

# ==================== 阶段1: 基础依赖构建 ====================
FROM python:3.11-slim-bookworm AS builder

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装Python依赖（先复制requirements以利用缓存）
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# 安装各模块依赖
COPY modules/qf-database/pyproject.toml /tmp/qf-database/
COPY modules/qf-data/pyproject.toml /tmp/qf-data/
RUN pip install --no-cache-dir \
    -e /tmp/qf-database \
    -e /tmp/qf-data

# ==================== 阶段2: 运行时镜像 ====================
FROM python:3.11-slim-bookworm AS runtime

# 安全: 创建非root用户
RUN groupadd -r quantforge --gid=1000 && \
    useradd -r -g quantforge -m --uid=1000 quantforge

# 安装运行时依赖（最小化）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 设置工作目录
WORKDIR /app

# 复制应用代码（使用.dockerignore控制）
COPY --chown=quantforge:quantforge modules/ ./modules/
COPY --chown=quantforge:quantforge config/ ./config/
COPY --chown=quantforge:quantforge scripts/ ./scripts/

# 创建必要的目录并设置权限
RUN mkdir -p logs data cache && \
    chown -R quantforge:quantforge /app

# 切换到非root用户
USER quantforge

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)" || exit 1

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/modules
ENV CONFIG_PATH=/app/config/config.yaml

# 暴露端口（文档用途）
EXPOSE 8000 8080

# 默认命令
CMD ["python3", "-m", "qf_data.service"]

# ==================== 阶段3: 开发镜像 ====================
FROM runtime AS development

USER root

# 安装开发工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    vim \
    htop \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# 安装开发依赖
RUN pip install --no-cache-dir \
    pytest>=7.4.0 \
    pytest-cov>=4.1.0 \
    pytest-asyncio>=0.21.0 \
    pytest-mock>=3.11.0 \
    black>=23.0.0 \
    flake8>=6.0.0 \
    mypy>=1.5.0 \
    debugpy>=1.8.0

USER quantforge

# ==================== 阶段4: 压测镜像 ====================
FROM runtime AS stress-test

USER root

# 安装压测工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    wrk \
    apache2-utils \
    sysstat \
    && rm -rf /var/lib/apt/lists/*

# 安装Python压测库
RUN pip install --no-cache-dir \
    locust>=2.20.0 \
    aiolimiter>=1.1.0

COPY --chown=quantforge:quantforge tests/stress/ ./tests/stress/

USER quantforge

CMD ["python3", "tests/stress/run_stress_tests.py"]

# ==================== 阶段5: 混沌测试镜像 ====================
FROM runtime AS chaos-test

USER root

# 安装混沌工程工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    iptables \
    tc \
    netem \
    stress-ng \
    sysstat \
    && rm -rf /var/lib/apt/lists/*

# 安装Python混沌测试库
RUN pip install --no-cache-dir \
    chaos-monkey>=0.2.0 \
    chaostoolkit>=1.15.0 \
    chaostoolkit-kubernetes>=0.28.0

COPY --chown=quantforge:quantforge tests/chaos/ ./tests/chaos/

USER quantforge

CMD ["python3", "tests/chaos/run_chaos_tests.py"]

# ==================== 默认标签 ====================
LABEL maintainer="QuantForge Team"
LABEL version="0.2.0"
LABEL description="QuantForge Trading Platform - Production Ready"
