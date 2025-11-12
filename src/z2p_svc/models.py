"""数据模型定义模块。

本模块定义API请求和响应的Pydantic模型，用于数据验证和序列化。
"""

from typing import Any, Dict, List, Optional, Union, Literal

from pydantic import BaseModel, Field


class ToolFunction(BaseModel):
    """工具函数定义（OpenAI 兼容）。
    
    定义一个可调用的工具函数，包含名称、描述和参数模式。
    """
    name: str = Field(..., description="函数名称")
    description: Optional[str] = Field(default=None, description="函数描述")
    parameters: Dict[str, Any] = Field(..., description="函数参数的 JSON Schema")


class Tool(BaseModel):
    """工具定义（OpenAI 兼容）。
    
    表示一个可供模型调用的工具。
    """
    type: Literal["function"] = Field(default="function", description="工具类型（目前仅支持 function）")
    function: ToolFunction = Field(..., description="函数定义")


class Message(BaseModel):
    """聊天消息模型。

    表示对话中的单条消息，支持文本和多模态内容。

    :param role: 消息角色（system/user/assistant/tool）
    :param content: 消息内容，字符串或多模态内容数组
    :param tool_calls: 工具调用列表（仅用于 assistant 角色）
    :param tool_call_id: 工具调用 ID（仅用于 tool 角色）
    :type role: str
    :type content: Union[str, list]
    :type tool_calls: Optional[List[Dict[str, Any]]]
    :type tool_call_id: Optional[str]
    """

    role: str = Field(..., description="消息角色")
    content: Union[str, list, None] = Field(default=None, description="消息内容")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="工具调用列表")
    tool_call_id: Optional[str] = Field(default=None, description="工具调用 ID")
    name: Optional[str] = Field(default=None, description="函数名称（用于 function 角色）")


class ChatRequest(BaseModel):
    """聊天补全请求模型（OpenAI 兼容）。
    
    符合 OpenAI Chat Completion API 规范的请求格式。
    支持通过模型名称后缀控制特殊功能。
    
    **支持的模型后缀:**
    
    - ``-nothinking``: 禁用深度思考
    - ``-search``: 启用网络搜索
    - ``-mcp``: 启用 MCP 工具调用
    
    :param model: 模型 ID，支持功能后缀（如 -search、-nothinking）
    :param messages: 对话消息列表，至少包含一条消息
    :param stream: 是否使用流式响应（Server-Sent Events）
    :param temperature: 采样温度（0.0-2.0），较高值使输出更随机
    :param top_p: 核采样参数（0.0-1.0），建议与 temperature 二选一
    :param max_tokens: 生成的最大 token 数量
    :param tools: 工具定义列表（用于 Toolify 模式）
    :param tool_choice: 工具选择策略（auto/none 或指定工具）
    :type model: str
    :type messages: list[Message]
    :type stream: bool
    :type temperature: float
    :type top_p: float
    :type max_tokens: int
    :type tools: Optional[List[Tool]]
    :type tool_choice: Optional[Union[str, Dict]]
    
    .. seealso::
       :class:`Message` - 消息对象
       :class:`ChatCompletionResponse` - 响应对象
    """

    model: str = Field(..., description="模型名称")
    messages: list[Message] = Field(..., description="消息列表")
    stream: bool = Field(default=False, description="是否流式响应")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="采样温度")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0, description="核采样参数")
    max_tokens: int = Field(default=8192, ge=1, description="最大token数")
    tools: Optional[List[Tool]] = Field(default=None, description="工具定义列表")
    tool_choice: Optional[Union[str, Dict]] = Field(default=None, description="工具选择策略")
    accept_language: Optional[str] = Field(
        default=None,
        description="客户端的 Accept-Language 头部值，用于传递给上游 API"
    )


# --- Upstream Models (上游 API 模型) ---

