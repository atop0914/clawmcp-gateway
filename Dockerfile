# ClawMCP Gateway Dockerfile

FROM python:3.12-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制配置文件
COPY configs/ ./configs/
COPY gateway.py ./
COPY templates/ ./templates/
COPY static/ ./static/

# 安装 Python 依赖
RUN pip install --no-cache-dir aiohttp httpx pyyaml watchdog

# 安装 minimax_mcp
RUN pip install --no-cache-dir minimax-coding-plan-mcp

# 暴露端口
EXPOSE 8080

# 启动
CMD ["python", "gateway.py"]
