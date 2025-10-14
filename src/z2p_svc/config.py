"""应用配置模块。

本模块使用django-environ进行环境变量管理，提供应用运行所需的所有配置参数。
"""

from functools import lru_cache
from typing import Final

import environ


class AppConfig:
    """应用配置类。

    通过环境变量自动加载配置，若环境变量未设置，则使用指定的默认值。
    使用 :func:`get_settings` 函数获取单例配置实例。

    :ivar host: 服务器监听地址
    :ivar port: 服务器监听端口
    :ivar debug: 是否开启调试模式
    :ivar workers: 工作进程数
    :ivar log_level: 日志级别
    :ivar proxy_url: 代理目标URL
    :ivar HEADERS: HTTP请求头常量
    :ivar ALLOWED_MODELS: 允许的模型列表
    :ivar MODELS_MAPPING: 模型名称映射
    """

    def __init__(self):
        """初始化配置，从环境变量读取设置。"""
        env = environ.Env(
            HOST=(str, "0.0.0.0"),
            PORT=(int, 8001),
            DEBUG=(bool, False),
            WORKERS=(int, 1),
            LOG_LEVEL=(str, "INFO"),
            PROXY_URL=(str, "https://chat.z.ai"),
        )

        environ.Env.read_env()

        self.host: str = env("HOST")
        self.port: int = env("PORT")
        self.debug: bool = env("DEBUG")
        self.workers: int = env("WORKERS")
        self.log_level: str = env("LOG_LEVEL")
        self.proxy_url: str = env("PROXY_URL")

        self.HEADERS: Final[dict[str, str]] = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://chat.z.ai",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "X-FE-Version": "prod-fe-1.0.97",
        }

        self.ALLOWED_MODELS: Final[list[dict[str, str]]] = [
            {"id": "glm-4.6", "name": "GLM-4.6"},
            {"id": "glm-4.5V", "name": "GLM-4.5V"},
            {"id": "glm-4.5", "name": "GLM-4.5"},
            {"id": "glm-4.6-search", "name": "GLM-4.6-SEARCH"},
            {"id": "glm-4.6-advanced-search", "name": "GLM-4.6-ADVANCED-SEARCH"},
            {"id": "glm-4.6-nothinking", "name": "GLM-4.6-NOTHINKING"},
        ]

        self.MODELS_MAPPING: Final[dict[str, str]] = {
            "glm-4.6": "GLM-4-6-API-V1",
            "glm-4.6-nothinking": "GLM-4-6-API-V1",
            "glm-4.6-search": "GLM-4-6-API-V1",
            "glm-4.6-advanced-search": "GLM-4-6-API-V1",
            "glm-4.5V": "glm-4.5v",
            "glm-4.5": "0727-360B-API",
        }


@lru_cache
def get_settings() -> AppConfig:
    """获取应用配置单例。

    使用lru_cache确保配置只被加载一次，提高性能。

    :return: AppConfig实例

    Example::

        >>> settings = get_settings()
        >>> print(settings.host, settings.port)
    """
    return AppConfig()