class UpstreamCapability(BaseModel):
    """上游模型能力配置。
    
    定义模型支持的各种功能特性，用于前端 UI 展示和功能开关。
    这是一个动态的键值对字典，不同模型可能有不同的能力字段。
    
    常见的能力字段包括：
    - vision: 视觉能力（图像理解）
    - web_search: 网络搜索
    - mcp: MCP 工具调用
    - file_qa: 文件问答
    - think: 深度思考（思维链）
    - citations: 引用来源
    - returnFc: 返回函数调用
    - returnThink: 返回思考过程
    
    注意：Pydantic 的 model_config 允许额外字段，以支持未来可能添加的新能力。
    """
    model_config = {"extra": "allow"}  # 允许额外的未定义字段
    
    # 定义已知的常见能力字段（带默认值）
    vision: bool = Field(default=False, description="视觉能力：支持图像理解和分析（如 GLM-4.5V）")
    citations: bool = Field(default=False, description="引用来源：在回答中提供信息来源引用")
    preview_mode: bool = Field(default=False, description="预览模式：支持预览功能")
    web_search: bool = Field(default=False, description="网络搜索：可联网搜索实时信息（生成 -search 变体）")
    language_detection: bool = Field(default=False, description="语言检测：自动检测输入语言")
    restore_n_source: bool = Field(default=False, description="恢复源内容：支持恢复原始内容")
    mcp: bool = Field(default=False, description="MCP 工具：支持 Model Context Protocol 工具调用（生成 -mcp 变体）")
    file_qa: bool = Field(default=False, description="文件问答：支持上传文件并进行问答（生成 -fileqa 变体）")
    returnFc: bool = Field(default=False, description="返回函数调用：在响应中包含函数调用信息")
    returnThink: bool = Field(default=False, description="返回思考过程：在响应中包含模型的思考过程")
    think: bool = Field(default=False, description="深度思考：支持思维链推理（生成 -nothinking 变体用于禁用）")


class UpstreamFeature(BaseModel):
    """上游功能特性配置。
    
    用于 suggestion_prompts 中定义特定功能的 UI 展示状态。
    """
    type: str = Field(..., description="功能类型：mcp（工具）、web_search（搜索）、tool_selector（工具选择器）")
    server: str = Field(..., description="服务器标识：如 vibe-coding（编程）、ppt-maker（PPT）、deep-research（深度研究）")
    status: str = Field(..., description="UI 状态：hidden（隐藏）、selected（已选）、pinned（固定显示）")


class UpstreamPromptRemixId(BaseModel):
    """上游提示词混音 ID。
    
    用于关联分享和源提示词的 ID，支持多语言版本。
    """
    zh_CN: Optional[Union[str, Dict[str, Any]]] = Field(
        alias="zh-CN",
        default=None,
        description="中文版本的分享或源 ID"
    )
    en_US: Optional[str] = Field(
        alias="en-US",
        default=None,
        description="英文版本的分享或源 ID"
    )


class UpstreamPrompt(BaseModel):
    """上游提示词配置。
    
    定义建议提示词的详细信息，用于前端 UI 展示和快速启动对话。
    """
    id: Optional[str] = Field(default=None, description="提示词唯一标识")
    name: str = Field(..., description="提示词中文名称（如：赛博功德+1）")
    name_en: str = Field(..., description="提示词英文名称")
    prompt: str = Field(..., description="提示词中文内容（实际发送给模型的文本）")
    prompt_en: str = Field(..., description="提示词英文内容")
    thumb: Optional[Union[str, Dict[str, str]]] = Field(
        default=None,
        description="缩略图：可以是 URL 字符串或包含 zh-CN/en-US 键的字典"
    )
    files: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="关联的文件列表（用于多模态输入）"
    )
    remix: Optional[Dict[str, UpstreamPromptRemixId]] = Field(
        default=None,
        description="混音信息：包含 share_id 和 source_id"
    )


class UpstreamSuggestionPrompt(BaseModel):
    """上游建议提示词组配置。
    
    定义一组相关的建议提示词，用于前端 UI 分组展示。
    例如：AI PPT、全栈开发、灵感画板、深度研究等场景。
    """
    id: Optional[str] = Field(default=None, description="提示词组唯一标识")
    group_name: str = Field(..., description="提示词组中文名称（如：AI PPT、全栈开发）")
    group_name_en: Optional[str] = Field(default=None, description="提示词组英文名称")
    icon: Optional[str] = Field(default=None, description="提示词组图标（SVG 字符串）")
    prompts: Optional[List[UpstreamPrompt]] = Field(default=None, description="该组包含的提示词列表")
    flags: Optional[List[str]] = Field(
        default=None,
        description="功能标志：ppt_composer（PPT生成）、web_dev（网页开发）、ai_design（AI设计）、deep_research（深度研究）"
    )
    features: Optional[List[UpstreamFeature]] = Field(
        default=None,
        description="功能特性配置：定义该组启用的工具和搜索功能"
    )
    display_name: Optional[str] = Field(default=None, description="显示名称（用于 UI）")
    tag: Optional[str] = Field(default=None, description="中文标签（如 🔥 表示热门）")
    tag_en: Optional[str] = Field(default=None, description="英文标签")
    media: Optional[bool] = Field(default=None, description="是否包含媒体内容（图片、视频等）")
    gallery: Optional[bool] = Field(default=None, description="是否在画廊中展示")
    hidden: Optional[bool] = Field(default=None, description="是否隐藏该提示词组")


