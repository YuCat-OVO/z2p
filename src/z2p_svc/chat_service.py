"""聊天服务模块。

本模块负责处理与上游API的交互，包括消息格式转换、图片上传处理、
流式和非流式响应处理、签名生成和请求构建。
"""

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator


from .config import get_settings
from .file_uploader import FileUploader
from .logger import get_logger
from .models import (
    ChatRequest,
    ModelFeatures,
    UpstreamRequestData,
    UpstreamRequestParams,
)
from .signature_generator import generate_signature
from .services.chat.converter import convert_messages
from .services.chat.streaming import process_streaming_response as _process_streaming_response
from .services.chat.non_streaming import process_non_streaming_response as _process_non_streaming_response

logger = get_logger(__name__)
settings = get_settings()




def get_model_features(model: str, streaming: bool, model_capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
    """获取模型特性配置。
    
    根据模型 ID 自动识别并配置功能开关。支持通过模型名称后缀
    控制特性（如 ``-nothinking``、``-search``、``-advanced-search``）。
    
    :param model: 模型名称（客户端请求的模型 ID，可能包含功能后缀）
    :param streaming: 是否为流式请求
    :param model_capabilities: 上游模型的能力配置（从模型列表获取）
    :type model: str
    :type streaming: bool
    :type model_capabilities: dict[str, Any] | None
    :return: 包含特性配置和 MCP 服务器列表的字典
    :rtype: dict[str, Any]
    
    **返回字典结构:**
    
    .. code-block:: python
    
       {
           "features": {
               "enable_thinking": bool,
               "web_search": bool,
               "auto_web_search": bool,
               "preview_mode": bool
           },
           "mcp_servers": List[str]
       }
    
    **支持的模型后缀:**
    
    - ``-nothinking``: 禁用深度思考功能
    - ``-search``: 启用网络搜索
    - ``-advanced-search``: 启用高级搜索（包含 MCP 服务器）
    
    .. note::
       非流式请求会自动禁用 thinking 功能
    """
    # 使用 Pydantic 模型构建特性配置
    features = ModelFeatures()
    mcp_servers = []
    
    model_lower = model.lower()

    # 检查模型ID中的功能后缀
    has_nothinking_suffix = "nothinking" in model_lower
    has_search_suffix = "search" in model_lower
    has_advanced_search_suffix = "advanced" in model_lower and "search" in model_lower

    # 处理 nothinking 后缀
    if has_nothinking_suffix:
        features.enable_thinking = False
        if settings.verbose_logging:
            logger.debug("Model feature detected: nothinking suffix disabled thinking for model={}", model)
    elif not streaming:
        features.enable_thinking = False
        if settings.verbose_logging:
            logger.debug("Thinking disabled for non-streaming request: model={}", model)
    else:
        # 检查上游模型是否支持 thinking 能力
        if model_capabilities:
            supports_thinking = model_capabilities.get("capabilities", {}).get("think", False)
            if not supports_thinking:
                features.enable_thinking = False
                if settings.verbose_logging:
                    logger.debug("Thinking disabled: upstream model does not support thinking capability, model={}", model)

    # 处理 search 后缀
    if has_search_suffix:
        features.web_search = True
        features.auto_web_search = True
        features.preview_mode = True
        if settings.verbose_logging:
            logger.debug("Model feature detected: search suffix enabled for model={}", model)
        
        if has_advanced_search_suffix:
            mcp_servers = ["advanced-search"]
            if settings.verbose_logging:
                logger.debug("Model feature detected: advanced-search suffix enabled MCP server for model={}", model)

    return {"features": features.model_dump(), "mcp_servers": mcp_servers}


async def prepare_request_data(
    chat_request: ChatRequest, access_token: str, streaming: bool = True
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    """准备上游 API 请求数据。
    
    执行完整的请求准备流程：
    
    1. 转换消息格式为上游 API 格式
    2. 并发处理文件上传（图片、视频、文档）
    3. 生成请求签名
    4. 构建请求头和查询参数
    5. 配置模型特性
    
    :param chat_request: 聊天请求对象
    :param access_token: 用户访问令牌
    :param streaming: 是否为流式请求，默认为 True
    :type chat_request: ChatRequest
    :type access_token: str
    :type streaming: bool
    :return: 包含请求数据、查询参数和请求头的三元组
    :rtype: tuple[dict[str, Any], dict[str, str], dict[str, str]]
    :raises FileUploadError: 当文件上传失败时
    :raises ValueError: 当模型 ID 无效时
    
    **返回值说明:**
    
    - ``tuple[0]``: 请求体数据（JSON 格式）
    - ``tuple[1]``: 查询参数字典（requestId、timestamp 等）
    - ``tuple[2]``: 请求头字典（Authorization、X-Signature 等）
    
    .. note::
       **文件处理逻辑:**
       
       - 图片/视频：嵌入到 ``messages.content`` 数组
       - 其他文件：放入顶层 ``files`` 数组
    
    .. warning::
       文件上传采用并发处理，失败的文件会被跳过而不会中断整个请求
    """
    logger.info(
        "Preparing request data: model={}, streaming={}, message_count={}",
        chat_request.model,
        streaming,
        len(chat_request.messages),
    )
    
    # 预加载模型映射表以支持动态模型ID转换
    from .model_service import get_models
    models = []  # 初始化 models 变量
    try:
        models_data = await get_models(access_token=access_token, use_cache=True)
        models = models_data.get("data", [])
    except Exception as e:
        logger.warning(
            "Failed to fetch models for mapping initialization: error={}. Will use existing mappings.",
            str(e)
        )
    
    converted = convert_messages(chat_request.messages)

    # chat_id 应该在会话开始时生成一次，然后在整个会话中复用
    # 这里每次都生成新的ID是为了模拟新会话，实际应用中应该从请求中获取或维护会话状态
    chat_id = str(uuid.uuid4())

    # user_id 应该从JWT token中提取，这里暂时生成随机ID
    user_id = str(uuid.uuid4())
    auth_token = access_token
    cookies = {}

    # 验证请求的模型是否在可用模型列表中
    model_exists = any(m["id"] == chat_request.model for m in models)
    
    if not model_exists:
        # 检查是否是上游原始模型ID（未经映射的）
        is_upstream_model = any(
            m.get("info", {}).get("id") == chat_request.model
            for m in models
        )
        
        if not is_upstream_model:
            logger.error(
                "Model not found in available models list: model={}, available_count={}",
                chat_request.model,
                len(models)
            )
            raise ValueError(
                f"模型 '{chat_request.model}' 不存在。请使用 /v1/models 接口查看可用模型列表。"
            )
    
    # 将客户端模型ID转换为上游API识别的模型ID
    # 支持多级映射：variant -> base_model -> upstream_model
    upstream_model_id = chat_request.model
    max_mapping_depth = 10  # 防止循环映射
    mapping_chain = [chat_request.model]
    
    for _ in range(max_mapping_depth):
        next_id = settings.REVERSE_MODELS_MAPPING.get(upstream_model_id)
        if next_id and next_id != upstream_model_id:
            upstream_model_id = next_id
            mapping_chain.append(upstream_model_id)
        else:
            break
    
    if len(mapping_chain) > 1:
        if settings.verbose_logging:
            logger.debug(
                "Model mapping chain: {}",
                " -> ".join(mapping_chain)
            )
    else:
        logger.warning(
            "No reverse mapping found for model={}, using original ID. This may cause upstream API errors.",
            chat_request.model
        )
    
    zai_data = UpstreamRequestData(
        stream=streaming,
        model=upstream_model_id,
        messages=converted.messages,
        signature_prompt=converted.last_user_message_text,
        variables={
            "{{CURRENT_DATETIME}}": datetime.now().isoformat(),
            "{{CURRENT_DATE}}": datetime.now().strftime("%Y-%m-%d"),
            "{{CURRENT_TIME}}": datetime.now().strftime("%H:%M:%S"),
            "{{CURRENT_WEEKDAY}}": datetime.now().strftime("%A"),
            "{{CURRENT_TIMEZONE}}": "Asia/Shanghai",
            "{{USER_LANGUAGE}}": "zh-CN",
        },
        chat_id=chat_id,
        id=str(uuid.uuid4()),
    )

    # 查找匹配的模型并提取完整的模型信息
    model_found = False
    model_capabilities = None
    for model in models:
        if model["id"] == chat_request.model:
            # 使用完整的模型对象，包含所有字段
            zai_data.model_item = model
            # 提取模型能力配置用于特性判断
            model_capabilities = model.get("info", {}).get("meta", {}).get("capabilities", {})
            model_found = True
            break
    
    # 如果没有找到模型，使用上游模型ID构造一个基本的model_item
    if not model_found:
        zai_data.model_item = {
            "id": upstream_model_id,
            "name": upstream_model_id,
            "owned_by": "openai",
            "info": {
                "id": upstream_model_id,
                "name": upstream_model_id,
                "meta": {
                    "capabilities": {}
                }
            }
        }
        logger.warning(
            "Model not found in models list, using upstream_model_id: model={}, upstream_model={}",
            chat_request.model,
            upstream_model_id
        )

    # 添加生成参数 (仅传递 ChatRequest 中存在的参数)
    if chat_request.temperature is not None:
        zai_data.params["temperature"] = chat_request.temperature
    if chat_request.top_p is not None:
        zai_data.params["top_p"] = chat_request.top_p
    if chat_request.max_tokens is not None:
        zai_data.params["max_tokens"] = chat_request.max_tokens

    signature_content = converted.last_user_message_text

    uploaded_file_objects = []  # 存储上传成功的完整文件对象

    if converted.file_urls:
        file_urls = converted.file_urls
        logger.info(
            "File upload processing started: file_count={}, model={}, chat_id={}, request_id={}",
            len(file_urls),
            chat_request.model,
            zai_data.chat_id,
            zai_data.id,
        )
        
        file_uploader = FileUploader(auth_token, zai_data.chat_id, cookies)
        
        # 并发上传文件
        async def upload_single_file(idx: int, url: str):
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
                    zai_data.id,
                )
                
                file_object = None
                
                if url.startswith("data:"):
                    if ";base64," in url:
                        header, base64_data = url.split(";base64,", 1)
                        mime_type = header.split(":", 1)[1] if ":" in header else ""
                        
                        file_ext = None
                        if mime_type.startswith("image/"):
                            file_ext = mime_type.split("/")[1]
                        elif mime_type.startswith("video/"):
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
                        
                        file_object = await file_uploader.upload_base64_file(base64_data, file_type=file_ext)
                    else:
                        logger.warning("Unsupported data URL format (missing base64): url={}", url[:50])
                        return None
                
                elif url.startswith("http"):
                    file_object = await file_uploader.upload_file_from_url(url)
                
                else:
                    logger.warning("Unsupported file URL format: url={}", url[:50])
                    return None

                if file_object:
                    logger.info(
                        "File uploaded successfully: index={}/{}, file_id={}, media={}, request_id={}",
                        idx + 1,
                        len(file_urls),
                        file_object["id"],
                        file_object["media"],
                        zai_data.id,
                    )
                    return file_object
                else:
                    logger.warning(
                        "File upload returned no object: index={}/{}, url_preview={}, request_id={}",
                        idx + 1,
                        len(file_urls),
                        url[:80] if len(url) > 80 else url,
                        zai_data.id,
                    )
                    return None
            except Exception as e:
                logger.error(
                    "File upload failed: index={}/{}, url_preview={}, error={}, request_id={}",
                    idx + 1,
                    len(file_urls),
                    url[:80] if len(url) > 80 else url,
                    str(e),
                    zai_data.id,
                )
                return None
        
        # 并发上传所有文件
        upload_tasks = [upload_single_file(idx, url) for idx, url in enumerate(file_urls)]
        upload_results = await asyncio.gather(*upload_tasks, return_exceptions=True)
        
        # 过滤出成功上传的文件
        uploaded_file_objects = [
            result for result in upload_results
            if result is not None and not isinstance(result, (Exception, BaseException)) and isinstance(result, dict)
        ]

        if uploaded_file_objects:
            logger.info(
                "File upload completed: total_files={}, successful={}, failed={}, model={}, request_id={}",
                len(file_urls),
                len(uploaded_file_objects),
                len(file_urls) - len(uploaded_file_objects),
                chat_request.model,
                zai_data.id,
            )
        else:
            logger.warning(
                "No files uploaded successfully: total_files={}, model={}, request_id={}",
                len(file_urls),
                chat_request.model,
                zai_data.id,
            )
        
        # 根据文档逻辑：根据media类型区分处理
        # 特殊处理：glm-4.6v 模型及其变体的图片放在 files 数组中（兼容上游行为）
        # 其他模型：图片/视频嵌入到messages.content数组，其他文件放入顶层files数组
        
        # 检查是否是 glm-4.6v 模型或其变体（需要特殊处理）
        is_glm46v_model = chat_request.model.lower().startswith("glm-4.6v")
        
        image_video_files = []
        other_files = []
        
        for file_obj in uploaded_file_objects:
            if file_obj["media"] in ("image", "video"):
                image_video_files.append(file_obj)
            else:
                other_files.append(file_obj)
        
        # 对于 glm-4.6v 模型，图片也放入 files 数组（而不是嵌入到 messages）
        if is_glm46v_model:
            if uploaded_file_objects:
                # glm-4.6v: 所有文件（包括图片）都放入 files 数组
                zai_data.files = uploaded_file_objects
                logger.info(
                    "GLM-4.6V model: all files added to top-level files array: total_count={}, image_count={}, video_count={}, other_count={}, request_id={}",
                    len(uploaded_file_objects),
                    sum(1 for f in image_video_files if f["media"] == "image"),
                    sum(1 for f in image_video_files if f["media"] == "video"),
                    len(other_files),
                    zai_data.id,
                )
        else:
            # 其他模型：标准处理逻辑
            # 处理最后一条用户消息
            if image_video_files and zai_data.messages:
                last_user_msg_idx = -1
                for i in range(len(zai_data.messages) - 1, -1, -1):
                    if zai_data.messages[i].get("role") == "user":
                        last_user_msg_idx = i
                        break
                
                if last_user_msg_idx >= 0:
                    last_msg = zai_data.messages[last_user_msg_idx]
                    text_content = last_msg.get("content", "")
                    
                    # 如果有图片或视频，构建content数组
                    if image_video_files:
                        content_array = [{"type": "text", "text": text_content}]
                        
                        for file_obj in image_video_files:
                            if file_obj["media"] == "image":
                                content_array.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"{file_obj['id']}_{file_obj['name']}"}
                                })
                            elif file_obj["media"] == "video":
                                content_array.append({
                                    "type": "video_url",
                                    "video_url": {"url": f"{file_obj['id']}_{file_obj['name']}"}
                                })
                        
                        zai_data.messages[last_user_msg_idx] = {
                            "role": "user",
                            "content": content_array
                        }
                        
                        logger.info(
                            "Message reconstructed with media files: text_length={}, image_count={}, video_count={}, request_id={}",
                            len(text_content),
                            sum(1 for f in image_video_files if f["media"] == "image"),
                            sum(1 for f in image_video_files if f["media"] == "video"),
                            zai_data.id,
                        )
            
            # 只有非图片/视频文件才放入顶层files数组
            if other_files:
                zai_data.files = other_files
                logger.info(
                    "Non-media files added to top-level files array: count={}, request_id={}",
                    len(other_files),
                    zai_data.id,
                )

    # 获取模型特性配置，传入模型能力信息
    features_dict = get_model_features(chat_request.model, streaming, model_capabilities)
    zai_data.features = features_dict["features"]
    if features_dict["mcp_servers"]:
        zai_data.mcp_servers = features_dict["mcp_servers"]

    # 使用 Pydantic 模型构造查询参数
    params = UpstreamRequestParams(
        requestId=str(uuid.uuid4()),
        timestamp=str(int(time.time() * 1000)),
        user_id=user_id,
        token=auth_token,
        version=settings.HEADERS["X-FE-Version"],
        user_agent=settings.HEADERS["User-Agent"],
    )

    request_params = f"requestId,{params.requestId},timestamp,{params.timestamp},user_id,{params.user_id}"
    signature_data = generate_signature(request_params, signature_content)
    params.signature_timestamp = str(signature_data["timestamp"])

    zai_data.signature_prompt = signature_content

    headers = settings.HEADERS.copy()
    headers["Authorization"] = f"Bearer {auth_token}"
    headers["X-Signature"] = signature_data["signature"]
    headers["Accept-Language"] = "zh-CN"
    headers["X-FE-Version"] = settings.HEADERS["X-FE-Version"] # 前端版本号
    headers["Referer"] = f"{settings.protocol}//{settings.base_url}/c/{chat_id}"

    files_processed = bool(converted.file_urls)
    logger.info(
        "Request data prepared successfully: chat_id={}, request_id={}, model={}, upstream_model={}, streaming={}, files_processed={}, features={}",
        zai_data.chat_id,
        params.requestId,
        chat_request.model,
        zai_data.model,
        streaming,
        files_processed,
        zai_data.features,
    )

    return zai_data.model_dump(), params.model_dump(), headers


def process_streaming_response(
    chat_request: ChatRequest, access_token: str
) -> AsyncGenerator[str, None]:
    """处理流式响应。

    :param chat_request: 聊天请求对象
    :param access_token: 访问令牌
    :yields: SSE格式的数据块
    :raises UpstreamAPIError: 当上游API返回错误状态码时

    .. note::
       响应格式遵循OpenAI的流式API规范。
    """
    return _process_streaming_response(chat_request, access_token, prepare_request_data)


async def process_non_streaming_response(
    chat_request: ChatRequest, access_token: str
) -> dict[str, Any]:
    """处理非流式响应。

    :param chat_request: 聊天请求对象
    :param access_token: 访问令牌
    :return: 完整的聊天补全响应
    :raises UpstreamAPIError: 当上游API返回错误状态码时

    .. note::
       响应格式遵循OpenAI的非流式API规范。
    """
    return await _process_non_streaming_response(chat_request, access_token, prepare_request_data)
