"""测试数据构建器。

使用 Builder 模式创建测试数据，提高测试代码的可读性和可维护性。
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4


class ChatRequestBuilder:
    """聊天请求构建器。

    使用链式调用构建测试用的聊天请求数据。

    Example::

        request = (ChatRequestBuilder()
            .with_model("glm-4.6")
            .with_message("user", "你好")
            .with_streaming(True)
            .build())
    """

    def __init__(self):
        self._data = {
            "model": "glm-4.6",
            "messages": [],
            "stream": False,
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 2048,
        }

    def with_model(self, model: str) -> "ChatRequestBuilder":
        """设置模型名称。"""
        self._data["model"] = model
        return self

    def with_message(self, role: str, content: str | list) -> "ChatRequestBuilder":
        """添加消息。"""
        self._data["messages"].append({"role": role, "content": content})
        return self

    def with_messages(self, messages: list[dict]) -> "ChatRequestBuilder":
        """批量添加消息。"""
        self._data["messages"].extend(messages)
        return self

    def with_streaming(self, stream: bool = True) -> "ChatRequestBuilder":
        """设置是否流式响应。"""
        self._data["stream"] = stream
        return self

    def with_temperature(self, temperature: float) -> "ChatRequestBuilder":
        """设置温度参数。"""
        self._data["temperature"] = temperature
        return self

    def with_top_p(self, top_p: float) -> "ChatRequestBuilder":
        """设置 top_p 参数。"""
        self._data["top_p"] = top_p
        return self

    def with_max_tokens(self, max_tokens: int) -> "ChatRequestBuilder":
        """设置最大 token 数。"""
        self._data["max_tokens"] = max_tokens
        return self

    def build(self) -> dict:
        """构建最终的请求数据。"""
        return self._data.copy()


class UpstreamRequestDataBuilder:
    """上游请求数据构建器。"""

    def __init__(self):
        self._data = {
            "stream": False,
            "model": "GLM-4-6-API-V1",
            "messages": [],
            "signature_prompt": "",
            "params": {},
            "files": [],
            "mcp_servers": [],
            "features": {
                "enable_thinking": True,
                "web_search": False,
                "auto_web_search": False,
                "preview_mode": False,
            },
            "variables": {
                "{{CURRENT_DATETIME}}": datetime.now().isoformat(),
                "{{CURRENT_DATE}}": datetime.now().strftime("%Y-%m-%d"),
                "{{CURRENT_TIME}}": datetime.now().strftime("%H:%M:%S"),
            },
            "chat_id": str(uuid4()),
            "id": str(uuid4()),
        }

    def with_stream(self, stream: bool) -> "UpstreamRequestDataBuilder":
        """设置是否流式。"""
        self._data["stream"] = stream
        return self

    def with_model(self, model: str) -> "UpstreamRequestDataBuilder":
        """设置模型。"""
        self._data["model"] = model
        return self

    def with_messages(self, messages: list[dict]) -> "UpstreamRequestDataBuilder":
        """设置消息列表。"""
        self._data["messages"] = messages
        return self

    def with_signature_prompt(self, prompt: str) -> "UpstreamRequestDataBuilder":
        """设置签名提示词。"""
        self._data["signature_prompt"] = prompt
        return self

    def with_features(self, **features) -> "UpstreamRequestDataBuilder":
        """设置特性。"""
        self._data["features"].update(features)
        return self

    def with_files(self, files: list[dict]) -> "UpstreamRequestDataBuilder":
        """设置文件列表。"""
        self._data["files"] = files
        return self

    def with_chat_id(self, chat_id: str) -> "UpstreamRequestDataBuilder":
        """设置聊天 ID。"""
        self._data["chat_id"] = chat_id
        return self

    def with_request_id(self, request_id: str) -> "UpstreamRequestDataBuilder":
        """设置请求 ID。"""
        self._data["id"] = request_id
        return self

    def build(self) -> dict:
        """构建最终数据。"""
        return self._data.copy()


class ChatCompletionResponseBuilder:
    """聊天补全响应构建器。"""

    def __init__(self):
        self._data = {
            "id": f"chatcmpl-{uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": "glm-4.6",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "这是一个测试响应。"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    def with_id(self, response_id: str) -> "ChatCompletionResponseBuilder":
        """设置响应 ID。"""
        self._data["id"] = response_id
        return self

    def with_model(self, model: str) -> "ChatCompletionResponseBuilder":
        """设置模型。"""
        self._data["model"] = model
        return self

    def with_content(self, content: str) -> "ChatCompletionResponseBuilder":
        """设置响应内容。"""
        self._data["choices"][0]["message"]["content"] = content
        return self

    def with_finish_reason(self, reason: str) -> "ChatCompletionResponseBuilder":
        """设置完成原因。"""
        self._data["choices"][0]["finish_reason"] = reason
        return self

    def with_usage(
        self, prompt_tokens: int, completion_tokens: int
    ) -> "ChatCompletionResponseBuilder":
        """设置使用统计。"""
        self._data["usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
        return self

    def build(self) -> dict:
        """构建最终响应。"""
        return self._data.copy()


class ChatCompletionChunkBuilder:
    """聊天补全流式响应块构建器。"""

    def __init__(self):
        self._data = {
            "id": f"chatcmpl-{uuid4().hex[:8]}",
            "object": "chat.completion.chunk",
            "created": int(datetime.now().timestamp()),
            "model": "glm-4.6",
            "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": None}],
        }

    def with_id(self, response_id: str) -> "ChatCompletionChunkBuilder":
        """设置响应 ID。"""
        self._data["id"] = response_id
        return self

    def with_model(self, model: str) -> "ChatCompletionChunkBuilder":
        """设置模型。"""
        self._data["model"] = model
        return self

    def with_content(self, content: str) -> "ChatCompletionChunkBuilder":
        """设置增量内容。"""
        self._data["choices"][0]["delta"]["content"] = content
        return self

    def with_role(self, role: str) -> "ChatCompletionChunkBuilder":
        """设置角色（仅首个块）。"""
        self._data["choices"][0]["delta"]["role"] = role
        return self

    def with_finish_reason(self, reason: str) -> "ChatCompletionChunkBuilder":
        """设置完成原因。"""
        self._data["choices"][0]["finish_reason"] = reason
        return self

    def with_usage(
        self, prompt_tokens: int, completion_tokens: int
    ) -> "ChatCompletionChunkBuilder":
        """添加使用统计（最后一个块）。"""
        self._data["usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
        return self

    def build(self) -> dict:
        """构建最终响应块。"""
        return self._data.copy()


class FileUploadResponseBuilder:
    """文件上传响应构建器。"""

    def __init__(self):
        self._data = {
            "id": f"file_{uuid4().hex[:8]}",
            "name": "test_file.png",
            "media": "image",
            "size": 1024,
            "url": "https://example.com/files/test_file.png",
        }

    def with_id(self, file_id: str) -> "FileUploadResponseBuilder":
        """设置文件 ID。"""
        self._data["id"] = file_id
        return self

    def with_name(self, name: str) -> "FileUploadResponseBuilder":
        """设置文件名。"""
        self._data["name"] = name
        return self

    def with_media_type(self, media: str) -> "FileUploadResponseBuilder":
        """设置媒体类型。"""
        self._data["media"] = media
        return self

    def with_size(self, size: int) -> "FileUploadResponseBuilder":
        """设置文件大小。"""
        self._data["size"] = size
        return self

    def build(self) -> dict:
        """构建最终响应。"""
        return self._data.copy()


class ModelResponseBuilder:
    """模型响应构建器。"""

    def __init__(self):
        self._data = {
            "id": "glm-4.6",
            "object": "model",
            "created": int(datetime.now().timestamp()),
            "owned_by": "zhipu",
            "info": {
                "id": "GLM-4-6-API-V1",
                "name": "GLM-4.6",
                "meta": {"capabilities": {"think": True, "web_search": False}},
            },
        }

    def with_id(self, model_id: str) -> "ModelResponseBuilder":
        """设置模型 ID。"""
        self._data["id"] = model_id
        return self

    def with_upstream_id(self, upstream_id: str) -> "ModelResponseBuilder":
        """设置上游模型 ID。"""
        self._data["info"]["id"] = upstream_id
        return self

    def with_name(self, name: str) -> "ModelResponseBuilder":
        """设置模型名称。"""
        self._data["info"]["name"] = name
        return self
    
    def with_capabilities(self, **capabilities) -> "ModelResponseBuilder":
        """设置模型能力。"""
        self._data["info"]["meta"]["capabilities"].update(capabilities)
        return self
    
    def build(self) -> dict:
        """构建最终模型数据。"""
        return self._data.copy()