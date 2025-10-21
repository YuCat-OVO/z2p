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
    
    :ivar vision: 是否支持视觉能力（图像理解）
    :ivar citations: 是否支持引用来源
    :ivar preview_mode: 是否支持预览模式
    :ivar web_search: 是否支持网络搜索
    :ivar language_detection: 是否支持语言检测
    :ivar restore_n_source: 是否支持恢复源内容
    :ivar mcp: 是否支持 MCP（Model Context Protocol）工具调用
    :ivar file_qa: 是否支持文件问答
    :ivar returnFc: 是否返回函数调用信息
    :ivar returnThink: 是否返回思考过程
    :ivar think: 是否支持深度思考（思维链）
    """
    vision: bool = False
    citations: bool = False
    preview_mode: bool = False
    web_search: bool = False
    language_detection: bool = False
    restore_n_source: bool = False
    mcp: bool = False
    file_qa: bool = False
    returnFc: bool = False
    returnThink: bool = False
    think: bool = False


class UpstreamFeature(BaseModel):
    """上游功能特性配置。
    
    用于 suggestion_prompts 中定义特定功能的状态。
    
    :ivar type: 功能类型（如 "mcp", "web_search", "tool_selector"）
    :ivar server: 服务器标识（如 "vibe-coding", "ppt-maker"）
    :ivar status: 功能状态（"hidden", "selected", "pinned"）
    """
    type: str
    server: str
    status: str


class UpstreamPromptRemixId(BaseModel):
    """上游提示词混音ID。
    
    用于关联分享和源提示词的ID。
    
    :ivar zh_CN: 中文版本的ID（可能是字符串或对象）
    :ivar en_US: 英文版本的ID
    """
    zh_CN: Optional[Union[str, Dict[str, Any]]] = Field(alias="zh-CN", default=None)
    en_US: Optional[str] = Field(alias="en-US", default=None)


class UpstreamPrompt(BaseModel):
    """上游提示词配置。
    
    定义建议提示词的详细信息，用于前端 UI 展示。
    
    :ivar id: 提示词唯一标识
    :ivar name: 提示词中文名称
    :ivar name_en: 提示词英文名称
    :ivar prompt: 提示词中文内容
    :ivar prompt_en: 提示词英文内容
    :ivar thumb: 缩略图（可以是 URL 字符串或包含多语言 URL 的字典）
    :ivar files: 关联的文件列表
    :ivar remix: 混音信息（分享和源ID）
    """
    id: Optional[str] = None
    name: str
    name_en: str
    prompt: str
    prompt_en: str
    thumb: Optional[Union[str, Dict[str, str]]] = None
    files: Optional[List[Dict[str, Any]]] = None
    remix: Optional[Dict[str, UpstreamPromptRemixId]] = None


class UpstreamSuggestionPrompt(BaseModel):
    """上游建议提示词组配置。
    
    定义一组相关的建议提示词，用于前端 UI 分组展示。
    
    :ivar id: 提示词组唯一标识
    :ivar group_name: 提示词组中文名称
    :ivar group_name_en: 提示词组英文名称
    :ivar icon: 提示词组图标（SVG 字符串）
    :ivar prompts: 提示词列表
    :ivar flags: 功能标志列表（如 "ppt_composer", "web_dev"）
    :ivar features: 功能特性配置列表
    :ivar display_name: 显示名称
    :ivar tag: 中文标签（如 "🔥"）
    :ivar tag_en: 英文标签
    :ivar media: 是否包含媒体内容
    :ivar gallery: 是否在画廊中展示
    :ivar hidden: 是否隐藏
    """
    id: Optional[str] = None
    group_name: str
    group_name_en: Optional[str] = None
    icon: Optional[str] = None
    prompts: Optional[List[UpstreamPrompt]] = None
    flags: Optional[List[str]] = None
    features: Optional[List[UpstreamFeature]] = None
    display_name: Optional[str] = None
    tag: Optional[str] = None
    tag_en: Optional[str] = None
    media: Optional[bool] = None
    gallery: Optional[bool] = None
    hidden: Optional[bool] = None


class UpstreamMeta(BaseModel):
    """上游模型元数据。
    
    包含模型的 UI 显示和功能相关信息。
    
    :ivar profile_image_url: 模型头像 URL
    :ivar description: 模型描述（根据 Accept-Language 本地化）
    :ivar capabilities: 模型能力配置
    :ivar mcpServerIds: 兼容的 MCP 服务器 ID 列表
    :ivar suggestion_prompts: 建议提示词组列表
    :ivar tags: 模型标签列表（如 [{"name": "NEW"}]）
    :ivar hidden: 是否隐藏此模型
    """
    profile_image_url: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[UpstreamCapability] = None
    mcpServerIds: Optional[List[str]] = None
    suggestion_prompts: Optional[List[UpstreamSuggestionPrompt]] = None
    tags: Optional[List[Dict[str, str]]] = None
    hidden: Optional[bool] = None


class UpstreamModelInfo(BaseModel):
    """上游模型详细信息。
    
    包含模型的所有详细元数据。
    
    :ivar id: 模型唯一标识符
    :ivar user_id: 创建者用户 ID
    :ivar base_model_id: 基础模型 ID（如果是微调模型）
    :ivar name: 模型名称
    :ivar params: 模型默认参数（如 max_tokens, temperature）
    :ivar meta: 模型元数据
    :ivar access_control: 访问控制配置
    :ivar is_active: 模型是否激活
    :ivar updated_at: 更新时间戳
    :ivar created_at: 创建时间戳
    """
    id: str
    user_id: Optional[str] = None
    base_model_id: Optional[str] = None
    name: str
    params: Optional[Dict[str, Any]] = None
    meta: Optional[UpstreamMeta] = None
    access_control: Optional[Any] = None
    is_active: bool = True
    updated_at: Optional[int] = None
    created_at: Optional[int] = None


class UpstreamOpenAI(BaseModel):
    """上游 OpenAI 配置。
    
    包含 OpenAI 兼容的配置信息。
    
    :ivar id: OpenAI 模型 ID
    :ivar name: OpenAI 模型名称
    :ivar owned_by: 所有者标识
    :ivar openai: 嵌套的 OpenAI 配置
    :ivar urlIdx: URL 索引（用于负载均衡）
    """
    id: str
    name: str
    owned_by: str
    openai: Dict[str, str]
    urlIdx: int


class UpstreamModel(BaseModel):
    """上游模型定义。
    
    表示从上游 API 返回的完整模型对象。
    
    :ivar id: 模型唯一标识符
    :ivar name: 模型用户友好显示名称
    :ivar owned_by: 模型所有者或提供商标识
    :ivar openai: OpenAI 兼容配置
    :ivar urlIdx: URL 索引
    :ivar info: 模型详细信息
    :ivar actions: 可用操作列表
    :ivar tags: 模型标签列表
    """
    id: str
    name: str
    owned_by: str
    openai: UpstreamOpenAI
    urlIdx: int
    info: UpstreamModelInfo
    actions: List[Any] = []
    tags: List[Dict[str, str]] = []


class UpstreamModelsResponse(BaseModel):
    """上游模型列表响应。
    
    表示从上游 API `/api/models` 端点返回的完整响应。
    
    :ivar data: 模型对象列表
    """
    data: List[UpstreamModel]


# --- Downstream Models (下游 OpenAI 兼容模型) ---

class DownstreamModel(BaseModel):
    """下游模型定义（OpenAI 兼容）。
    
    符合 OpenAI API 规范的简化模型对象，用于 `/v1/models` 端点。
    参考：https://platform.openai.com/docs/api-reference/models/object
    
    :ivar id: 模型唯一标识符
    :ivar object: 对象类型，固定为 "model"
    :ivar created: 模型创建时间戳（Unix 时间）
    :ivar name: 模型显示名称
    :ivar owned_by: 模型所有者，默认为 "z.ai"
    """
    id: str = Field(..., description="模型唯一标识符")
    object: str = Field(default="model", description="对象类型")
    created: int = Field(..., description="创建时间戳")
    name: str = Field(..., description="模型显示名称")
    owned_by: str = Field(default="z.ai", description="模型所有者")


class DownstreamModelsResponse(BaseModel):
    """下游模型列表响应（OpenAI 兼容）。
    
    符合 OpenAI API 规范的模型列表响应，用于 `/v1/models` 端点。
    参考：https://platform.openai.com/docs/api-reference/models/list
    
    :ivar object: 对象类型，固定为 "list"
    :ivar data: 模型对象列表
    """
    object: str = Field(default="list", description="对象类型")
    data: List[DownstreamModel] = Field(..., description="模型列表")
