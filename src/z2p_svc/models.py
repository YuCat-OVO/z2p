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


# --- Upstream Models ---
class UpstreamCapability(BaseModel):
    """上游模型能力配置。"""
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
    """上游功能特性配置。"""
    type: str
    server: str
    status: str


class UpstreamPromptRemixId(BaseModel):
    """上游提示词混音ID。"""
    zh_CN: Optional[Union[str, Dict[str, Any]]] = Field(alias="zh-CN", default=None)
    en_US: Optional[str] = Field(alias="en-US", default=None)


class UpstreamPrompt(BaseModel):
    """上游提示词配置。"""
    id: Optional[str] = None
    name: str
    name_en: str
    prompt: str
    prompt_en: str
    thumb: Optional[Union[str, Dict[str, str]]] = None
    files: Optional[List[Dict[str, Any]]] = None
    remix: Optional[Dict[str, UpstreamPromptRemixId]] = None


class UpstreamSuggestionPrompt(BaseModel):
    """上游建议提示词配置。"""
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
    """上游模型元数据。"""
    profile_image_url: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[UpstreamCapability] = None
    mcpServerIds: Optional[List[str]] = None
    suggestion_prompts: Optional[List[UpstreamSuggestionPrompt]] = None
    tags: Optional[List[Dict[str, str]]] = None
    hidden: Optional[bool] = None


class UpstreamModelInfo(BaseModel):
    """上游模型信息。"""
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
    """上游OpenAI配置。"""
    id: str
    name: str
    owned_by: str
    openai: Dict[str, str]
    urlIdx: int


class UpstreamModel(BaseModel):
    """上游模型定义。"""
    id: str
    name: str
    owned_by: str
    openai: UpstreamOpenAI
    urlIdx: int
    info: UpstreamModelInfo
    actions: List[Any] = []
    tags: List[Dict[str, str]] = []


class UpstreamModelsResponse(BaseModel):
    """上游模型列表响应。"""
    data: List[UpstreamModel]


# --- Downstream Models ---
class DownstreamCapability(BaseModel):
    """下游模型能力配置。"""
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


class DownstreamMeta(BaseModel):
    """下游模型元数据。"""
    profile_image_url: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[DownstreamCapability] = None
    suggestion_prompts: Optional[List[Dict[str, Any]]] = None
    hidden: Optional[bool] = None


class DownstreamModel(BaseModel):
    """下游模型定义。"""
    id: str
    object: str = "model"
    created: int
    owned_by: str = "z.ai"
    name: str
    meta: Optional[DownstreamMeta] = None
    info: Optional[Dict[str, Any]] = None
    original: Optional[Dict[str, Any]] = None


class DownstreamModelsResponse(BaseModel):
    """下游模型列表响应。"""
    object: str = "list"
    data: List[DownstreamModel]
