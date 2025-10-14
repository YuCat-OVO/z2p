#!/usr/bin/env python3
"""使用 Granian 启动应用的脚本。

此脚本提供了一个便捷的方式来使用 Granian ASGI 服务器启动应用。
可以通过命令行参数自定义启动配置。

Example::

    # 使用默认配置启动
    python main.py
    
    # 自定义主机和端口
    python main.py --host 127.0.0.1 --port 8080
    
    # 使用多个 workers
    python main.py --workers 4
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from z2p_svc.config import get_settings


def main():
    """主函数：解析命令行参数并启动 Granian 服务器。"""
    settings = get_settings()
    
    parser = argparse.ArgumentParser(
        description="使用 Granian 启动 ZAI Proxy API 服务"
    )
    parser.add_argument(
        "--host",
        default=settings.host,
        help=f"服务器监听地址 (默认: {settings.host})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.port,
        help=f"服务器监听端口 (默认: {settings.port})"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=settings.workers,
        help=f"工作进程数 (默认: {settings.workers})"
    )
    parser.add_argument(
        "--interface",
        default="asgi",
        choices=["asgi", "rsgi", "wsgi"],
        help="服务器接口类型 (默认: asgi)"
    )
    parser.add_argument(
        "--log-level",
        default=settings.log_level.lower(),
        choices=["critical", "error", "warning", "info", "debug"],
        help=f"日志级别 (默认: {settings.log_level.lower()})"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用热重载（开发模式）"
    )
    
    args = parser.parse_args()
    
    # 构建 Granian 命令
    cmd_parts = [
        "granian",
        "--interface", args.interface,
        "z2p_svc.asgi:app",
        "--host", args.host,
        "--port", str(args.port),
        "--workers", str(args.workers),
        "--log-level", args.log_level,
    ]
    
    if args.reload:
        cmd_parts.append("--reload")
    
    print(f"启动命令: {' '.join(cmd_parts)}")
    print(f"服务将在 http://{args.host}:{args.port} 上运行")
    print(f"Workers: {args.workers}")
    print(f"日志级别: {args.log_level}")
    print("-" * 60)
    
    # 使用 subprocess 执行命令
    import subprocess
    try:
        subprocess.run(cmd_parts, check=True)
    except KeyboardInterrupt:
        print("\n服务已停止")
    except subprocess.CalledProcessError as e:
        print(f"启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()