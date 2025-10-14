"""聊天服务模块。

本模块负责处理与上游API的交互，包括消息格式转换、图片上传处理、
流式和非流式响应处理、签名生成和请求构建。
"""

import json
import re
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

import httpx

from .auth_service import get_user_info
from .config import get_settings
from .image_uploader import ImageUploader
from .logger import get_logger
from .models import ChatRequest, Message
from .signature_generator import generate_signature

logger = get_logger(__name__)
settings = get_settings()


class UpstreamAPIError(Exception):
    """上游API错误异常类。
    
    用于封装上游API返回的HTTP错误，包含状态码和错误信息。
    """
    
    def __init__(self, status_code: int, message: str, error_type: str = "upstream_error"):
        self.status_code = status_code
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)


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
    delta: dict[str, str] = {"role": "assistant"}

    if phase == "thinking":
        delta["reasoning_content"] = content
    elif phase in ("answer", "tool_call"):
        delta["content"] = content
    elif phase == "other":
        delta["content"] = content

    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
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
        "usage": usage,
    }


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
        "created": int(datetime.now().timestamp()),
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


def convert_messages(messages: list[Message]) -> dict[str, Any]:
    """转换消息格式为上游API所需格式。

    :param messages: 输入消息列表
    :return: 包含转换后的消息、图片URL和签名内容的字典
    """
    trans_messages = []
    image_urls = []
    last_user_message_text = ""

    for message in messages:
        role = message.role
        content = message.content
        
        if isinstance(content, str):
            trans_messages.append({"role": role, "content": content})
            if role == "user":
                last_user_message_text = content
        elif isinstance(content, list):
            # 处理多模态消息（文本+图片+工具调用）
            text_content = ""
            has_images = False
            dont_append = False
            new_message = {"role": role}
            
            for part in content:
                part_type = part.get("type")
                
                # 处理文本内容
                if part_type == "text":
                    text_content = part.get("text", "")
                
                # 处理图片
                elif part_type == "image_url":
                    image_url = part.get("image_url", {}).get("url", "")
                    if image_url:
                        image_urls.append(image_url)
                        has_images = True
                
                # Anthropic - 处理助理使用工具 (tool_use)
                elif part_type == "tool_use" and role == "assistant":
                    if new_message.get("tool_calls") is None:
                        new_message["tool_calls"] = []
                    
                    new_message["tool_calls"].append({
                        "id": part.get("id"),
                        "type": "function",
                        "function": {
                            "name": part.get("name"),
                            "arguments": json.dumps(part.get("input", {}) or {}, ensure_ascii=False)
                        }
                    })
                    dont_append = True
                
                # Anthropic - 处理工具结果 (tool_result)
                elif part_type == "tool_result":
                    tool_result_content = part.get("content", [])
                    
                    # 如果工具结果内容是数组，提取所有 text 类型的内容
                    if isinstance(tool_result_content, list):
                        text_parts = []
                        for item in tool_result_content:
                            if item.get("type") == "text" and item.get("text", ""):
                                text_parts.append(item.get("text"))
                        result = "".join(text_parts) if text_parts else ""
                    else:
                        result = tool_result_content
                    
                    trans_messages.append({
                        "role": "tool",
                        "tool_call_id": part.get("tool_use_id"),
                        "content": result
                    })
                    dont_append = True
            
            # 如果有文本内容，记录用于签名
            if text_content and role == "user":
                last_user_message_text = text_content
            
            # 添加消息（如果不是 tool_result 类型）
            if not dont_append and text_content:
                trans_messages.append({
                    "role": role,
                    "content": text_content
                })
            elif not dont_append and new_message.get("tool_calls"):
                # 如果有 tool_calls，添加该消息
                if text_content:
                    new_message["content"] = text_content
                trans_messages.append(new_message)

    return {
        "messages": trans_messages,
        "image_urls": image_urls,
        "last_user_message_text": last_user_message_text
    }


