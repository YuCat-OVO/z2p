"""ASGI应用入口模块。

本模块导出FastAPI应用实例，供ASGI服务器（如Granian、Uvicorn等）使用。

Example::

    # 使用Uvicorn运行
    uvicorn z2p_svc.asgi:app --host 0.0.0.0 --port 8000

    # 使用Granian运行
    granian --interface asgi z2p_svc.asgi:app
"""

from .app import app

__all__ = ["app"]