class UpstreamMeta(BaseModel):
    """上游模型元数据。
    
    包含模型的 UI 显示、功能配置和建议提示词等信息。
    """
    profile_image_url: Optional[str] = Field(
        default=None,
        description="模型头像 URL（通常为 /static/favicon.png）"
    )
    description: Optional[str] = Field(
        default=None,
        description="模型描述（根据 Accept-Language 本地化，如：Most advanced model, excelling in all-round tasks）"
    )
    capabilities: Optional[UpstreamCapability] = Field(
        default=None,
        description="模型能力配置：定义支持的功能（vision、web_search、mcp、think 等）"
    )
    mcpServerIds: Optional[List[str]] = Field(
        default=None,
        description="兼容的 MCP 服务器 ID 列表（如：deep-web-search、ppt-maker、vibe-coding）"
    )
    suggestion_prompts: Optional[List[UpstreamSuggestionPrompt]] = Field(
        default=None,
        description="建议提示词组列表：为该模型推荐的使用场景和示例"
    )
    tags: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="模型标签列表（如 [{'name': 'NEW'}] 表示新模型）"
    )
    hidden: Optional[bool] = Field(
        default=None,
        description="是否隐藏此模型（隐藏的模型不在前端显示）"
    )


class UpstreamModelInfo(BaseModel):
    """上游模型详细信息。
    
    包含模型的所有详细元数据和配置信息。
    """
    id: str = Field(..., description="模型唯一标识符（如：GLM-4-6-API-V1）")
    user_id: Optional[str] = Field(default=None, description="创建者用户 ID")
    base_model_id: Optional[str] = Field(default=None, description="基础模型 ID（用于微调模型）")
    name: str = Field(..., description="模型名称（如：GLM-4.6）")
    params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="模型默认参数：max_tokens（最大令牌数）、temperature（温度）、top_p（核采样）"
    )
    meta: Optional[UpstreamMeta] = Field(
        default=None,
        description="模型元数据：包含能力、描述、建议提示词等"
    )
    access_control: Optional[Any] = Field(default=None, description="访问控制配置")
    is_active: bool = Field(default=True, description="模型是否激活（仅激活的模型会被转换）")
    updated_at: Optional[int] = Field(default=None, description="更新时间戳（Unix 时间）")
    created_at: Optional[int] = Field(default=None, description="创建时间戳（Unix 时间）")


class UpstreamOpenAI(BaseModel):
    """上游 OpenAI 兼容配置。
    
    包含 OpenAI 格式的配置信息（用于兼容性）。
    """
    id: str = Field(..., description="OpenAI 格式的模型 ID")
    name: str = Field(..., description="OpenAI 格式的模型名称")
    owned_by: str = Field(..., description="所有者标识（通常为 openai）")
    openai: Dict[str, str] = Field(..., description="嵌套的 OpenAI 配置（包含 id）")
    urlIdx: int = Field(..., description="URL 索引（用于负载均衡和多端点路由）")


class UpstreamModel(BaseModel):
    """上游模型定义。
    
    表示从上游 API `/api/models` 端点返回的完整模型对象。
    包含模型的所有信息：基本信息、能力配置、建议提示词等。
    """
    id: str = Field(..., description="模型唯一标识符（如：GLM-4-6-API-V1、glm-4.5v）")
    name: str = Field(..., description="模型用户友好显示名称（如：GLM-4.6、GLM-4.5V）")
    owned_by: str = Field(..., description="模型所有者或提供商标识（通常为 openai）")
    openai: UpstreamOpenAI = Field(..., description="OpenAI 兼容配置")
    urlIdx: int = Field(..., description="URL 索引（用于负载均衡）")
    info: UpstreamModelInfo = Field(..., description="模型详细信息：包含能力、参数、元数据等")
    actions: List[Any] = Field(default_factory=list, description="可用操作列表（通常为空）")
    tags: List[Dict[str, str]] = Field(
        default_factory=list,
        description="模型标签列表（如 [{'name': 'NEW'}]）"
    )


