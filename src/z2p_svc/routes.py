"""API路由模块。

本模块定义所有HTTP端点，包括聊天补全、模型列表和CORS预检请求处理。
"""

import json
from typing import Union

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from .chat_service import process_non_streaming_response, process_streaming_response
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
    :raises HTTPException: 当模型不在允许列表中时

    .. note::
       需要在Authorization头中提供Bearer token。
    """
    logger.info(
        "chat_request_received",
        model=chat_request.model,
        stream=chat_request.stream,
        message_count=len(chat_request.messages),
    )

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        logger.warning("missing_authorization_header")
        return Response(
            status_code=401,
            content=json.dumps({"message": "Unauthorized: Access token is missing"}),
            media_type="application/json",
        )

    access_token = auth_header.split(" ")[-1] if " " in auth_header else auth_header

    if chat_request.model not in [model["id"] for model in settings.ALLOWED_MODELS]:
        allowed_models = ", ".join(model["id"] for model in settings.ALLOWED_MODELS)
        logger.warning(
            "invalid_model_requested",
            requested_model=chat_request.model,
            allowed_models=allowed_models,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Model {chat_request.model} is not allowed. Allowed models are: {allowed_models}",
        )

    if chat_request.stream:
        logger.debug("processing_streaming_request")
        return StreamingResponse(
            process_streaming_response(chat_request, access_token),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
            },
        )
    else:
        logger.debug("processing_non_streaming_request")
        return await process_non_streaming_response(chat_request, access_token)
