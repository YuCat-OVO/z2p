"""日志配置模块。

本模块使用structlog进行结构化日志记录，提供统一的日志配置和获取接口，
支持开发和生产环境的不同配置。
"""

import logging
import sys

import structlog
from structlog.types import FilteringBoundLogger


def configure_logging(log_level: str = "INFO", use_colors: bool = True) -> None:
    """配置structlog日志系统。

    :param log_level: 日志级别，可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL
    :param use_colors: 是否在控制台输出中使用颜色

    .. note::
       此函数应在应用启动时调用一次，配置全局日志行为。
       开发环境使用彩色输出便于阅读，生产环境使用JSON格式便于日志收集和分析。
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )
    
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if use_colors and sys.stderr.isatty():
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]
    else:
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    """获取logger实例。

    :param name: logger名称，通常使用模块的__name__。如果为None，使用调用者的模块名
    :return: 配置好的structlog logger实例

    Example::

        >>> logger = get_logger(__name__)
        >>> logger.info("application_started", version="1.0.0")
    """
    return structlog.get_logger(name)