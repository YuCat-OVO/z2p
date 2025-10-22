"""Mock 对象工厂。

提供预配置的 Mock 对象，用于隔离测试。
"""

from typing import Any, AsyncIterator, Optional
from unittest.mock import AsyncMock, Mock, MagicMock
import json


class MockHttpxResponse:
    """模拟 httpx.Response 对象。"""
    
    def __init__(
        self,
        status_code: int = 200,
        json_data: Optional[dict] = None,
        text: str = "",
        headers: Optional[dict] = None,
        stream_data: Optional[list] = None
    ):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.headers = headers or {}
        self._stream_data = stream_data or []
        self.is_error = status_code >= 400
    
    def json(self):
        """返回 JSON 数据。"""
        return self._json_data
    
    async def aiter_lines(self) -> AsyncIterator[str]:
        """异步迭代行数据（用于流式响应）。"""
        for line in self._stream_data:
            yield line
    
    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        """异步迭代字节数据。"""
        for line in self._stream_data:
            yield line.encode() if isinstance(line, str) else line
    
    def raise_for_status(self):
        """检查状态码。"""
        if self.is_error:
            raise Exception(f"HTTP {self.status_code}")


class MockFileUploader:
    """模拟文件上传器。"""
    
    @staticmethod
    def create(
        upload_base64_result: Optional[dict] = None,
        upload_url_result: Optional[dict] = None,
        should_fail: bool = False
    ) -> AsyncMock:
        """创建文件上传器 Mock。
        
        :param upload_base64_result: base64 上传返回结果
        :param upload_url_result: URL 上传返回结果
        :param should_fail: 是否模拟失败
        """
        uploader = AsyncMock()
        
        if should_fail:
            uploader.upload_base64_file = AsyncMock(side_effect=Exception("Upload failed"))
            uploader.upload_file_from_url = AsyncMock(side_effect=Exception("Upload failed"))
        else:
            default_base64_result = {
                "id": "file_base64_123",
                "name": "test_image.png",
                "media": "image",
                "size": 1024
            }
            default_url_result = {
                "id": "file_url_456",
                "name": "remote_image.jpg",
                "media": "image",
                "size": 2048
            }
            
            uploader.upload_base64_file = AsyncMock(
                return_value=upload_base64_result or default_base64_result
            )
            uploader.upload_file_from_url = AsyncMock(
                return_value=upload_url_result or default_url_result
            )
        
        return uploader


class MockModelService:
    """模拟模型服务。"""
    
    @staticmethod
    def create(models_data: Optional[dict] = None) -> AsyncMock:
        """创建模型服务 Mock。
        
        :param models_data: 模型列表数据
        """
        default_models = {
            "object": "list",
            "data": [
                {
                    "id": "glm-4.6",
                    "object": "model",
                    "created": 1234567890,
                    "owned_by": "zhipu",
                    "info": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "meta": {
                            "capabilities": {
                                "think": True,
                                "web_search": False
                            }
                        }
                    }
                }
            ]
        }
        
        service = AsyncMock()
        service.get_models = AsyncMock(return_value=models_data or default_models)
        return service


class MockSignatureGenerator:
    """模拟签名生成器。"""
    
    @staticmethod
    def create(signature: str = "mock_signature_123", timestamp: int = 1234567890000) -> Mock:
        """创建签名生成器 Mock。
        
        :param signature: 签名字符串
        :param timestamp: 时间戳
        """
        def generate_mock(request_params: str, content: str) -> dict:
            return {
                "signature": signature,
                "timestamp": timestamp
            }
        
        return Mock(side_effect=generate_mock)


class MockStreamingResponse:
    """模拟流式响应。"""
    
    @staticmethod
    def create_sse_chunks(
        chunks: list[str],
        include_thinking: bool = False,
        include_usage: bool = True
    ) -> list[str]:
        """创建 SSE 格式的数据块。
        
        :param chunks: 内容块列表
        :param include_thinking: 是否包含 thinking 阶段
        :param include_usage: 是否包含使用统计
        """
        sse_lines = []
        
        # Thinking 阶段
        if include_thinking:
            sse_lines.append('data: {"phase":"thinking","delta_content":"思考中..."}\n')
        
        # Answer 阶段
        for chunk in chunks:
            sse_lines.append(f'data: {{"phase":"answer","delta_content":"{chunk}"}}\n')
        
        # 结束阶段
        if include_usage:
            usage_data = {
                "phase": "other",
                "delta_content": "",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30
                }
            }
            sse_lines.append(f'data: {json.dumps(usage_data)}\n')
        
        sse_lines.append('data: [DONE]\n')
        
        return sse_lines


class MockHttpxClient:
    """模拟 httpx.AsyncClient。"""
    
    @staticmethod
    def create(
        get_response: Optional[MockHttpxResponse] = None,
        post_response: Optional[MockHttpxResponse] = None,
        stream_response: Optional[MockHttpxResponse] = None
    ) -> AsyncMock:
        """创建 HTTP 客户端 Mock。
        
        :param get_response: GET 请求响应
        :param post_response: POST 请求响应
        :param stream_response: 流式请求响应
        """
        client = AsyncMock()
        
        # 默认响应
        default_response = MockHttpxResponse(
            status_code=200,
            json_data={"data": []},
            text="",
            headers={}
        )
        
        # 配置方法
        client.get = AsyncMock(return_value=get_response or default_response)
        client.post = AsyncMock(return_value=post_response or default_response)
        
        # 配置流式响应
        if stream_response:
            async def mock_stream(*args, **kwargs):
                class StreamContext:
                    async def __aenter__(self):
                        return stream_response
                    async def __aexit__(self, *args):
                        pass
                return StreamContext()
            
            client.stream = mock_stream
        else:
            client.stream = AsyncMock()
        
        return client


class MockConverter:
    """模拟消息转换器。"""
    
    @staticmethod
    def create(
        messages: Optional[list] = None,
        last_user_message: str = "测试消息",
        file_urls: Optional[list] = None
    ) -> Mock:
        """创建转换器 Mock。
        
        :param messages: 转换后的消息列表
        :param last_user_message: 最后一条用户消息
        :param file_urls: 文件 URL 列表
        """
        class ConvertResult:
            def __init__(self):
                self.messages = messages or [
                    {"role": "user", "content": last_user_message}
                ]
                self.last_user_message_text = last_user_message
                self.file_urls = file_urls or []
        
        def convert_mock(input_messages):
            return ConvertResult()
        
        return Mock(side_effect=convert_mock)


def create_mock_settings(**overrides) -> Mock:
    """创建配置 Mock。
    
    :param overrides: 要覆盖的配置项
    """
    settings = Mock()
    settings.proxy_url = overrides.get("proxy_url", "https://test.example.com")
    settings.secret_key = overrides.get("secret_key", "test_secret_key_16chars")
    settings.protocol = overrides.get("protocol", "https:")
    settings.base_url = overrides.get("base_url", "test.example.com")
    settings.verbose_logging = overrides.get("verbose_logging", False)
    settings.log_level = overrides.get("log_level", "INFO")
    settings.HEADERS = overrides.get("HEADERS", {
        "User-Agent": "Test/1.0",
        "X-FE-Version": "test-1.0.0"
    })
    settings.MODELS_MAPPING = overrides.get("MODELS_MAPPING", {
        "GLM-4-6-API-V1": "glm-4.6"
    })
    settings.REVERSE_MODELS_MAPPING = overrides.get("REVERSE_MODELS_MAPPING", {
        "glm-4.6": "GLM-4-6-API-V1"
    })
    return settings