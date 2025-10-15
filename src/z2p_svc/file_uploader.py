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
import uuid

import httpx

from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)


class FileUploader:
    """文件上传工具类。

    支持从base64数据或URL上传各种文件类型到上游服务。

    :ivar access_token: API访问令牌
    :ivar upload_url: 文件上传端点URL
    :ivar chat_id: 聊天会话ID，用于构建Referer头
    :ivar cookies: 从上游获取的cookies字典
    """
    
    MIME_TYPES = {
        # 图片格式
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'bmp': 'image/bmp',
        'webp': 'image/webp',
        # 文档格式
        'pdf': 'application/pdf',
        'doc': 'application/msword',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'txt': 'text/plain',
        'md': 'text/markdown',
        # 表格格式
        'xls': 'application/vnd.ms-excel',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'csv': 'text/csv',
        # 演示文稿格式
        'ppt': 'application/vnd.ms-powerpoint',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        # 代码格式
        'py': 'text/x-python',
    }

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
        
        headers["Referer"] = f"{self.settings.protocol}//{self.settings.base_url}/c/{self.chat_id}"
        headers["Authorization"] = f"Bearer {self.access_token}"
        
        return headers

    def _get_mime_type(self, filename: str) -> str:
        """根据文件扩展名获取MIME类型。
        
        :param filename: 文件名
        :return: MIME类型字符串
        """
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        return self.MIME_TYPES.get(ext, 'application/octet-stream')
    
    async def upload_base64_file(
        self, base64_data: str, filename: str | None = None, file_type: str | None = None
    ) -> str | None:
        """上传base64编码的文件。

        :param base64_data: base64编码的文件数据（不包含data:...;base64,前缀）
        :param filename: 可选的文件名，如果不提供将自动生成
        :param file_type: 可选的文件类型（扩展名），用于确定MIME类型
        :return: 上传成功返回文件ID（格式：id_filename），失败返回None

        Example::

            >>> uploader = FileUploader("token")
            >>> file_id = await uploader.upload_base64_file("iVBORw0KGgo...", "document.pdf")
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
                file_filename = result.get("filename")
                cdn_url = result.get("meta", {}).get("cdn_url")

                if file_id and file_filename:
                    full_id = f"{file_id}_{file_filename}"
                    logger.info(
                        "File uploaded: filename={}, file_id={}, size={}, cdn_url={}",
                        filename,
                        full_id,
                        len(file_data),
                        cdn_url,
                    )
                    return full_id
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
    
    async def upload_file_from_url(self, file_url: str) -> str | None:
        """从URL下载文件并上传。

        :param file_url: 文件URL
        :return: 上传成功返回文件ID（格式：id_filename），失败返回None

        Example::

            >>> uploader = FileUploader("token")
            >>> file_id = await uploader.upload_file_from_url("https://example.com/document.pdf")
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

                return await self.upload_base64_file(base64_data, filename)

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