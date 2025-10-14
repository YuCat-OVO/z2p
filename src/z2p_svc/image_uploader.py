"""图片上传模块。

本模块支持从base64数据或URL上传图片到上游服务。
"""

import base64
import io
import time

import httpx

from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)


class ImageUploader:
    """图片上传工具类。

    支持从base64数据或URL上传图片到上游服务。

    :ivar access_token: API访问令牌
    :ivar upload_url: 图片上传端点URL
    """

    def __init__(self, access_token: str) -> None:
        """初始化图片上传器。

        :param access_token: 认证令牌
        """
        self.settings = get_settings()
        self.access_token = access_token
        self.upload_url = f"{self.settings.proxy_url}/api/v1/files/"

    def _get_headers(self) -> dict[str, str]:
        """获取上传请求头。

        :return: 包含认证信息的请求头字典
        """
        return {
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Origin": "https://chat.z.ai",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "authorization": f"Bearer {self.access_token}",
        }

    async def upload_base64_image(
        self, base64_data: str, filename: str | None = None
    ) -> str | None:
        """上传base64编码的图片。

        :param base64_data: base64编码的图片数据（不包含data:image/...;base64,前缀）
        :param filename: 可选的文件名，如果不提供将自动生成
        :return: 上传成功返回图片ID，失败返回None

        Example::

            >>> uploader = ImageUploader("token")
            >>> pic_id = await uploader.upload_base64_image("iVBORw0KGgo...")
        """
        if not filename:
            filename = f"pasted_image_{int(time.time() * 1000)}.png"

        try:
            image_data = base64.b64decode(base64_data)
        except Exception as e:
            logger.error("base64_decode_failed", filename=filename, error=str(e))
            return None

        file_obj = io.BytesIO(image_data)
        files = {"file": (filename, file_obj, "image/png")}

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
                cdn_url = result.get("meta", {}).get("cdn_url")

                if pic_id and cdn_url:
                    logger.info(
                        "image_uploaded",
                        filename=filename,
                        pic_id=pic_id,
                        size=len(image_data),
                    )
                    return pic_id
                else:
                    logger.error("upload_response_missing_data", response=result)
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(
                "upload_http_error",
                status_code=e.response.status_code,
                response_text=e.response.text[:200],
            )
            return None
        except Exception as e:
            logger.error("upload_failed", filename=filename, error=str(e))
            return None

    async def upload_image_from_url(self, image_url: str) -> str | None:
        """从URL下载图片并上传。

        :param image_url: 图片URL
        :return: 上传成功返回图片ID，失败返回None

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
                    filename = f"downloaded_image_{int(time.time() * 1000)}.png"

                base64_data = base64.b64encode(response.content).decode("utf-8")

                logger.debug(
                    "image_downloaded",
                    url=image_url,
                    size=len(response.content),
                    filename=filename,
                )

                return await self.upload_base64_image(base64_data, filename)

        except httpx.HTTPStatusError as e:
            logger.error(
                "download_http_error",
                url=image_url,
                status_code=e.response.status_code,
            )
            return None
        except Exception as e:
            logger.error("download_failed", url=image_url, error=str(e))
            return None