class UpstreamModelsResponse(BaseModel):
    """上游模型列表响应。
    
    表示从上游 API `/api/models` 端点返回的完整响应。
    包含所有可用模型的列表。
    """
    data: List[UpstreamModel] = Field(..., description="模型对象列表（包含所有可用模型）")


# --- Downstream Models (下游 OpenAI 兼容模型) ---

class DownstreamModel(BaseModel):
    """下游模型定义（OpenAI 兼容）。
    
    符合 OpenAI API 规范的简化模型对象，用于 `/v1/models` 端点。
    参考：https://platform.openai.com/docs/api-reference/models/object
    
    本转换程序会为每个上游模型生成：
    - 基础模型（如：glm-4.6）
    - 功能变体（如：glm-4.6-nothinking、glm-4.6-search、glm-4.6-mcp）
    """
    id: str = Field(
        ...,
        description="模型唯一标识符（如：glm-4.6、glm-4.6-nothinking、glm-4.6-search）"
    )
    object: str = Field(
        default="model",
        description="对象类型（固定为 model，符合 OpenAI 规范）"
    )
    created: int = Field(
        ...,
        description="模型创建时间戳（Unix 时间，从上游模型的 created_at 字段获取）"
    )
    name: str = Field(
        ...,
        description="模型显示名称（如：GLM-4.6、GLM-4.6-NOTHINKING、GLM-4.6-SEARCH）"
    )
    owned_by: str = Field(
        default="z.ai",
        description="模型所有者（默认为 z.ai，表示本转换服务）"
    )


class DownstreamModelsResponse(BaseModel):
    """下游模型列表响应（OpenAI 兼容）。
    
    符合 OpenAI API 规范的模型列表响应，用于 `/v1/models` 端点。
    参考：https://platform.openai.com/docs/api-reference/models/list
    
    本转换程序将上游的非标准模型列表转换为标准 OpenAI 格式，
    并为已映射的模型自动生成功能变体（-nothinking、-search、-mcp 等）。
    """
    object: str = Field(
        default="list",
        description="对象类型（固定为 list，符合 OpenAI 规范）"
    )
    data: List[DownstreamModel] = Field(
        ...,
        description="模型列表（包含基础模型和所有生成的功能变体）"
    )


# --- Chat Completion Models (聊天补全相关模型) ---

class ChatCompletionChunkDelta(BaseModel):
    """聊天补全流式响应的 delta 对象。
    
    表示流式响应中的增量内容。
    """
    role: Optional[str] = Field(default=None, description="消息角色（assistant）")
    content: Optional[str] = Field(default=None, description="增量文本内容")
    reasoning_content: Optional[str] = Field(default=None, description="推理过程内容（thinking 阶段）")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="工具调用列表（流式）")


class ChatCompletionChunkChoice(BaseModel):
    """聊天补全流式响应的选择对象。"""
    index: int = Field(default=0, description="选择索引")
    delta: ChatCompletionChunkDelta = Field(..., description="增量内容")
    finish_reason: Optional[str] = Field(default=None, description="完成原因：stop, length, error 等")


class ChatCompletionUsage(BaseModel):
    """聊天补全的使用统计信息。"""
    prompt_tokens: Optional[int] = Field(default=None, description="输入 token 数量")
    completion_tokens: Optional[int] = Field(default=None, description="输出 token 数量")
    total_tokens: Optional[int] = Field(default=None, description="总 token 数量")


class ChatCompletionChunk(BaseModel):
    """聊天补全流式响应块（OpenAI 兼容）。
    
    符合 OpenAI API 规范的流式响应格式。
    参考：https://platform.openai.com/docs/api-reference/chat/streaming
    """
    id: str = Field(..., description="响应唯一标识符（如 chatcmpl-xxx）")
    object: str = Field(default="chat.completion.chunk", description="对象类型")
    created: int = Field(..., description="创建时间戳（Unix 时间）")
    model: str = Field(..., description="使用的模型名称")
    choices: List[ChatCompletionChunkChoice] = Field(..., description="响应选择列表")
    usage: Optional[ChatCompletionUsage] = Field(default=None, description="使用统计（仅在最后一个块中包含）")


class ChatCompletionMessage(BaseModel):
    """聊天补全的完整消息对象。"""
    role: str = Field(..., description="消息角色（assistant）")
    content: Optional[str] = Field(default=None, description="完整的消息内容")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="工具调用列表")


