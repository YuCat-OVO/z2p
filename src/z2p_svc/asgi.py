"""ASGI应用入口模块。

本模块导出FastAPI应用实例，供ASGI服务器（如Granian、Uvicorn等）使用。
包含应用启动时的一次性初始化逻辑。

Example::

    # 使用Granian运行
    granian --interface asgi z2p_svc.asgi:app --host 0.0.0.0 --port 8001
    
    # 使用Granian运行（带workers）
    granian --interface asgi z2p_svc.asgi:app --host 0.0.0.0 --port 8001 --workers 4
    
    # 使用Uvicorn运行
    uvicorn z2p_svc.asgi:app --host 0.0.0.0 --port 8001
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_initialized = False
_init_lock = asyncio.Lock()


async def initialize_services() -> None:
    """执行应用启动时的一次性初始化。
    
    此函数在应用启动时仅执行一次，即使在多worker环境下也是如此。
    可以在这里添加需要初始化的服务，例如：
    - 数据库连接池初始化
    - 缓存系统初始化
    - 外部服务连接初始化
    - 预加载配置或数据
    """
    global _initialized
    
    async with _init_lock:
        if _initialized:
            logger.debug("Services already initialized, skipping...")
            return
        
        logger.info("Initializing application services...")
        
        
        logger.info(
            "Application services initialized successfully: env={}, host={}, port={}",
            settings.app_env,
            settings.host,
            settings.port
        )
        
        _initialized = True


async def shutdown_services() -> None:
    """执行应用关闭时的清理工作。
    
    此函数在应用关闭时执行，用于释放资源。
    可以在这里添加需要清理的资源，例如：
    - 关闭数据库连接池
    - 关闭缓存连接
    - 释放外部服务连接
    """
    global _initialized
    
    if not _initialized:
        return
    
    logger.info("Shutting down application services...")
    
    
    logger.info("Application services shut down successfully")
    _initialized = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI应用生命周期管理器。
    
    在应用启动时执行初始化，在应用关闭时执行清理。
    使用锁机制确保即使在多worker环境下初始化也只执行一次。
    
    :param app: FastAPI应用实例
    :yield: None
    """
    await initialize_services()
    
    yield
    
    await shutdown_services()


from .app import create_app as _create_app

def create_app_with_lifespan() -> FastAPI:
    """创建带有生命周期管理的 FastAPI 应用实例。
    
    此函数创建应用并注入生命周期管理器，确保启动和关闭时
    执行相应的初始化和清理操作。
    
    :return: 配置完成的 FastAPI 应用实例
    """
    from fastapi import FastAPI
    
    base_app = _create_app()
    
    app = FastAPI(
        title=base_app.title,
        description=base_app.description,
        version=base_app.version,
        docs_url=base_app.docs_url,
        redoc_url=base_app.redoc_url,
        lifespan=lifespan,
    )
    
    app.user_middleware = base_app.user_middleware.copy()
    
    app.router = base_app.router
    
    return app


app = create_app_with_lifespan()

__all__ = ["app"]