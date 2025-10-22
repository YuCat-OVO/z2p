"""流式聊天响应处理模块。

本模块负责处理与上游API的流式交互，包括流式响应解析和SSE格式转换。
"""

import json
import re
import time
import uuid
from datetime import datetime, UTC
from typing import Any, AsyncGenerator

import httpx

from ...config import get_settings
from ...exceptions import UpstreamAPIError
from ...logger import get_logger
from ...models import (
    ChatRequest,
    ChatCompletionChunk,
    ChatCompletionUsage,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
)
from ...utils.error_handler import handle_upstream_error

logger = get_logger(__name__)
settings = get_settings()


def create_chat_completion_chunk(
    content: str,
    model: str,
    timestamp: int,
    phase: str,
    usage: dict[str, Any] | None = None,
    finish_reason: str | None = None,
) -> dict[str, Any]:
    """创建聊天补全数据块。

    :param content: 响应内容
    :param model: 模型名称
    :param timestamp: 时间戳
    :param phase: 响应阶段（thinking/answer/other/tool_call）
    :param usage: 使用统计信息
    :param finish_reason: 完成原因
    :return: 符合OpenAI格式的响应数据块
    """
    # 构建 delta 对象
    delta_kwargs = {"role": "assistant"}
    if phase == "thinking":
        delta_kwargs["reasoning_content"] = content
    elif phase in ("answer", "tool_call", "other"):
        delta_kwargs["content"] = content

    delta = ChatCompletionChunkDelta(**delta_kwargs)

    # 构建 choice 对象
    choice = ChatCompletionChunkChoice(
        index=0, delta=delta, finish_reason=finish_reason if phase == "other" else None
    )

    # 构建完整的响应块
    chunk = ChatCompletionChunk(
        id=f"chatcmpl-{uuid.uuid4()}",
        created=timestamp,
        model=model,
        choices=[choice],
        usage=ChatCompletionUsage(**usage) if usage else None,
    )

    return chunk.model_dump(exclude_none=True)


def create_error_chunk(
    error_message: str,
    error_type: str,
    model: str,
    status_code: int | None = None,
) -> str:
    """创建错误响应块。

    :param error_message: 错误消息
    :param error_type: 错误类型
    :param model: 模型名称
    :param status_code: HTTP状态码
    :return: SSE格式的错误响应
    """
    error_data = {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion.chunk",
        "created": int(datetime.now(UTC).timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "error",
            }
        ],
        "error": {
            "message": error_message,
            "type": error_type,
            "code": status_code,
        },
    }
    return f"data: {json.dumps(error_data)}\n\n"


async def process_streaming_response(
    chat_request: ChatRequest, access_token: str, prepare_request_data_func
) -> AsyncGenerator[str, None]:
    """处理流式响应。

    :param chat_request: 聊天请求对象
    :param access_token: 访问令牌
    :param prepare_request_data_func: 用于准备请求数据的函数
    :yields: SSE格式的数据块
    :raises UpstreamAPIError: 当上游API返回错误状态码时

    .. note::
       响应格式遵循OpenAI的流式API规范。
    """
    zai_data, params, headers = await prepare_request_data_func(
        chat_request, access_token
    )

    request_id = params.get("requestId", "unknown")
    user_id = params.get("user_id", "unknown")
    timestamp = params.get("timestamp", "unknown")

    logger.info(
        "Streaming request initiated: request_id={}, user_id={}, model={}, upstream_url={}",
        request_id,
        user_id,
        chat_request.model,
        f"{settings.proxy_url}/api/chat/completions",
    )

    if settings.verbose_logging:
        logger.debug(
            "Streaming request details: request_id={}, upstream_url={}, headers={}, params={}, json_body={}",
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
                "POST",
                f"{settings.proxy_url}/api/chat/completions",
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
                        is_streaming=True,
                    )

                logger.info(
                    "Streaming response started: request_id={}, status_code={}, model={}",
                    request_id,
                    response.status_code,
                    chat_request.model,
                )

                timestamp = int(datetime.now().timestamp())
                chunk_count = 0

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    json_str = line[6:]
                    
                    # 输出原始SSE数据块
                    if settings.verbose_logging:
                        logger.debug(
                            "Streaming SSE line: request_id={}, data={}",
                            request_id,
                            json_str[:300]
                        )
                    
                    try:
                        json_object = json.loads(json_str)
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON in stream: line={}", line[:100])
                        continue

                    data = json_object.get("data", {})
                    phase = data.get("phase")

                    if phase == "thinking":
                        content = data.get("delta_content", "")
                        if "</summary>\n" in content:
                            content = content.split("</summary>\n")[-1]
                        chunk_count += 1
                        if settings.verbose_logging:
                            logger.debug(
                                "Streaming thinking chunk: request_id={}, chunks={}, content={}",
                                request_id,
                                chunk_count,
                                content[:200]
                            )
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, chat_request.model, timestamp, 'thinking'))}\n\n"

                    elif phase == "answer":
                        content = data.get("delta_content") or data.get(
                            "edit_content", ""
                        )
                        if "</details>" in content:
                            content = content.split("</details>")[-1]
                        chunk_count += 1
                        if settings.verbose_logging:
                            logger.debug(
                                "Streaming answer chunk: request_id={}, chunks={}, content={}",
                                request_id,
                                chunk_count,
                                content[:200]
                            )
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, chat_request.model, timestamp, 'answer'))}\n\n"

                    elif phase == "tool_call":
                        content = data.get("delta_content") or data.get(
                            "edit_content", ""
                        )
                        content = re.sub(
                            r'\n*<glm_block[^>]*>{"type": "mcp", "data": {"metadata": {',
                            "{",
                            content,
                        )
                        content = re.sub(r'", "result": "".*</glm_block>', "", content)
                        chunk_count += 1
                        if settings.verbose_logging:
                            logger.debug(
                                "Streaming tool_call chunk: request_id={}, chunks={}, content={}",
                                request_id,
                                chunk_count,
                                content[:200]
                            )
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, chat_request.model, timestamp, 'tool_call'))}\n\n"

                    elif phase == "other":
                        usage = data.get("usage", {})
                        content = data.get("delta_content", "")
                        logger.info(
                            "Streaming completion: request_id={}, model={}, total_chunks={}, usage={}",
                            request_id,
                            chat_request.model,
                            chunk_count,
                            usage,
                        )
                        if settings.verbose_logging and content:
                            logger.debug(
                                "Streaming other chunk: request_id={}, content={}",
                                request_id,
                                content[:200]
                            )
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, chat_request.model, timestamp, 'other', usage, 'stop'))}\n\n"

                    elif phase == "done":
                        logger.info(
                            "Streaming finished: request_id={}, model={}, total_chunks={}",
                            request_id,
                            chat_request.model,
                            chunk_count,
                        )
                        yield "data: [DONE]\n\n"
                        break

        except UpstreamAPIError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "Unexpected HTTP status error: status_code={}, error={}, request_id={}, user_id={}, timestamp={}",
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
                "Upstream request error: error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                type(e).__name__,
                str(e),
                request_id,
                user_id,
                timestamp,
            )
            raise UpstreamAPIError(500, f"请求错误: {str(e)}", "request_error") from e
        except Exception as e:
            logger.error(
                "Unexpected error streaming: error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                type(e).__name__,
                str(e),
                request_id,
                user_id,
                timestamp,
            )
            raise UpstreamAPIError(500, f"未知错误: {str(e)}", "unknown_error") from e