def get_model_features(model: str, streaming: bool) -> dict[str, Any]:
    """获取模型特性配置。

    :param model: 模型名称
    :param streaming: 是否为流式请求
    :return: 包含特性和MCP服务器配置的字典
    """
    features = {
        "image_generation": False,
        "web_search": False,
        "auto_web_search": False,
        "preview_mode": False,
        "flags": [],
        "enable_thinking": streaming,
    }

    mcp_servers = []

    if model in ("glm-4.6-search", "glm-4.6-advanced-search"):
        features["web_search"] = True
        features["auto_web_search"] = True
        features["preview_mode"] = True

    if model == "glm-4.6-nothinking":
        features["enable_thinking"] = False

    if model == "glm-4.6-advanced-search":
        mcp_servers = ["advanced-search"]

    return {"features": features, "mcp_servers": mcp_servers}


async def prepare_request_data(
    request: ChatRequest, access_token: str, streaming: bool = True
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    """准备上游API请求数据。

    :param request: 聊天请求对象
    :param access_token: 访问令牌
    :param streaming: 是否为流式请求
    :return: 包含请求数据、查询参数和请求头的元组
    """
    if settings.verbose_logging:
        logger.debug(
            "Prepare request data start: model={}, streaming={}, message_count={}",
            request.model,
            streaming,
            len(request.messages),
        )
    
    # 生成 chat_id
    chat_id = str(uuid.uuid4())
    
    # 获取用户信息（包含真实的 user_id、认证后的 token 和 cookies）
    # 传递 chat_id 以便获取聊天页面的 cookies(特别是 acw_tc)
    user_info = await get_user_info(access_token, chat_id)
    user_id = user_info["user_id"]
    auth_token = user_info["token"]  # 使用认证后的 token
    cookies = user_info["cookies"]  # 获取从上游返回的 cookies(包括聊天页面的)
    
    convert_dict = convert_messages(request.messages)

    zai_data = {
        "stream": True,
        "model": settings.MODELS_MAPPING.get(request.model),
        "messages": convert_dict["messages"],
        "chat_id": chat_id,
        "id": str(uuid.uuid4()),
    }

    # 用于签名的内容（最后一条用户消息的文本）
    signature_content = convert_dict.get("last_user_message_text", "")
    if not signature_content and zai_data["messages"]:
        # 如果没有提取到，使用最后一条消息的内容
        last_msg = zai_data["messages"][-1]
        if isinstance(last_msg.get("content"), str):
            signature_content = last_msg["content"]

    if convert_dict["image_urls"]:
        if settings.verbose_logging:
            logger.debug(
                "Processing images: image_count={}, chat_id={}",
                len(convert_dict["image_urls"]),
                zai_data["chat_id"],
            )
        
        # 使用认证后的 token 和 cookies 创建 ImageUploader
        image_uploader = ImageUploader(auth_token, zai_data["chat_id"], cookies)
        uploaded_pic_ids = []
        
        for idx, url in enumerate(convert_dict["image_urls"]):
            try:
                if settings.verbose_logging:
                    url_type = "base64" if url.startswith("data:image/") else "http" if url.startswith("http") else "unknown"
                    logger.debug(
                        "Uploading image: index={}, url_type={}, url_preview={}",
                        idx,
                        url_type,
                        url[:50],
                    )
                
                if url.startswith("data:image/"):
                    image_base64 = url.split("base64,")[-1]
                    pic_id = await image_uploader.upload_base64_image(image_base64)
                elif url.startswith("http"):
                    pic_id = await image_uploader.upload_image_from_url(url)
                else:
                    logger.warning("Unsupported image URL format: url={}", url)
                    continue

                if pic_id:
                    uploaded_pic_ids.append(pic_id)
                    if settings.verbose_logging:
                        logger.debug("Image uploaded successfully: index={}, pic_id={}", idx, pic_id)
            except Exception as e:
                logger.error("Image upload failed: url={}, error={}", url[:50], str(e))

        # 如果有图片上传成功，需要重构最后一条用户消息为多模态格式
        if uploaded_pic_ids and zai_data["messages"]:
            # 找到最后一条用户消息
            last_user_msg_idx = -1
            for i in range(len(zai_data["messages"]) - 1, -1, -1):
                if zai_data["messages"][i].get("role") == "user":
                    last_user_msg_idx = i
                    break
            
            if last_user_msg_idx >= 0:
                last_msg = zai_data["messages"][last_user_msg_idx]
                text_content = last_msg.get("content", "")
                
                # 构建多模态内容数组
                content_array = [
                    {"type": "text", "text": text_content}
                ]
                
                # 添加所有图片
                for pic_id in uploaded_pic_ids:
                    content_array.append({
                        "type": "image_url",
                        "image_url": {"url": pic_id}
                    })
                
                # 更新最后一条用户消息为多模态格式
                zai_data["messages"][last_user_msg_idx] = {
                    "role": "user",
                    "content": content_array
                }
                
                if settings.verbose_logging:
                    logger.debug(
                        "Reconstructed last user message with images: text_length={}, image_count={}",
                        len(text_content),
                        len(uploaded_pic_ids),
                    )

    features_dict = get_model_features(request.model, streaming)
    zai_data["features"] = features_dict["features"]
    if features_dict["mcp_servers"]:
        zai_data["mcp_servers"] = features_dict["mcp_servers"]

    params = {
        "requestId": str(uuid.uuid4()),
        "timestamp": str(int(time.time() * 1000)),
        "user_id": user_id,
    }

    request_params = f"requestId,{params['requestId']},timestamp,{params['timestamp']},user_id,{params['user_id']}"
    # 使用提取的文本内容进行签名（不包含图片信息）
    signature_data = generate_signature(request_params, signature_content)
    params["signature_timestamp"] = str(signature_data["timestamp"])
    
    # 添加 signature_prompt 字段
    zai_data["signature_prompt"] = signature_content

    headers = settings.HEADERS.copy()
    headers["Authorization"] = f"Bearer {auth_token}"  # 使用认证后的 token
    headers["X-Signature"] = signature_data["signature"]
    
    # 将 cookies 附加到 Cookie 头中
    if cookies:
        cookie_str = "; ".join([f"{key}={value}" for key, value in cookies.items()])
        headers["Cookie"] = cookie_str
        if settings.verbose_logging:
            logger.debug("Cookies attached to chat request: cookie_count={}, has_acw_tc={}", len(cookies), "acw_tc" in cookies)

    if settings.verbose_logging:
        logger.debug(
            "Prepare request data complete: chat_id={}, request_id={}, model_mapped={}, has_files={}, features={}",
            zai_data["chat_id"],
            params["requestId"],
            zai_data["model"],
            "files" in zai_data,
            zai_data["features"],
        )

    return zai_data, params, headers


async def process_streaming_response(
    request: ChatRequest, access_token: str
) -> AsyncGenerator[str, None]:
    """处理流式响应。

    :param request: 聊天请求对象
    :param access_token: 访问令牌
    :yields: SSE格式的数据块
    :raises UpstreamAPIError: 当上游API返回错误状态码时

    .. note::
       响应格式遵循OpenAI的流式API规范。
    """
    zai_data, params, headers = await prepare_request_data(request, access_token)
    
    # 记录请求上下文信息
    request_id = params.get("requestId", "unknown")
    user_id = params.get("user_id", "unknown")
    timestamp = params.get("timestamp", "unknown")

    if settings.verbose_logging:
        logger.debug(
            "Streaming request start: request_id={}, user_id={}, model={}, url={}",
            request_id,
            user_id,
            request.model,
            f"{settings.proxy_url}/api/chat/completions",
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
                # 检查HTTP状态码
                if response.status_code != 200:
                    # 读取响应内容
                    error_content = await response.aread()
                    error_text = error_content.decode('utf-8', errors='ignore')
                    
                    # 记录详细的错误日志
                    logger.error(
                        "Upstream HTTP error: status_code={}, response_text={}, request_id={}, user_id={}, timestamp={}, model={}, url={}",
                        response.status_code,
                        error_text[:200],
                        request_id,
                        user_id,
                        timestamp,
                        request.model,
                        str(response.url),
                    )
                    
                    # 根据状态码返回相应的错误信息
                    if response.status_code == 400:
                        error_msg = "请求参数错误：请检查请求格式和参数"
                        error_type = "bad_request_error"
                    elif response.status_code == 401:
                        error_msg = "认证失败：访问令牌无效或已过期"
                        error_type = "authentication_error"
                    elif response.status_code == 403:
                        error_msg = "权限不足：无权访问该资源"
                        error_type = "permission_error"
                    elif response.status_code == 405:
                        error_msg = "请求方法不允许：请求的HTTP方法不被支持"
                        error_type = "method_not_allowed_error"
                    elif response.status_code == 429:
                        error_msg = "请求过于频繁，请稍后再试"
                        error_type = "rate_limit_error"
                    elif response.status_code >= 500:
                        error_msg = "上游服务器错误，请稍后再试"
                        error_type = "server_error"
                    else:
                        error_msg = f"HTTP错误 {response.status_code}: {error_text[:100]}"
                        error_type = "http_error"
                    
                    # 抛出异常而不是返回错误块
                    raise UpstreamAPIError(response.status_code, error_msg, error_type)
                
                # 正常处理200响应
                if settings.verbose_logging:
                    logger.debug(
                        "Streaming response received: request_id={}, status_code={}",
                        request_id,
                        response.status_code,
                    )
                
                timestamp = int(datetime.now().timestamp())
                chunk_count = 0

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    json_str = line[6:]
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
                        if settings.verbose_logging and chunk_count % 10 == 0:
                            logger.debug("Streaming thinking progress: request_id={}, chunks={}", request_id, chunk_count)
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, request.model, timestamp, 'thinking'))}\n\n"

                    elif phase == "answer":
                        content = data.get("delta_content") or data.get("edit_content", "")
                        if "</details>" in content:
                            content = content.split("</details>")[-1]
                        chunk_count += 1
                        if settings.verbose_logging and chunk_count % 10 == 0:
                            logger.debug("Streaming answer progress: request_id={}, chunks={}", request_id, chunk_count)
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, request.model, timestamp, 'answer'))}\n\n"

                    elif phase == "tool_call":
                        content = data.get("delta_content") or data.get("edit_content", "")
                        # 清理 glm_block 标签
                        content = re.sub(r'\n*<glm_block[^>]*>{"type": "mcp", "data": {"metadata": {', '{', content)
                        content = re.sub(r'", "result": "".*</glm_block>', '', content)
                        chunk_count += 1
                        if settings.verbose_logging and chunk_count % 10 == 0:
                            logger.debug("Streaming tool_call progress: request_id={}, chunks={}", request_id, chunk_count)
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, request.model, timestamp, 'tool_call'))}\n\n"

                    elif phase == "other":
                        usage = data.get("usage", {})
                        content = data.get("delta_content", "")
                        if settings.verbose_logging:
                            logger.debug("Streaming completion: request_id={}, total_chunks={}, usage={}", request_id, chunk_count, usage)
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, request.model, timestamp, 'other', usage, 'stop'))}\n\n"

                    elif phase == "done":
                        if settings.verbose_logging:
                            logger.debug("Streaming done: request_id={}, total_chunks={}", request_id, chunk_count)
                        yield "data: [DONE]\n\n"
                        break

        except UpstreamAPIError:
            # 重新抛出上游API错误，让路由层处理
            raise
        except httpx.HTTPStatusError as e:
            # 这个异常不应该被触发，因为我们已经手动检查了状态码
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
                "http_error"
            )
        except httpx.RequestError as e:
            logger.error(
                "Upstream request error: error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                type(e).__name__,
                str(e),
                request_id,
                user_id,
                timestamp,
            )
            raise UpstreamAPIError(
                500,
                f"请求错误: {str(e)}",
                "request_error"
            )
        except Exception as e:
            logger.error(
                "Unexpected error streaming: error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                type(e).__name__,
                str(e),
                request_id,
                user_id,
                timestamp,
            )
            raise UpstreamAPIError(
                500,
                f"未知错误: {str(e)}",
                "unknown_error"
            )


