# 构建阶段
FROM ghcr.io/astral-sh/uv:python3.13-alpine AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 创建虚拟环境
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制依赖文件并安装
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev && \
    uv pip install --no-cache --system .


# 最终镜像
FROM ghcr.io/astral-sh/uv:python3.13-alpine

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制应用代码
COPY main.py .
COPY src/ ./src/
COPY .env.example ./.env.production

EXPOSE 8001

CMD ["python", "main.py"]