class ChatCompletionChoice(BaseModel):
    """聊天补全非流式响应的选择对象。"""
    index: int = Field(default=0, description="选择索引")
    message: ChatCompletionMessage = Field(..., description="完整的消息对象")
    finish_reason: str = Field(..., description="完成原因：stop, length 等")


class ChatCompletionResponse(BaseModel):
    """聊天补全非流式响应（OpenAI 兼容）。
    
    符合 OpenAI API 规范的非流式响应格式。
    参考：https://platform.openai.com/docs/api-reference/chat/object
    """
    id: str = Field(..., description="响应唯一标识符（如 chatcmpl-xxx）")
    object: str = Field(default="chat.completion", description="对象类型")
    created: int = Field(..., description="创建时间戳（Unix 时间）")
    model: str = Field(..., description="使用的模型名称")
    choices: List[ChatCompletionChoice] = Field(..., description="响应选择列表")
    usage: Optional[ChatCompletionUsage] = Field(default=None, description="使用统计信息")


class ErrorDetail(BaseModel):
    """API 错误详情。"""
    message: str = Field(..., description="错误消息")
    type: str = Field(..., description="错误类型")
    code: Optional[int] = Field(default=None, description="错误代码")


class ErrorResponse(BaseModel):
    """API 错误响应。"""
    error: ErrorDetail = Field(..., description="错误详情")


# --- File Upload Models (文件上传相关模型) ---

class FileObject(BaseModel):
    """文件对象（OpenAI 兼容）。
    
    符合 OpenAI API 规范的文件对象格式。
    参考：https://platform.openai.com/docs/api-reference/files/object
    """
    id: str = Field(..., description="文件唯一标识符")
    object: str = Field(default="file", description="对象类型")
    bytes: int = Field(..., description="文件大小（字节）")
    created_at: int = Field(..., description="创建时间戳（Unix 时间）")
    filename: str = Field(..., description="文件名")
    purpose: str = Field(..., description="文件用途（如 assistants）")


class UploadedFileObject(BaseModel):
    """上游 API 返回的文件对象。
    
    包含上游 API 特有的字段，用于内部处理。
    """
    id: str = Field(..., description="文件唯一标识符（UUID）")
    name: str = Field(..., description="文件名")
    media: str = Field(..., description="媒体类型：image, video, document 等")
    size: Optional[int] = Field(default=None, description="文件大小（字节）")
    url: Optional[str] = Field(default=None, description="文件访问 URL")


# --- Upstream Request Models (上游请求相关模型) ---

class UpstreamRequestParams(BaseModel):
    """上游 API 请求参数。

    包含发送到上游 API 的查询参数，用于请求签名和追踪。
    """
    model_config = {"extra": "allow"}  # 允许额外字段

    requestId: str = Field(..., description="请求唯一标识符（UUID）")
    timestamp: str = Field(..., description="请求时间戳（毫秒）")
    user_id: str = Field(..., description="用户 ID（UUID）")
    token: str = Field(..., description="JWT 访问令牌")
    version: str = Field(..., description="前端应用版本号")
    user_agent: str = Field(..., description="用户代理字符串")
    platform: str = Field(default="web", description="客户端平台")
    language: str = Field(default="zh-CN", description="界面语言")
    languages: str = Field(default="zh-CN", description="接受的语言列表")
    timezone: str = Field(default="Asia/Shanghai", description="时区")
    signature_timestamp: Optional[str] = Field(default=None, description="签名时间戳")
    cookie_enabled: bool = Field(default=True, description="是否启用Cookie")
    screen_width: int = Field(default=1920, description="屏幕宽度")
    screen_height: int = Field(default=1080, description="屏幕高度")
    screen_resolution: str = Field(default="1920x1080", description="屏幕分辨率")
    viewport_width: int = Field(default=1920, description="视口宽度")
    viewport_height: int = Field(default=1080, description="视口高度")
    viewport_size: str = Field(default="1920x1080", description="视口尺寸")
    color_depth: int = Field(default=24, description="颜色深度")
    pixel_ratio: float = Field(default=1.0, description="像素比率")
    current_url: str = Field(default="", description="当前URL")
    pathname: str = Field(default="/", description="路径名")
    search: str = Field(default="", description="查询字符串")
    hash: str = Field(default="", description="URL哈希")
    host: str = Field(default="chat.z.ai", description="主机名")
    hostname: str = Field(default="chat.z.ai", description="主机名")
    protocol: str = Field(default="https:", description="协议")
    referrer: str = Field(default="", description="来源页面")
    title: str = Field(default="Z.ai Chat", description="页面标题")
    timezone_offset: int = Field(default=-480, description="时区偏移（分钟）")
    local_time: str = Field(default="", description="本地时间")
    utc_time: str = Field(default="", description="UTC时间")
    is_mobile: bool = Field(default=False, description="是否移动设备")
    is_touch: bool = Field(default=False, description="是否触摸设备")
    max_touch_points: int = Field(default=0, description="最大触摸点数")
    browser_name: str = Field(default="Chrome", description="浏览器名称")
    os_name: str = Field(default="Windows", description="操作系统名称")


