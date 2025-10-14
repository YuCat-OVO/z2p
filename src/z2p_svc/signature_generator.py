"""签名生成模块。

本模块实现了基于时间戳和HMAC-SHA256的双层签名算法，用于API请求的身份验证。
"""

import base64
import hashlib
import hmac
import time
from typing import TypedDict

from .logger import get_logger

logger = get_logger(__name__)


class SignatureResult(TypedDict):
    """签名生成结果。

    :ivar signature: 生成的HMAC-SHA256签名
    :ivar timestamp: 毫秒级时间戳
    """

    signature: str
    timestamp: str


def generate_signature(request_params: str, content: str) -> SignatureResult:
    """生成API请求签名。

    使用双层HMAC-SHA256算法生成签名：基于时间窗口生成中间密钥，
    然后使用中间密钥对请求参数和内容生成最终签名。

    :param request_params: 请求参数字符串，格式为"key1,value1,key2,value2,..."
    :param content: 请求内容，将被Base64编码后参与签名
    :return: 包含签名和时间戳的字典

    Example::

        >>> params = "requestId,xxx,timestamp,123,user_id,yyy"
        >>> result = generate_signature(params, "hello world")
        >>> print(result["signature"], result["timestamp"])

    .. note::
       签名算法使用5分钟时间窗口，同一时间窗口内生成的中间密钥相同。content参数会被Base64编码后再参与签名计算。
    """
    # 硬编码的主密钥，与JS脚本中保持一致
    SECRET_KEY = "junjie"
    # 签名有效的时间窗口（5分钟，单位：毫秒）
    TIME_WINDOW_MS = 5 * 60 * 1000

    # 获取当前时间的Unix毫秒时间戳
    timestamp_ms = int(time.time() * 1000)
    timestamp_str = str(timestamp_ms)

    # 计算一个随时间变化的窗口值，用于派生中间密钥
    time_window = timestamp_ms // TIME_WINDOW_MS

    # 使用主密钥和时间窗口生成一个短期的中间密钥
    intermediate_key = hmac.new(
        SECRET_KEY.encode("utf-8"),
        str(time_window).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # 构建由参数和时间戳组成的原始签名载荷
    # 关键：content需要进行Base64编码
    base64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = f"{request_params}|{base64_content}|{timestamp_str}"

    # 使用中间密钥对最终载荷进行签名
    final_signature = hmac.new(
        intermediate_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    logger.debug(
        "signature_generated",
        timestamp=timestamp_str,
        time_window=time_window,
        payload_length=len(payload),
    )

    return {"signature": final_signature, "timestamp": timestamp_str}
