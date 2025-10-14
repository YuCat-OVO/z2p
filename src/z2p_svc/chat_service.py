"""聊天服务模块。

本模块负责处理与上游API的交互，包括消息格式转换、图片上传处理、
流式和非流式响应处理、签名生成和请求构建。
"""

import json
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

import httpx

from .config import get_settings
from .image_uploader import ImageUploader
from .logger import get_logger
from .models import ChatRequest, Message
from .signature_generator import generate_signature

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


def convert_messages(messages: list[Message]) -> dict[str, Any]:
    """转换消息格式为上游API所需格式。

    :param messages: 输入消息列表
    :return: 包含转换后的消息和图片URL的字典
    """
    trans_messages = []
    image_urls = []

    for message in messages:
        if isinstance(message.content, str):
            trans_messages.append({"role": message.role, "content": message.content})
        elif isinstance(message.content, list):
            for part in message.content:
                if part.get("type") == "text":
                    trans_messages.append(
                        {"role": "user", "content": part.get("text", "")}
                    )
                elif part.get("type") == "image_url":
                    image_url = part.get("image_url", {}).get("url", "")
                    if image_url:
                        image_urls.append(image_url)

    return {"messages": trans_messages, "image_urls": image_urls}


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
    convert_dict = convert_messages(request.messages)

    zai_data = {
        "stream": True,
        "model": settings.MODELS_MAPPING.get(request.model),
        "messages": convert_dict["messages"],
        "chat_id": str(uuid.uuid4()),
        "id": str(uuid.uuid4()),
    }

    if convert_dict["image_urls"]:
        image_uploader = ImageUploader(access_token)
        files = []
        for url in convert_dict["image_urls"]:
            try:
                if url.startswith("data:image/"):
                    image_base64 = url.split("base64,")[-1]
                    pic_id = await image_uploader.upload_base64_image(image_base64)
                elif url.startswith("http"):
                    pic_id = await image_uploader.upload_image_from_url(url)
                else:
                    logger.warning("unsupported_image_url_format", url=url)
                    continue

                if pic_id:
                    files.append({"type": "image", "id": pic_id})
            except Exception as e:
                logger.error("image_upload_failed", url=url[:50], error=str(e))

        if files:
            zai_data["files"] = files

    features_dict = get_model_features(request.model, streaming)
    zai_data["features"] = features_dict["features"]
    if features_dict["mcp_servers"]:
        zai_data["mcp_servers"] = features_dict["mcp_servers"]

    params = {
        "requestId": str(uuid.uuid4()),
        "timestamp": str(int(time.time() * 1000)),
        "user_id": str(uuid.uuid4()),
    }

    request_params = f"requestId,{params['requestId']},timestamp,{params['timestamp']},user_id,{params['user_id']}"
    content = zai_data["messages"][-1]["content"]
    signature_data = generate_signature(request_params, content)
    params["signature_timestamp"] = str(signature_data["timestamp"])

    headers = settings.HEADERS.copy()
    headers["Authorization"] = f"Bearer {access_token}"
    headers["X-Signature"] = signature_data["signature"]

    return zai_data, params, headers


async def process_streaming_response(
    request: ChatRequest, access_token: str
) -> AsyncGenerator[str, None]:
    """处理流式响应。

    :param request: 聊天请求对象
    :param access_token: 访问令牌
    :yields: SSE格式的数据块

    .. note::
       响应格式遵循OpenAI的流式API规范。
    """
    zai_data, params, headers = await prepare_request_data(request, access_token)

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
                response.raise_for_status()
                timestamp = int(datetime.now().timestamp())

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    json_str = line[6:]
                    try:
                        json_object = json.loads(json_str)
                    except json.JSONDecodeError:
                        logger.warning("invalid_json_in_stream", line=line[:100])
                        continue

                    data = json_object.get("data", {})
                    phase = data.get("phase")

                    if phase == "thinking":
                        content = data.get("delta_content", "")
                        if "</summary>\n" in content:
                            content = content.split("</summary>\n")[-1]
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, request.model, timestamp, 'thinking'))}\n\n"

                    elif phase == "answer":
                        content = data.get("delta_content") or data.get("edit_content", "")
                        if "</details>" in content:
                            content = content.split("</details>")[-1]
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, request.model, timestamp, 'answer'))}\n\n"

                    elif phase == "other":
                        usage = data.get("usage", {})
                        content = data.get("delta_content", "")
                        yield f"data: {json.dumps(create_chat_completion_chunk(content, request.model, timestamp, 'other', usage, 'stop'))}\n\n"

                    elif phase == "done":
                        yield "data: [DONE]\n\n"
                        break

        except httpx.HTTPStatusError as e:
            logger.error(
                "http_error",
                status_code=e.response.status_code,
                response_text=e.response.text[:200],
            )
        except httpx.RequestError as e:
            logger.error("request_error", error=str(e))


async def process_non_streaming_response(
    request: ChatRequest, access_token: str
) -> dict[str, Any]:
    """处理非流式响应。

    :param request: 聊天请求对象
    :param access_token: 访问令牌
    :return: 完整的聊天补全响应

    .. note::
       响应格式遵循OpenAI的非流式API规范。
    """
    zai_data, params, headers = await prepare_request_data(request, access_token, False)
    full_response = ""
    usage = {}

    async with httpx.AsyncClient() as client:
        async with client.stream(
            method="POST",
            url=f"{settings.proxy_url}/api/chat/completions",
            headers=headers,
            params=params,
            json=zai_data,
            timeout=300,
        ) as response:
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
                elif phase == "other":
                    usage = data.get("usage", {})
                    content = data.get("delta_content", "")
                    full_response += content

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
