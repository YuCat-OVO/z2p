"""模型服务模块。

本模块负责从上游API获取模型列表，并进行智能处理和格式化。
参考temp.py中的get_model_id和get_model_name函数实现。
"""

import httpx
import stamina
from typing import Any, Dict, List
from datetime import datetime

from .config import get_settings
from .logger import get_logger
from .models import (
    UpstreamModelsResponse,
    DownstreamModelsResponse,
    DownstreamModel,
)

logger = get_logger(__name__)
settings = get_settings()

_models_cache: dict[str, Any] | None = None

# 定义所有可能的功能开关及其尾缀和描述
# 这里的键名应与 UpstreamCapability 中的字段名一致
FEATURE_SWITCHES: Dict[str, Dict[str, Any]] = {
    "think": {
        "suffix": "-nothinking",
        "name_suffix": "-NOTHINKING",
        "description_suffix": "(禁用深度思考)",
        "negate": True
    },
    "web_search": {
        "suffix": "-search",
        "name_suffix": "-SEARCH",
        "description_suffix": "(启用网络搜索)"
    },
    "mcp": {
        "suffix": "-mcp",
        "name_suffix": "-MCP",
        "description_suffix": "(启用MCP工具)"
    },
    "vision": {
        "suffix": "-vision",
        "name_suffix": "-VISION",
        "description_suffix": "(启用视觉能力)"
    },
    "file_qa": {
        "suffix": "-fileqa",
        "name_suffix": "-FILEQA",
        "description_suffix": "(启用文件问答)"
    },
}


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
    
    # 简单转大写即可，保持原有的连字符和点号结构
    return name.upper()


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


@stamina.retry(on=Exception, attempts=3, wait_initial=1.0, wait_max=5.0)
async def fetch_models_from_upstream(access_token: str | None = None) -> dict[str, Any]:
    """从上游API获取模型列表（带重试机制）。
    
    使用 stamina 进行自动重试：
    - 最多重试 3 次
    - 初始等待 1 秒
    - 最大等待 5 秒
    
    :param access_token: 可选的访问令牌
    :return: 包含模型列表的字典
    :raises Exception: 当API请求失败且重试耗尽时
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
    - mcp变体：启用MCP工具
    - vision变体：启用视觉能力
    - fileqa变体：启用文件问答
    
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
    
    upstream_raw_data = await fetch_models_from_upstream(access_token)
    upstream_data = UpstreamModelsResponse.model_validate(upstream_raw_data)
    
    default_logo = "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2030%2030%22%20style%3D%22background%3A%232D2D2D%22%3E%3Cpath%20fill%3D%22%23FFFFFF%22%20d%3D%22M15.47%207.1l-1.3%201.85c-.2.29-.54.47-.9.47h-7.1V7.09c0%20.01%209.31.01%209.31.01z%22%2F%3E%3Cpath%20fill%3D%22%23FFFFFF%22%20d%3D%22M24.3%207.1L13.14%2022.91H5.7l11.16-15.81z%22%2F%3E%3Cpath%20fill%3D%22%23FFFFFF%22%20d%3D%22M14.53%2022.91l1.31-1.86c.2-.29.54-.47.9-.47h7.09v2.33h-9.3z%22%2F%3E%3C%2Fsvg%3E"
    
    downstream_models: List[DownstreamModel] = []
    
    for m in upstream_data.data:
        if not m.info.is_active:
            continue
        
        source_id = m.id
        source_name = m.name
        model_info = m.info
        model_meta = model_info.meta
        
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
        
        # 创建基础模型（OpenAI 兼容格式）
        base_downstream_model = DownstreamModel(
            id=processed_id,
            object="model",
            name=processed_name,
            created=model_info.created_at or int(datetime.now().timestamp()),
            owned_by="z.ai",
        )
        downstream_models.append(base_downstream_model)
        
        logger.info(
            "Base model generated: id={}, name={}, upstream_id={}",
            base_downstream_model.id,
            base_downstream_model.name,
            source_id
        )
        
        # 只为已映射的模型生成变体
        is_mapped_model = source_id in settings.MODELS_MAPPING
        
        if is_mapped_model and model_meta and model_meta.capabilities:
            for feature_key, feature_config in FEATURE_SWITCHES.items():
                is_enabled = getattr(model_meta.capabilities, feature_key, False)
                
                # 如果是 "think" 且 negate 为 True，则当 think 为 True 时生成 nothinking 变体
                # 否则，当功能启用时生成变体
                should_generate_variant = (is_enabled and not feature_config.get("negate", False)) or \
                                          (is_enabled and feature_config.get("negate", False))
                
                # 检查模型名称是否已经包含该功能标识，避免重复变体
                # 例如 glm-4.5v 已经表示 vision，不应再生成 glm-4.5v-vision
                already_has_feature = False
                
                # 特殊处理：模型名称末尾为版本号+v（如 4.5v, 4.1v）表示 vision
                if feature_key == "vision" and processed_name.lower().endswith("v"):
                    # 检查 v 前面是否是数字（版本号）
                    import re
                    if re.search(r'\d+\.?\d*v$', processed_name.lower()):
                        already_has_feature = True
                
                # 通用检查：功能名是否包含在模型名中
                if not already_has_feature:
                    feature_name_lower = feature_key.lower().replace("_", "")
                    model_name_lower = processed_name.lower().replace("-", "").replace("_", "")
                    already_has_feature = feature_name_lower in model_name_lower
                
                if should_generate_variant and not already_has_feature:
                    variant_id = f"{processed_id}{feature_config['suffix']}"
                    variant_name = f"{processed_name}{feature_config['name_suffix']}"
                    
                    # 创建变体模型（OpenAI 兼容格式）
                    variant_downstream_model = DownstreamModel(
                        id=variant_id,
                        object="model",
                        name=variant_name,
                        created=model_info.created_at or int(datetime.now().timestamp()),
                        owned_by="z.ai",
                    )
                    downstream_models.append(variant_downstream_model)
                    
                    if variant_id not in settings.REVERSE_MODELS_MAPPING:
                        settings.REVERSE_MODELS_MAPPING[variant_id] = source_id
                        logger.info(
                            "Added reverse mapping for variant: {} -> {}",
                            variant_id,
                            source_id
                        )
                    logger.info(
                        "Generated variant: base_id={}, base_name={} -> variant_id={}, variant_name={}, upstream_id={}, feature={}",
                        processed_id,
                        processed_name,
                        variant_id,
                        variant_name,
                        source_id,
                        feature_key
                    )
    
    result = DownstreamModelsResponse(
        object="list",
        data=downstream_models,
    )
    
    _models_cache = result.model_dump()  # 缓存 Pydantic 模型转换为字典
    
    upstream_total = len(upstream_data.data)
    active_count = len([m for m in upstream_data.data if m.info.is_active])
    variants_count = len(downstream_models)
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
    
    return result.model_dump()  # 返回 Pydantic 模型转换为字典


def clear_models_cache() -> None:
    """清除模型列表缓存。"""
    global _models_cache
    _models_cache = None
    logger.debug("Models cache cleared")