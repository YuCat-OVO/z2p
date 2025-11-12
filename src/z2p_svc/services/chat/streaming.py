"""流式聊天响应处理模块。

本模块负责处理与上游API的流式交互，包括流式响应解析和SSE格式转换。
"""

import re
import time
from datetime import datetime, UTC
from typing import Any, AsyncGenerator

from curl_cffi.requests import AsyncSession

# 尝试使用 orjson 加速 JSON 操作
try:
    import orjson

    def json_dumps(obj: dict) -> str:
        """使用 orjson 快速序列化"""
        return orjson.dumps(obj).decode("utf-8")

    def json_loads(s: str) -> dict:
        """使用 orjson 快速反序列化"""
        return orjson.loads(s)
except ImportError:
    import json

    json_dumps = json.dumps
    json_loads = json.loads

from ...config import get_settings
from ...exceptions import UpstreamAPIError
from ...logger import get_logger, json_str as log_json
from ...models import (
    ChatRequest,
    ChatCompletionChunk,
    ChatCompletionUsage,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
)
from ...utils.error_handler import handle_upstream_error
from ...utils.uuid_helper import generate_completion_id

logger = get_logger(__name__)
settings = get_settings()

# 预编译正则表达式（避免每次都编译，提升性能）
SUMMARY_PATTERN = re.compile(r"</summary>\n")
DETAILS_PATTERN = re.compile(r"</details>")
GLM_BLOCK_START_PATTERN = re.compile(
    r'\n*<glm_block[^>]*>{"type": "mcp", "data": {"metadata": {'
)
GLM_BLOCK_END_PATTERN = re.compile(r'", "result": "".*</glm_block>')


def create_chat_completion_chunk(
    content: str,
    model: str,
    timestamp: int,
    phase: str,
    chunk_id: str,
    usage: dict[str, Any] | None = None,
    finish_reason: str | None = None,
) -> dict[str, Any]:
    """创建聊天补全数据块（优化版：减少对象构造）。

    :param content: 响应内容
    :param model: 模型名称
    :param timestamp: 时间戳
    :param phase: 响应阶段（thinking/answer/other/tool_call）
    :param chunk_id: chunk ID（复用以减少UUID生成）
    :param usage: 使用统计信息
    :param finish_reason: 完成原因
    :return: 符合OpenAI格式的响应数据块
    """
    # 直接构造字典，避免 Pydantic 模型的开销
    delta = {"role": "assistant"}
    if phase == "thinking":
        delta["reasoning_content"] = content
    elif phase in ("answer", "tool_call", "other"):
        delta["content"] = content

    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": timestamp,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason if phase == "other" else None,
            }
        ],
    }

    if usage:
        chunk["usage"] = usage

    return chunk


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
        "id": generate_completion_id(),
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
    return f"data: {json_dumps(error_data)}\n\n"


