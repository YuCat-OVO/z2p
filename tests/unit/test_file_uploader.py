"""文件上传器单元测试。

测试 file_uploader 模块的核心功能，包括文件验证、Base64上传、URL上传等。
"""

import base64
import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.z2p_svc.file_uploader import FileUploader
from src.z2p_svc.exceptions import FileUploadError


@pytest.mark.unit
class TestFileUploaderInit:
    """FileUploader 初始化测试。"""

    def test_basic_initialization(self, mock_access_token):
        """测试基本初始化。"""
        uploader = FileUploader(mock_access_token)

        assert uploader.access_token == mock_access_token
        assert uploader.chat_id is not None
        assert uploader.upload_url.endswith("/api/v1/files/")

    def test_with_chat_id(self, mock_access_token):
        """测试带聊天ID初始化。"""
        chat_id = "test-chat-123"
        uploader = FileUploader(mock_access_token, chat_id=chat_id)

        assert uploader.chat_id == chat_id

    def test_with_cookies(self, mock_access_token):
        """测试带cookies初始化。"""
        cookies = {"acw_tc": "test_cookie"}
        uploader = FileUploader(mock_access_token, cookies=cookies)

        assert uploader.cookies == cookies


@pytest.mark.unit
class TestGetHeaders:
    """_get_headers 方法测试。"""

    def test_headers_structure(self, mock_access_token):
        """测试请求头结构。"""
        uploader = FileUploader(mock_access_token)
        headers = uploader._get_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == f"Bearer {mock_access_token}"
        assert "Referer" in headers
        assert "Content-Type" not in headers  # 应该被移除

    def test_authorization_format(self, mock_access_token):
        """测试授权格式。"""
        uploader = FileUploader(mock_access_token)
        headers = uploader._get_headers()

        assert headers["Authorization"].startswith("Bearer ")