async def process_non_streaming_response(
    request: ChatRequest, access_token: str
) -> dict[str, Any]:
    """处理非流式响应。

    :param request: 聊天请求对象
    :param access_token: 访问令牌
    :return: 完整的聊天补全响应
    :raises UpstreamAPIError: 当上游API返回错误状态码时

    .. note::
       响应格式遵循OpenAI的非流式API规范。
    """
    zai_data, params, headers = await prepare_request_data(request, access_token, False)
    full_response = ""
    usage = {}
    
    # 记录请求上下文信息
    request_id = params.get("requestId", "unknown")
    user_id = params.get("user_id", "unknown")
    timestamp = params.get("timestamp", "unknown")

    if settings.verbose_logging:
        logger.debug(
            "Non-streaming request start: request_id={}, user_id={}, model={}, url={}",
            request_id,
            user_id,
            request.model,
            f"{settings.proxy_url}/api/chat/completions",
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
                # 检查HTTP状态码
                if response.status_code != 200:
                    error_content = await response.aread()
                    error_text = error_content.decode('utf-8', errors='ignore')
                    
                    # 记录详细的错误日志
                    logger.error(
                        "Upstream HTTP error (non-streaming): status_code={}, response_text={}, request_id={}, user_id={}, timestamp={}, model={}, url={}",
                        response.status_code,
                        error_text[:200],
                        request_id,
                        user_id,
                        timestamp,
                        request.model,
                        str(response.url),
                    )
                    
                    # 根据状态码返回相应的错误信息
                    if response.status_code == 400:
                        error_msg = "请求参数错误：请检查请求格式和参数"
                        error_type = "bad_request_error"
                    elif response.status_code == 401:
                        error_msg = "认证失败：访问令牌无效或已过期"
                        error_type = "authentication_error"
                    elif response.status_code == 403:
                        error_msg = "权限不足：无权访问该资源"
                        error_type = "permission_error"
                    elif response.status_code == 405:
                        error_msg = "请求方法不允许：请求的HTTP方法不被支持"
                        error_type = "method_not_allowed_error"
                    elif response.status_code == 429:
                        error_msg = "请求过于频繁，请稍后再试"
                        error_type = "rate_limit_error"
                    elif response.status_code >= 500:
                        error_msg = "上游服务器错误，请稍后再试"
                        error_type = "server_error"
                    else:
                        error_msg = f"HTTP错误 {response.status_code}: {error_text[:100]}"
                        error_type = "http_error"
                    
                    # 抛出异常而不是返回错误对象
                    raise UpstreamAPIError(response.status_code, error_msg, error_type)
                
                # 正常处理200响应
                if settings.verbose_logging:
                    logger.debug(
                        "Non-streaming response received: request_id={}, status_code={}",
                        request_id,
                        response.status_code,
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
                        if settings.verbose_logging:
                            logger.debug(
                                "Non-streaming completion: request_id={}, chunks={}, response_length={}, usage={}",
                                request_id,
                                chunk_count,
                                len(full_response),
                                usage,
                            )

        except UpstreamAPIError:
            # 重新抛出上游API错误，让路由层处理
            raise
        except httpx.HTTPStatusError as e:
            # 这个异常不应该被触发，因为我们已经手动检查了状态码
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
                "http_error"
            )
        except httpx.RequestError as e:
            logger.error(
                "Upstream request error (non-streaming): error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                type(e).__name__,
                str(e),
                request_id,
                user_id,
                timestamp,
            )
            raise UpstreamAPIError(
                500,
                f"请求错误: {str(e)}",
                "request_error"
            )
        except Exception as e:
            logger.error(
                "Unexpected error (non-streaming): error_type={}, error={}, request_id={}, user_id={}, timestamp={}",
                type(e).__name__,
                str(e),
                request_id,
                user_id,
                timestamp,
            )
            raise UpstreamAPIError(
                500,
                f"未知错误: {str(e)}",
                "unknown_error"
            )

    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": full_response},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }
