"""用户认证服务模块。

本模块负责处理用户认证和Token验证，每次请求都会调用认证接口获取最新的user_id。
"""

import httpx
from typing import TypedDict

from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class UserInfo(TypedDict):
    """用户信息类型。
    
    :ivar user_id: 用户ID
    :ivar token: 访问令牌
    :ivar name: 用户名（可选）
    :ivar cookies: 从上游获取的cookies字典
    """
    user_id: str
    token: str
    name: str | None
    cookies: dict[str, str]


async def fetch_acw_tc_cookie(access_token: str) -> dict[str, str]:
    """访问聊天页面以获取 acw_tc cookie。
    
    :param access_token: 访问令牌
    :return: 包含 acw_tc cookie 的字典
    
    Example::
    
        >>> cookies = await fetch_acw_tc_cookie("token")
        >>> print(cookies.get("acw_tc"))
    """
    chat_page_url = f"{settings.proxy_url}"
    
    headers = {
        **settings.HEADERS,
        "Authorization": f"Bearer {access_token}",
    }
    
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                chat_page_url,
                headers=headers,
                timeout=10.0,
            )
            
            # 从响应中提取 cookies
            cookies = dict(response.cookies)
            
            has_acw_tc = "acw_tc" in cookies
            cookie_keys = list(cookies.keys())
            
            logger.debug(
                "Acw_tc cookie fetched: url={}, status_code={}, cookies={}, has_acw_tc={}",
                chat_page_url,
                response.status_code,
                cookie_keys,
                has_acw_tc,
            )
            
            return cookies
            
    except httpx.RequestError as e:
        logger.error(
            "Acw_tc cookie request error: error_type={}, error={}",
            type(e).__name__,
            str(e),
        )
        return {}
    except Exception as e:
        logger.error(
            "Acw_tc cookie unexpected error: error_type={}, error={}",
            type(e).__name__,
            str(e),
        )
        return {}


async def authenticate_with_cookies(access_token: str, chat_id: str | None = None) -> tuple[str, str, str | None, dict[str, str]]:
    """获取 acw_tc cookie 并使用它进行认证。
    
    首先获取 acw_tc cookie，然后使用该 cookie 调用认证接口获取 Bearer token。
    
    :param access_token: 客户端提供的访问令牌
    :param chat_id: 可选的聊天会话ID，用于构建Referer头
    :return: 包含 user_id、auth_token、user_name 和 cookies 的元组
    
    Example::
    
        >>> user_id, auth_token, user_name, cookies = await authenticate_with_cookies("your_token")
        >>> print(cookies.get("acw_tc"))
        >>> print(auth_token)
    """
    # 首先获取 acw_tc cookie
    cookies = await fetch_acw_tc_cookie(access_token)
    
    # 构建请求头，优先使用config中的值，补充缺失的头信息
    headers = {
        **settings.HEADERS,
        "Authorization": f"Bearer {access_token}",
        "Host": settings.base_url,
    }
    
    # 如果提供了 chat_id，则在 Referer 中使用它
    if chat_id:
        headers["Referer"] = f"{settings.proxy_url}/c/{chat_id}"
    
    # 将 acw_tc cookie 附加到 Cookie 头中
    if cookies and "acw_tc" in cookies:
        cookie_str = "; ".join([f"{key}={value}" for key, value in cookies.items()])
        headers["Cookie"] = cookie_str
        logger.debug("Acw_tc cookie attached to auth request: has_acw_tc={}", "acw_tc" in cookies)
    
    auth_url = f"{settings.proxy_url}/api/v1/auths/"
    
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                auth_url,
                headers=headers,
                timeout=10.0,
            )
            
            if response.status_code == 200:
                data = response.json()
                user_id = data.get("id")
                user_name = data.get("name")
                auth_token = data.get("token")
                
                if not user_id:
                    logger.error("Auth response missing user_id: response_data={}", data)
                    raise Exception("认证响应中缺少 user_id")
                
                # 从响应中提取额外的 cookies
                response_cookies = dict(response.cookies)
                # 合并 cookies，保留原有的 acw_tc
                cookies.update(response_cookies)
                
                token_preview = f"{auth_token}..." if auth_token and len(auth_token) > 12 else "***"
                # 记录 cookies 信息(特别关注 acw_tc)
                cookie_keys = list(cookies.keys())
                has_acw_tc = "acw_tc" in cookies
                logger.debug(
                    "Authentication successful: user_id={}, user_name={}, token={}, cookies={}, has_acw_tc={}",
                    user_id,
                    user_name,
                    token_preview,
                    cookie_keys,
                    has_acw_tc,
                )
                
                return user_id, auth_token, user_name, cookies
            else:
                error_text = response.text
                logger.error(
                    "Auth request failed: status_code={}, response_text={}",
                    response.status_code,
                    error_text[:200],
                )
                raise Exception(f"认证失败 (HTTP {response.status_code}): {error_text[:100]}")
                
    except httpx.RequestError as e:
        logger.error(
            "Auth request error: error_type={}, error={}",
            type(e).__name__,
            str(e),
        )
        raise Exception(f"认证请求错误: {str(e)}")
    except Exception as e:
        logger.error(
            "Auth unexpected error: error_type={}, error={}",
            type(e).__name__,
            str(e),
        )
        raise


async def get_user_info(access_token: str, chat_id: str | None = None) -> UserInfo:
    """获取用户信息。
    
    使用新的认证流程：首先获取 acw_tc cookie，然后使用该 cookie 调用认证接口获取 Bearer token。
    确保数据始终是最新的，避免缓存失效问题。
    
    :param access_token: 客户端提供的访问令牌
    :param chat_id: 可选的聊天会话ID，用于构建Referer头
    :return: 包含 user_id、token、name 和 cookies 的用户信息字典
    :raises Exception: 当认证接口返回错误时
    
    Example::
    
        >>> user_info = await get_user_info("your_token_here", "chat-id")
        >>> print(user_info["user_id"])
        >>> print(user_info["cookies"])
    
    .. note::
       此函数不使用缓存，每次都会请求认证接口，确保数据一致性。
       使用新的认证流程确保 acw_tc cookie 和 Bearer token 的一致性。
    """
    # 使用新的认证流程获取 user_id、token、name 和 cookies
    user_id, auth_token, user_name, cookies = await authenticate_with_cookies(access_token, chat_id)
    
    # 构建用户信息
    user_info: UserInfo = {
        "user_id": user_id,
        "token": auth_token,
        "name": user_name,
        "cookies": cookies,
    }
    
    token_preview = f"{auth_token}..." if auth_token and len(auth_token) > 12 else "***"
    # 记录 cookies 信息(特别关注 acw_tc)
    cookie_keys = list(cookies.keys())
    has_acw_tc = "acw_tc" in cookies
    logger.debug(
        "User info fetched: user_id={}, user_name={}, token={}, cookies={}, has_acw_tc={}",
        user_id,
        user_name,
        token_preview,
        cookie_keys,
        has_acw_tc,
    )
    
    return user_info