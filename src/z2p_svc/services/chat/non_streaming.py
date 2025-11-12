"""非流式聊天响应处理模块。

本模块负责处理与上游API的非流式交互，包括非流式响应解析和结果构建。
"""

from datetime import datetime
from typing import Any

from curl_cffi.requests import AsyncSession

# 尝试使用 orjson 加速 JSON 操作
try:
    import orjson

    def json_loads(s: str) -> dict:
        """使用 orjson 快速反序列化"""
        return orjson.loads(s)
except ImportError:
    import json

    json_loads = json.loads

from ...config import get_settings
from ...exceptions import UpstreamAPIError
from ...logger import get_logger, json_str as log_json
from ...models import (
    ChatRequest,
    ChatCompletionMessage,
    ChatCompletionChoice,
    ChatCompletionResponse,
    ChatCompletionUsage,
)
from ...utils.error_handler import handle_upstream_error
from ...utils.uuid_helper import generate_completion_id

logger = get_logger(__name__)
settings = get_settings()


async def process_non_streaming_response(
    chat_request: ChatRequest, access_token: str, prepare_request_data_func
) -> dict[str, Any]:
    """处理非流式响应。

    :param chat_request: 聊天请求对象
    :param access_token: 访问令牌
    :param prepare_request_data_func: 用于准备请求数据的函数
    :return: 完整的聊天补全响应
    :raises UpstreamAPIError: 当上游API返回错误状态码时

    .. note::
       响应格式遵循OpenAI的非流式API规范。
    """
    async with AsyncSession(impersonate=settings.get_browser_version()) as session:  # type: ignore
        # 准备请求数据，先不传入 user_agent（使用空字符串占位）
        zai_data, params, headers = await prepare_request_data_func(
            chat_request, access_token, streaming=False, user_agent=""
        )
        
        # 从 curl_cffi session 获取实际的 User-Agent
        # impersonate 参数会自动设置对应浏览器的 User-Agent
        # 使用 type: ignore 来忽略 Pylance 的类型检查警告
        actual_user_agent = ""
        try:
            if hasattr(session, 'headers') and 'User-Agent' in session.headers:
                actual_user_agent = session.headers['User-Agent']  # type: ignore
        except Exception:
            pass
        
        # 更新 params 中的 user_agent
        if actual_user_agent:
            params["user_agent"] = actual_user_agent

        full_response = ""
        usage_info = None
        request_id = params.get("requestId", "unknown")
        user_id = params.get("user_id", "unknown")
        timestamp = params.get("timestamp", "unknown")

        logger.info(
            "Non-streaming request initiated: request_id={}, user_id={}, model={}, upstream_url={}",
            request_id,
            user_id,
            chat_request.model,
            f"{settings.proxy_url}/api/chat/completions",
        )

        if settings.verbose_logging:
            # 为日志创建数据副本，移除 model_item 以避免污染日志
            log_data = {k: v for k, v in zai_data.items() if k != "model_item"}
            logger.debug(
                "Non-streaming request details: request_id={}, upstream_url={}, headers={}, params={}, json_body={}",
                request_id,
                f"{settings.proxy_url}/api/chat/completions",
                log_json({
                    k: v if k.lower() != "authorization" else v[:20] + "..."
                    for k, v in headers.items()
                }),
                log_json(params),
                log_json(log_data),
            )

        try:
            response = await session.post(
                f"{settings.proxy_url}/api/chat/completions",
                headers=headers,
                params=params,
                json=zai_data,
                timeout=float(settings.timeout_chat),
                stream=True,  # 接收SSE流
            )
            
            if response.status_code != 200:
                await handle_upstream_error(
                    response,
                    request_id,
                    user_id,
                    timestamp,
                    chat_request.model,
                    is_streaming=False,
                )

            logger.info(
                "Non-streaming response started: request_id={}, status_code={}, model={}",
                request_id,
                response.status_code,
                chat_request.model,
            )

            # 伪非流式：接收SSE流并聚合
            try:
                async for line in response.aiter_lines():
                    if not line:
                        continue

                    if isinstance(line, bytes):
                        line = line.decode("utf-8")

                    if not line.startswith("data:"):
                        continue

                    json_str = line[6:].strip()

                    if settings.verbose_logging:
                        logger.debug(
                            "Non-streaming SSE line: request_id={}, data={}",
                            request_id,
                            json_str[:300],
                        )

                    try:
                        json_object = json_loads(json_str)
                    except Exception:
                        continue

                    if json_object.get("type") != "chat:completion":
                        continue

                    data = json_object.get("data", {})

                    # 检查是否有错误（如内容安全警告）
                    error_info = data.get("error")
                    if error_info:
                        error_detail = error_info.get("detail", "Unknown error")
                        logger.warning(
                            "Content security warning: request_id={}, detail={}",
                            request_id,
                            error_detail
                        )
                        # 将错误信息添加到响应中
                        full_response += f"\n\n[Error: {error_detail}]"
                        break

                    # 提取usage信息（可能在任何阶段出现）
                    if data.get("usage"):
                        usage_info = data["usage"]

                    # 聚合answer和other阶段的内容
                    phase = data.get("phase")
                    if phase in ("answer", "other"):
                        content = data.get("delta_content") or data.get("edit_content", "")
                        if content:
                            full_response += content

                    # 检查done标记
                    if phase == "done":
                        logger.info(
                            "Non-streaming done signal received: request_id={}, model={}",
                            request_id,
                            chat_request.model,
                        )
                        break

            finally:
                await response.aclose()

            # 构建完整OpenAI格式响应
            message = ChatCompletionMessage(role="assistant", content=full_response)
            choice = ChatCompletionChoice(index=0, message=message, finish_reason="stop")

            response_obj = ChatCompletionResponse(
                id=generate_completion_id(),
                created=int(datetime.now().timestamp()),
                model=chat_request.model,
                choices=[choice],
                usage=ChatCompletionUsage(**usage_info) if usage_info else None,
            )

            logger.info(
                "Non-streaming response completed: request_id={}, model={}, content_length={}",
                request_id,
                chat_request.model,
                len(full_response),
            )

            return response_obj.model_dump(exclude_none=True)
            
        except UpstreamAPIError:
            raise
        except Exception as e:
            if "status" in str(type(e).__name__).lower() or "HTTP" in str(e):
                status_code = getattr(e, "status_code", 500)
                logger.error(
                    "Unexpected HTTP status error (non-streaming): status_code={}, error={}, request_id={}, user_id={}, timestamp={}",
                    status_code,
                    str(e),
                    request_id,
                    user_id,
                    timestamp,
                )
                raise UpstreamAPIError(
                    status_code,
                    f"HTTP错误 {status_code}",
                    "http_error",
                ) from e
            elif "request" in str(type(e).__name__).lower():
                logger.error(
                    "Upstream request error (non-streaming): error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                    type(e).__name__,
                    str(e),
                    request_id,
                    user_id,
                    timestamp,
                )
                raise UpstreamAPIError(
                    500, f"请求错误: {str(e)}", "request_error"
                ) from e
            else:
                logger.error(
                    "Unexpected error (non-streaming): error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                    type(e).__name__,
                    str(e),
                    request_id,
                    user_id,
                    timestamp,
                )
                raise UpstreamAPIError(
                    500, f"未知错误: {str(e)}", "unknown_error"
                ) from e