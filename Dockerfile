# syntax=docker/dockerfile:1.9
FROM python:3.13-alpine AS build

SHELL ["sh", "-exc"]

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

# 创建虚拟环境
RUN uv venv /app

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
COPY . /src
WORKDIR /src
RUN --mount=type=cache,target=/root/.cache \
    uv pip install \
        --python /app/bin/python \
        --no-deps \
        .

##########################################################################

FROM python:3.13-alpine AS runtime

SHELL ["sh", "-exc"]

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PATH="/app/bin:$PATH"

# 从 build 阶段复制预构建的 /app 目录到运行时容器
COPY --from=build /app /app

# 复制 entrypoint 脚本
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8001

# 可选：运行冒烟测试验证应用可以被导入
RUN <<EOT
python -V
python -Im site
python -Ic 'import z2p_svc'
EOT

# 使用 entrypoint 脚本启动服务
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["granian"]