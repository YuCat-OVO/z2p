"""自定义异常模块。

本模块定义了应用中使用的自定义异常类型。
"""

import json
from typing import Any


class UpstreamAPIError(Exception):
    """上游API错误异常类。

    用于封装上游API返回的HTTP错误，包含状态码和错误信息。
    """

    def __init__(
        self, status_code: int, message: str, error_type: str = "upstream_error"
    ):
        self.status_code = status_code
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)


class AuthenticationError(UpstreamAPIError):
    """认证相关错误。"""

    def __init__(
        self,
        message: str = "认证失败",
        status_code: int = 401,
        error_type: str = "authentication_error",
    ):
        super().__init__(status_code, message, error_type)


class FileUploadError(UpstreamAPIError):
    """文件上传错误。"""

    def __init__(
        self,
        message: str = "文件上传失败",
        status_code: int = 400,
        error_type: str = "file_upload_error",
    ):
        super().__init__(status_code, message, error_type)


class RateLimitError(UpstreamAPIError):
    """请求速率限制错误。"""

    def __init__(
        self,
        message: str = "请求过于频繁",
        status_code: int = 429,
        error_type: str = "rate_limit_error",
    ):
        super().__init__(status_code, message, error_type)


class BadRequestError(UpstreamAPIError):
    """请求参数错误。"""

    def __init__(
        self,
        message: str = "请求参数错误",
        status_code: int = 400,
        error_type: str = "bad_request_error",
    ):
        super().__init__(status_code, message, error_type)


class PermissionError(UpstreamAPIError):
    """权限不足错误。"""

    def __init__(
        self,
        message: str = "权限不足",
        status_code: int = 403,
        error_type: str = "permission_error",
    ):
        super().__init__(status_code, message, error_type)


class MethodNotAllowedError(UpstreamAPIError):
    """请求方法不允许错误。"""

    def __init__(
        self,
        message: str = "请求方法不允许",
        status_code: int = 405,
        error_type: str = "method_not_allowed_error",
    ):
        super().__init__(status_code, message, error_type)


class ServerError(UpstreamAPIError):
    """上游服务器错误。"""

    def __init__(
        self,
        message: str = "上游服务器错误",
        status_code: int = 500,
        error_type: str = "server_error",
    ):
        super().__init__(status_code, message, error_type)


def is_aliyun_blocked_response(response_text: str) -> bool:
    """检测是否为阿里云拦截的405响应。

    阿里云的拦截响应包含特定的HTML特征：
    - 包含 "data-spm" 属性
    - 包含 "block_message" 或 "block_traceid" 等特定ID
    - 包含阿里云错误图片URL

    :param response_text: HTTP响应文本内容
    :return: 如果是阿里云拦截响应返回True，否则返回False
    """
    # 检查阿里云拦截响应的特征标识
    aliyun_indicators = [
        "data-spm",
        "block_message",
        "block_traceid",
        "errors.aliyun.com",
        "potential threats to the server",
        "由于您访问的URL有可能对网站造成安全威胁",
    ]

    # 如果包含多个特征标识，则判定为阿里云拦截
    matches = sum(1 for indicator in aliyun_indicators if indicator in response_text)
    return matches >= 2