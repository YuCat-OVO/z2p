"""UUID 生成工具模块（使用 fastuuid 优化性能）"""

from fastuuid import uuid4


def generate_uuid_str() -> str:
    """生成 UUID v4 字符串（性能优化版本）
    
    使用 fastuuid 替代标准库 uuid，性能提升约 3-5 倍
    
    Returns:
        str: UUID v4 字符串
    """
    return str(uuid4())


def generate_chat_id() -> str:
    """生成聊天会话 ID"""
    return generate_uuid_str()


def generate_request_id() -> str:
    """生成请求 ID"""
    return generate_uuid_str()


def generate_completion_id() -> str:
    """生成 completion ID（OpenAI 格式）"""
    return f"chatcmpl-{uuid4().hex[:8]}"