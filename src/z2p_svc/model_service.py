"""模型服务模块。

本模块负责从上游API获取模型列表，并进行智能处理和格式化。
参考temp.py中的get_model_id和get_model_name函数实现。
"""

import httpx
from typing import Any
from datetime import datetime

from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_models_cache: dict[str, Any] | None = None


def format_model_name(name: str) -> str:
    """格式化模型名称。
    
    将模型名称转换为标准格式，例如：
    - glm-4.6 -> GLM-4.6
    - glm-4.5v -> GLM-4.5V
    
    :param name: 原始模型名称
    :return: 格式化后的模型名称
    """
    if not name:
        return ""
    
    parts = name.split('-')
    if len(parts) == 1:
        return parts[0].upper()
    
    formatted = [parts[0].upper()]
    for p in parts[1:]:
        if not p:
            formatted.append("")
        elif p.isdigit():
            formatted.append(p)
        elif any(c.isalpha() for c in p):
            formatted.append(p.capitalize())
        else:
            formatted.append(p)
    
    return "-".join(formatted)


def get_model_name(source_id: str, model_name: str) -> str:
    """获取模型名称：优先使用自带名称，其次智能生成。
    
    :param source_id: 上游API返回的模型ID
    :param model_name: 上游API返回的模型名称
    :return: 处理后的模型名称
    """
    # 处理自带系列名的模型名称
    if source_id.startswith(("GLM", "Z")) and "." in source_id:
        return source_id
    
    if model_name.startswith(("GLM", "Z")) and "." in model_name:
        return model_name
    
    # 无法识别系列名，但名称仍为英文
    if not model_name or not ('A' <= model_name[0] <= 'Z' or 'a' <= model_name[0] <= 'z'):
        model_name = format_model_name(source_id)
        if not model_name.upper().startswith(("GLM", "Z")):
            model_name = "GLM-" + format_model_name(source_id)
    
    return model_name


def get_model_id(source_id: str, model_name: str) -> str:
    """获取模型ID：优先使用配置映射，其次智能生成。
    
    :param source_id: 上游API返回的模型ID
    :param model_name: 处理后的模型名称
    :return: 用于API的模型ID
    """
    if source_id in settings.MODELS_MAPPING:
        return settings.MODELS_MAPPING[source_id]
    
    # 将模型名称转换为小写并替换空格为连字符作为ID
    smart_id = model_name.lower().replace(" ", "-")
    return smart_id


async def fetch_models_from_upstream(access_token: str | None = None) -> dict[str, Any]:
    """从上游API获取模型列表。
    
    :param access_token: 可选的访问令牌
    :return: 包含模型列表的字典
    :raises Exception: 当API请求失败时
    """
    headers = {
        **settings.HEADERS,
        "Content-Type": "application/json",
    }
    
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    models_url = f"{settings.proxy_url}/api/models"
    
    logger.info("Fetching models from upstream: url={}", models_url)
    
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                models_url,
                headers=headers,
                timeout=10.0,
            )
            
            if response.status_code == 200:
                data = response.json()
                model_count = len(data.get("data", []))
                logger.info(
                    "Models fetched successfully from upstream: total_count={}, url={}",
                    model_count,
                    models_url
                )
                return data
            else:
                error_text = response.text
                logger.error(
                    "Failed to fetch models from upstream: status_code={}, url={}, response_text={}",
                    response.status_code,
                    models_url,
                    error_text[:200],
                )
                raise Exception(f"获取模型列表失败 (HTTP {response.status_code}): {error_text[:100]}")
                
    except httpx.RequestError as e:
        logger.error(
            "Models request error: error_type={}, error={}, url={}",
            type(e).__name__,
            str(e),
            models_url,
        )
        raise Exception(f"模型列表请求错误: {str(e)}")
    except Exception as e:
        logger.error(
            "Models unexpected error: error_type={}, error={}, url={}",
            type(e).__name__,
            str(e),
            models_url,
        )
        raise


