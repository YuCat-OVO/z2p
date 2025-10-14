"""API路由模块。

本模块定义所有HTTP端点，包括聊天补全、模型列表和CORS预检请求处理。
"""

import json
from typing import AsyncGenerator, Union

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from .chat_service import (
    UpstreamAPIError,
    process_non_streaming_response,
    process_streaming_response,
)
from .config import get_settings
from .logger import get_logger
from .models import ChatRequest

logger = get_logger(__name__)
router = APIRouter()
settings = get_settings()


@router.options("/chat/completions")
async def chat_completions_options() -> Response:
    """处理CORS预检请求。

    :return: 包含CORS头的响应
    """
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
    )


@router.get("/models")
async def list_models() -> dict:
    """列出所有可用的模型。

    :return: 包含模型列表的字典

    Example::

        >>> response = await list_models()
        >>> print(response["data"])
    """
    return {"object": "list", "data": settings.ALLOWED_MODELS, "success": True}


@router.post("/chat/completions", response_model=None)
async def chat_completions(request: Request, chat_request: ChatRequest) -> Union[Response, StreamingResponse]:
    """处理聊天补全请求。

    支持流式和非流式两种响应模式，根据chat_request.stream参数决定。

    :param request: FastAPI请求对象，用于获取认证信息
    :param chat_request: 聊天请求参数
    :return: 流式响应或JSON响应
    :raises HTTPException: 当模型不在允许列表中或上游API出错时

    .. note::
       需要在Authorization头中提供Bearer token。
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        logger.warning("Missing authorization header")
        return Response(
            status_code=401,
            content=json.dumps({"message": "Unauthorized: Access token is missing"}),
            media_type="application/json",
        )

    access_token = auth_header.split(" ")[-1] if " " in auth_header else auth_header
    
    # INFO级别：记录请求和API Key（脱敏）用于审计
    token_preview = f"{access_token}" if len(access_token) > 12 else "***"
    logger.info(
        "Chat request received: model={}, stream={}, message_count={}, api_key={}",
        chat_request.model,
        chat_request.stream,
        len(chat_request.messages),
        token_preview,
    )

    if chat_request.model not in [model["id"] for model in settings.ALLOWED_MODELS]:
        allowed_models = ", ".join(model["id"] for model in settings.ALLOWED_MODELS)
        logger.warning(
            "Invalid model requested: requested_model={}, allowed_models={}",
            chat_request.model,
            allowed_models,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Model {chat_request.model} is not allowed. Allowed models are: {allowed_models}",
        )

    try:
        if chat_request.stream:
            logger.debug("Processing streaming request")
            # 创建生成器
            stream_generator = process_streaming_response(chat_request, access_token)
            
            # 尝试获取第一个数据块以提前检测错误
            try:
                first_chunk = await anext(stream_generator)
            except UpstreamAPIError as e:
                # 如果在开始流式传输前就出错,直接返回错误响应
                logger.error(
                    "Upstream API error before streaming: status_code={}, error_message={}, error_type={}, model={}",
                    e.status_code,
                    e.message,
                    e.error_type,
                    chat_request.model,
                )
                return Response(
                    status_code=e.status_code,
                    content=json.dumps({
                        "error": {
                            "message": e.message,
                            "type": e.error_type,
                            "code": e.status_code,
                        }
                    }),
                    media_type="application/json",
                )
            
            # 创建新的生成器,首先产出第一个数据块,然后继续原生成器
            async def stream_with_first_chunk() -> AsyncGenerator[str, None]:
                yield first_chunk
                async for chunk in stream_generator:
                    yield chunk
            
            return StreamingResponse(
                stream_with_first_chunk(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Transfer-Encoding": "chunked",
                },
            )
        else:
            logger.debug("Processing non-streaming request")
            return await process_non_streaming_response(chat_request, access_token)
    except UpstreamAPIError as e:
        # 捕获上游API错误并返回相应的HTTP错误响应
        logger.error(
            "Upstream API error in route: status_code={}, error_message={}, error_type={}, model={}",
            e.status_code,
            e.message,
            e.error_type,
            chat_request.model,
        )
        return Response(
            status_code=e.status_code,
            content=json.dumps({
                "error": {
                    "message": e.message,
                    "type": e.error_type,
                    "code": e.status_code,
                }
            }),
            media_type="application/json",
        )
