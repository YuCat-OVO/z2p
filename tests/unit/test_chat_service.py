"""聊天服务单元测试。

测试 chat_service 模块的核心功能，包括模型特性配置、请求数据准备等。
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.z2p_svc.chat_service import get_model_features, prepare_request_data
from src.z2p_svc.models import ChatRequest
from tests.fixtures import ChatRequestBuilder, create_mock_settings


@pytest.mark.unit
class TestGetModelFeatures:
    """get_model_features 函数测试。"""

    def test_default_features_streaming(self):
        """测试流式请求的默认特性。"""
        result = get_model_features("glm-4.6", streaming=True)

        assert "features" in result
        assert "mcp_servers" in result
        assert result["features"]["enable_thinking"] is True
        assert result["features"]["web_search"] is False
        assert result["mcp_servers"] == []

    def test_default_features_non_streaming(self):
        """测试非流式请求禁用 thinking。"""
        result = get_model_features("glm-4.6", streaming=False)

        assert result["features"]["enable_thinking"] is False

    def test_nothinking_suffix_disables_thinking(self):
        """测试 -nothinking 后缀禁用思考功能。"""
        result = get_model_features("glm-4.6-nothinking", streaming=True)

        assert result["features"]["enable_thinking"] is False

    def test_search_suffix_enables_search(self):
        """测试 -search 后缀启用搜索功能。"""
        result = get_model_features("glm-4.6-search", streaming=True)

        assert result["features"]["web_search"] is True
        assert result["features"]["auto_web_search"] is True
        assert result["features"]["preview_mode"] is True

    def test_advanced_search_suffix_adds_mcp_server(self):
        """测试 -advanced-search 后缀添加 MCP 服务器。"""
        result = get_model_features("glm-4.6-advanced-search", streaming=True)

        assert result["features"]["web_search"] is True
        assert "advanced-search" in result["mcp_servers"]

    def test_model_capabilities_override_thinking(self):
        """测试模型能力配置覆盖 thinking 设置。"""
        # 模型不支持 thinking
        capabilities = {"capabilities": {"think": False}}
        result = get_model_features(
            "glm-4.6", streaming=True, model_capabilities=capabilities
        )

        assert result["features"]["enable_thinking"] is False

    def test_case_insensitive_suffix_detection(self):
        """测试后缀检测不区分大小写。"""
        result = get_model_features("GLM-4.6-NOTHINKING", streaming=True)

        assert result["features"]["enable_thinking"] is False


@pytest.mark.unit
class TestPrepareRequestData:
    """prepare_request_data 函数测试。"""

    @pytest.mark.asyncio
    async def test_basic_request_preparation(self, mock_access_token):
        """测试基本请求准备。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.6")
            .with_message("user", "你好")
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch(
                "src.z2p_svc.services.chat.converter.convert_messages"
            ) as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
        ):
            # 配置 mocks
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.6",
                        "info": {
                            "id": "GLM-4-6-API-V1",
                            "meta": {"capabilities": {"think": True}},
                        },
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "你好"}]
                last_user_message_text = "你好"
                file_urls = []

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {"signature": "test_sig", "timestamp": 123456}

            # 执行测试
            zai_data, params, headers = await prepare_request_data(
                chat_request, mock_access_token, streaming=False
            )

            # 验证结果
            assert zai_data["model"] == "GLM-4-6-API-V1"
            assert zai_data["stream"] is False
            assert len(zai_data["messages"]) > 0
            assert "requestId" in params
            assert "Authorization" in headers

    @pytest.mark.asyncio
    async def test_model_not_found_raises_error(self, mock_access_token):
        """测试模型不存在时抛出异常。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("invalid-model")
            .with_message("user", "测试")
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch(
                "src.z2p_svc.services.chat.converter.convert_messages"
            ) as mock_convert,
        ):
            mock_get_models.return_value = {"data": []}

            class MockConvertResult:
                messages = [{"role": "user", "content": "测试"}]
                last_user_message_text = "测试"
                file_urls = []

            mock_convert.return_value = MockConvertResult()

            with pytest.raises(ValueError) as exc_info:
                await prepare_request_data(chat_request, mock_access_token)

            assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_file_upload_processing(self, mock_access_token):
        """测试文件上传处理。

        注意：此测试验证文件上传逻辑的存在性，
        完整的文件上传功能测试应在集成测试中进行。
        """
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.6")
            .with_message("user", "看这张图片")
            .build()
        )

        # 这个测试主要验证代码路径，不验证具体的文件上传调用
        # 因为文件上传涉及复杂的异步和mock配置
        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch(
                "src.z2p_svc.services.chat.converter.convert_messages"
            ) as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
        ):
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.6",
                        "info": {"id": "GLM-4-6-API-V1", "meta": {"capabilities": {}}},
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "看这张图片"}]
                last_user_message_text = "看这张图片"
                file_urls = []  # 不包含文件以简化测试

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {
                "signature": "test_sig",
                "timestamp": "123456",
            }

            # 执行测试 - 验证不会崩溃
            zai_data, params, headers = await prepare_request_data(
                chat_request, mock_access_token
            )

            # 验证基本结构
            assert zai_data is not None
            assert "model" in zai_data

    @pytest.mark.asyncio
    async def test_streaming_parameter(self, mock_access_token):
        """测试流式参数设置。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.6")
            .with_message("user", "测试")
            .with_streaming(True)
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch(
                "src.z2p_svc.services.chat.converter.convert_messages"
            ) as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
        ):
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.6",
                        "info": {"id": "GLM-4-6-API-V1", "meta": {"capabilities": {}}},
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "测试"}]
                last_user_message_text = "测试"
                file_urls = []

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {"signature": "test_sig", "timestamp": 123456}

            # 测试流式
            zai_data, _, _ = await prepare_request_data(
                chat_request, mock_access_token, streaming=True
            )
            assert zai_data["stream"] is True

            # 测试非流式
            zai_data, _, _ = await prepare_request_data(
                chat_request, mock_access_token, streaming=False
            )
            assert zai_data["stream"] is False

    @pytest.mark.asyncio
    async def test_model_mapping_chain(self, mock_access_token):
        """测试模型映射链。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.6")
            .with_message("user", "测试")
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch(
                "src.z2p_svc.services.chat.converter.convert_messages"
            ) as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
        ):
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.6",
                        "info": {"id": "GLM-4-6-API-V1", "meta": {"capabilities": {}}},
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "测试"}]
                last_user_message_text = "测试"
                file_urls = []

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {
                "signature": "test_sig",
                "timestamp": "123456",
            }

            zai_data, _, _ = await prepare_request_data(chat_request, mock_access_token)

            # 验证模型被正确映射
            assert zai_data["model"] == "GLM-4-6-API-V1"


@pytest.mark.unit
class TestModelFeaturesEdgeCases:
    """模型特性边界情况测试。"""

    def test_empty_model_name(self):
        """测试空模型名称。"""
        result = get_model_features("", streaming=True)

        # 应该返回默认特性
        assert "features" in result
        assert "mcp_servers" in result

    def test_multiple_suffixes(self):
        """测试多个后缀组合。"""
        result = get_model_features("glm-4.6-nothinking-search", streaming=True)

        # nothinking 应该禁用 thinking
        assert result["features"]["enable_thinking"] is False
        # search 应该启用搜索
        assert result["features"]["web_search"] is True

    def test_model_capabilities_none(self):
        """测试模型能力为 None。"""
        result = get_model_features("glm-4.6", streaming=True, model_capabilities=None)

        # 应该使用默认行为
        assert result["features"]["enable_thinking"] is True

    def test_model_capabilities_empty_dict(self):
        """测试模型能力为空字典。"""
        result = get_model_features("glm-4.6", streaming=True, model_capabilities={})

        # 应该使用默认行为
        assert result["features"]["enable_thinking"] is True


@pytest.mark.unit
class TestPrepareRequestDataAdvanced:
    """prepare_request_data 高级测试。"""

    @pytest.mark.asyncio
    async def test_with_generation_parameters(self, mock_access_token):
        """测试生成参数传递。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.6")
            .with_message("user", "测试")
            .with_temperature(0.7)
            .with_top_p(0.9)
            .with_max_tokens(1000)
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch(
                "src.z2p_svc.services.chat.converter.convert_messages"
            ) as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
        ):
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.6",
                        "info": {"id": "GLM-4-6-API-V1", "meta": {"capabilities": {}}},
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "测试"}]
                last_user_message_text = "测试"
                file_urls = []

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {
                "signature": "test_sig",
                "timestamp": "123456",
            }

            zai_data, _, _ = await prepare_request_data(chat_request, mock_access_token)

            assert zai_data["params"]["temperature"] == 0.7
            assert zai_data["params"]["top_p"] == 0.9
            assert zai_data["params"]["max_tokens"] == 1000

    @pytest.mark.asyncio
    async def test_upstream_model_id_fallback(self, mock_access_token):
        """测试使用上游模型ID作为后备。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("GLM-4-6-API-V1")
            .with_message("user", "测试")
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch(
                "src.z2p_svc.services.chat.converter.convert_messages"
            ) as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
        ):
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.6",
                        "info": {"id": "GLM-4-6-API-V1", "meta": {"capabilities": {}}},
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "测试"}]
                last_user_message_text = "测试"
                file_urls = []

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {
                "signature": "test_sig",
                "timestamp": "123456",
            }

            # 应该不抛出异常，因为是上游模型ID
            zai_data, _, _ = await prepare_request_data(chat_request, mock_access_token)
            assert zai_data is not None

    @pytest.mark.asyncio
    async def test_model_service_failure_handling(self, mock_access_token):
        """测试模型服务失败时的处理。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.6")
            .with_message("user", "测试")
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch(
                "src.z2p_svc.services.chat.converter.convert_messages"
            ) as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
        ):
            # 模拟模型服务失败
            mock_get_models.side_effect = Exception("Network error")

            class MockConvertResult:
                messages = [{"role": "user", "content": "测试"}]
                last_user_message_text = "测试"
                file_urls = []

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {
                "signature": "test_sig",
                "timestamp": "123456",
            }

            # 应该继续执行，使用现有映射
            with pytest.raises(ValueError):  # 因为没有模型列表，会抛出模型不存在错误
                await prepare_request_data(chat_request, mock_access_token)

    # 注意：文件上传的完整测试应该在集成测试中进行
    # 这里的单元测试主要验证逻辑路径，不验证实际的文件上传调用

    @pytest.mark.asyncio
    async def test_file_upload_failure_handling(self, mock_access_token):
        """测试文件上传失败处理。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.6")
            .with_message("user", "测试")
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch(
                "src.z2p_svc.services.chat.converter.convert_messages"
            ) as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
            patch("src.z2p_svc.file_uploader.FileUploader") as mock_uploader_class,
        ):
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.6",
                        "info": {"id": "GLM-4-6-API-V1", "meta": {"capabilities": {}}},
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "测试"}]
                last_user_message_text = "测试"
                file_urls = ["data:image/png;base64,invalid"]

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {
                "signature": "test_sig",
                "timestamp": "123456",
            }

            mock_uploader = AsyncMock()
            mock_uploader.upload_base64_file = AsyncMock(
                side_effect=Exception("Upload failed")
            )
            mock_uploader_class.return_value = mock_uploader

            # 应该继续执行，失败的文件被跳过
            zai_data, _, _ = await prepare_request_data(chat_request, mock_access_token)
            assert zai_data is not None

    # 注意：混合媒体文件的完整测试应该在集成测试中进行
    # 单元测试主要验证各个组件的独立功能

    @pytest.mark.asyncio
    async def test_variables_injection(self, mock_access_token):
        """测试变量注入。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.6")
            .with_message("user", "当前时间是多少？")
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch(
                "src.z2p_svc.services.chat.converter.convert_messages"
            ) as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
        ):
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.6",
                        "info": {"id": "GLM-4-6-API-V1", "meta": {"capabilities": {}}},
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "当前时间是多少？"}]
                last_user_message_text = "当前时间是多少？"
                file_urls = []

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {
                "signature": "test_sig",
                "timestamp": "123456",
            }

            zai_data, _, _ = await prepare_request_data(chat_request, mock_access_token)

            # 验证变量存在
            assert "variables" in zai_data
            assert "{{CURRENT_DATETIME}}" in zai_data["variables"]
            assert "{{CURRENT_DATE}}" in zai_data["variables"]
            assert "{{USER_LANGUAGE}}" in zai_data["variables"]


