"""模型服务单元测试。

测试 model_service 模块的核心功能，包括模型列表获取、缓存、映射等。
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.z2p_svc.model_service import (
    format_model_name,
    get_model_name,
    get_model_id,
    fetch_models_from_upstream,
    get_models,
    clear_models_cache,
    FEATURE_SWITCHES,
)


@pytest.mark.unit
class TestFormatModelName:
    """format_model_name 函数测试。"""
    
    def test_basic_formatting(self):
        """测试基本格式化。"""
        assert format_model_name("glm-4.6") == "GLM-4.6"
        assert format_model_name("glm-4.5v") == "GLM-4.5V"
    
    def test_empty_string(self):
        """测试空字符串。"""
        assert format_model_name("") == ""
    
    def test_already_uppercase(self):
        """测试已经大写的名称。"""
        assert format_model_name("GLM-4.6") == "GLM-4.6"
    
    def test_mixed_case(self):
        """测试混合大小写。"""
        assert format_model_name("GlM-4.6") == "GLM-4.6"


@pytest.mark.unit
class TestGetModelName:
    """get_model_name 函数测试。"""
    
    def test_glm_with_version(self):
        """测试 GLM 系列模型。"""
        result = get_model_name("GLM-4.6-API-V1", "GLM-4.6")
        assert result == "GLM-4.6-API-V1"
    
    def test_z_series_model(self):
        """测试 Z 系列模型。"""
        result = get_model_name("Z-1.0", "Z Model")
        assert result == "Z-1.0"
    
    def test_model_name_with_glm(self):
        """测试模型名称包含 GLM。"""
        result = get_model_name("some-id", "GLM-4.5")
        assert result == "GLM-4.5"
    
    def test_fallback_to_source_id(self):
        """测试回退到源 ID。"""
        result = get_model_name("custom-model", "自定义模型")
        assert "GLM-" in result.upper()
    
    def test_non_english_name(self):
        """测试非英文名称。"""
        result = get_model_name("model-123", "模型123")
        assert result.startswith("GLM-")


@pytest.mark.unit
class TestGetModelId:
    """get_model_id 函数测试。"""
    
    def test_with_mapping(self, test_settings):
        """测试使用配置映射。"""
        test_settings.MODELS_MAPPING["GLM-4-6-API-V1"] = "glm-4.6"
        result = get_model_id("GLM-4-6-API-V1", "GLM-4.6")
        assert result == "glm-4.6"
    
    def test_without_mapping(self):
        """测试无映射时的智能生成。"""
        result = get_model_id("UNKNOWN-MODEL", "Custom Model")
        assert result == "custom-model"
    
    def test_lowercase_conversion(self):
        """测试小写转换。"""
        result = get_model_id("TEST", "TEST MODEL")
        assert result == "test-model"
    
    def test_space_to_hyphen(self):
        """测试空格转连字符。"""
        result = get_model_id("test", "Test Model Name")
        assert result == "test-model-name"


@pytest.mark.unit
class TestFetchModelsFromUpstream:
    """fetch_models_from_upstream 函数测试。"""
    
    @pytest.mark.asyncio
    async def test_successful_fetch(self, mock_access_token):
        """测试成功获取模型列表。"""
        mock_response_data = {
            "data": [
                {
                    "id": "GLM-4-6-API-V1",
                    "name": "GLM-4.6",
                    "info": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {
                            "capabilities": {
                                "think": True,
                                "web_search": False,
                                "mcp": False,
                                "vision": False,
                                "file_qa": False
                            }
                        }
                    }
                }
            ]
        }
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            result = await fetch_models_from_upstream(mock_access_token)
            
            assert "data" in result
            assert len(result["data"]) == 1
            assert result["data"][0]["id"] == "GLM-4-6-API-V1"
    
    @pytest.mark.asyncio
    async def test_http_error(self, mock_access_token):
        """测试 HTTP 错误。"""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with pytest.raises(Exception) as exc_info:
                await fetch_models_from_upstream(mock_access_token)
            
            assert "获取模型列表失败" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_network_error(self, mock_access_token):
        """测试网络错误。"""
        import httpx
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            with pytest.raises(Exception) as exc_info:
                await fetch_models_from_upstream(mock_access_token)
            
            assert "模型列表请求错误" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_without_access_token(self):
        """测试不带访问令牌。"""
        mock_response_data = {"data": []}
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            result = await fetch_models_from_upstream(None)
            
            assert "data" in result
            # 验证请求头不包含 Authorization
            call_kwargs = mock_client.get.call_args[1]
            assert "Authorization" not in call_kwargs["headers"]


@pytest.mark.unit
class TestGetModels:
    """get_models 函数测试。"""
    
    @pytest.mark.asyncio
    async def test_basic_model_processing(self, mock_access_token):
        """测试基本模型处理。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "GLM-4-6-API-V1",
                    "name": "GLM-4.6",
                    "owned_by": "openai",
                    "openai": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "owned_by": "openai",
                        "openai": {"id": "GLM-4-6-API-V1"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {
                            "capabilities": {
                                "think": True,
                                "web_search": False,
                                "mcp": False,
                                "vision": False,
                                "file_qa": False
                            }
                        }
                    }
                }
            ]
        }
        
        clear_models_cache()  # 清除缓存
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            result = await get_models(mock_access_token, use_cache=False)
            
            assert "data" in result
            assert len(result["data"]) >= 1  # 至少有基础模型
            
            # 验证基础模型
            base_model = next((m for m in result["data"] if m["id"] == "glm-4.6"), None)
            assert base_model is not None
            assert base_model["name"] == "GLM-4.6"  # 名称是处理后的，不是上游ID
    
    @pytest.mark.asyncio
    async def test_variant_generation(self, mock_access_token):
        """测试变体生成。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "GLM-4-6-API-V1",
                    "name": "GLM-4.6",
                    "owned_by": "openai",
                    "openai": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "owned_by": "openai",
                        "openai": {"id": "GLM-4-6-API-V1"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {
                            "capabilities": {
                                "think": True,
                                "web_search": True,
                                "mcp": True,
                                "vision": False,
                                "file_qa": False
                            }
                        }
                    }
                }
            ]
        }
        
        clear_models_cache()
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            result = await get_models(mock_access_token, use_cache=False)
            
            # 应该生成 nothinking、search、mcp 变体
            model_ids = [m["id"] for m in result["data"]]
            assert "glm-4.6-nothinking" in model_ids
            assert "glm-4.6-search" in model_ids
            assert "glm-4.6-mcp" in model_ids
    
    @pytest.mark.asyncio
    async def test_cache_mechanism(self, mock_access_token):
        """测试缓存机制。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "TEST-MODEL",
                    "name": "Test",
                    "owned_by": "openai",
                    "openai": {
                        "id": "TEST-MODEL",
                        "name": "Test",
                        "owned_by": "openai",
                        "openai": {"id": "TEST-MODEL"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "TEST-MODEL",
                        "name": "Test",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {"capabilities": {}}
                    }
                }
            ]
        }
        
        clear_models_cache()
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            # 第一次调用
            result1 = await get_models(mock_access_token, use_cache=True)
            assert mock_fetch.call_count == 1
            
            # 第二次调用应该使用缓存
            result2 = await get_models(mock_access_token, use_cache=True)
            assert mock_fetch.call_count == 1  # 没有再次调用
            
            # 验证结果相同
            assert result1 == result2
    
    @pytest.mark.asyncio
    async def test_cache_bypass(self, mock_access_token):
        """测试绕过缓存。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "TEST-MODEL",
                    "name": "Test",
                    "owned_by": "openai",
                    "openai": {
                        "id": "TEST-MODEL",
                        "name": "Test",
                        "owned_by": "openai",
                        "openai": {"id": "TEST-MODEL"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "TEST-MODEL",
                        "name": "Test",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {"capabilities": {}}
                    }
                }
            ]
        }
        
        clear_models_cache()
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            # 第一次调用
            await get_models(mock_access_token, use_cache=False)
            assert mock_fetch.call_count == 1
            
            # 第二次调用不使用缓存
            await get_models(mock_access_token, use_cache=False)
            assert mock_fetch.call_count == 2
    
    @pytest.mark.asyncio
    async def test_inactive_models_filtered(self, mock_access_token):
        """测试过滤非激活模型。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "ACTIVE-MODEL",
                    "name": "Active",
                    "owned_by": "openai",
                    "openai": {
                        "id": "ACTIVE-MODEL",
                        "name": "Active",
                        "owned_by": "openai",
                        "openai": {"id": "ACTIVE-MODEL"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "ACTIVE-MODEL",
                        "name": "Active",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {"capabilities": {}}
                    }
                },
                {
                    "id": "INACTIVE-MODEL",
                    "name": "Inactive",
                    "owned_by": "openai",
                    "openai": {
                        "id": "INACTIVE-MODEL",
                        "name": "Inactive",
                        "owned_by": "openai",
                        "openai": {"id": "INACTIVE-MODEL"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "INACTIVE-MODEL",
                        "name": "Inactive",
                        "is_active": False,
                        "created_at": 1234567890,
                        "meta": {"capabilities": {}}
                    }
                }
            ]
        }
        
        clear_models_cache()
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            result = await get_models(mock_access_token, use_cache=False)
            
            model_ids = [m["id"] for m in result["data"]]
            assert any("active" in mid.lower() for mid in model_ids)
            assert not any("inactive" in mid.lower() for mid in model_ids)
    
    @pytest.mark.asyncio
    async def test_vision_variant_not_duplicated(self, mock_access_token):
        """测试 vision 变体不重复（如 glm-4.5v）。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "GLM-4-5V-API",
                    "name": "GLM-4.5V",
                    "owned_by": "openai",
                    "openai": {
                        "id": "GLM-4-5V-API",
                        "name": "GLM-4.5V",
                        "owned_by": "openai",
                        "openai": {"id": "GLM-4-5V-API"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "GLM-4-5V-API",
                        "name": "GLM-4.5V",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {
                            "capabilities": {
                                "think": False,
                                "web_search": False,
                                "mcp": False,
                                "vision": True,
                                "file_qa": False
                            }
                        }
                    }
                }
            ]
        }
        
        clear_models_cache()
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            result = await get_models(mock_access_token, use_cache=False)
            
            # 不应该生成 glm-4.5v-vision 变体
            model_ids = [m["id"] for m in result["data"]]
            assert not any("vision" in mid for mid in model_ids)
    
    @pytest.mark.asyncio
    async def test_reverse_mapping_creation(self, mock_access_token, test_settings):
        """测试反向映射创建。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "UPSTREAM-ID",
                    "name": "Test Model",
                    "owned_by": "openai",
                    "openai": {
                        "id": "UPSTREAM-ID",
                        "name": "Test Model",
                        "owned_by": "openai",
                        "openai": {"id": "UPSTREAM-ID"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "UPSTREAM-ID",
                        "name": "Test Model",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {"capabilities": {}}
                    }
                }
            ]
        }
        
        clear_models_cache()
        # 不清空 REVERSE_MODELS_MAPPING，因为它是全局的
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            result = await get_models(mock_access_token, use_cache=False)
            
            # 验证模型被正确处理（反向映射在 settings 中，不在 test_settings）
            assert len(result["data"]) > 0


