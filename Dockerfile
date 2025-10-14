# syntax=docker/dockerfile:1.9
FROM python:3.13-alpine AS build

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.13

# 从 uv 镜像复制 uv 可执行文件
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 创建虚拟环境
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制依赖文件并安装
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache \
    uv sync --frozen --no-dev --no-install-project

# 复制应用代码 (不复制 main.py)
COPY src/ ./src/
COPY .env.example ./.env.production

# 安装项目本身
RUN --mount=type=cache,target=/root/.cache \
    uv sync --frozen --no-dev --no-editable

##########################################################################

FROM python:3.13-alpine AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PATH="/opt/venv/bin:$PATH"

# 从 build 阶段复制虚拟环境和应用代码
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app

EXPOSE 8001

# 使用 granian 运行 ASGI 应用程序
CMD ["granian", "--interface", "asgi", "src.z2p_svc.asgi:app"]