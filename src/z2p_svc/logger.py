"""日志配置模块。

本模块使用loguru进行结构化日志记录，提供统一的日志配置和获取接口，
支持开发和生产环境的不同配置，输出规范漂亮的日志。
"""

import sys
from loguru import logger


def configure_logging(log_level: str = "INFO", use_colors: bool = True) -> None:
    """配置loguru日志系统。

    :param log_level: 日志级别，可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL
    :param use_colors: 是否在控制台输出中使用颜色

    .. note::
       此函数应在应用启动时调用一次，配置全局日志行为。
       开发环境使用彩色输出便于阅读，生产环境使用JSON格式便于日志收集和分析。
       
       日志级别说明：
       - DEBUG: 输出详细的调试日志，包括请求准备、图片上传、响应流程等各个阶段
       - INFO: 输出关键业务日志和API Key审计信息（脱敏显示）
       - WARNING及以上: 仅输出警告和错误信息
    """
    logger.remove()
    
    level = log_level.upper()
    
    if use_colors and sys.stderr.isatty():
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=level,
            colorize=True,
            backtrace=True,
            diagnose=True,
        )
    else:
        logger.add(
            sys.stderr,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            level=level,
            colorize=False,
            backtrace=True,
            diagnose=False,
        )


def get_logger(name: str | None = None):
    """获取logger实例。

    :param name: logger名称，通常使用模块的__name__。loguru使用全局logger，此参数用于兼容性
    :return: 配置好的loguru logger实例

    Example::

        >>> from z2p_svc.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Application started with version {}", "1.0.0")
        >>> logger.debug("Processing request: request_id={}, user_id={}", "123", "456")
        >>> logger.error("Request failed: {}", "Connection timeout")
    
    Note:
        loguru 使用 {} 占位符进行字符串格式化，而不是结构化的键值对。
        例如：logger.info("User {} logged in", username) 而不是 logger.info("user_logged_in", username=username)
    """
    return logger