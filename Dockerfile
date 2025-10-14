FROM docker.io/library/python:3.13-alpine

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

# 安装 uv
RUN pip install --no-cache-dir uv

# 创建虚拟环境
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制依赖文件并安装
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 复制应用代码
COPY main.py .
COPY src/ ./src/
COPY .env.example ./.env.production

EXPOSE 8001

CMD ["python", "main.py"]