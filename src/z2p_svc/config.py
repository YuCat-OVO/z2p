"""应用配置模块。

本模块使用pydantic-settings进行环境变量管理，提供应用运行所需的所有配置参数。
支持多环境配置：
- 开发环境：读取 .env.development
- 生产环境：读取 .env.production
- 默认：读取 .env

环境通过 APP_ENV 环境变量指定，默认为 development。
"""

import os
import random
from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, field_validator
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
    
    使用 Pydantic BaseSettings 从环境变量加载配置。
    支持从 ``.env`` 文件读取，优先级：环境变量 > .env 文件 > 默认值。
    
    **配置文件查找顺序:**
    
    1. ``.env.{APP_ENV}`` (如 ``.env.production``)
    2. ``.env``
    
    :param app_env: 应用运行环境（development/production）
    :param host: 服务器监听地址
    :param port: 服务器监听端口（1-65535）
    :param workers: 工作进程数（≥1）
    :param log_level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
    :param verbose_logging: 是否启用详细日志模式
    :param proxy_url: 代理目标 URL
    :param secret_key: 应用密钥，用于签名生成（最少 16 字符）
    :param mihomo_api_url: Mihomo API URL
    :param mihomo_api_secret: Mihomo API 密钥
    :param mihomo_proxy_group: Mihomo 代理组名称
    :param enable_mihomo_switch: 是否启用 Mihomo 代理切换
    :type app_env: Literal["development", "production"]
    :type host: str
    :type port: int
    :type workers: int
    :type log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    :type verbose_logging: bool
    :type proxy_url: str
    :type secret_key: str
    :type mihomo_api_url: str
    :type mihomo_api_secret: str
    :type mihomo_proxy_group: str
    :type enable_mihomo_switch: bool
    
    .. code-block:: bash
    
       # .env 文件示例
       APP_ENV=production
       SECRET_KEY=your-super-secret-key
       PROXY_URL=https://chat.z.ai
       LOG_LEVEL=INFO
    
    .. seealso::
       :func:`get_settings` - 获取配置单例
    
    .. warning::
       生产环境必须设置强密钥，最少 16 个字符。
       不要使用默认值或简单密码。
    """

    model_config = SettingsConfigDict(
        env_file=_get_env_files(),
        env_file_encoding="utf-8",
        extra="allow",
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
    
    fe_version: str = Field(
        default="prod-fe-1.0.109",
        description="前端版本号（可自动获取）"
    )
    
    proxy_url: str = Field(
        default="https://chat.z.ai",
        description="代理目标URL"
    )
    
    secret_key: str = Field(
        ...,  # 必填,不提供默认值
        description="应用密钥",
        min_length=16
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
    
    # FE 版本管理配置
    fe_version_source_url: str = Field(
        default="https://chat.z.ai",
        description="FE版本获取源URL"
    )
    fe_version_cache_ttl: int = Field(
        default=1800,
        ge=60,
        description="FE版本缓存时间(秒)"
    )
    fe_version_update_interval: int = Field(
        default=1800,
        ge=60,
        description="FE版本自动更新间隔(秒)"
    )
    
    # HTTP 超时配置（秒）
    timeout_chat: int = Field(
        default=300,
        ge=30,
        description="聊天请求超时(秒)"
    )
    timeout_proxy_switch: int = Field(
        default=5,
        ge=1,
        description="代理切换超时(秒)"
    )
    timeout_model_list: int = Field(
        default=10,
        ge=5,
        description="模型列表获取超时(秒)"
    )
    timeout_file_upload: int = Field(
        default=30,
        ge=10,
        description="文件上传超时(秒)"
    )
    timeout_auth: int = Field(
        default=10,
        ge=5,
        description="认证请求超时(秒)"
    )
    
    # curl_cffi 浏览器模拟配置
    browser_impersonate: str = Field(
        default="random",
        description="curl_cffi 浏览器模拟类型 (random/chrome136/chrome133a/chrome131/safari260/safari184/firefox133等)"
    )
    
    # 支持的较新浏览器版本列表
    _BROWSER_VERSIONS = [
        "chrome136", "chrome133a", "chrome131", "chrome124", "chrome123",
        "safari260", "safari260_ios", "safari184", "safari184_ios", "safari180", "safari180_ios",
        "firefox133", "edge101"
    ]

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

    def get_browser_version(self) -> str:
        """获取实际使用的浏览器版本。
        
        如果配置为random，则从支持的版本列表中随机选择。
        """
        if self.browser_impersonate == "random":
            return random.choice(self._BROWSER_VERSIONS)
        return self.browser_impersonate
    
    @computed_field
    @property
    def HEADERS(self) -> dict[str, str]:
        """HTTP请求头常量。
        
        只包含业务相关的headers，curl_cffi会自动处理浏览器相关的headers。
        """
        return {
            "Content-Type": "application/json",
            "Origin": f"{self.protocol}//{self.base_url}",
            "X-FE-Version": self.fe_version,
        }

    @property
    def ALLOWED_MODELS(self) -> list[dict[str, str]]:
        """允许的模型列表。"""
        return [
            {"id": "glm-4.6", "name": "GLM-4.6"},
            {"id": "glm-4.6v", "name": "GLM-4.6V"},
            {"id": "glm-4.5V", "name": "GLM-4.5V"},
            {"id": "glm-4.5", "name": "GLM-4.5"},
            {"id": "glm-4.6-search", "name": "GLM-4.6-SEARCH"},
            {"id": "glm-4.6-advanced-search", "name": "GLM-4.6-ADVANCED-SEARCH"},
            {"id": "glm-4.6-nothinking", "name": "GLM-4.6-NOTHINKING"},
        ]

    @computed_field
    @property
    def MODELS_MAPPING(self) -> dict[str, str]:
        """模型名称映射。"""
        return {
            "GLM-4-6-API-V1": "glm-4.6",
            "glm-4.5v": "glm-4.5v",
            "0727-360B-API": "glm-4.5",
        }

    def __init__(self, **data):
        """初始化配置并设置反向映射表。"""
        super().__init__(**data)
        # 初始化反向映射表为可修改的字典
        # 从 MODELS_MAPPING 生成基础映射
        self._reverse_models_mapping = {v: k for k, v in self.MODELS_MAPPING.items()}
    
    @property
    def REVERSE_MODELS_MAPPING(self) -> dict[str, str]:
        """反向模型映射表（可修改）。
        
        初始从 :attr:`MODELS_MAPPING` 自动生成反向映射，
        用于将客户端模型 ID 转换为上游 API 模型 ID。
        运行时可以添加变体映射（如 glm-4.6-nothinking -> glm-4.6）。
        
        :return: 反向映射字典 {客户端模型ID: 上游模型ID或基础模型ID}
        :rtype: dict[str, str]
        
        .. code-block:: python
        
           # 静态映射: MODELS_MAPPING = {"GLM-4-6-API-V1": "glm-4.6"}
           # 初始反向映射: {"glm-4.6": "GLM-4-6-API-V1"}
           
           # 运行时添加变体映射
           settings.REVERSE_MODELS_MAPPING["glm-4.6-nothinking"] = "glm-4.6"
           
           # 映射链: glm-4.6-nothinking -> glm-4.6 -> GLM-4-6-API-V1
        """
        return self._reverse_models_mapping

    @field_validator("proxy_url")
    @classmethod
    def validate_proxy_url(cls, v: str) -> str:
        """验证代理 URL 格式"""
        if not v.startswith(("http://", "https://")):
            raise ValueError("proxy_url 必须以 http:// 或 https:// 开头")
        return v


@lru_cache
def get_settings() -> AppConfig:
    """获取应用配置单例。

    使用lru_cache确保配置只被加载一次，提高性能。

    :return: AppConfig实例

    Example::

        >>> settings = get_settings()
        >>> print(settings.host, settings.port)
    """
    # 在生产环境中，secret_key 必须通过环境变量提供
    # 在开发环境中，为了方便测试，如果未设置环境变量，则提供一个默认值
    if os.getenv("APP_ENV") == "development" and "SECRET_KEY" not in os.environ:
        os.environ["SECRET_KEY"] = "default_dev_secret_key_for_testing"
    
    return AppConfig()
