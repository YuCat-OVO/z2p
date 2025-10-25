"""Z.AI前端版本自动获取模块。

从 https://chat.z.ai 页面自动提取最新的 X-FE-Version 值。
该模块会缓存版本号并在后台定时更新。
"""

import asyncio
import re
import time
from typing import Optional

from curl_cffi.requests import AsyncSession

from .config import get_settings
from .logger import logger

_version_pattern = re.compile(r"prod-fe-\d+\.\d+\.\d+")
_cached_version: str = ""
_cached_at: float = 0.0
_update_task: Optional[asyncio.Task] = None


def _extract_version(page_content: str) -> Optional[str]:
    """从页面内容中提取版本号。"""
    if not page_content:
        return None
    matches = _version_pattern.findall(page_content)
    return max(matches) if matches else None


async def _fetch_version_from_remote(browser_version: str) -> Optional[str]:
    """从远程获取版本号。"""
    settings = get_settings()
    try:
        logger.debug("正在从远程获取FE版本号: {}", settings.fe_version_source_url)
        async with AsyncSession(impersonate=browser_version) as session:  # type: ignore
            response = await session.get(
                settings.fe_version_source_url,
                timeout=float(settings.timeout_auth),
                allow_redirects=True,
            )
            
            if response.status_code == 200:
                version = _extract_version(response.text)
                if version:
                    logger.info("成功获取FE版本号: {}", version)
                    return version
                logger.error("无法在页面中找到FE版本号")
            else:
                logger.error("获取FE版本号失败: status_code={}", response.status_code)
    except Exception as exc:
        logger.error("获取FE版本号异常: {}", str(exc))
    return None


async def update_fe_version(browser_version: str) -> Optional[str]:
    """更新FE版本号。"""
    global _cached_version, _cached_at
    
    version = await _fetch_version_from_remote(browser_version)
    if version:
        if version != _cached_version:
            logger.info("检测到FE版本更新: {} -> {}", _cached_version or "无", version)
        _cached_version = version
        _cached_at = time.time()
        return version
    return None


async def _background_update_task(browser_version_func) -> None:
    """后台定时更新任务。"""
    settings = get_settings()
    while True:
        try:
            await asyncio.sleep(settings.fe_version_update_interval)
            browser_version = browser_version_func()
            await update_fe_version(browser_version)
        except asyncio.CancelledError:
            logger.info("FE版本后台更新任务已取消")
            break
        except Exception as e:
            logger.error("FE版本后台更新失败: {}", str(e))


def start_background_update(browser_version_func) -> None:
    """启动后台更新任务。"""
    global _update_task
    if _update_task is None or _update_task.done():
        _update_task = asyncio.create_task(_background_update_task(browser_version_func))


def stop_background_update() -> None:
    """停止后台更新任务。"""
    global _update_task
    if _update_task and not _update_task.done():
        _update_task.cancel()
        logger.info("FE版本后台更新任务已停止")


def get_cached_version() -> str:
    """获取缓存的版本号。"""
    return _cached_version


async def initialize_fe_version(browser_version: str, fallback: str) -> str:
    """初始化FE版本号。"""
    global _cached_version, _cached_at
    
    version = await _fetch_version_from_remote(browser_version)
    if version:
        _cached_version = version
        _cached_at = time.time()
        return version
    
    logger.warning("无法获取FE版本号，使用降级值: {}", fallback)
    _cached_version = fallback
    _cached_at = time.time()
    return fallback