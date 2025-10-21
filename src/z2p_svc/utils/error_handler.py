"""错误处理工具模块。

提供统一的上游 API 错误处理逻辑，包括阿里云拦截检测和代理切换。
"""

import json
import httpx

from ..logger import get_logger
from ..proxy_manager import switch_proxy_node
from ..config import get_settings
from ..exceptions import is_aliyun_blocked_response, UpstreamAPIError

logger = get_logger(__name__)
settings = get_settings()


async def handle_upstream_error(
    response: httpx.Response,
    request_id: str,
    user_id: str,
    timestamp: str,
    model: str,
    is_streaming: bool = True,
) -> None:
    """统一处理上游 API 错误。

    检测并处理各种上游 API 错误，包括：

    - 阿里云拦截（405 状态码）
    - 认证错误（401）
    - 速率限制（429）
    - 权限错误（403）
    - 服务器错误（5xx）

    :param response: HTTP 响应对象
    :param request_id: 请求 ID
    :param user_id: 用户 ID
    :param timestamp: 时间戳
    :param model: 模型 ID
    :param is_streaming: 是否为流式请求
    :type response: httpx.Response
    :type request_id: str
    :type user_id: str
    :type timestamp: str
    :type model: str
    :type is_streaming: bool
    :raises UpstreamAPIError: 总是抛出对应的异常

    .. note::
       检测到阿里云拦截时，如果启用了 Mihomo 代理切换
       (``ENABLE_MIHOMO_SWITCH=true``)，会自动切换代理节点
    """
    error_content = await response.aread()
    error_text = error_content.decode("utf-8", errors="ignore")

    # 检测阿里云拦截
    if response.status_code == 405 and is_aliyun_blocked_response(error_text):
        log_prefix = "Aliyun blocked request detected (405 -> 429)"
        if not is_streaming:
            log_prefix += " (non-streaming)"
        logger.warning(
            f"{log_prefix}: request_id={{}}, user_id={{}}, timestamp={{}}, model={{}}, url={{}}",
            request_id,
            user_id,
            timestamp,
            model,
            str(response.url),
        )
        if settings.enable_mihomo_switch:
            logger.info(
                f"Attempting Mihomo proxy switch due to Aliyun block{' (non-streaming)' if not is_streaming else ''}: request_id={{}}",
                request_id,
            )
            await switch_proxy_node()
        raise UpstreamAPIError(
            429, "请求过于频繁：同一IP多次请求被拦截，请稍后再试", "rate_limit_error"
        )

    log_prefix = "Upstream HTTP error"
    if not is_streaming:
        log_prefix += " (non-streaming)"
    logger.error(
        f"{log_prefix}: status_code={{}}, response_text={{}}, request_id={{}}, user_id={{}}, timestamp={{}}, model={{}}, url={{}}",
        response.status_code,
        error_text[:200],
        request_id,
        user_id,
        timestamp,
        model,
        str(response.url),
    )

    error_map = {
        400: ("请求参数错误：请检查请求格式和参数", "bad_request_error"),
        401: ("认证失败：访问令牌无效或已过期", "authentication_error"),
        403: ("权限不足：无权访问该资源", "permission_error"),
        405: ("请求方法不允许：请求的HTTP方法不被支持", "method_not_allowed_error"),
        429: ("请求过于频繁，请稍后再试", "rate_limit_error"),
    }

    error_msg, error_type = error_map.get(
        response.status_code,
        (f"HTTP错误 {response.status_code}: {error_text[:100]}", "http_error"),
    )

    if response.status_code >= 500:
        error_msg = "上游服务器错误，请稍后再试"
        error_type = "server_error"

    raise UpstreamAPIError(response.status_code, error_msg, error_type)