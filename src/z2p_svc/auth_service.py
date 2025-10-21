"""用户认证服务模块。

本模块负责处理用户认证和Token验证，每次请求都会调用认证接口获取最新的user_id。

⚠️ 注意：此模块中的认证机制已被暂时屏蔽，当前服务直接使用客户端提供的 access_token 进行请求。
以下功能暂时不需要：
- fetch_acw_tc_cookie: 获取 acw_tc cookie
- authenticate_with_cookies: 使用 cookie 进行认证
- get_user_info: 获取用户信息和认证 token

如需恢复认证机制，请在 chat_service.py 中的 prepare_request_data 函数中重新启用对 get_user_info 的调用。
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
    :type access_token: str
    :return: 包含 acw_tc cookie 的字典
    :rtype: dict[str, str]
    
    .. note::
       acw_tc cookie 用于阿里云 WAF 验证
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
    """通过 cookie 链式认证获取用户信息。
    
    采用两步认证流程：
    
    1. 获取 acw_tc cookie
    2. 使用该 cookie 调用认证接口获取 Bearer token
    
    :param access_token: 客户端提供的访问令牌
    :param chat_id: 聊天会话 ID（可选），用于构建 Referer 头
    :type access_token: str
    :type chat_id: str | None
    :return: (user_id, auth_token, user_name, cookies) 四元组
    :rtype: tuple[str, str, str | None, dict[str, str]]
    :raises Exception: 当认证失败时
    
    .. note::
       如果提供了 chat_id，会添加 Referer 头以模拟真实浏览器行为
    """
    cookies = await fetch_acw_tc_cookie(access_token)
    
    # 构建认证请求头，包含访问令牌和Host信息
    headers = {
        **settings.HEADERS,
        "Authorization": f"Bearer {access_token}",
        "Host": settings.base_url,
    }
    
    # 如果提供了chat_id，添加Referer头以模拟真实浏览器行为
    if chat_id:
        headers["Referer"] = f"{settings.proxy_url}/c/{chat_id}"
    
    # 将获取的cookie附加到请求头中
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
                
                response_cookies = dict(response.cookies)
                cookies.update(response_cookies)
                
                cookie_keys = list(cookies.keys())
                has_acw_tc = "acw_tc" in cookies
                logger.debug(
                    "Authentication successful: user_id={}, user_name={}, token={}, cookies={}, has_acw_tc={}",
                    user_id,
                    user_name,
                    auth_token,
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
    
    采用无缓存的实时认证策略，每次调用都重新获取 cookie 和 token，确保数据一致性。
    
    :param access_token: 客户端提供的访问令牌
    :param chat_id: 聊天会话 ID（可选），用于构建 Referer 头
    :type access_token: str
    :type chat_id: str | None
    :return: 包含 user_id、token、name 和 cookies 的用户信息字典
    :rtype: UserInfo
    :raises Exception: 当认证接口返回错误时
    
    .. note::
       此函数不使用缓存，每次都会请求认证接口，确保数据一致性。
       采用 cookie 链式认证流程确保 acw_tc cookie 和 Bearer token 的一致性。
    
    .. warning::
       当前服务已暂时屏蔽此认证机制，直接使用客户端提供的 access_token
    """
    user_id, auth_token, user_name, cookies = await authenticate_with_cookies(access_token, chat_id)
    
    user_info: UserInfo = {
        "user_id": user_id,
        "token": auth_token,
        "name": user_name,
        "cookies": cookies,
    }
    
    cookie_keys = list(cookies.keys())
    has_acw_tc = "acw_tc" in cookies
    logger.debug(
        "User info fetched: user_id={}, user_name={}, token={}, cookies={}, has_acw_tc={}",
        user_id,
        user_name,
        auth_token,
        cookie_keys,
        has_acw_tc,
    )
    
    return user_info