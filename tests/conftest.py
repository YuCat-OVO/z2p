"""全局测试配置和 fixtures。

本模块提供所有测试共享的 fixtures 和配置。
"""

import os
import sys
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from httpx import AsyncClient

# 在导入任何模块之前设置必需的环境变量
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_testing_only_16chars")
os.environ.setdefault("PROXY_URL", "https://test.example.com")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("VERBOSE_LOGGING", "false")

# 确保可以导入 src 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.z2p_svc.config import AppConfig


@pytest.fixture(scope="session")
def test_settings() -> AppConfig:
    """测试环境配置。
    
    提供隔离的测试配置，避免影响生产环境。
    """
    os.environ["APP_ENV"] = "development"
    os.environ["SECRET_KEY"] = "test_secret_key_for_testing_only_16chars"
    os.environ["PROXY_URL"] = "https://test.example.com"
    os.environ["LOG_LEVEL"] = "DEBUG"
    os.environ["VERBOSE_LOGGING"] = "false"
    
    return AppConfig()


@pytest.fixture
def mock_settings(test_settings: AppConfig) -> AppConfig:
    """可修改的测试配置副本。"""
    return test_settings.model_copy(deep=True)


@pytest.fixture
def mock_access_token() -> str:
    """模拟访问令牌。"""
    return "test_access_token_12345"


@pytest.fixture
def mock_user_id() -> str:
    """模拟用户 ID。"""
    return "test_user_id_67890"


@pytest.fixture
def mock_chat_id() -> str:
    """模拟聊天会话 ID。"""
    return "test_chat_id_abcde"


@pytest.fixture
def mock_request_id() -> str:
    """模拟请求 ID。"""
    return "test_request_id_fghij"


@pytest.fixture
def mock_httpx_client() -> AsyncMock:
    """模拟 httpx.AsyncClient。
    
    提供预配置的 AsyncClient mock，用于测试 HTTP 请求。
    """
    client = AsyncMock(spec=AsyncClient)
    
    # 配置默认响应
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = AsyncMock(return_value={"data": []})
    mock_response.text = ""
    mock_response.headers = {}
    
    client.get = AsyncMock(return_value=mock_response)
    client.post = AsyncMock(return_value=mock_response)
    client.stream = AsyncMock()
    
    return client


@pytest.fixture
def sample_chat_request_data() -> dict:
    """示例聊天请求数据。"""
    return {
        "model": "glm-4.6",
        "messages": [
            {"role": "system", "content": "你是一个有帮助的助手。"},
            {"role": "user", "content": "你好，请介绍一下自己。"}
        ],
        "stream": False,
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 2048
    }


@pytest.fixture
def sample_streaming_chat_request_data(sample_chat_request_data: dict) -> dict:
    """示例流式聊天请求数据。"""
    data = sample_chat_request_data.copy()
    data["stream"] = True
    return data


@pytest.fixture
def sample_models_response() -> dict:
    """示例模型列表响应。"""
    return {
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
            },
            {
                "id": "glm-4.5",
                "object": "model",
                "created": 1234567890,
                "owned_by": "zhipu",
                "info": {
                    "id": "0727-360B-API",
                    "name": "GLM-4.5",
                    "meta": {
                        "capabilities": {
                            "think": False,
                            "web_search": False
                        }
                    }
                }
            }
        ]
    }


@pytest.fixture
def sample_file_upload_response() -> dict:
    """示例文件上传响应。"""
    return {
        "id": "file_12345",
        "name": "test_image.png",
        "media": "image",
        "size": 1024,
        "url": "https://example.com/files/file_12345"
    }


@pytest.fixture
def sample_chat_completion_response() -> dict:
    """示例聊天补全响应（非流式）。"""
    return {
        "id": "chatcmpl-12345",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "glm-4.6",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "你好！我是一个AI助手。"
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 20,
            "completion_tokens": 15,
            "total_tokens": 35
        }
    }


@pytest.fixture
def sample_chat_completion_chunk() -> dict:
    """示例聊天补全响应块（流式）。"""
    return {
        "id": "chatcmpl-12345",
        "object": "chat.completion.chunk",
        "created": 1234567890,
        "model": "glm-4.6",
        "choices": [
            {
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": "你好"
                },
                "finish_reason": None
            }
        ]
    }


@pytest.fixture
def mock_file_uploader() -> AsyncMock:
    """模拟文件上传器。"""
    uploader = AsyncMock()
    uploader.upload_base64_file = AsyncMock(return_value={
        "id": "file_12345",
        "name": "test_file.png",
        "media": "image",
        "size": 1024
    })
    uploader.upload_file_from_url = AsyncMock(return_value={
        "id": "file_67890",
        "name": "remote_file.jpg",
        "media": "image",
        "size": 2048
    })
    return uploader


@pytest.fixture
def mock_signature_generator() -> Mock:
    """模拟签名生成器。"""
    def generate_signature_mock(request_params: str, content: str) -> dict:
        return {
            "signature": "mock_signature_abcdef123456",
            "timestamp": 1234567890000
        }
    return Mock(side_effect=generate_signature_mock)


@pytest.fixture(autouse=True)
def reset_lru_cache():
    """自动重置 LRU 缓存。
    
    确保每个测试都有干净的缓存状态。
    """
    from src.z2p_svc.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_logger() -> Mock:
    """模拟日志记录器。"""
    logger = Mock()
    logger.debug = Mock()
    logger.info = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    logger.critical = Mock()
    return logger


# 异步测试辅助 fixtures
@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """异步 HTTP 客户端。
    
    用于集成测试和端到端测试。
    """
    async with AsyncClient() as client:
        yield client


@pytest.fixture
def anyio_backend():
    """指定 anyio 后端为 asyncio。"""
    return "asyncio"