FROM python:3.11-slim

# 安装基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制程序
COPY fnos-pack-web.py .

# 创建目录
RUN mkdir -p /data/fnpack /data/output /data/cache

# 环境变量
ENV FNPACK_PATH=/data/fnpack/fnpack
ENV OUTPUT_ROOT=/data/output
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

# 启动
CMD ["streamlit", "run", "fnos-pack-web.py", "--server.port=8501", "--server.address=0.0.0.0"]