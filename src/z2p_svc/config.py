"""应用配置模块。

本模块使用pydantic-settings进行环境变量管理，提供应用运行所需的所有配置参数。
支持多环境配置：
- 开发环境：读取 .env.development
- 生产环境：读取 .env.production
- 默认：读取 .env

环境通过 APP_ENV 环境变量指定，默认为 development。
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, HttpUrl, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_env_files() -> tuple[str, ...]:
    """根据APP_ENV环境变量获取要加载的.env文件列表。
    
    返回的文件列表按优先级从高到低排列。
    
    :return: .env文件路径元组
    """
    app_env = os.getenv("APP_ENV", "development")
    
    env_files_map = {
        "development": (".env.development", ".env"),
        "production": (".env.production", ".env"),
    }
    
    return env_files_map.get(app_env, (".env",))


class AppConfig(BaseSettings):
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

    model_config = SettingsConfigDict(
        env_file=_get_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "production"] = Field(
        default="development",
        description="应用运行环境"
    )
    
    host: str = Field(
        default="0.0.0.0",
        description="服务器监听地址"
    )
    
    port: int = Field(
        default=8001,
        description="服务器监听端口",
        gt=0,
        lt=65536
    )
    
    workers: int = Field(
        default=1,
        description="工作进程数",
        ge=1
    )
    
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="日志级别"
    )
    
    verbose_logging: bool = Field(
        default=False,
        description="是否启用详细日志模式"
    )
    
    proxy_url: str = Field(
        default="https://chat.z.ai",
        description="代理目标URL"
    )
    
    secret_key: str = Field(
        default="junjie",
        description="应用密钥"
    )
    
    # Mihomo代理配置
    mihomo_api_url: str = Field(
        default="",
        description="Mihomo API URL"
    )
    
    mihomo_api_secret: str = Field(
        default="",
        description="Mihomo API 密钥"
    )
    
    mihomo_proxy_group: str = Field(
        default="ZhipuAI",
        description="Mihomo 代理组"
    )
    
    enable_mihomo_switch: bool = Field(
        default=False,
        description="是否启用 Mihomo 切换"
    )

    @field_validator("verbose_logging", mode="before")
    @classmethod
    def auto_enable_verbose_for_debug(cls, v: bool, info) -> bool:
        """如果日志级别为DEBUG，自动启用详细日志（除非明确设置为False）。"""
        # 如果已经明确设置了verbose_logging，则使用该值
        if v is not None and isinstance(v, bool):
            return v
        # 如果log_level为DEBUG且verbose_logging未设置，则自动启用
        log_level = info.data.get("log_level", "INFO")
        if log_level and log_level.upper() == "DEBUG":
            return True
        return False

    @computed_field
    @property
    def protocol(self) -> str:
        """从proxy_url解析协议。"""
        if self.proxy_url.startswith("https://"):
            return "https:"
        elif self.proxy_url.startswith("http://"):
            return "http:"
        else:
            return "https:"

    @computed_field
    @property
    def base_url(self) -> str:
        """从proxy_url解析基础URL。"""
        if self.proxy_url.startswith("https://"):
            return self.proxy_url[8:]
        elif self.proxy_url.startswith("http://"):
            return self.proxy_url[7:]
        else:
            return self.proxy_url

    @computed_field
    @property
    def HEADERS(self) -> dict[str, str]:
        """HTTP请求头常量。"""
        return {
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

    @property
    def ALLOWED_MODELS(self) -> list[dict[str, str]]:
        """允许的模型列表。"""
        return [
            {"id": "glm-4.6", "name": "GLM-4.6"},
            {"id": "glm-4.5V", "name": "GLM-4.5V"},
            {"id": "glm-4.5", "name": "GLM-4.5"},
            {"id": "glm-4.6-search", "name": "GLM-4.6-SEARCH"},
            {"id": "glm-4.6-advanced-search", "name": "GLM-4.6-ADVANCED-SEARCH"},
            {"id": "glm-4.6-nothinking", "name": "GLM-4.6-NOTHINKING"},
        ]

    @property
    def MODELS_MAPPING(self) -> dict[str, str]:
        """模型名称映射。"""
        return {
            "GLM-4-6-API-V1": "glm-4.6",
            "glm-4.5v": "glm-4.5v",
            "0727-360B-API": "glm-4.5",
        }

    @property
    def REVERSE_MODELS_MAPPING(self) -> dict[str, str]:
        """反向模型名称映射。"""
        return {
            "glm-4.6": "GLM-4-6-API-V1",
            "glm-4.6-nothinking": "GLM-4-6-API-V1",
            "glm-4.6-search": "GLM-4-6-API-V1",
            "glm-4.6-advanced-search": "GLM-4-6-API-V1",
            "glm-4.5v": "glm-4.5v",
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
