"""Mihomo代理管理模块。"""

import httpx
from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def switch_proxy_node() -> bool:
    """切换到下一个代理节点。
    
    :return: 切换成功返回True，否则返回False
    """
    if not settings.enable_mihomo_switch or not settings.mihomo_api_url:
        return False
    
    try:
        headers = {}
        if settings.mihomo_api_secret:
            headers["Authorization"] = f"Bearer {settings.mihomo_api_secret}"
        
        async with httpx.AsyncClient() as client:
            # 获取当前代理组
            resp = await client.get(
                f"{settings.mihomo_api_url}/proxies",
                headers=headers,
                timeout=5
            )
            if resp.status_code != 200:
                logger.error("Failed to get proxies: status={}", resp.status_code)
                return False
            
            proxies = resp.json().get("proxies", {})
            
            # 使用配置的代理组名称
            proxy_group = settings.mihomo_proxy_group
            if proxy_group not in proxies:
                logger.warning("Proxy group '{}' not found", proxy_group)
                return False
            
            group_info = proxies[proxy_group]
            group_type = group_info.get("type")
            
            # 支持Selector和LoadBalance类型
            if group_type not in ("Selector", "LoadBalance"):
                logger.warning("Proxy group '{}' type '{}' not supported", proxy_group, group_type)
                return False
            
            # 获取当前选中的节点和所有可用节点
            current = group_info.get("now")
            all_nodes = group_info.get("all", [])
            
            if not all_nodes or len(all_nodes) < 2:
                logger.warning("Not enough nodes to switch")
                return False
            
            # 找到下一个节点
            try:
                current_idx = all_nodes.index(current)
                next_node = all_nodes[(current_idx + 1) % len(all_nodes)]
            except (ValueError, IndexError):
                next_node = all_nodes[0]
            
            # 切换节点
            switch_resp = await client.put(
                f"{settings.mihomo_api_url}/proxies/{proxy_group}",
                headers=headers,
                json={"name": next_node},
                timeout=5
            )
            
            if switch_resp.status_code == 204:
                logger.info("Proxy switched: {} -> {}", current, next_node)
                return True
            else:
                logger.error("Failed to switch proxy: status={}", switch_resp.status_code)
                return False
                
    except Exception as e:
        logger.error("Error switching proxy: {}", str(e))
        return False