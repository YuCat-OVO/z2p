"""数据模型定义模块。

本模块定义API请求和响应的Pydantic模型，用于数据验证和序列化。
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class Message(BaseModel):
    """聊天消息模型。

    :ivar role: 消息角色，可选值：system, user, assistant
    :ivar content: 消息内容，可以是字符串或包含多个部分的列表（用于多模态输入）
    """

    role: str = Field(..., description="消息角色")
    content: Union[str, list] = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """聊天补全请求模型。

    :ivar model: 使用的模型名称
    :ivar messages: 消息列表
    :ivar stream: 是否使用流式响应
    :ivar temperature: 采样温度，控制输出的随机性，范围0.0-2.0
    :ivar top_p: 核采样参数，范围0.0-1.0
    :ivar max_tokens: 最大生成token数，最小值为1
    """

    model: str = Field(..., description="模型名称")
    messages: list[Message] = Field(..., description="消息列表")
    stream: bool = Field(default=False, description="是否流式响应")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="采样温度")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0, description="核采样参数")
    max_tokens: int = Field(default=8192, ge=1, description="最大token数")


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
