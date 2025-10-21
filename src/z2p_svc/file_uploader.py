"""文件上传模块。

本模块支持从base64数据或URL上传各种文件类型到上游服务，包括：
- 图片：png, jpg, jpeg, gif, bmp, webp
- 文档：pdf, docx, doc, txt, md
- 表格：xls, xlsx, csv
- 演示文稿：ppt, pptx
- 代码：py

⚠️ 注意：当前直接使用客户端提供的 access_token，不再使用认证服务获取的 cookies。
"""

import base64
import io
import re # 导入 re 模块
import uuid
from typing import Any

import httpx

from .config import get_settings
from .exceptions import FileUploadError
from .logger import get_logger
from .models import UploadedFileObject

logger = get_logger(__name__)


class FileUploader:
    """文件上传工具类。
    
    负责处理各种类型文件的上传到智谱 AI 平台。
    
    **支持的文件类型:**
    
    - 图片：PNG, JPG, JPEG, GIF, BMP, WebP
    - 视频：MP4
    - 文档：PDF, DOC, DOCX, TXT, MD
    - 表格：XLS, XLSX, CSV
    - 演示：PPT, PPTX
    - 代码：PY
    
    **支持的上传方式:**
    
    - Base64 编码文件
    - HTTP/HTTPS URL 文件
    
    :param access_token: 用户访问令牌
    :param chat_id: 聊天会话 ID（可选）
    :param cookies: 额外的 Cookie 字典（可选）
    :type access_token: str
    :type chat_id: str | None
    :type cookies: dict[str, str] | None
    
    .. attribute:: MAX_FILE_SIZE
       :type: int
       
       最大文件大小限制（字节），默认 10MB
    
    .. attribute:: ALLOWED_MIME_TYPES
       :type: set[str]
       
       允许的 MIME 类型白名单
    """

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_MIME_TYPES = {
        # 图片格式
        'image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'image/webp',
        # 视频格式
        'video/mp4',
        # 文档格式
        'application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain', 'text/markdown',
        # 表格格式
        'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'text/csv',
        # 演示文稿格式
        'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        # 代码格式
        'text/x-python',
    }
    
    MIME_TYPES_MAP = {
        # 图片格式
        'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'bmp': 'image/bmp', 'webp': 'image/webp',
        # 视频格式
        'mp4': 'video/mp4',
        # 文档格式
        'pdf': 'application/pdf', 'doc': 'application/msword', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'txt': 'text/plain', 'md': 'text/markdown',
        # 表格格式
        'xls': 'application/vnd.ms-excel', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'csv': 'text/csv',
        # 演示文稿格式
        'ppt': 'application/vnd.ms-powerpoint', 'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        # 代码格式
        'py': 'text/x-python',
    }
    
    # 文件类型分类（根据chat.z.ai前端逻辑）
    IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp']
    VIDEO_EXTENSIONS = ['mp4']
    DOCUMENT_EXTENSIONS = ['pdf', 'docx', 'doc', 'xls', 'xlsx', 'ppt', 'pptx']
    TEXT_EXTENSIONS = ['csv', 'py', 'txt', 'md']

    def __init__(self, access_token: str, chat_id: str | None = None, cookies: dict[str, str] | None = None) -> None:
        """初始化文件上传器。

        :param access_token: 认证令牌
        :param chat_id: 可选的聊天会话ID，用于设置Referer头
        :param cookies: 可选的从上游获取的cookies字典(特别是acw_tc)
        """
        self.settings = get_settings()
        self.access_token = access_token
        self.chat_id = chat_id or str(uuid.uuid4())
        self.upload_url = f"{self.settings.proxy_url}/api/v1/files/"
        self.cookies = cookies or {}
        
        if self.settings.verbose_logging:
            cookie_keys = list(self.cookies.keys())
            has_acw_tc = "acw_tc" in self.cookies
            logger.debug(
                "File uploader initialized: token_length={}, token={}, chat_id={}, cookies={}, has_acw_tc={}",
                len(access_token),
                access_token,
                self.chat_id,
                cookie_keys,
                has_acw_tc,
            )

    def _get_headers(self) -> dict[str, str]:
        """获取上传请求头。

        :return: 包含认证信息和cookies的请求头字典
        """
        headers = {**self.settings.HEADERS}
        
        # 移除不适用于文件上传的请求头
        headers.pop("Content-Type", None)
        headers.pop("X-FE-Version", None)
        
        headers["Referer"] = f"{self.settings.protocol}//{self.settings.base_url}/"
        headers["Authorization"] = f"Bearer {self.access_token}"
        
        return headers

    def _get_mime_type(self, filename: str) -> str:
        """根据文件扩展名获取MIME类型。
        
        :param filename: 文件名
        :return: MIME类型字符串
        """
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        return self.MIME_TYPES_MAP.get(ext, 'application/octet-stream')
    
    def _get_media_type(self, filename: str) -> str:
        """根据文件扩展名确定媒体类型（用于API负载构建）。
        
        :param filename: 文件名
        :return: 媒体类型：'image', 'video', 'doc', 或 'file'
        """
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        
        if ext in self.IMAGE_EXTENSIONS:
            return 'image'
        elif ext in self.VIDEO_EXTENSIONS:
            return 'video'
        elif ext in self.VIDEO_EXTENSIONS: # 修复：这里应该是VIDEO_EXTENSIONS
            return 'video'
        elif ext in self.DOCUMENT_EXTENSIONS:
            return 'doc'
        elif ext in self.TEXT_EXTENSIONS:
            return 'file'
        else:
            return 'file'

    def _validate_file(self, file_data: bytes, mime_type: str) -> None:
        """验证文件大小和MIME类型。
        
        :param file_data: 文件字节数据
        :param mime_type: 文件的MIME类型
        :raises FileUploadError: 如果文件不符合验证规则
        """
        if len(file_data) > self.MAX_FILE_SIZE:
            raise FileUploadError(f"文件过大，最大允许 {self.MAX_FILE_SIZE / (1024 * 1024):.1f}MB")
        if mime_type not in self.ALLOWED_MIME_TYPES:
            raise FileUploadError(f"不支持的文件类型: {mime_type}")
    
    async def upload_base64_file(
        self, base64_data: str, filename: str | None = None, file_type: str | None = None
    ) -> dict[str, Any] | None:
        """上传 Base64 编码的文件。
        
        :param base64_data: Base64 编码的文件数据（不含 ``data:`` 前缀）
        :param filename: 文件名（可选），未提供时自动生成
        :param file_type: 文件扩展名（如 ``"png"``、``"pdf"``），可选
        :type base64_data: str
        :type filename: str | None
        :type file_type: str | None
        :return: 上传成功返回文件对象，失败返回 None
        :rtype: dict[str, Any] | None
        :raises FileUploadError: 当文件验证失败或上传失败时
        
        **返回的文件对象结构:**
        
        .. code-block:: python
        
           {
               "id": "file_abc123",
               "name": "image.png",
               "media": "image",
               "url": "/api/v1/files/file_abc123",
               "size": 12345
           }
        
        .. note::
           如果未指定 ``file_type``，会尝试从文件名推断
        
        .. warning::
           文件大小不能超过 :attr:`MAX_FILE_SIZE` (10MB)
        """
        if not filename:
            ext = file_type if file_type else 'png'
            filename = f"{uuid.uuid4()}.{ext}"
        elif "." not in filename:
            ext = file_type if file_type else 'png'
            filename = f"{filename}.{ext}"

        try:
            file_data = base64.b64decode(base64_data)
            logger.info(
                "File decoded from base64: filename={}, size={} bytes, mime_type={}",
                filename,
                len(file_data),
                self._get_mime_type(filename),
            )
        except Exception as e:
            logger.error("Base64 decode failed: filename={}, error={}", filename, str(e))
            return None
 
        mime_type = self._get_mime_type(filename)
        
        try:
            self._validate_file(file_data, mime_type)
        except FileUploadError as e:
            logger.error("File validation failed: filename={}, error={}", filename, str(e))
            return None

        # 将文件数据包装为类文件对象以便上传
        file_obj = io.BytesIO(file_data)
        files = {"file": (filename, file_obj, mime_type)}
        
        logger.info(
            "Starting file upload: filename={}, size={} bytes, mime_type={}, upload_url={}",
            filename,
            len(file_data),
            mime_type,
            self.upload_url,
        )
        
        if self.settings.verbose_logging:
            logger.debug(
                "File upload request details: filename={}, upload_url={}, headers={}",
                filename,
                self.upload_url,
                {k: v if k.lower() != 'authorization' else v[:20] + '...' for k, v in self._get_headers().items()}, # 脱敏 Authorization
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.upload_url,
                    headers=self._get_headers(),
                    files=files,
                    timeout=30.0,
                )
                response.raise_for_status()

                result = response.json()
                file_id = result.get("id")
                file_filename = result.get("filename", filename)
                cdn_url = result.get("meta", {}).get("cdn_url")

                if file_id:
                    # 确保file_id是纯UUID（不包含文件名）
                    pure_file_id = file_id.split('_')[0] if '_' in file_id else file_id
                    
                    # 使用 Pydantic 模型构建文件对象
                    file_object = UploadedFileObject(
                        id=pure_file_id,
                        name=file_filename,
                        media=self._get_media_type(file_filename),
                        size=len(file_data),
                        url=f"/api/v1/files/{pure_file_id}",
                    )
                    
                    logger.info(
                        "File uploaded: filename={}, file_id={}, size={}, media={}, cdn_url={}",
                        file_filename,
                        pure_file_id,
                        len(file_data),
                        file_object.media,
                        cdn_url,
                    )
                    return file_object.model_dump()
                else:
                    logger.error("Upload response missing data: response={}", result)
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(
                "Upload HTTP error: filename={}, status_code={}, response_text={}, upload_url={}",
                filename,
                e.response.status_code,
                e.response.text[:200],
                self.upload_url,
            )
            return None
        except Exception as e:
            logger.error(
                "Upload failed: filename={}, error_type={}, error={}, upload_url={}",
                filename,
                type(e).__name__,
                str(e),
                self.upload_url,
            )
            return None
    
    async def upload_file_from_url(self, file_url: str) -> dict[str, Any] | None:
        """从URL下载文件并上传。

        :param file_url: 文件URL
        :return: 上传成功返回完整的文件对象（包含id、name、meta等），失败返回None

        Example::

            >>> uploader = FileUploader("token")
            >>> file_obj = await uploader.upload_file_from_url("https://example.com/document.pdf")
        """
        try:
            logger.info("Starting file download from URL: url={}", file_url)
            
            async with httpx.AsyncClient() as client:
                response = await client.get(file_url, timeout=30.0)
                response.raise_for_status()

                filename = file_url.split("/")[-1]
                if not filename or "." not in filename:
                    filename = f"{uuid.uuid4()}.png"

                base64_data = base64.b64encode(response.content).decode("utf-8")

                logger.info(
                    "File downloaded successfully: url={}, size={} bytes, filename={}, content_type={}",
                    file_url,
                    len(response.content),
                    filename,
                    response.headers.get("content-type", "unknown"),
                )

                # 尝试从响应头中获取文件名和MIME类型
                content_disposition = response.headers.get("content-disposition")
                if content_disposition:
                    fname_match = re.search(r'filename\*?=(?:UTF-8\'\')?\"?([^\";]+)\"?', content_disposition)
                    if fname_match:
                        filename = fname_match.group(1)
                
                mime_type = response.headers.get("content-type", self._get_mime_type(filename))
                
                # 在上传前进行验证
                try:
                    self._validate_file(response.content, mime_type)
                except FileUploadError as e:
                    logger.error("Downloaded file validation failed: url={}, error={}", file_url, str(e))
                    return None

                return await self.upload_base64_file(base64_data, filename, file_type=mime_type.split('/')[-1])

        except httpx.HTTPStatusError as e:
            logger.error(
                "Download HTTP error: url={}, status_code={}, response_text={}",
                file_url,
                e.response.status_code,
                e.response.text[:200] if hasattr(e.response, 'text') else 'N/A',
            )
            return None
        except httpx.TimeoutException as e:
            logger.error(
                "Download timeout: url={}, timeout=30s, error={}",
                file_url,
                str(e),
            )
            return None
        except Exception as e:
            logger.error(
                "Download failed: url={}, error_type={}, error={}",
                file_url,
                type(e).__name__,
                str(e),
            )
            return None