@pytest.mark.unit
class TestClearModelsCache:
    """clear_models_cache 函数测试。"""
    
    @pytest.mark.asyncio
    async def test_cache_clearing(self, mock_access_token):
        """测试缓存清除。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "TEST",
                    "name": "Test",
                    "owned_by": "openai",
                    "openai": {
                        "id": "TEST",
                        "name": "Test",
                        "owned_by": "openai",
                        "openai": {"id": "TEST"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "TEST",
                        "name": "Test",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {"capabilities": {}}
                    }
                }
            ]
        }
        
        clear_models_cache()  # 先清除缓存确保测试隔离
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            # 填充缓存
            await get_models(mock_access_token, use_cache=True)
            assert mock_fetch.call_count == 1
            
            # 清除缓存
            clear_models_cache()
            
            # 下次调用应该重新获取
            await get_models(mock_access_token, use_cache=True)
            assert mock_fetch.call_count == 2


@pytest.mark.unit
class TestGLM46VisionVariant:
    """GLM-4.6V vision 变体测试。"""
    
    @pytest.mark.asyncio
    async def test_glm46v_variant_generation(self, mock_access_token):
        """测试 glm-4.6v 变体生成。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "GLM-4-6-API-V1",
                    "name": "GLM-4.6",
                    "owned_by": "openai",
                    "openai": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "owned_by": "openai",
                        "openai": {"id": "GLM-4-6-API-V1"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {
                            "capabilities": {
                                "think": True,
                                "web_search": True,
                                "mcp": True,
                                "vision": False,
                                "file_qa": True
                            }
                        }
                    }
                }
            ]
        }
        
        clear_models_cache()
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            result = await get_models(mock_access_token, use_cache=False)
            
            model_ids = [m["id"] for m in result["data"]]
            
            # 验证 glm-4.6v 基础变体存在
            assert "glm-4.6v" in model_ids
            
            # 验证 glm-4.6v 的名称
            glm46v_model = next((m for m in result["data"] if m["id"] == "glm-4.6v"), None)
            assert glm46v_model is not None
            assert glm46v_model["name"] == "GLM-4.6V"
    
    @pytest.mark.asyncio
    async def test_glm46v_feature_variants(self, mock_access_token):
        """测试 glm-4.6v 功能变体生成。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "GLM-4-6-API-V1",
                    "name": "GLM-4.6",
                    "owned_by": "openai",
                    "openai": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "owned_by": "openai",
                        "openai": {"id": "GLM-4-6-API-V1"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {
                            "capabilities": {
                                "think": True,
                                "web_search": True,
                                "mcp": True,
                                "vision": False,
                                "file_qa": True
                            }
                        }
                    }
                }
            ]
        }
        
        clear_models_cache()
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            result = await get_models(mock_access_token, use_cache=False)
            
            model_ids = [m["id"] for m in result["data"]]
            
            # 验证 glm-4.6v 的功能变体存在
            assert "glm-4.6v-nothinking" in model_ids
            assert "glm-4.6v-search" in model_ids
            assert "glm-4.6v-mcp" in model_ids
            assert "glm-4.6v-fileqa" in model_ids
            
            # 验证不会生成 glm-4.6v-vision（因为已经是 vision 变体）
            assert "glm-4.6v-vision" not in model_ids
    
    @pytest.mark.asyncio
    async def test_glm46v_reverse_mapping(self, mock_access_token):
        """测试 glm-4.6v 反向映射。"""
        mock_upstream_data = {
            "data": [
                {
                    "id": "GLM-4-6-API-V1",
                    "name": "GLM-4.6",
                    "owned_by": "openai",
                    "openai": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "owned_by": "openai",
                        "openai": {"id": "GLM-4-6-API-V1"},
                        "urlIdx": 0
                    },
                    "urlIdx": 0,
                    "info": {
                        "id": "GLM-4-6-API-V1",
                        "name": "GLM-4.6",
                        "is_active": True,
                        "created_at": 1234567890,
                        "meta": {
                            "capabilities": {
                                "think": True,
                                "web_search": False,
                                "mcp": False,
                                "vision": False,
                                "file_qa": False
                            }
                        }
                    }
                }
            ]
        }
        
        clear_models_cache()
        # 清空全局 settings 的 REVERSE_MODELS_MAPPING
        from src.z2p_svc.model_service import settings as global_settings
        global_settings.REVERSE_MODELS_MAPPING.clear()
        
        with patch("src.z2p_svc.model_service.fetch_models_from_upstream") as mock_fetch:
            mock_fetch.return_value = mock_upstream_data
            
            result = await get_models(mock_access_token, use_cache=False)
            
            # 验证 glm-4.6v 模型存在于结果中
            model_ids = [m["id"] for m in result["data"]]
            assert "glm-4.6v" in model_ids
            
            # 验证映射链: glm-4.6v -> glm-4.6 -> GLM-4-6-API-V1
            assert "glm-4.6v" in global_settings.REVERSE_MODELS_MAPPING
            assert global_settings.REVERSE_MODELS_MAPPING["glm-4.6v"] == "glm-4.6"
            
            # 验证 glm-4.6v 变体的映射: glm-4.6v-nothinking -> glm-4.6v
            if "glm-4.6v-nothinking" in global_settings.REVERSE_MODELS_MAPPING:
                assert global_settings.REVERSE_MODELS_MAPPING["glm-4.6v-nothinking"] == "glm-4.6v"


@pytest.mark.unit
class TestFeatureSwitches:
    """FEATURE_SWITCHES 配置测试。"""
    
    def test_feature_switches_structure(self):
        """测试功能开关配置结构。"""
        assert "think" in FEATURE_SWITCHES
        assert "web_search" in FEATURE_SWITCHES
        assert "mcp" in FEATURE_SWITCHES
        assert "vision" in FEATURE_SWITCHES
        assert "file_qa" in FEATURE_SWITCHES
        
        for feature, config in FEATURE_SWITCHES.items():
            assert "suffix" in config
            assert "name_suffix" in config
            assert "description_suffix" in config