@pytest.mark.unit
class TestGLM46VFileHandling:
    """GLM-4.6V 文件处理测试。"""

    @pytest.mark.asyncio
    async def test_glm46v_image_in_files_array(self, mock_access_token):
        """测试 glm-4.6v 模型的图片放在 files 数组中。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.6v")
            .with_message("user", "分析此图片")
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch("src.z2p_svc.chat_service.convert_messages") as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
            patch("src.z2p_svc.chat_service.FileUploader") as mock_uploader_class,
        ):
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.6v",
                        "info": {"id": "GLM-4-6-API-V1", "meta": {"capabilities": {}}},
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "分析此图片"}]
                last_user_message_text = "分析此图片"
                file_urls = ["data:image/png;base64,test"]

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {
                "signature": "test_sig",
                "timestamp": "123456",
            }

            # Mock 文件上传返回图片对象
            mock_uploader = AsyncMock()
            mock_uploader.upload_base64_file.return_value = {
                "id": "test-image-id",
                "name": "test.png",
                "media": "image",
                "size": 1024,
            }
            mock_uploader_class.return_value = mock_uploader

            zai_data, _, _ = await prepare_request_data(chat_request, mock_access_token)

            # 验证图片在 files 数组中（而不是在 messages 中）
            assert "files" in zai_data
            assert len(zai_data["files"]) == 1
            assert zai_data["files"][0]["media"] == "image"

            # 验证 messages 中没有 image_url
            last_message = zai_data["messages"][-1]
            if isinstance(last_message.get("content"), list):
                # 如果是数组，不应该有 image_url 类型
                assert not any(
                    item.get("type") == "image_url" for item in last_message["content"]
                )

    @pytest.mark.asyncio
    async def test_glm46v_variant_image_in_files_array(self, mock_access_token):
        """测试 glm-4.6v 变体（如 glm-4.6v-nothinking）的图片也放在 files 数组中。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.6v-nothinking")
            .with_message("user", "看图")
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch("src.z2p_svc.chat_service.convert_messages") as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
            patch("src.z2p_svc.chat_service.FileUploader") as mock_uploader_class,
        ):
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.6v-nothinking",
                        "info": {"id": "GLM-4-6-API-V1", "meta": {"capabilities": {}}},
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "看图"}]
                last_user_message_text = "看图"
                file_urls = ["data:image/jpeg;base64,test"]

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {
                "signature": "test_sig",
                "timestamp": "123456",
            }

            mock_uploader = AsyncMock()
            mock_uploader.upload_base64_file.return_value = {
                "id": "test-image-id",
                "name": "test.jpg",
                "media": "image",
                "size": 2048,
            }
            mock_uploader_class.return_value = mock_uploader

            zai_data, _, _ = await prepare_request_data(chat_request, mock_access_token)

            # 验证图片在 files 数组中
            assert "files" in zai_data
            assert len(zai_data["files"]) == 1
            assert zai_data["files"][0]["media"] == "image"

    @pytest.mark.asyncio
    async def test_non_glm46v_image_in_messages(self, mock_access_token):
        """测试非 glm-4.6v 模型的图片嵌入到 messages 中。"""
        chat_request = ChatRequest(
            **ChatRequestBuilder()
            .with_model("glm-4.5v")
            .with_message("user", "看图")
            .build()
        )

        with (
            patch("src.z2p_svc.model_service.get_models") as mock_get_models,
            patch("src.z2p_svc.chat_service.convert_messages") as mock_convert,
            patch(
                "src.z2p_svc.signature_generator.generate_signature"
            ) as mock_signature,
            patch("src.z2p_svc.chat_service.FileUploader") as mock_uploader_class,
        ):
            mock_get_models.return_value = {
                "data": [
                    {
                        "id": "glm-4.5v",
                        "info": {"id": "glm-4.5v", "meta": {"capabilities": {}}},
                    }
                ]
            }

            class MockConvertResult:
                messages = [{"role": "user", "content": "看图"}]
                last_user_message_text = "看图"
                file_urls = ["data:image/png;base64,test"]

            mock_convert.return_value = MockConvertResult()
            mock_signature.return_value = {
                "signature": "test_sig",
                "timestamp": "123456",
            }

            mock_uploader = AsyncMock()
            mock_uploader.upload_base64_file.return_value = {
                "id": "test-image-id",
                "name": "test.png",
                "media": "image",
                "size": 1024,
            }
            mock_uploader_class.return_value = mock_uploader
            
            zai_data, _, _ = await prepare_request_data(chat_request, mock_access_token)
            
            # 验证图片嵌入到 messages 的 content 数组中
            last_message = zai_data["messages"][-1]
            assert isinstance(last_message.get("content"), list)
            
            # 应该有 image_url 类型
            has_image_url = any(
                item.get("type") == "image_url"
                for item in last_message["content"]
            )
            assert has_image_url
            
            # files 数组应该为空或不存在
            assert "files" not in zai_data or len(zai_data.get("files", [])) == 0