class ModelFeatures(BaseModel):
    """模型功能特性配置。
    
    定义模型的各种功能开关，用于控制模型行为。
    """
    web_search: bool = Field(default=False, description="是否启用网络搜索")
    auto_web_search: bool = Field(default=False, description="是否自动触发网络搜索")
    preview_mode: bool = Field(default=True, description="是否启用预览模式")
    flags: List[str] = Field(default_factory=list, description="功能标志列表")
    enable_thinking: bool = Field(default=True, description="是否启用深度思考（思维链）")


class UpstreamRequestData(BaseModel):
    """上游 API 请求数据体。
    
    构建发送给智谱 AI API 的完整请求数据。
    包含智谱 AI 特有的字段和配置。
    
    :param stream: 是否流式响应
    :param model: 上游模型 ID（已转换）
    :param messages: 转换后的消息列表
    :param signature_prompt: 用于签名的提示词
    :param params: 生成参数（temperature, top_p, max_tokens）
    :param files: 非媒体文件列表
    :param mcp_servers: MCP 服务器列表
    :param features: 功能特性配置
    :param variables: 模板变量（如 {{CURRENT_DATETIME}}）
    :param model_item: 完整的模型对象
    :param background_tasks: 后台任务配置
    :param stream_options: 流式响应选项
    :param chat_id: 聊天会话 ID（UUID）
    :param id: 请求 ID（UUID）
    :type stream: bool
    :type model: str
    :type messages: List[Dict[str, Any]]
    :type signature_prompt: str
    :type params: Dict[str, Any]
    :type files: List[Dict[str, Any]]
    :type mcp_servers: List[str]
    :type features: Dict[str, Any]
    :type variables: Dict[str, str]
    :type model_item: Optional[Dict[str, Any]]
    :type background_tasks: Dict[str, bool]
    :type stream_options: Dict[str, bool]
    :type chat_id: str
    :type id: str
    
    .. note::
       此模型与 OpenAI API 不完全兼容，包含智谱 AI 扩展字段
    
    .. warning::
       ``signature_prompt`` 字段用于生成请求签名，必须与实际发送的内容一致
    """
    model_config = {"extra": "allow"}  # 允许额外字段以支持未来扩展
    
    stream: bool = Field(..., description="是否使用流式响应")
    model: str = Field(..., description="上游模型 ID")
    messages: List[Dict[str, Any]] = Field(..., description="转换后的消息列表")
    signature_prompt: str = Field(default="", description="用于签名的提示词内容")
    params: Dict[str, Any] = Field(default_factory=dict, description="生成参数（temperature, top_p, max_tokens）")
    files: List[Dict[str, Any]] = Field(default_factory=list, description="非媒体文件列表")
    features: Dict[str, Any] = Field(default_factory=dict, description="功能特性配置（包含 features 数组）")
    variables: Dict[str, str] = Field(default_factory=dict, description="模板变量（日期时间等）")
    model_item: Optional[Dict[str, Any]] = Field(default=None, description="完整的模型对象")
    background_tasks: Dict[str, bool] = Field(
        default_factory=lambda: {"title_generation": True, "tags_generation": True},
        description="后台任务配置"
    )
    chat_id: str = Field(..., description="会话 ID（UUID）")
    id: str = Field(..., description="请求 ID（UUID）")
    current_user_message_id: Optional[str] = Field(default=None, description="当前用户消息 ID")
    current_user_message_parent_id: Optional[str] = Field(default=None, description="当前用户消息父 ID")


class ConvertedMessages(BaseModel):
    """消息转换结果。
    
    包含转换后的消息、文件 URL 和最后一条用户消息文本。
    """
    messages: List[Dict[str, Any]] = Field(..., description="转换后的消息列表")
    file_urls: List[str] = Field(default_factory=list, description="文件 URL 列表")
    last_user_message_text: str = Field(default="", description="最后一条用户消息的文本内容")
