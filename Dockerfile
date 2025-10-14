# 使用 uv 官方镜像
FROM ghcr.io/astral-sh/uv:latest

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装依赖和项目包
RUN uv sync --frozen --no-dev && \
    uv pip install --no-cache .

# 复制应用代码
COPY main.py ./
COPY src/ ./src/
COPY .env.example ./.env.production

# 暴露端口
EXPOSE 8001

# 启动应用
CMD ["uv", "run", "python", "main.py"]