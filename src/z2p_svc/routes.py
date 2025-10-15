"""API路由模块。

本模块定义所有HTTP端点，包括聊天补全、模型列表和CORS预检请求处理。
"""

import json
from typing import AsyncGenerator, Union

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from .chat_service import (
    UpstreamAPIError,
    process_non_streaming_response,
    process_streaming_response,
)
from .config import get_settings
from .logger import get_logger
from .models import ChatRequest
from .model_service import get_models

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
async def list_models(request: Request) -> dict:
    """列出所有可用的模型。
    
    从上游API动态获取模型列表，并进行智能处理和格式化。

    :param request: FastAPI请求对象，用于获取认证信息
    :return: 包含模型列表的字典

    Example::

        >>> response = await list_models()
        >>> print(response["data"])
    """
    auth_header = request.headers.get("Authorization")
    access_token = None
    if auth_header and " " in auth_header:
        access_token = auth_header.split(" ")[-1]
    
    try:
        models_data = await get_models(access_token=access_token, use_cache=True)
        return {**models_data, "success": True}
    except Exception as e:
        logger.error("Failed to fetch models: error={}", str(e))
        logger.warning("Falling back to default models from config")
        return {"object": "list", "data": settings.ALLOWED_MODELS, "success": False}


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
    
    try:
        models_data = await get_models(access_token=access_token, use_cache=True)
        allowed_model_ids = [model["id"] for model in models_data.get("data", [])]
        
        if not allowed_model_ids:
            logger.warning("No models from upstream, using config defaults")
            allowed_model_ids = [model["id"] for model in settings.ALLOWED_MODELS]
    except Exception as e:
        logger.warning("Failed to fetch models for validation, using config defaults: error={}", str(e))
        allowed_model_ids = [model["id"] for model in settings.ALLOWED_MODELS]
    
    if chat_request.model not in allowed_model_ids:
        allowed_models = ", ".join(allowed_model_ids)
        logger.warning(
            "Invalid model requested: requested_model={}, allowed_models={}",
            chat_request.model,
            allowed_models,
        )
        return Response(
            status_code=400,
            content=json.dumps({
                "error": {
                    "message": f"Model {chat_request.model} is not allowed. Allowed models are: {allowed_models}",
                    "type": "invalid_request_error",
                    "code": 400,
                }
            }),
            media_type="application/json",
        )
    
    logger.info(
        "Chat request received: model={}, stream={}, message_count={}, api_key={}",
        chat_request.model,
        chat_request.stream,
        len(chat_request.messages),
        access_token,
    )

    try:
        if chat_request.stream:
            logger.debug("Processing streaming request")
            stream_generator = process_streaming_response(chat_request, access_token)
            
            # 预先获取第一个数据块以便在流式传输前检测错误
            try:
                first_chunk = await anext(stream_generator)
            except UpstreamAPIError as e:
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