async def get_models(access_token: str | None = None, use_cache: bool = True) -> dict[str, Any]:
    """获取格式化的模型列表。
    
    自动为支持特殊功能的模型生成变体：
    - 基础模型：原始模型ID
    - nothinking变体：禁用深度思考
    - search变体：启用网络搜索
    - advanced-search变体：启用高级搜索
    
    :param access_token: 可选的访问令牌
    :param use_cache: 是否使用缓存
    :return: 格式化后的模型列表字典
    """
    global _models_cache
    
    if use_cache and _models_cache:
        cached_count = len(_models_cache.get("data", []))
        logger.info("Returning cached models: cached_count={}", cached_count)
        return _models_cache
    
    logger.info("Fetching fresh models from upstream: use_cache={}", use_cache)
    
    upstream_data = await fetch_models_from_upstream(access_token)
    
    default_logo = "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2030%2030%22%20style%3D%22background%3A%232D2D2D%22%3E%3Cpath%20fill%3D%22%23FFFFFF%22%20d%3D%22M15.47%207.1l-1.3%201.85c-.2.29-.54.47-.9.47h-7.1V7.09c0%20.01%209.31.01%209.31.01z%22%2F%3E%3Cpath%20fill%3D%22%23FFFFFF%22%20d%3D%22M24.3%207.1L13.14%2022.91H5.7l11.16-15.81z%22%2F%3E%3Cpath%20fill%3D%22%23FFFFFF%22%20d%3D%22M14.53%2022.91l1.31-1.86c.2-.29.54-.47.9-.47h7.09v2.33h-9.3z%22%2F%3E%3C%2Fsvg%3E"
    
    models = []
    for m in upstream_data.get("data", []):
        if not m.get("info", {}).get("is_active", True):
            continue
        
        source_id = m.get("id")
        source_name = m.get("name")
        model_info = m.get("info", {})
        model_meta = model_info.get("meta", {})
        
        processed_name = get_model_name(source_id, source_name)
        processed_id = get_model_id(source_id, processed_name)
        
        # 建立客户端模型ID到上游模型ID的反向映射
        if processed_id not in settings.REVERSE_MODELS_MAPPING:
            settings.REVERSE_MODELS_MAPPING[processed_id] = source_id
            logger.info(
                "Added reverse mapping: processed_id={} -> source_id={}",
                processed_id,
                source_id
            )
        
        logger.info(
            "Model mapping: source_id={}, source_name={} -> processed_id={}, processed_name={}",
            source_id,
            source_name,
            processed_id,
            processed_name
        )
        
        model_meta_processed = {
            "profile_image_url": default_logo,
            "capabilities": model_meta.get("capabilities"),
            "description": model_meta.get("description"),
            "hidden": model_meta.get("hidden"),
            "suggestion_prompts": [
                {"content": item["prompt"]}
                for item in (model_meta.get("suggestion_prompts") or [])
                if isinstance(item, dict) and "prompt" in item
            ]
        }
        
        base_model = {
            "id": processed_id,
            "object": "model",
            "name": processed_name,
            "meta": model_meta_processed,
            "info": {
                "meta": model_meta_processed
            },
            "created": model_info.get("created_at", int(datetime.now().timestamp())),
            "owned_by": "z.ai",
            "original": {
                "name": source_name,
                "id": source_id,
                "info": model_info
            },
        }
        models.append(base_model)
        
        capabilities = model_meta.get("capabilities", {})
        
        # 为支持深度思考的模型生成禁用思考的变体
        if capabilities.get("think", False):
            nothinking_id = f"{processed_id}-nothinking"
            nothinking_name = f"{processed_name}-NOTHINKING"
            
            if nothinking_id not in settings.REVERSE_MODELS_MAPPING:
                settings.REVERSE_MODELS_MAPPING[nothinking_id] = source_id
                logger.info(
                    "Added reverse mapping for variant: {} -> {}",
                    nothinking_id,
                    source_id
                )
            
            models.append({
                **base_model,
                "id": nothinking_id,
                "name": nothinking_name,
                "meta": {
                    **model_meta_processed,
                    "description": f"{model_meta_processed.get('description', '')} (禁用深度思考)".strip()
                },
            })
            logger.info(
                "Generated nothinking variant: base_id={}, base_name={} -> variant_id={}, variant_name={}, upstream_id={}",
                processed_id,
                processed_name,
                nothinking_id,
                nothinking_name,
                source_id
            )
        
        # 为支持网络搜索的模型生成搜索变体
        if capabilities.get("web_search", False):
            search_id = f"{processed_id}-search"
            search_name = f"{processed_name}-SEARCH"
            
            if search_id not in settings.REVERSE_MODELS_MAPPING:
                settings.REVERSE_MODELS_MAPPING[search_id] = source_id
                logger.info(
                    "Added reverse mapping for variant: {} -> {}",
                    search_id,
                    source_id
                )
            
            models.append({
                **base_model,
                "id": search_id,
                "name": search_name,
                "meta": {
                    **model_meta_processed,
                    "description": f"{model_meta_processed.get('description', '')} (启用网络搜索)".strip()
                },
            })
            logger.info(
                "Generated search variant: base_id={}, base_name={} -> variant_id={}, variant_name={}, upstream_id={}",
                processed_id,
                processed_name,
                search_id,
                search_name,
                source_id
            )
            
            # 生成高级搜索变体（包含MCP服务器支持）
            advanced_search_id = f"{processed_id}-advanced-search"
            advanced_search_name = f"{processed_name}-ADVANCED-SEARCH"
            
            if advanced_search_id not in settings.REVERSE_MODELS_MAPPING:
                settings.REVERSE_MODELS_MAPPING[advanced_search_id] = source_id
                logger.info(
                    "Added reverse mapping for variant: {} -> {}",
                    advanced_search_id,
                    source_id
                )
            
            models.append({
                **base_model,
                "id": advanced_search_id,
                "name": advanced_search_name,
                "meta": {
                    **model_meta_processed,
                    "description": f"{model_meta_processed.get('description', '')} (启用高级搜索)".strip()
                },
            })
            logger.info(
                "Generated advanced-search variant: base_id={}, base_name={} -> variant_id={}, variant_name={}, upstream_id={}",
                processed_id,
                processed_name,
                advanced_search_id,
                advanced_search_name,
                source_id
            )
    
    result = {
        "object": "list",
        "data": models,
    }
    
    _models_cache = result
    
    upstream_total = len(upstream_data.get("data", []))
    active_count = len([m for m in upstream_data.get("data", []) if m.get("info", {}).get("is_active", True)])
    variants_count = len(models)
    reverse_mapping_count = len(settings.REVERSE_MODELS_MAPPING)
    
    logger.info(
        "Models processed successfully: upstream_total={}, active_models={}, generated_variants={}, reverse_mappings={}, cache_updated=True",
        upstream_total,
        active_count,
        variants_count,
        reverse_mapping_count
    )
    
    if settings.verbose_logging:
        logger.debug("Current reverse mappings: {}", dict(settings.REVERSE_MODELS_MAPPING))
    
    return result


def clear_models_cache() -> None:
    """清除模型列表缓存。"""
    global _models_cache
    _models_cache = None
    logger.debug("Models cache cleared")