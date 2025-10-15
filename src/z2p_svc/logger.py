"""日志配置模块。

本模块使用loguru进行结构化日志记录，提供统一的日志配置和获取接口，
支持开发和生产环境的不同配置，输出规范漂亮的日志。
"""

import sys
from loguru import logger


def configure_logging(log_level: str = "INFO", use_colors: bool = True, verbose: bool = False) -> None:
    """配置loguru日志系统。

    :param log_level: 日志级别，可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL
    :param use_colors: 是否在控制台输出中使用颜色
    :param verbose: 是否启用详细日志模式（包含完整时间戳、行号、backtrace和diagnose）

    .. note::
       此函数应在应用启动时调用一次，配置全局日志行为。
       
       日志模式说明：
       - 简洁模式（verbose=False，默认）：适用于生产环境和Docker容器
         * 简短时间格式（HH:mm:ss）
         * 不显示行号
         * 不启用backtrace和diagnose
         * 彩色输出（如果use_colors=True）
       
       - 详细模式（verbose=True）：适用于开发环境调试
         * 完整时间格式（YYYY-MM-DD HH:mm:ss.SSS）
         * 显示行号
         * 启用backtrace和diagnose
         * 彩色输出（如果use_colors=True）
       
       日志级别说明：
       - DEBUG: 输出详细的调试日志，包括请求准备、文件上传、响应流程等各个阶段
       - INFO: 输出关键业务日志和访问令牌审计信息（脱敏显示）
       - WARNING及以上: 仅输出警告和错误信息
    """
    logger.remove()
    
    level = log_level.upper()
    
    if verbose:
        # 详细模式：用于开发环境，包含完整信息和诊断
        if use_colors:
            logger.add(
                sys.stderr,
                format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <5}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                level=level,
                colorize=True,
                backtrace=True,
                diagnose=True,
            )
        else:
            logger.add(
                sys.stderr,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <5} | {name}:{function}:{line} - {message}",
                level=level,
                colorize=False,
                backtrace=True,
                diagnose=False,
            )
    else:
        # 简洁模式：用于生产环境和Docker，简洁清晰
        if use_colors:
            logger.add(
                sys.stderr,
                format="<green>{time:HH:mm:ss}</green> | <level>{level: <5}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
                level=level,
                colorize=True,
                backtrace=False,
                diagnose=False,
            )
        else:
            logger.add(
                sys.stderr,
                format="{time:HH:mm:ss} | {level: <5} | {name}:{function} - {message}",
                level=level,
                colorize=False,
                backtrace=False,
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
    
    .. note::
       loguru使用{}占位符进行字符串格式化，而不是结构化的键值对。
       例如：logger.info("User {} logged in", username)
    """
    return logger