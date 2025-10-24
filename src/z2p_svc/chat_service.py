"""聊天服务模块。

本模块负责处理与上游API的交互，包括消息格式转换、图片上传处理、
流式和非流式响应处理、签名生成和请求构建。
"""

import asyncio
import time
from datetime import datetime
from typing import Any, AsyncGenerator

from .config import get_settings
from .file_uploader import FileUploader
from .logger import get_logger, json_str
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
from .utils.uuid_helper import generate_chat_id, generate_uuid_str, generate_request_id

logger = get_logger(__name__)
settings = get_settings()




def get_model_features(model: str, streaming: bool, model_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """获取模型特性配置。
    
    根据模型 ID 自动识别并配置功能开关。支持通过模型名称后缀
    控制特性（如 ``-nothinking``、``-search``、``-advanced-search``）。
    
    :param model: 模型名称（客户端请求的模型 ID，可能包含功能后缀）
    :param streaming: 是否为流式请求
    :param model_meta: 上游模型的meta信息（包含capabilities和mcpServerIds）
    :type model: str
    :type streaming: bool
    :type model_meta: dict[str, Any] | None
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
    - ``-search``: 启用网络搜索（添加 deep-web-search MCP）
    - ``-advanced-search``: 启用高级搜索（添加 advanced-search MCP）
    
    .. note::
       - 非流式请求会自动禁用 thinking 功能
       - 所有模型默认合并上游 MCP 服务器列表（从 meta.mcpServerIds 获取）
       - web_search 仅在 search 相关后缀时启用
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
        if model_meta:
            supports_thinking = model_meta.get("capabilities", {}).get("think", False)
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
            mcp_servers.append("advanced-search")
            if settings.verbose_logging:
                logger.debug("Model feature detected: advanced-search suffix enabled MCP server for model={}", model)
        else:
            mcp_servers.append("deep-web-search")
            if settings.verbose_logging:
                logger.debug("Model feature detected: search suffix enabled MCP server for model={}", model)
    
    # 合并上游 MCP 列表（所有模型默认使用）
    if model_meta:
        upstream_mcp_servers = model_meta.get("mcpServerIds", [])
        if upstream_mcp_servers:
            for server in upstream_mcp_servers:
                if server not in mcp_servers:
                    mcp_servers.append(server)
            if settings.verbose_logging:
                logger.debug("Merged upstream MCP servers: model={}, mcp_servers={}", model, json_str(mcp_servers))

    return {"features": features.model_dump(), "mcp_servers": mcp_servers}


async def prepare_request_data(
    chat_request: ChatRequest, access_token: str, streaming: bool = True, user_agent: str = ""
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
    from .model_service import get_models, get_upstream_models_cache
    models = []  # 初始化 models 变量（下游模型列表）
    upstream_models = []  # 上游模型列表（包含完整的 meta 信息）
    try:
        models_data = await get_models(access_token=access_token, use_cache=True)
        models = models_data.get("data", [])
        
        # 从缓存获取上游模型信息（避免重复请求）
        upstream_models = get_upstream_models_cache()
        if not upstream_models:
            logger.warning("Upstream models cache is empty, will use limited model info")
    except Exception as e:
        logger.warning(
            "Failed to fetch models for mapping initialization: error={}. Will use existing mappings.",
            str(e)
        )
    
    converted = convert_messages(chat_request.messages)
    
    # 检查是否需要启用 toolify
    enable_toolify = chat_request.tools is not None and len(chat_request.tools) > 0
    
    if enable_toolify and chat_request.tools:
        # 注入工具提示词
        from .services.toolify.prompt import inject_tool_prompt
        converted_messages = inject_tool_prompt(
            converted.messages,
            [tool.model_dump() for tool in chat_request.tools]
        )
        logger.info(f"[TOOLIFY] 已启用，工具数量: {len(chat_request.tools)}")
    else:
        converted_messages = converted.messages

    # chat_id 应该在会话开始时生成一次，然后在整个会话中复用
    # 这里每次都生成新的ID是为了模拟新会话，实际应用中应该从请求中获取或维护会话状态
    chat_id = generate_chat_id()

    # user_id 应该从JWT token中提取，这里暂时生成随机ID
    user_id = generate_uuid_str()
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
                json_str(mapping_chain)
            )
    elif chat_request.model not in settings.REVERSE_MODELS_MAPPING:
        logger.warning(
            "No reverse mapping found for model={}, using original ID. This may cause upstream API errors.",
            chat_request.model
        )
    
    # 从客户端请求中获取语言偏好，如果没有则使用默认值
    user_language = "zh-CN"
    if chat_request.accept_language:
        # 提取主要语言代码（例如从 "en-US,en;q=0.9" 提取 "en-US"）
        user_language = chat_request.accept_language.split(',')[0].strip()
    
    # 上游始终使用stream=True返回SSE流
    # 非流式请求通过聚合SSE流来实现"伪非流式"
    zai_data = UpstreamRequestData(
        stream=True,
        model=upstream_model_id,
        messages=converted_messages,
        signature_prompt=converted.last_user_message_text,
        variables={
            "{{USER_LOCATION}}": "Unknown",  # 添加用户位置变量（默认值）
            "{{CURRENT_DATETIME}}": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # 匹配上游格式
            "{{CURRENT_DATE}}": datetime.now().strftime("%Y-%m-%d"),
            "{{CURRENT_TIME}}": datetime.now().strftime("%H:%M:%S"),
            "{{CURRENT_WEEKDAY}}": datetime.now().strftime("%A"),
            "{{CURRENT_TIMEZONE}}": "Asia/Shanghai",
            "{{USER_LANGUAGE}}": user_language,
        },
        chat_id=chat_id,
        id=generate_uuid_str(),
    )

    # 查找匹配的下游模型（用于 model_item）
    model_found = False
    for model in models:
        if model["id"] == chat_request.model:
            # 使用下游模型对象（OpenAI 兼容格式，不包含冗余的 info）
            zai_data.model_item = model
            model_found = True
            break
    
    # 如果没有找到模型，使用上游模型ID构造一个基本的model_item
    if not model_found:
        zai_data.model_item = {
            "id": upstream_model_id,
            "name": upstream_model_id,
            "owned_by": "openai",
        }
        logger.warning(
            "Model not found in models list, using upstream_model_id: model={}, upstream_model={}",
            chat_request.model,
            upstream_model_id
        )
    
    # 从上游模型列表中查找对应的模型，提取完整的上游模型对象
    model_capabilities = None
    model_meta = None
    upstream_model_obj = None
    for upstream_model in upstream_models:
        # 匹配上游模型ID（通过反向映射链）
        if upstream_model.get("id") == upstream_model_id or upstream_model.get("info", {}).get("id") == upstream_model_id:
            upstream_model_obj = upstream_model  # 保存完整的上游模型对象
            model_meta = upstream_model.get("info", {}).get("meta", {})
            model_capabilities = model_meta.get("capabilities", {})
            if settings.verbose_logging:
                logger.debug(
                    "Found upstream model: model={}, upstream_id={}, capabilities={}, mcp_servers={}",
                    chat_request.model,
                    upstream_model_id,
                    json_str(list(model_capabilities.keys()) if model_capabilities else []),
                    json_str(model_meta.get("mcpServerIds", []))
                )
            break
    
    if not model_meta:
        logger.warning(
            "Upstream model not found: model={}, upstream_model={}. Using empty capabilities.",
            chat_request.model,
            upstream_model_id
        )
        model_meta = {}
        model_capabilities = {}
    
    # 使用完整的上游模型对象作为 model_item（匹配上游格式）
    if upstream_model_obj:
        zai_data.model_item = upstream_model_obj
    # 如果没有找到上游模型，保持之前设置的简化 model_item

    # 添加生成参数 (仅在客户端明确提供时添加，否则保持空对象)
    # 参考上游格式：params 默认为空对象 {}
    params_dict = {}
    if chat_request.temperature is not None:
        params_dict["temperature"] = chat_request.temperature
    if chat_request.top_p is not None:
        params_dict["top_p"] = chat_request.top_p
    if chat_request.max_tokens is not None:
        params_dict["max_tokens"] = chat_request.max_tokens
    zai_data.params = params_dict

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
                
                logger.debug(
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
                    logger.debug(
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
        
        # 根据media类型区分处理
        # 默认情况：所有文件放入 files 数组
        # 特殊情况：如果模型支持 vision 能力，图片/视频使用 image_url/video_url 嵌入到 messages.content
        
        # 检查模型是否支持 vision 能力
        has_vision = model_capabilities.get("vision", False) if model_capabilities else False
        
        image_video_files = []
        other_files = []
        
        for file_obj in uploaded_file_objects:
            if file_obj["media"] in ("image", "video"):
                image_video_files.append(file_obj)
            else:
                other_files.append(file_obj)
        
        # 无 vision 能力：所有文件都放入 files 数组
        if not has_vision:
            if uploaded_file_objects:
                zai_data.files = uploaded_file_objects
                logger.debug(
                    "Non-vision model: all files added to top-level files array: total_count={}, image_count={}, video_count={}, other_count={}, request_id={}",
                    len(uploaded_file_objects),
                    sum(1 for f in image_video_files if f["media"] == "image"),
                    sum(1 for f in image_video_files if f["media"] == "video"),
                    len(other_files),
                    zai_data.id,
                )
        else:
            # 有 vision 能力：图片/视频嵌入到 messages.content，其他文件放入 files 数组
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
                        
                        logger.debug(
                            "Message reconstructed with media files: text_length={}, image_count={}, video_count={}, request_id={}",
                            len(text_content),
                            sum(1 for f in image_video_files if f["media"] == "image"),
                            sum(1 for f in image_video_files if f["media"] == "video"),
                            zai_data.id,
                        )
            
            # 只有非图片/视频文件才放入顶层files数组
            if other_files:
                zai_data.files = other_files
                logger.debug(
                    "Non-media files added to top-level files array: count={}, request_id={}",
                    len(other_files),
                    zai_data.id,
                )

    # 获取模型特性配置，传入完整的meta信息（包含capabilities和mcpServerIds）
    features_dict = get_model_features(chat_request.model, streaming, model_meta)
    
    # 构建 features 对象（匹配上游格式）
    features_obj = features_dict["features"].copy()
    features_obj["image_generation"] = False  # 添加 image_generation 字段
    
    # 将 MCP 服务器转换为 features.features 数组格式
    mcp_servers_list = features_dict.get("mcp_servers", [])
    features_array = []
    for server_id in mcp_servers_list:
        features_array.append({
            "type": "mcp",
            "server": server_id,
            "status": "hidden"  # 默认状态为 hidden
        })
    
    # 如果有 web_search，添加 web_search 类型的 feature
    if features_obj.get("web_search"):
        features_array.append({
            "type": "web_search",
            "server": "web_search",
            "status": "hidden"
        })
    
    # 添加 tool_selector（如果有 MCP 服务器）
    if mcp_servers_list:
        features_array.append({
            "type": "tool_selector",
            "server": "tool_selector",
            "status": "hidden"
        })
    
    features_obj["features"] = features_array
    zai_data.features = features_obj

    # 使用 Pydantic 模型构造查询参数
    params = UpstreamRequestParams(
        requestId=generate_request_id(),
        timestamp=str(int(time.time() * 1000)),
        user_id=user_id,
        token=auth_token,
        version=settings.HEADERS["X-FE-Version"],
        user_agent=user_agent,  # 从调用方传入的User-Agent（来自curl_cffi session）
        language=user_language,
        languages=chat_request.accept_language or "zh-CN",
    )

    request_params = f"requestId,{params.requestId},timestamp,{params.timestamp},user_id,{params.user_id}"
    signature_data = generate_signature(request_params, signature_content)
    params.signature_timestamp = str(signature_data["timestamp"])

    zai_data.signature_prompt = signature_content

    headers = settings.HEADERS.copy()
    headers["Authorization"] = f"Bearer {auth_token}"
    headers["X-Signature"] = signature_data["signature"]
    # 使用客户端提供的 Accept-Language，如果没有则使用默认值
    headers["Accept-Language"] = chat_request.accept_language or "zh-CN,zh;q=0.9"
    headers["X-FE-Version"] = settings.HEADERS["X-FE-Version"] # 前端版本号
    headers["Referer"] = f"{settings.protocol}//{settings.base_url}/c/{chat_id}"

    files_processed = bool(converted.file_urls)
    
    # info 等级：输出关键摘要信息
    logger.info(
        "Request prepared: chat_id={}, request_id={}, model={}, upstream_model={}, streaming={}, messages={}, files={}, features={}",
        zai_data.chat_id,
        params.requestId,
        chat_request.model,
        zai_data.model,
        streaming,
        len(zai_data.messages),
        len(zai_data.files) if zai_data.files else 0,
        json_str(list(zai_data.features.keys()) if zai_data.features else [])
    )
    
    # debug 等级：输出完整数据（用于调试）
    if settings.verbose_logging:
        zai_data_dict = zai_data.model_dump()
        log_data = {k: v for k, v in zai_data_dict.items() if k != "model_item"}
        logger.debug(
            "Request data details: chat_id={}, request_id={}, data={}",
            zai_data.chat_id,
            params.requestId,
            json_str(log_data),
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
    # 检查是否启用 toolify
    enable_toolify = chat_request.tools is not None and len(chat_request.tools) > 0
    return _process_streaming_response(chat_request, access_token, prepare_request_data, enable_toolify)


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
