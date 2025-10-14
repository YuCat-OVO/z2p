FROM ghcr.io/astral-sh/uv:latest

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY main.py ./
COPY src/ ./src/
COPY .env.example ./.env.production

# 安装项目依赖
RUN uv sync --frozen --no-dev

# 暴露端口
EXPOSE 8001

# 设置生产环境
ENV APP_ENV=production

# 使用 uv run 启动应用
CMD ["uv", "run", "python", "main.py", "--host", "0.0.0.0", "--port", "8001"]