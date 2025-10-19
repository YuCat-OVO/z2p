"""应用配置模块。

本模块使用django-environ进行环境变量管理，提供应用运行所需的所有配置参数。
支持多环境配置：
- 开发环境：读取 .env.development
- 生产环境：读取 .env.production
- 默认：读取 .env

环境通过 APP_ENV 环境变量指定，默认为 development。
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Final

import environ


class AppConfig:
    """应用配置类。

    通过环境变量自动加载配置，若环境变量未设置，则使用指定的默认值。
    使用 :func:`get_settings` 函数获取单例配置实例。

    :ivar host: 服务器监听地址（仅用于信息展示，实际由granian通过环境变量读取）
    :ivar port: 服务器监听端口（仅用于信息展示，实际由granian通过环境变量读取）
    :ivar workers: 工作进程数（仅用于信息展示，实际由granian通过环境变量读取）
    :ivar log_level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
    :ivar verbose_logging: 是否启用详细日志模式（包含完整时间戳、行号、backtrace和diagnose）
    :ivar proxy_url: 代理目标URL
    :ivar HEADERS: HTTP请求头常量
    :ivar ALLOWED_MODELS: 允许的模型列表
    :ivar MODELS_MAPPING: 模型名称映射
    """

    def __init__(self):
        """初始化配置，从环境变量读取设置。
        
        根据 APP_ENV 环境变量加载对应的 .env 文件：
        - development: .env.development
        - production: .env.production
        - 默认: .env
        """
        app_env = os.getenv("APP_ENV", "development")
        
        env_file = self._get_env_file(app_env)
        
        env = environ.Env(
            APP_ENV=(str, "development"),
            HOST=(str, "0.0.0.0"),
            PORT=(int, 8001),
            WORKERS=(int, 1),
            LOG_LEVEL=(str, "INFO"),
            VERBOSE_LOGGING=(bool, False),
            PROXY_URL=(str, "https://chat.z.ai"),
            SECRET_KEY=(str, "junjie"),
        )

        if env_file.exists():
            environ.Env.read_env(env_file)
        else:
            default_env = Path(".env")
            if default_env.exists():
                environ.Env.read_env(default_env)
        
        self.app_env: str = env("APP_ENV")

        self.host: str = env("HOST")
        self.port: int = env("PORT")
        self.workers: int = env("WORKERS")
        self.log_level: str = env("LOG_LEVEL")
        self.verbose_logging: bool = env("VERBOSE_LOGGING")
        self.proxy_url: str = env("PROXY_URL")
        self.secret_key: str = env("SECRET_KEY")
        
        if self.proxy_url.startswith("https://"):
            self.protocol: str = "https:"
            self.base_url: str = self.proxy_url[8:]
        elif self.proxy_url.startswith("http://"):
            self.protocol: str = "http:"
            self.base_url: str = self.proxy_url[7:]
        else:
            self.protocol: str = "https:"
            self.base_url: str = self.proxy_url
        
        # 如果日志级别为DEBUG，自动启用详细日志（除非明确设置为False）
        if self.log_level.upper() == "DEBUG" and not env.bool("VERBOSE_LOGGING", default=None):
            self.verbose_logging = True

        self.HEADERS: Final[dict[str, str]] = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": f"{self.protocol}//{self.base_url}",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
            "X-FE-Version": "prod-fe-1.0.103",
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
            "GLM-4-6-API-V1": "glm-4.6",
            "glm-4.5v": "glm-4.5v",
            "0727-360B-API": "glm-4.5",
        }
        
        self.REVERSE_MODELS_MAPPING: Final[dict[str, str]] = {
            "glm-4.6": "GLM-4-6-API-V1",
            "glm-4.6-nothinking": "GLM-4-6-API-V1",
            "glm-4.6-search": "GLM-4-6-API-V1",
            "glm-4.6-advanced-search": "GLM-4-6-API-V1",
            "glm-4.5v": "glm-4.5v",
            "glm-4.5": "0727-360B-API",
        }
    
    @staticmethod
    def _get_env_file(app_env: str) -> Path:
        """根据环境名称获取对应的 .env 文件路径。
        
        :param app_env: 环境名称（development/production）
        :return: .env 文件的 Path 对象
        """
        env_files = {
            "development": Path(".env.development"),
            "production": Path(".env.production"),
        }
        return env_files.get(app_env, Path(".env"))


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
