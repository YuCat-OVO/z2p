"""FastAPI应用主模块。

本模块负责创建和配置FastAPI应用实例，包括中间件、路由和全局异常处理。
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .logger import configure_logging, get_logger
from .routes import router

settings = get_settings()
configure_logging(settings.log_level, use_colors=settings.verbose_logging)
logger = get_logger(__name__)


def create_app() -> FastAPI:
    """创建并配置FastAPI应用实例。

    配置包括CORS中间件、可信主机中间件、API路由和全局异常处理。

    :return: 配置完成的FastAPI应用实例

    .. note::
       当LOG_LEVEL=DEBUG时会启用API文档（/docs和/redoc）和配置查看端点（/config）。
       生命周期管理器需要在asgi.py中单独配置。
    """
    app = FastAPI(
        title="ZAI Proxy API",
        description="ZAI Proxy API for accessing ZAI models",
        version="0",
        docs_url="/docs" if settings.verbose_logging else None,
        redoc_url="/redoc" if settings.verbose_logging else None,
        lifespan=None,  # 生命周期管理器将在asgi.py中配置
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"],
    )

    app.include_router(router, prefix="/v1")

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """全局异常处理器。

        :param request: FastAPI请求对象
        :param exc: 捕获的异常
        :return: 包含错误信息的JSON响应
        """
        logger.error(
            "Unhandled exception: path={}, method={}, error={}",
            request.url.path,
            request.method,
            str(exc)
        )
        return JSONResponse(
            status_code=500,
            content={
                "message": "An internal server error occurred.",
                "detail": str(exc) if settings.verbose_logging else None,
            },
        )

    @app.get("/")
    async def root() -> dict:
        """根路径端点。

        :return: 包含欢迎信息和版本号的字典
        """
        return {"message": "Hello z2p", "version": "0"}

    if settings.verbose_logging:

        @app.get("/config")
        async def get_config() -> dict:
            """获取当前配置信息（仅DEBUG模式）。

            :return: 当前应用配置的字典表示

            .. warning::
               此端点仅在LOG_LEVEL=DEBUG时可用，生产环境不应暴露配置信息。
            """
            return {
                "host": settings.host,
                "port": settings.port,
                "workers": settings.workers,
                "log_level": settings.log_level,
                "verbose_logging": settings.verbose_logging,
                "proxy_url": settings.proxy_url,
                "allowed_models": settings.ALLOWED_MODELS,
            }

    logger.info(
        "Application created: log_level={}, verbose_logging={}",
        settings.log_level,
        settings.verbose_logging,
    )

    return app


app = create_app()
