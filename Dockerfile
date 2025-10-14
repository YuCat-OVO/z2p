# syntax=docker/dockerfile:1.9
FROM python:3.13-alpine AS build

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.13 \
    UV_PROJECT_ENVIRONMENT=/app

# 从 uv 镜像复制 uv 可执行文件
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 同步依赖（不安装项目本身）
# 这一层会被缓存，直到 uv.lock 或 pyproject.toml 改变
RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync \
        --frozen \
        --no-dev \
        --no-install-project

# 现在从 /src 安装应用程序（不包含依赖）
# /src 不会被复制到运行时容器
COPY . /src
WORKDIR /src
RUN --mount=type=cache,target=/root/.cache \
    uv sync \
        --frozen \
        --no-dev \
        --no-editable

##########################################################################

FROM python:3.13-alpine AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PATH="/app/bin:$PATH"

# 从 build 阶段复制预构建的 /app 目录到运行时容器
COPY --from=build /app /app

EXPOSE 8001

# 使用 granian 运行 ASGI 应用程序
CMD ["granian", "--interface", "asgi", "z2p_svc.asgi:app"]