# -*- coding: utf-8 -*-
"""HTTP错误处理测试模块

测试各种HTTP错误场景，特别是：
- 400 Bad Request
- 405 Method Not Allowed
- 其他HTTP状态码错误
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from z2p_svc.app import app
from z2p_svc.chat_service import (
    process_non_streaming_response,
    process_streaming_response,
)
from z2p_svc.models import ChatRequest, Message


@pytest.fixture(name="client")
def _client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture(name="valid_chat_request")
def _valid_chat_request():
    """创建有效的聊天请求"""
    return ChatRequest(
        model="glm-4.6",
        messages=[
            Message(role="user", content="Hello, how are you?")
        ],
        stream=True,
    )


@pytest.fixture(name="valid_access_token")
def _valid_access_token():
    """创建有效的访问令牌"""
    return "test_access_token_12345"


class TestHTTP400BadRequest:
    """测试400 Bad Request错误场景"""

    @pytest.mark.asyncio
    async def test_streaming_response_400_error(
        self, valid_chat_request, valid_access_token
    ):
        """测试流式响应中的400错误"""
        # 创建模拟的400错误响应
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request: Invalid parameters"
        mock_response.url = "https://chat.z.ai/api/chat/completions"
        
        # 创建HTTPStatusError
        http_error = httpx.HTTPStatusError(
            "Client error '400 Bad Request' for url 'https://chat.z.ai/api/chat/completions'",
            request=MagicMock(),
            response=mock_response,
        )

        # Mock httpx.AsyncClient
        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(side_effect=http_error)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            # 执行测试
            result_chunks = []
            async for chunk in process_streaming_response(
                valid_chat_request, valid_access_token
            ):
                result_chunks.append(chunk)

            # 验证：由于错误被捕获，应该没有返回任何数据块
            assert len(result_chunks) == 0

    @pytest.mark.asyncio
    async def test_non_streaming_response_400_error(
        self, valid_chat_request, valid_access_token
    ):
        """测试非流式响应中的400错误"""
        valid_chat_request.stream = False
        
        # 创建模拟的400错误响应
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request: Invalid model parameter"
        mock_response.url = "https://chat.z.ai/api/chat/completions"
        
        # 创建HTTPStatusError
        http_error = httpx.HTTPStatusError(
            "Client error '400 Bad Request'",
            request=MagicMock(),
            response=mock_response,
        )

        # Mock httpx.AsyncClient
        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(side_effect=http_error)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            # 执行测试 - 应该抛出异常或返回空响应
            with pytest.raises(Exception):
                await process_non_streaming_response(
                    valid_chat_request, valid_access_token
                )

    def test_api_endpoint_400_invalid_model(self, client):
        """测试API端点：无效模型导致400错误"""
        response = client.post(
            "/v1/chat/completions",  # 修复：添加/v1前缀
            headers={"Authorization": "Bearer test_token"},
            json={
                "model": "invalid-model-name",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        
        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"].lower()


class TestHTTP405MethodNotAllowed:
    """测试405 Method Not Allowed错误场景"""

    @pytest.mark.asyncio
    async def test_streaming_response_405_error(
        self, valid_chat_request, valid_access_token
    ):
        """测试流式响应中的405错误"""
        # 创建模拟的405错误响应
        mock_response = MagicMock()
        mock_response.status_code = 405
        mock_response.text = "Method Not Allowed"
        mock_response.url = "https://chat.z.ai/api/chat/completions"
        
        # 创建HTTPStatusError
        http_error = httpx.HTTPStatusError(
            "Client error '405 Not Allowed' for url 'https://chat.z.ai/api/chat/completions'",
            request=MagicMock(),
            response=mock_response,
        )

        # Mock httpx.AsyncClient
        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(side_effect=http_error)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            # 执行测试
            result_chunks = []
            async for chunk in process_streaming_response(
                valid_chat_request, valid_access_token
            ):
                result_chunks.append(chunk)

            # 验证：由于错误被捕获，应该没有返回任何数据块
            assert len(result_chunks) == 0

    @pytest.mark.asyncio
    async def test_non_streaming_response_405_error(
        self, valid_chat_request, valid_access_token
    ):
        """测试非流式响应中的405错误"""
        valid_chat_request.stream = False
        
        # 创建模拟的405错误响应
        mock_response = MagicMock()
        mock_response.status_code = 405
        mock_response.text = "Method Not Allowed"
        mock_response.url = "https://chat.z.ai/api/chat/completions"
        
        # 创建HTTPStatusError
        http_error = httpx.HTTPStatusError(
            "Client error '405 Not Allowed'",
            request=MagicMock(),
            response=mock_response,
        )

        # Mock httpx.AsyncClient
        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(side_effect=http_error)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            # 执行测试
            with pytest.raises(Exception):
                await process_non_streaming_response(
                    valid_chat_request, valid_access_token
                )

    def test_api_endpoint_405_wrong_method(self, client):
        """测试API端点：使用错误的HTTP方法"""
        # 尝试使用GET方法访问POST端点
        response = client.get(
            "/v1/chat/completions",  # 修复：添加/v1前缀
            headers={"Authorization": "Bearer test_token"},
        )
        
        assert response.status_code == 405


class TestOtherHTTPErrors:
    """测试其他HTTP错误场景"""

    @pytest.mark.asyncio
    async def test_streaming_response_401_unauthorized(
        self, valid_chat_request, valid_access_token
    ):
        """测试流式响应中的401未授权错误"""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.url = "https://chat.z.ai/api/chat/completions"
        
        http_error = httpx.HTTPStatusError(
            "Client error '401 Unauthorized'",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(side_effect=http_error)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            result_chunks = []
            async for chunk in process_streaming_response(
                valid_chat_request, valid_access_token
            ):
                result_chunks.append(chunk)

            assert len(result_chunks) == 0

    @pytest.mark.asyncio
    async def test_streaming_response_500_server_error(
        self, valid_chat_request, valid_access_token
    ):
        """测试流式响应中的500服务器错误"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.url = "https://chat.z.ai/api/chat/completions"
        
        http_error = httpx.HTTPStatusError(
            "Server error '500 Internal Server Error'",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(side_effect=http_error)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            result_chunks = []
            async for chunk in process_streaming_response(
                valid_chat_request, valid_access_token
            ):
                result_chunks.append(chunk)

            assert len(result_chunks) == 0

    @pytest.mark.asyncio
    async def test_streaming_response_timeout_error(
        self, valid_chat_request, valid_access_token
    ):
        """测试流式响应中的超时错误"""
        timeout_error = httpx.TimeoutException("Request timeout")

        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(side_effect=timeout_error)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            result_chunks = []
            async for chunk in process_streaming_response(
                valid_chat_request, valid_access_token
            ):
                result_chunks.append(chunk)

            assert len(result_chunks) == 0

    @pytest.mark.asyncio
    async def test_streaming_response_connection_error(
        self, valid_chat_request, valid_access_token
    ):
        """测试流式响应中的连接错误"""
        connection_error = httpx.ConnectError("Connection failed")

        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(side_effect=connection_error)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            result_chunks = []
            async for chunk in process_streaming_response(
                valid_chat_request, valid_access_token
            ):
                result_chunks.append(chunk)

            assert len(result_chunks) == 0

    def test_api_endpoint_missing_authorization(self, client):
        """测试API端点：缺少授权头"""
        response = client.post(
            "/v1/chat/completions",  # 修复：添加/v1前缀
            json={
                "model": "glm-4.6",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        
        assert response.status_code == 401
        assert "Unauthorized" in response.json()["message"]


class TestHTTPErrorWithQueryParams:
    """测试带查询参数的HTTP错误场景（模拟实际错误日志中的情况）"""

    @pytest.mark.asyncio
    async def test_400_error_with_query_params(
        self, valid_chat_request, valid_access_token
    ):
        """测试带完整查询参数的400错误（模拟实际日志）"""
        # 模拟实际错误日志中的URL
        error_url = (
            "https://chat.z.ai/api/chat/completions"
            "?requestId=320e99ce-b06a-45b8-9efa-8d777e158fb4"
            "&timestamp=1760351123066"
            "&user_id=c7d53921-b3ae-493e-9ade-9eb625a14a19"
            "&signature_timestamp=1760351123066"
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request: Invalid signature or parameters"
        mock_response.url = error_url
        
        http_error = httpx.HTTPStatusError(
            f"Client error '400 Bad Request' for url '{error_url}'",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(side_effect=http_error)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            result_chunks = []
            async for chunk in process_streaming_response(
                valid_chat_request, valid_access_token
            ):
                result_chunks.append(chunk)

            # 验证错误被正确处理
            assert len(result_chunks) == 0

    @pytest.mark.asyncio
    async def test_405_error_with_query_params(
        self, valid_chat_request, valid_access_token
    ):
        """测试带完整查询参数的405错误（模拟实际日志）"""
        # 模拟实际错误日志中的URL
        error_url = (
            "https://chat.z.ai/api/chat/completions"
            "?requestId=5e83b651-a27a-4468-a8df-46ba16167ac8"
            "&timestamp=1760338140981"
            "&user_id=93e3773f-d617-4079-bec3-8dd0203d9cfe"
            "&signature_timestamp=1760338140981"
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 405
        mock_response.text = "Method Not Allowed"
        mock_response.url = error_url
        
        http_error = httpx.HTTPStatusError(
            f"Client error '405 Not Allowed' for url '{error_url}'",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(side_effect=http_error)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            result_chunks = []
            async for chunk in process_streaming_response(
                valid_chat_request, valid_access_token
            ):
                result_chunks.append(chunk)

            # 验证错误被正确处理
            assert len(result_chunks) == 0


class TestErrorRecovery:
    """测试错误恢复和重试机制"""

    @pytest.mark.asyncio
    async def test_partial_stream_then_error(
        self, valid_chat_request, valid_access_token
    ):
        """测试流式响应中途出错的情况"""
        
        async def mock_aiter_lines():
            """模拟部分成功后出错"""
            yield 'data: {"data": {"phase": "thinking", "delta_content": "思考中..."}}'
            yield 'data: {"data": {"phase": "answer", "delta_content": "回答开始"}}'
            # 然后抛出错误
            raise httpx.ReadError("Connection lost")
        
        with patch("z2p_svc.chat_service.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.aiter_lines = mock_aiter_lines
            mock_response.raise_for_status = MagicMock()
            
            mock_stream_context = MagicMock()
            mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.stream.return_value = mock_stream_context
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client

            result_chunks = []
            try:
                async for chunk in process_streaming_response(
                    valid_chat_request, valid_access_token
                ):
                    result_chunks.append(chunk)
            except Exception:
                pass  # 错误被捕获

            # 验证至少收到了部分数据
            assert len(result_chunks) >= 2