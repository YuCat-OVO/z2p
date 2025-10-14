#!/bin/sh
set -e

# 默认配置
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8001"
DEFAULT_WORKERS="1"
DEFAULT_INTERFACE="asgi"
DEFAULT_LOG_LEVEL="info"

# 使用环境变量或默认值
HOST="${HOST:-$DEFAULT_HOST}"
PORT="${PORT:-$DEFAULT_PORT}"
WORKERS="${WORKERS:-$DEFAULT_WORKERS}"
INTERFACE="${INTERFACE:-$DEFAULT_INTERFACE}"
LOG_LEVEL="${LOG_LEVEL:-$DEFAULT_LOG_LEVEL}"

# 打印启动信息
echo "=================================================="
echo "Starting Z2P Service with Granian"
echo "=================================================="
echo "Environment: ${APP_ENV:-production}"
echo "Host: ${HOST}"
echo "Port: ${PORT}"
echo "Workers: ${WORKERS}"
echo "Interface: ${INTERFACE}"
echo "Log Level: ${LOG_LEVEL}"
echo "=================================================="

# 如果第一个参数不是以 - 开头，则认为是自定义命令
if [ "${1#-}" != "$1" ]; then
    set -- granian "$@"
fi

# 如果命令是 granian，使用配置的参数启动
if [ "$1" = 'granian' ]; then
    exec granian \
        --interface "$INTERFACE" \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        --log-level "$LOG_LEVEL" \
        z2p_svc.asgi:app
fi

# 否则执行传入的命令
exec "$@"