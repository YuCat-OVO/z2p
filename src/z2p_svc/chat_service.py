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

from .config import get_settings
from .file_uploader import FileUploader
from .logger import get_logger
from .models import ChatRequest, Message
from .signature_generator import generate_signature

logger = get_logger(__name__)
settings = get_settings()


def is_aliyun_blocked_response(response_text: str) -> bool:
    """检测是否为阿里云拦截的405响应。
    
    阿里云的拦截响应包含特定的HTML特征：
    - 包含 "data-spm" 属性
    - 包含 "block_message" 或 "block_traceid" 等特定ID
    - 包含阿里云错误图片URL
    
    :param response_text: HTTP响应文本内容
    :return: 如果是阿里云拦截响应返回True，否则返回False
    """
    if not response_text:
        return False
    
    # 检查阿里云拦截响应的特征标识
    aliyun_indicators = [
        'data-spm',
        'block_message',
        'block_traceid',
        'errors.aliyun.com',
        'potential threats to the server',
        '由于您访问的URL有可能对网站造成安全威胁'
    ]
    
    # 如果包含多个特征标识，则判定为阿里云拦截
    matches = sum(1 for indicator in aliyun_indicators if indicator in response_text)
    return matches >= 2


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
    :return: 包含转换后的消息、文件URL（包括图片和其他文件）和签名内容的字典
    """
    trans_messages = []
    file_urls = []
    last_user_message_text = ""

    for message in messages:
        role = message.role
        content = message.content
        
        if isinstance(content, str):
            trans_messages.append({"role": role, "content": content})
            if role == "user":
                last_user_message_text = content
        elif isinstance(content, list):
            text_content = ""
            dont_append = False
            new_message = {"role": role}
            
            for part in content:
                part_type = part.get("type")
                
                if part_type == "text":
                    text_content = part.get("text", "")
                
                elif part_type == "image_url":
                    file_url = part.get("image_url", {}).get("url", "")
                    if file_url:
                        file_urls.append(file_url)
                
                elif part_type == "file":
                    file_url = part.get("url", "")
                    if file_url:
                        file_urls.append(file_url)
                
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
                
                elif part_type == "tool_result":
                    tool_result_content = part.get("content", [])
                    
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
            
            if text_content and role == "user":
                last_user_message_text = text_content
            
            if not dont_append and text_content:
                trans_messages.append({
                    "role": role,
                    "content": text_content
                })
            elif not dont_append and new_message.get("tool_calls"):
                if text_content:
                    new_message["content"] = text_content
                trans_messages.append(new_message)

    return {
        "messages": trans_messages,
        "file_urls": file_urls,
        "last_user_message_text": last_user_message_text
    }


def get_model_features(model: str, streaming: bool) -> dict[str, Any]:
    """获取模型特性配置。
    
    根据模型ID自动识别并配置相应的功能开关：
    - nothinking: 禁用深度思考
    - search: 启用网络搜索
    - advanced-search: 启用高级搜索（包含MCP服务器）

    :param model: 模型名称
    :param streaming: 是否为流式请求
    :return: 包含特性和MCP服务器配置的字典
    """
    features = {
        "web_search": False,
        "auto_web_search": False,
        "preview_mode": False,
        "flags": [],
        "enable_thinking": True,
    }

    mcp_servers = []
    
    model_lower = model.lower()

    if "nothinking" in model_lower:
        features["enable_thinking"] = False
        if settings.verbose_logging:
            logger.debug("Model feature detected: nothinking disabled for model={}", model)
    elif not streaming:
        features["enable_thinking"] = False
        if settings.verbose_logging:
            logger.debug("Thinking disabled for non-streaming request: model={}", model)

    if "search" in model_lower:
        features["web_search"] = True
        features["auto_web_search"] = True
        features["preview_mode"] = True
        if settings.verbose_logging:
            logger.debug("Model feature detected: search enabled for model={}", model)
        
        if "advanced" in model_lower:
            mcp_servers = ["advanced-search"]
            if settings.verbose_logging:
                logger.debug("Model feature detected: advanced-search MCP server enabled for model={}", model)

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
    logger.info(
        "Preparing request data: model={}, streaming={}, message_count={}",
        request.model,
        streaming,
        len(request.messages),
    )
    
    # 预加载模型映射表以支持动态模型ID转换
    from .model_service import get_models
    try:
        await get_models(access_token=access_token, use_cache=True)
    except Exception as e:
        logger.warning(
            "Failed to fetch models for mapping initialization: error={}. Will use existing mappings.",
            str(e)
        )
    
    convert_dict = convert_messages(request.messages)
    
    chat_id = str(uuid.uuid4())
    
    user_id = "anonymous"
    auth_token = access_token
    cookies = {}

    # 将客户端模型ID转换为上游API识别的模型ID
    upstream_model_id = settings.REVERSE_MODELS_MAPPING.get(request.model)
    
    if upstream_model_id:
        if settings.verbose_logging:
            logger.debug(
                "Model mapped via REVERSE_MODELS_MAPPING: {} -> {}",
                request.model,
                upstream_model_id
            )
    else:
        upstream_model_id = request.model
        logger.warning(
            "No reverse mapping found for model={}, using original ID. This may cause upstream API errors.",
            request.model
        )
    
    zai_data = {
        "stream": True,
        "model": upstream_model_id,
        "messages": convert_dict["messages"],
        "chat_id": chat_id,
        "id": str(uuid.uuid4()),
    }

    # 提取用户最后一条消息文本用于签名生成
    signature_content = convert_dict.get("last_user_message_text", "")
    if not signature_content and zai_data["messages"]:
        last_msg = zai_data["messages"][-1]
        if isinstance(last_msg.get("content"), str):
            signature_content = last_msg["content"]

    if convert_dict.get("file_urls"):
        file_urls = convert_dict.get("file_urls", [])
        logger.info(
            "File upload processing started: file_count={}, model={}, chat_id={}, request_id={}",
            len(file_urls),
            request.model,
            zai_data["chat_id"],
            zai_data["id"],
        )
        
        file_uploader = FileUploader(auth_token, zai_data["chat_id"], cookies)
        uploaded_file_ids = []
        
        # 遍历所有文件URL并根据协议类型选择上传方式
        for idx, url in enumerate(file_urls):
            try:
                if url.startswith("data:"):
                    url_type = "base64"
                elif url.startswith("http"):
                    url_type = "http"
                else:
                    url_type = "unknown"
                
                logger.info(
                    "File upload attempt: index={}/{}, url_type={}, url_preview={}, request_id={}",
                    idx + 1,
                    len(file_urls),
                    url_type,
                    url[:80] if len(url) > 80 else url,
                    zai_data["id"],
                )
                
                # 处理base64编码的数据URL
                if url.startswith("data:"):
                    if ";base64," in url:
                        header, base64_data = url.split(";base64,", 1)
                        mime_type = header.split(":", 1)[1] if ":" in header else ""
                        
                        # 根据MIME类型推断文件扩展名
                        file_ext = None
                        if mime_type.startswith("image/"):
                            file_ext = mime_type.split("/")[1]
                        elif "pdf" in mime_type:
                            file_ext = "pdf"
                        elif "word" in mime_type or "msword" in mime_type:
                            file_ext = "docx" if "openxmlformats" in mime_type else "doc"
                        elif "sheet" in mime_type or "excel" in mime_type:
                            file_ext = "xlsx" if "openxmlformats" in mime_type else "xls"
                        elif "presentation" in mime_type or "powerpoint" in mime_type:
                            file_ext = "pptx" if "openxmlformats" in mime_type else "ppt"
                        elif "text/plain" in mime_type:
                            file_ext = "txt"
                        elif "text/markdown" in mime_type:
                            file_ext = "md"
                        elif "text/csv" in mime_type:
                            file_ext = "csv"
                        elif "python" in mime_type:
                            file_ext = "py"
                        
                        file_id = await file_uploader.upload_base64_file(base64_data, file_type=file_ext)
                    else:
                        logger.warning("Unsupported data URL format (missing base64): url={}", url[:50])
                        continue
                
                # 处理HTTP/HTTPS URL
                elif url.startswith("http"):
                    file_id = await file_uploader.upload_file_from_url(url)
                
                else:
                    logger.warning("Unsupported file URL format: url={}", url[:50])
                    continue

                if file_id:
                    uploaded_file_ids.append(file_id)
                    logger.info(
                        "File uploaded successfully: index={}/{}, file_id={}, request_id={}",
                        idx + 1,
                        len(file_urls),
                        file_id,
                        zai_data["id"],
                    )
                else:
                    logger.warning(
                        "File upload returned no ID: index={}/{}, url_preview={}, request_id={}",
                        idx + 1,
                        len(file_urls),
                        url[:80] if len(url) > 80 else url,
                        zai_data["id"],
                    )
            except Exception as e:
                logger.error(
                    "File upload failed: index={}/{}, url_preview={}, error={}, request_id={}",
                    idx + 1,
                    len(file_urls),
                    url[:80] if len(url) > 80 else url,
                    str(e),
                    zai_data["id"],
                )

        if uploaded_file_ids:
            logger.info(
                "File upload completed: total_files={}, successful={}, failed={}, model={}, request_id={}",
                len(file_urls),
                len(uploaded_file_ids),
                len(file_urls) - len(uploaded_file_ids),
                request.model,
                zai_data["id"],
            )
        else:
            logger.warning(
                "No files uploaded successfully: total_files={}, model={}, request_id={}",
                len(file_urls),
                request.model,
                zai_data["id"],
            )
        
        # 将上传成功的文件ID附加到最后一条用户消息中
        if uploaded_file_ids and zai_data["messages"]:
            last_user_msg_idx = -1
            for i in range(len(zai_data["messages"]) - 1, -1, -1):
                if zai_data["messages"][i].get("role") == "user":
                    last_user_msg_idx = i
                    break
            
            if last_user_msg_idx >= 0:
                last_msg = zai_data["messages"][last_user_msg_idx]
                text_content = last_msg.get("content", "")
                
                content_array = [
                    {"type": "text", "text": text_content}
                ]
                
                for file_id in uploaded_file_ids:
                    content_array.append({
                        "type": "image_url",
                        "image_url": {"url": file_id}
                    })
                
                zai_data["messages"][last_user_msg_idx] = {
                    "role": "user",
                    "content": content_array
                }
                
                logger.info(
                    "Message reconstructed with files: text_length={}, file_count={}, request_id={}",
                    len(text_content),
                    len(uploaded_file_ids),
                    zai_data["id"],
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
    signature_data = generate_signature(request_params, signature_content)
    params["signature_timestamp"] = str(signature_data["timestamp"])
    
    zai_data["signature_prompt"] = signature_content

    headers = settings.HEADERS.copy()
    headers["Authorization"] = f"Bearer {auth_token}"
    headers["X-Signature"] = signature_data["signature"]

    files_processed = bool(convert_dict.get("file_urls"))
    logger.info(
        "Request data prepared successfully: chat_id={}, request_id={}, model={}, upstream_model={}, streaming={}, files_processed={}, features={}",
        zai_data["chat_id"],
        params["requestId"],
        request.model,
        zai_data["model"],
        streaming,
        files_processed,
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
    
    request_id = params.get("requestId", "unknown")
    user_id = params.get("user_id", "unknown")
    timestamp = params.get("timestamp", "unknown")

    logger.info(
        "Streaming request initiated: request_id={}, user_id={}, model={}, upstream_url={}",
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
                if response.status_code != 200:
                    error_content = await response.aread()
                    error_text = error_content.decode('utf-8', errors='ignore')
                    
                    # 检测是否为阿里云拦截的405响应
                    if response.status_code == 405 and is_aliyun_blocked_response(error_text):
                        logger.warning(
                            "Aliyun blocked request detected (405 -> 429): request_id={}, user_id={}, timestamp={}, model={}, url={}",
                            request_id,
                            user_id,
                            timestamp,
                            request.model,
                            str(response.url),
                        )
                        # 将阿里云的405拦截转换为429限流错误
                        error_msg = "请求过于频繁：同一IP多次请求被拦截，请稍后再试"
                        error_type = "rate_limit_error"
                        raise UpstreamAPIError(429, error_msg, error_type)
                    
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
                    
                    raise UpstreamAPIError(response.status_code, error_msg, error_type)
                
                logger.info(
                    "Streaming response started: request_id={}, status_code={}, model={}",
                    request_id,
                    response.status_code,
                    request.model,
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
                        content = re.sub(r'\n*<glm_block[^>]*>{"type": "mcp", "data": {"metadata": {', '{', content)
                        content = re.sub(r'", "result": "".*</glm_block>', '', content)
                        chunk_count += 1
                        if settings.verbose_logging and chunk_count % 10 == 0:
                            logger.debug("Streaming tool_call progress: request_id={}, chunks={}", request_id, chunk_count)
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, request.model, timestamp, 'tool_call'))}\n\n"

                    elif phase == "other":
                        usage = data.get("usage", {})
                        content = data.get("delta_content", "")
                        logger.info(
                            "Streaming completion: request_id={}, model={}, total_chunks={}, usage={}",
                            request_id,
                            request.model,
                            chunk_count,
                            usage
                        )
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, request.model, timestamp, 'other', usage, 'stop'))}\n\n"

                    elif phase == "done":
                        logger.info(
                            "Streaming finished: request_id={}, model={}, total_chunks={}",
                            request_id,
                            request.model,
                            chunk_count
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
    
    request_id = params.get("requestId", "unknown")
    user_id = params.get("user_id", "unknown")
    timestamp = params.get("timestamp", "unknown")

    logger.info(
        "Non-streaming request initiated: request_id={}, user_id={}, model={}, upstream_url={}",
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
                if response.status_code != 200:
                    error_content = await response.aread()
                    error_text = error_content.decode('utf-8', errors='ignore')
                    
                    # 检测是否为阿里云拦截的405响应
                    if response.status_code == 405 and is_aliyun_blocked_response(error_text):
                        logger.warning(
                            "Aliyun blocked request detected (405 -> 429) (non-streaming): request_id={}, user_id={}, timestamp={}, model={}, url={}",
                            request_id,
                            user_id,
                            timestamp,
                            request.model,
                            str(response.url),
                        )
                        # 将阿里云的405拦截转换为429限流错误
                        error_msg = "请求过于频繁：同一IP多次请求被拦截，请稍后再试"
                        error_type = "rate_limit_error"
                        raise UpstreamAPIError(429, error_msg, error_type)
                    
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
                    
                    raise UpstreamAPIError(response.status_code, error_msg, error_type)
                
                logger.info(
                    "Non-streaming response started: request_id={}, status_code={}, model={}",
                    request_id,
                    response.status_code,
                    request.model,
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
                            request.model,
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
