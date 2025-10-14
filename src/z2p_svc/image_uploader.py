"""图片上传模块。

本模块支持从base64数据或URL上传图片到上游服务。

⚠️ 注意：当前直接使用客户端提供的 access_token，不再使用认证服务获取的 cookies。
"""

import base64
import io
import uuid

import httpx

from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)


class ImageUploader:
    """图片上传工具类。

    支持从base64数据或URL上传图片到上游服务。

    :ivar access_token: API访问令牌
    :ivar upload_url: 图片上传端点URL
    :ivar chat_id: 聊天会话ID，用于构建Referer头
    :ivar cookies: 从上游获取的cookies字典
    """

    def __init__(self, access_token: str, chat_id: str | None = None, cookies: dict[str, str] | None = None) -> None:
        """初始化图片上传器。

        :param access_token: 认证令牌
        :param chat_id: 可选的聊天会话ID，用于设置Referer头
        :param cookies: 可选的从上游获取的cookies字典(特别是acw_tc)
        """
        self.settings = get_settings()
        self.access_token = access_token
        self.chat_id = chat_id or str(uuid.uuid4())
        self.upload_url = f"{self.settings.proxy_url}/api/v1/files/"
        self.cookies = cookies or {}
        
        # DEBUG: 输出完整的 TOKEN（仅用于调试）
        if self.settings.verbose_logging:
            token_preview = f"{access_token}" if len(access_token) > 20 else "***"
            cookie_keys = list(self.cookies.keys())
            has_acw_tc = "acw_tc" in self.cookies
            logger.debug(
                "Image uploader initialized: token_length={}, token={}, chat_id={}, cookies={}, has_acw_tc={}",
                len(access_token),
                token_preview,
                self.chat_id,
                cookie_keys,
                has_acw_tc,
            )

    def _get_headers(self) -> dict[str, str]:
        """获取上传请求头。

        :return: 包含认证信息和cookies的请求头字典
        """
        # 使用配置中的基础请求头，并添加文件上传特定的头
        headers = {**self.settings.HEADERS}
        
        # 移除 Content-Type，让 httpx 自动设置 multipart/form-data
        headers.pop("Content-Type", None)
        headers.pop("X-FE-Version",None)
        
        # 添加文件上传特定的头
        headers["Referer"] = f"{self.settings.protocol}//{self.settings.base_url}/c/{self.chat_id}"
        headers["Authorization"] = f"Bearer {self.access_token}"
        
        # ⚠️ 暂时不使用 cookies，直接使用客户端提供的 token
        # if self.cookies:
        #     cookie_str = "; ".join([f"{key}={value}" for key, value in self.cookies.items()])
        #     headers["Cookie"] = cookie_str
        #     if self.settings.verbose_logging:
        #         logger.debug("Cookies attached to request: cookie_count={}, has_acw_tc={}", len(self.cookies), "acw_tc" in self.cookies)
        
        return headers

    async def upload_base64_image(
        self, base64_data: str, filename: str | None = None
    ) -> str | None:
        """上传base64编码的图片。

        :param base64_data: base64编码的图片数据（不包含data:image/...;base64,前缀）
        :param filename: 可选的文件名，如果不提供将自动生成
        :return: 上传成功返回图片ID（格式：id_filename），失败返回None

        Example::

            >>> uploader = ImageUploader("token")
            >>> pic_id = await uploader.upload_base64_image("iVBORw0KGgo...")
        """
        # 生成唯一文件名
        if not filename:
            filename = f"{uuid.uuid4()}.png"
        elif "." not in filename:
            filename = f"{filename}.png"

        try:
            image_data = base64.b64decode(base64_data)
        except Exception as e:
            logger.error("Base64 decode failed: filename={}, error={}", filename, str(e))
            return None

        # 根据文件扩展名确定MIME类型
        mime_type = "image/png"
        if filename.lower().endswith((".jpg", ".jpeg")):
            mime_type = "image/jpeg"
        elif filename.lower().endswith(".gif"):
            mime_type = "image/gif"
        elif filename.lower().endswith(".webp"):
            mime_type = "image/webp"

        file_obj = io.BytesIO(image_data)
        files = {"file": (filename, file_obj, mime_type)}

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
                pic_id = result.get("id")
                pic_filename = result.get("filename")
                cdn_url = result.get("meta", {}).get("cdn_url")

                if pic_id and pic_filename:
                    # 返回格式：id_filename
                    full_id = f"{pic_id}_{pic_filename}"
                    logger.info(
                        "Image uploaded: filename={}, pic_id={}, size={}, cdn_url={}",
                        filename,
                        full_id,
                        len(image_data),
                        cdn_url,
                    )
                    return full_id
                else:
                    logger.error("Upload response missing data: response={}", result)
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(
                "Upload HTTP error: status_code={}, response_text={}",
                e.response.status_code,
                e.response.text[:200],
            )
            return None
        except Exception as e:
            logger.error("Upload failed: filename={}, error={}", filename, str(e))
            return None

    async def upload_image_from_url(self, image_url: str) -> str | None:
        """从URL下载图片并上传。

        :param image_url: 图片URL
        :return: 上传成功返回图片ID（格式：id_filename），失败返回None

        Example::

            >>> uploader = ImageUploader("token")
            >>> pic_id = await uploader.upload_image_from_url("https://example.com/image.png")
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url, timeout=30.0)
                response.raise_for_status()

                filename = image_url.split("/")[-1]
                if not filename or "." not in filename:
                    filename = f"{uuid.uuid4()}.png"

                base64_data = base64.b64encode(response.content).decode("utf-8")

                logger.debug(
                    "Image downloaded: url={}, size={}, filename={}",
                    image_url,
                    len(response.content),
                    filename,
                )

                return await self.upload_base64_image(base64_data, filename)

        except httpx.HTTPStatusError as e:
            logger.error(
                "Download HTTP error: url={}, status_code={}",
                image_url,
                e.response.status_code,
            )
            return None
        except Exception as e:
            logger.error("Download failed: url={}, error={}", image_url, str(e))
            return None
