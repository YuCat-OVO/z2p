"""数据模型定义模块。

本模块定义API请求和响应的Pydantic模型，用于数据验证和序列化。
"""

from typing import Union

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