@pytest.mark.unit
class TestGetMimeType:
    """_get_mime_type 方法测试。"""

    def test_image_types(self, mock_access_token):
        """测试图片类型。"""
        uploader = FileUploader(mock_access_token)

        assert uploader._get_mime_type("test.png") == "image/png"
        assert uploader._get_mime_type("test.jpg") == "image/jpeg"
        assert uploader._get_mime_type("test.jpeg") == "image/jpeg"
        assert uploader._get_mime_type("test.gif") == "image/gif"

    def test_document_types(self, mock_access_token):
        """测试文档类型。"""
        uploader = FileUploader(mock_access_token)

        assert uploader._get_mime_type("test.pdf") == "application/pdf"
        assert (
            uploader._get_mime_type("test.docx")
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert uploader._get_mime_type("test.txt") == "text/plain"

    def test_unknown_type(self, mock_access_token):
        """测试未知类型。"""
        uploader = FileUploader(mock_access_token)

        assert uploader._get_mime_type("test.unknown") == "application/octet-stream"

    def test_no_extension(self, mock_access_token):
        """测试无扩展名。"""
        uploader = FileUploader(mock_access_token)

        assert uploader._get_mime_type("testfile") == "application/octet-stream"


@pytest.mark.unit
class TestGetMediaType:
    """_get_media_type 方法测试。"""

    def test_image_media(self, mock_access_token):
        """测试图片媒体类型。"""
        uploader = FileUploader(mock_access_token)

        assert uploader._get_media_type("test.png") == "image"
        assert uploader._get_media_type("test.jpg") == "image"

    def test_video_media(self, mock_access_token):
        """测试视频媒体类型。"""
        uploader = FileUploader(mock_access_token)

        assert uploader._get_media_type("test.mp4") == "video"

    def test_document_media(self, mock_access_token):
        """测试文档媒体类型。"""
        uploader = FileUploader(mock_access_token)

        assert uploader._get_media_type("test.pdf") == "doc"
        assert uploader._get_media_type("test.docx") == "doc"

    def test_text_media(self, mock_access_token):
        """测试文本媒体类型。"""
        uploader = FileUploader(mock_access_token)

        assert uploader._get_media_type("test.txt") == "file"
        assert uploader._get_media_type("test.py") == "file"

    def test_unknown_media(self, mock_access_token):
        """测试未知媒体类型。"""
        uploader = FileUploader(mock_access_token)

        assert uploader._get_media_type("test.unknown") == "file"


@pytest.mark.unit
class TestValidateFile:
    """_validate_file 方法测试。"""

    def test_valid_file(self, mock_access_token):
        """测试有效文件。"""
        uploader = FileUploader(mock_access_token)
        file_data = b"test data"

        # 不应抛出异常
        uploader._validate_file(file_data, "image/png")

    def test_file_too_large(self, mock_access_token):
        """测试文件过大。"""
        uploader = FileUploader(mock_access_token)
        file_data = b"x" * (FileUploader.MAX_FILE_SIZE + 1)

        with pytest.raises(FileUploadError) as exc_info:
            uploader._validate_file(file_data, "image/png")

        assert "文件过大" in str(exc_info.value)

    def test_invalid_mime_type(self, mock_access_token):
        """测试无效MIME类型。"""
        uploader = FileUploader(mock_access_token)
        file_data = b"test data"

        with pytest.raises(FileUploadError) as exc_info:
            uploader._validate_file(file_data, "application/x-executable")

        assert "不支持的文件类型" in str(exc_info.value)


@pytest.mark.unit
class TestUploadBase64File:
    """upload_base64_file 方法测试。"""

    @pytest.mark.asyncio
    async def test_successful_upload(self, mock_access_token):
        """测试成功上传。"""
        uploader = FileUploader(mock_access_token)

        # 创建一个小的测试图片
        test_data = b"fake image data"
        base64_data = base64.b64encode(test_data).decode("utf-8")

        mock_response_data = {
            "id": "file123",
            "filename": "test.png",
            "meta": {"cdn_url": "https://cdn.example.com/file123"},
        }

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_base64_file(base64_data, "test.png")

            assert result is not None
            assert result["id"] == "file123"
            assert result["name"] == "test.png"
            assert result["media"] == "image"

    @pytest.mark.asyncio
    async def test_auto_filename_generation(self, mock_access_token):
        """测试自动文件名生成。"""
        uploader = FileUploader(mock_access_token)

        test_data = b"test"
        base64_data = base64.b64encode(test_data).decode("utf-8")

        mock_response_data = {"id": "file123", "filename": "generated.png", "meta": {}}

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_base64_file(base64_data)

            assert result is not None
            # 验证调用了post方法
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_base64(self, mock_access_token):
        """测试无效Base64数据。"""
        uploader = FileUploader(mock_access_token)

        result = await uploader.upload_base64_file("invalid base64!!!", "test.png")

        assert result is None

    @pytest.mark.asyncio
    async def test_file_too_large_validation(self, mock_access_token):
        """测试文件大小验证。"""
        uploader = FileUploader(mock_access_token)

        # 创建超大文件
        large_data = b"x" * (FileUploader.MAX_FILE_SIZE + 1)
        base64_data = base64.b64encode(large_data).decode("utf-8")

        result = await uploader.upload_base64_file(base64_data, "large.png")

        assert result is None

    @pytest.mark.asyncio
    async def test_http_error_handling(self, mock_access_token):
        """测试HTTP错误处理。"""
        uploader = FileUploader(mock_access_token)

        test_data = b"test"
        base64_data = base64.b64encode(test_data).decode("utf-8")

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Server Error"
            mock_response.raise_for_status = Mock(side_effect=Exception("HTTP 500"))
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_base64_file(base64_data, "test.png")

            assert result is None

    @pytest.mark.asyncio
    async def test_missing_file_id_in_response(self, mock_access_token):
        """测试响应中缺少文件ID。"""
        uploader = FileUploader(mock_access_token)

        test_data = b"test"
        base64_data = base64.b64encode(test_data).decode("utf-8")

        mock_response_data = {"filename": "test.png"}  # 缺少 id

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_base64_file(base64_data, "test.png")

            assert result is None

    @pytest.mark.asyncio
    async def test_file_id_with_underscore(self, mock_access_token):
        """测试带下划线的文件ID处理。"""
        uploader = FileUploader(mock_access_token)

        test_data = b"test"
        base64_data = base64.b64encode(test_data).decode("utf-8")

        mock_response_data = {
            "id": "file123_test.png",  # 包含下划线和文件名
            "filename": "test.png",
            "meta": {},
        }

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_base64_file(base64_data, "test.png")

            assert result is not None
            assert result["id"] == "file123"  # 应该只保留UUID部分


@pytest.mark.unit
class TestUploadFileFromUrl:
    """upload_file_from_url 方法测试。"""

    @pytest.mark.asyncio
    async def test_successful_url_upload(self, mock_access_token):
        """测试成功从URL上传。"""
        uploader = FileUploader(mock_access_token)

        test_url = "https://example.com/test.png"
        test_data = b"fake image data"

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()

            # Mock GET请求（下载文件）
            mock_get_response = Mock()
            mock_get_response.status_code = 200
            mock_get_response.content = test_data
            mock_get_response.headers = {"content-type": "image/png"}
            mock_get_response.raise_for_status = Mock()

            # Mock POST请求（上传文件）
            mock_post_response = Mock()
            mock_post_response.status_code = 200
            mock_post_response.json.return_value = {
                "id": "file456",
                "filename": "test.png",
                "meta": {},
            }
            mock_post_response.raise_for_status = Mock()

            async def mock_request(url, **kwargs):
                if url == test_url:
                    return mock_get_response
                else:
                    return mock_post_response

            mock_client.get = AsyncMock(return_value=mock_get_response)
            mock_client.post = AsyncMock(return_value=mock_post_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_file_from_url(test_url)

            assert result is not None
            assert result["id"] == "file456"

    @pytest.mark.asyncio
    async def test_url_download_failure(self, mock_access_token):
        """测试URL下载失败。"""
        uploader = FileUploader(mock_access_token)

        test_url = "https://example.com/notfound.png"

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_response.raise_for_status = Mock(side_effect=Exception("HTTP 404"))
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_file_from_url(test_url)

            assert result is None

    @pytest.mark.asyncio
    async def test_url_timeout(self, mock_access_token):
        """测试URL超时。"""
        uploader = FileUploader(mock_access_token)
        test_url = "https://example.com/slow.png"

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_file_from_url(test_url)

            assert result is None

    @pytest.mark.asyncio
    async def test_url_with_content_disposition(self, mock_access_token):
        """测试带Content-Disposition的URL。"""
        uploader = FileUploader(mock_access_token)

        test_url = "https://example.com/download"
        test_data = b"test"

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()

            mock_get_response = Mock()
            mock_get_response.status_code = 200
            mock_get_response.content = test_data
            mock_get_response.headers = {
                "content-type": "application/pdf",
                "content-disposition": 'attachment; filename="document.pdf"',
            }
            mock_get_response.raise_for_status = Mock()

            mock_post_response = Mock()
            mock_post_response.status_code = 200
            mock_post_response.json.return_value = {
                "id": "file789",
                "filename": "document.pdf",
                "meta": {},
            }
            mock_post_response.raise_for_status = Mock()

            mock_client.get = AsyncMock(return_value=mock_get_response)
            mock_client.post = AsyncMock(return_value=mock_post_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_file_from_url(test_url)

            assert result is not None

    @pytest.mark.asyncio
    async def test_url_file_too_large(self, mock_access_token):
        """测试从URL下载的文件过大。"""
        uploader = FileUploader(mock_access_token)

        test_url = "https://example.com/large.png"
        large_data = b"x" * (FileUploader.MAX_FILE_SIZE + 1)

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.content = large_data
            mock_response.headers = {"content-type": "image/png"}
            mock_response.raise_for_status = Mock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_file_from_url(test_url)

            assert result is None

    @pytest.mark.asyncio
    async def test_url_without_filename(self, mock_access_token):
        """测试URL不包含文件名。"""
        uploader = FileUploader(mock_access_token)

        test_url = "https://example.com/"
        test_data = b"test"

        with patch("src.z2p_svc.file_uploader.AsyncSession") as mock_client_class:
            mock_client = AsyncMock()

            mock_get_response = Mock()
            mock_get_response.status_code = 200
            mock_get_response.content = test_data
            mock_get_response.headers = {"content-type": "image/png"}
            mock_get_response.raise_for_status = Mock()

            mock_post_response = Mock()
            mock_post_response.status_code = 200
            mock_post_response.json.return_value = {
                "id": "file999",
                "filename": "generated.png",
                "meta": {},
            }
            mock_post_response.raise_for_status = Mock()

            mock_client.get = AsyncMock(return_value=mock_get_response)
            mock_client.post = AsyncMock(return_value=mock_post_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await uploader.upload_file_from_url(test_url)

            assert result is not None


@pytest.mark.unit
class TestFileUploaderConstants:
    """FileUploader 常量测试。"""

    def test_max_file_size(self):
        """测试最大文件大小常量。"""
        assert FileUploader.MAX_FILE_SIZE == 10 * 1024 * 1024

    def test_allowed_mime_types(self):
        """测试允许的MIME类型。"""
        assert "image/png" in FileUploader.ALLOWED_MIME_TYPES
        assert "application/pdf" in FileUploader.ALLOWED_MIME_TYPES
        assert "video/mp4" in FileUploader.ALLOWED_MIME_TYPES
    
    def test_mime_types_map(self):
        """测试MIME类型映射。"""
        assert FileUploader.MIME_TYPES_MAP["png"] == "image/png"
        assert FileUploader.MIME_TYPES_MAP["pdf"] == "application/pdf"
    
    def test_extension_categories(self):
        """测试扩展名分类。"""
        assert "png" in FileUploader.IMAGE_EXTENSIONS
        assert "mp4" in FileUploader.VIDEO_EXTENSIONS
        assert "pdf" in FileUploader.DOCUMENT_EXTENSIONS
        assert "txt" in FileUploader.TEXT_EXTENSIONS