async def process_streaming_response(
    chat_request: ChatRequest, access_token: str, prepare_request_data_func, enable_toolify: bool = False
) -> AsyncGenerator[str, None]:
    """处理流式响应。

    :param chat_request: 聊天请求对象
    :param access_token: 访问令牌
    :param prepare_request_data_func: 用于准备请求数据的函数
    :param enable_toolify: 是否启用 toolify 模式
    :yields: SSE格式的数据块
    :raises UpstreamAPIError: 当上游API返回错误状态码时

    .. note::
       响应格式遵循OpenAI的流式API规范。
    """
    async with AsyncSession(impersonate=settings.get_browser_version()) as session:  # type: ignore
        # 准备请求数据，先不传入 user_agent（使用空字符串占位）
        zai_data, params, headers = await prepare_request_data_func(
            chat_request, access_token, user_agent=""
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
            # 为日志创建数据副本，移除 model_item 以避免污染日志
            log_data = {k: v for k, v in zai_data.items() if k != "model_item"}
            logger.debug(
                "Streaming request details: request_id={}, upstream_url={}, headers={}, params={}, json_body={}",
                request_id,
                f"{settings.proxy_url}/api/chat/completions",
                log_json({
                    k: v if k.lower() != "authorization" else v[:20] + "..."
                    for k, v in headers.items()
                }),  # 脱敏 Authorization
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
                stream=True,
            )
            try:
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

                # 预创建资源以提升性能
                timestamp = int(datetime.now().timestamp())
                chunk_id = generate_completion_id()
                chunk_count = 0
                
                # 初始化 toolify 检测器
                detector = None
                if enable_toolify:
                    from ..toolify import StreamingToolCallDetector, get_toolify_core
                    toolify_core = get_toolify_core()
                    detector = StreamingToolCallDetector(toolify_core.trigger_signal)
                    logger.info(f"[TOOLIFY] 流式检测器已启用，触发信号: {toolify_core.trigger_signal}")

                # verbose logging 合并状态
                last_phase = None
                phase_chunk_count = 0
                phase_content_buffer = ""
                PHASE_LOG_INTERVAL = 32

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # curl_cffi返回bytes，需要解码
                    if isinstance(line, bytes):
                        line = line.decode("utf-8")

                    if not line.startswith("data:"):
                        continue

                    json_str = line[6:]

                    try:
                        json_object = json_loads(json_str)
                    except Exception:
                        logger.warning("Invalid JSON in stream: line={}", line[:100])
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
                        # 返回错误信息给下游
                        error_chunk = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": timestamp,
                            "model": chat_request.model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": f"\n\n[Error: {error_detail}]"},
                                "finish_reason": "content_filter"
                            }]
                        }
                        yield f"data: {json_dumps(error_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                        break

                    phase = data.get("phase")

                    # verbose logging 合并逻辑
                    if settings.verbose_logging and phase:
                        if phase != last_phase and last_phase:
                            logger.debug(
                                "Phase completed: phase={}, chunks={}, content_preview={}",
                                last_phase,
                                phase_chunk_count,
                                phase_content_buffer[:200]
                            )
                            phase_chunk_count = 0
                            phase_content_buffer = ""
                        last_phase = phase

                        # 达到间隔次数时输出中间统计
                        if phase_chunk_count > 0 and phase_chunk_count % PHASE_LOG_INTERVAL == 0:
                            logger.debug(
                                "Phase progress: phase={}, chunks={}, content_preview={}",
                                phase,
                                phase_chunk_count,
                                phase_content_buffer[:200]
                            )

                    if phase == "thinking":
                        content = data.get("delta_content", "")
                        if "</summary>\n" in content:
                            content = SUMMARY_PATTERN.split(content)[-1]
                        chunk_count += 1
                        if settings.verbose_logging:
                            phase_chunk_count += 1
                            phase_content_buffer += content
                        yield f"data: {json_dumps(create_chat_completion_chunk(content, chat_request.model, timestamp, 'thinking', chunk_id))}\n\n"

                    elif phase == "answer":
                        content = data.get("delta_content") or data.get("edit_content", "")
                        # 使用预编译正则快速清理
                        if "</details>" in content:
                            content = DETAILS_PATTERN.split(content)[-1]
                        
                        # 如果启用了 toolify，使用检测器处理内容
                        if detector:
                            is_tool, output_content = detector.process_chunk(content)
                            if output_content:
                                chunk_count += 1
                                if settings.verbose_logging:
                                    phase_chunk_count += 1
                                    phase_content_buffer += output_content
                                yield f"data: {json_dumps(create_chat_completion_chunk(output_content, chat_request.model, timestamp, 'answer', chunk_id))}\n\n"
                        else:
                            chunk_count += 1
                            if settings.verbose_logging:
                                phase_chunk_count += 1
                                phase_content_buffer += content
                            yield f"data: {json_dumps(create_chat_completion_chunk(content, chat_request.model, timestamp, 'answer', chunk_id))}\n\n"

                    elif phase == "tool_call":
                        content = data.get("delta_content") or data.get("edit_content", "")
                        content = GLM_BLOCK_START_PATTERN.sub("{", content)
                        content = GLM_BLOCK_END_PATTERN.sub("", content)
                        chunk_count += 1
                        if settings.verbose_logging:
                            phase_chunk_count += 1
                            phase_content_buffer += content
                        yield f"data: {json_dumps(create_chat_completion_chunk(content, chat_request.model, timestamp, 'tool_call', chunk_id))}\n\n"

                    elif phase == "other":
                        usage = data.get("usage", {})
                        content = data.get("delta_content") or data.get("edit_content", "")
                        logger.info(
                            "Streaming completion: request_id={}, model={}, total_chunks={}, usage={}",
                            request_id,
                            chat_request.model,
                            chunk_count,
                            log_json(usage),
                        )
                        if settings.verbose_logging and content:
                            phase_chunk_count += 1
                            phase_content_buffer += content
                        if content or usage:
                            yield f"data: {json_dumps(create_chat_completion_chunk(content, chat_request.model, timestamp, 'other', chunk_id, usage, 'stop'))}\n\n"

                    elif phase == "done":
                        # 如果启用了 toolify，finalize 检测器
                        if detector:
                            parsed_tools, remaining = detector.finalize()
                            if remaining:
                                yield f"data: {json_dumps(create_chat_completion_chunk(remaining, chat_request.model, timestamp, 'answer', chunk_id))}\n\n"
                            
                            if parsed_tools:
                                # 转换为 OpenAI 格式并发送
                                from ..toolify.parser import convert_to_openai_tool_calls
                                tool_calls = convert_to_openai_tool_calls(parsed_tools)
                                
                                # 发送 tool_calls chunk
                                tool_chunk = {
                                    "id": chunk_id,
                                    "object": "chat.completion.chunk",
                                    "created": timestamp,
                                    "model": chat_request.model,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"tool_calls": tool_calls},
                                        "finish_reason": "tool_calls"
                                    }]
                                }
                                yield f"data: {json_dumps(tool_chunk)}\n\n"
                                logger.info(f"[TOOLIFY] 发送了 {len(tool_calls)} 个工具调用")
                        
                        # 输出最后一个 phase 的统计信息
                        if settings.verbose_logging and last_phase and phase_chunk_count > 0:
                            logger.debug(
                                "Phase completed: phase={}, chunks={}, content_preview={}",
                                last_phase,
                                phase_chunk_count,
                                phase_content_buffer[:200]
                            )

                        logger.info(
                            "Streaming finished: request_id={}, model={}, total_chunks={}",
                            request_id,
                            chat_request.model,
                            chunk_count,
                        )
                        yield "data: [DONE]\n\n"
                        break

            finally:
                await response.aclose()
        except UpstreamAPIError:
            raise
        except Exception as e:
            if "status" in str(type(e).__name__).lower() or "HTTP" in str(e):
                status_code = getattr(e, "status_code", 500)
                logger.error(
                    "Unexpected HTTP status error: status_code={}, error={}, request_id={}, user_id={}, timestamp={}",
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
                    "Upstream request error: error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
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
                    "Unexpected error streaming: error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                    type(e).__name__,
                    str(e),
                    request_id,
                    user_id,
                    timestamp,
                )
                raise UpstreamAPIError(
                    500, f"未知错误: {str(e)}", "unknown_error"
                ) from e