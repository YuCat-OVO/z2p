"""非流式聊天响应处理模块。

本模块负责处理与上游API的非流式交互，包括非流式响应解析和结果构建。
"""

import json
import uuid
import re
import codecs
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
    reasoning_content = ""
    usage_info = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

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
            },
            params,
            zai_data,
        )

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            async with client.stream(
                method="POST",
                url=f"{settings.proxy_url}/api/chat/completions",
                headers=headers,
                params=params,
                json=zai_data,
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
                    
                    # 输出原始SSE数据块
                    if settings.verbose_logging:
                        logger.debug(
                            "Non-streaming SSE line: request_id={}, data={}",
                            request_id,
                            json_str[:300]
                        )
                    
                    if not json_str or json_str in ("[DONE]", "DONE", "done"):
                        if json_str in ("[DONE]", "DONE", "done"):
                            logger.info(
                                "Non-streaming [DONE] received: request_id={}",
                                request_id
                            )
                        break

                    try:
                        json_object = json.loads(json_str)
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON in non-stream: line={}", line[:100])
                        continue

                    if json_object.get("type") != "chat:completion":
                        continue

                    data = json_object.get("data", {})
                    phase = data.get("phase")
                    delta_content = data.get("delta_content", "")
                    edit_content = data.get("edit_content", "")

                    # 记录用量
                    if data.get("usage"):
                        usage_info = data["usage"]
                        if settings.verbose_logging:
                            logger.debug(
                                "Non-streaming usage received: request_id={}, usage={}",
                                request_id,
                                usage_info
                            )

                    # 处理tool_call阶段
                    if phase == "tool_call":
                        if edit_content and "<glm_block" in edit_content and "search" in edit_content:
                            try:
                                decoded = edit_content
                                try:
                                    decoded = edit_content.encode('utf-8').decode('unicode_escape').encode('latin1').decode('utf-8')
                                except:
                                    try:
                                        decoded = codecs.decode(edit_content, 'unicode_escape')
                                    except:
                                        pass
                                
                                queries_match = re.search(r'"queries":\s*\[(.*?)\]', decoded)
                                if queries_match:
                                    queries_str = queries_match.group(1)
                                    queries = re.findall(r'"([^"]+)"', queries_str)
                                    if queries:
                                        search_info = "🔍 **搜索：** " + "　".join(queries[:5])
                                        reasoning_content += f"\n\n{search_info}\n\n"
                            except Exception:
                                pass
                        continue

                    # 思考阶段
                    elif phase == "thinking":
                        if delta_content:
                            if delta_content.startswith("<details"):
                                cleaned = (
                                    delta_content.split("</summary>\n>")[-1].strip()
                                    if "</summary>\n>" in delta_content
                                    else delta_content
                                )
                            else:
                                cleaned = delta_content
                            reasoning_content += cleaned
                            chunk_count += 1
                            if settings.verbose_logging:
                                logger.debug(
                                    "Non-streaming thinking chunk: request_id={}, content={}",
                                    request_id,
                                    cleaned[:200]
                                )
                    
                    # 答案阶段
                    elif phase == "answer":
                        if edit_content and "</details>\n" in edit_content:
                            content_after = edit_content.split("</details>\n")[-1]
                            if content_after:
                                full_response += content_after
                                if settings.verbose_logging:
                                    logger.debug(
                                        "Non-streaming answer chunk (from edit): request_id={}, length={}",
                                        request_id,
                                        len(content_after)
                                    )
                        elif delta_content:
                            full_response += delta_content
                            if settings.verbose_logging:
                                logger.debug(
                                    "Non-streaming answer chunk: request_id={}, length={}",
                                    request_id,
                                    len(delta_content)
                                )
                        chunk_count += 1
                    
                    # other阶段
                    elif phase == "other":
                        if delta_content:
                            full_response += delta_content
                            if settings.verbose_logging:
                                logger.debug(
                                    "Non-streaming other chunk: request_id={}, content={}",
                                    request_id,
                                    delta_content[:200]
                                )
                        chunk_count += 1
                        # 检查是否有done标记，如果有则结束
                        if data.get("done"):
                            logger.info(
                                "Non-streaming done in other phase: request_id={}",
                                request_id
                            )
                            break
                    
                    # done阶段
                    elif phase == "done":
                        logger.info(
                            "Non-streaming done signal: request_id={}",
                            request_id
                        )
                        break

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

    # 清理并返回
    full_response = (full_response or "").strip()
    reasoning_content = (reasoning_content or "").strip()
    
    # 若没有聚合到答案，但有思考内容，则保底返回思考内容
    if not full_response and reasoning_content:
        full_response = reasoning_content

    logger.info(
        "Non-streaming completion: request_id={}, model={}, chunks={}, response_length={}, usage={}",
        request_id,
        chat_request.model,
        chunk_count,
        len(full_response),
        usage_info,
    )

    # 使用 Pydantic 模型构建响应
    message = ChatCompletionMessage(role="assistant", content=full_response)
    choice = ChatCompletionChoice(index=0, message=message, finish_reason="stop")

    response = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4()}",
        created=int(datetime.now().timestamp()),
        model=chat_request.model,
        choices=[choice],
        usage=ChatCompletionUsage(**usage_info) if usage_info else None,
    )
    
    return response.model_dump(exclude_none=True)