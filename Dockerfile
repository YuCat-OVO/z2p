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

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN uv venv /app

RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync \
        --frozen \
        --no-dev \
        --no-install-project

COPY . /src
WORKDIR /src
RUN --mount=type=cache,target=/root/.cache \
    uv pip install \
        --python /app/bin/python \
        --no-deps \
        .

FROM python:3.13-alpine AS runtime

SHELL ["sh", "-exc"]

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PATH="/app/bin:$PATH"

COPY --from=build /app /app

COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/

EXPOSE 8001

RUN <<EOT
python -V
python -Im site
python -Ic 'import z2p_svc'
EOT

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["granian"]