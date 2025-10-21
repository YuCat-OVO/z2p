"""非流式聊天响应处理模块。

本模块负责处理与上游API的非流式交互，包括非流式响应解析和结果构建。
"""

import json
import uuid
from datetime import datetime
from typing import Any

import httpx

from ...config import get_settings
from ...exceptions import UpstreamAPIError
from ...logger import get_logger
from ...models import (
    ChatRequest,
    ChatCompletionMessage,
    ChatCompletionChoice,
    ChatCompletionResponse,
    ChatCompletionUsage,
)
from ...utils.error_handler import handle_upstream_error

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
    zai_data, params, headers = await prepare_request_data_func(
        chat_request, access_token, False
    )
    full_response = ""
    usage = {}

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
        logger.debug(
            "Non-streaming request details: request_id={}, upstream_url={}, headers={}, params={}, json_body={}",
            request_id,
            f"{settings.proxy_url}/api/chat/completions",
            {
                k: v if k.lower() != "authorization" else v[:20] + "..."
                for k, v in headers.items()
            },  # 脱敏 Authorization
            params,
            zai_data,
        )

    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                method="POST",
                url=f"{settings.proxy_url}/api/chat/completions",
                headers=headers,
                params=params,
                json=zai_data,
                timeout=300,
            ) as response:
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

                chunk_count = 0
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    json_str = line[6:]
                    try:
                        json_object = json.loads(json_str)
                    except json.JSONDecodeError:
                        continue

                    data = json_object.get("data", {})
                    phase = data.get("phase")

                    if phase == "answer":
                        content = data.get("delta_content", "")
                        full_response += content
                        chunk_count += 1
                    elif phase == "other":
                        usage = data.get("usage", {})
                        content = data.get("delta_content", "")
                        full_response += content
                        logger.info(
                            "Non-streaming completion: request_id={}, model={}, chunks={}, response_length={}, usage={}",
                            request_id,
                            chat_request.model,
                            chunk_count,
                            len(full_response),
                            usage,
                        )

        except UpstreamAPIError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "Unexpected HTTP status error (non-streaming): status_code={}, error={}, request_id={}, user_id={}, timestamp={}",
                e.response.status_code,
                str(e),
                request_id,
                user_id,
                timestamp,
            )
            raise UpstreamAPIError(
                e.response.status_code,
                f"HTTP错误 {e.response.status_code}",
                "http_error",
            ) from e
        except httpx.RequestError as e:
            logger.error(
                "Upstream request error (non-streaming): error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                type(e).__name__,
                str(e),
                request_id,
                user_id,
                timestamp,
            )
            raise UpstreamAPIError(500, f"请求错误: {str(e)}", "request_error") from e
        except Exception as e:
            logger.error(
                "Unexpected error (non-streaming): error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                type(e).__name__,
                str(e),
                request_id,
                user_id,
                timestamp,
            )
            raise UpstreamAPIError(500, f"未知错误: {str(e)}", "unknown_error") from e

    # 使用 Pydantic 模型构建响应
    message = ChatCompletionMessage(role="assistant", content=full_response)
    choice = ChatCompletionChoice(index=0, message=message, finish_reason="stop")

    response = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4()}",
        created=int(datetime.now().timestamp()),
        model=chat_request.model,
        choices=[choice],
        usage=ChatCompletionUsage(**usage) if usage else None,
    )
    
    return response.model_dump(exclude_none=True)