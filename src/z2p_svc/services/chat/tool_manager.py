"""工具调用管理模块。

提供工具调用映射管理和格式化功能。
"""

import time
import threading
from typing import Dict, Any, Optional
from collections import OrderedDict


class ToolCallMappingManager:
    """工具调用映射管理器。

    管理工具调用ID与调用内容的映射关系，支持TTL和LRU缓存。
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """初始化映射管理器。

        :param max_size: 最大存储条目数
        :param ttl_seconds: 条目生存时间（秒）
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._data: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.RLock()

    def store(self, tool_call_id: str, name: str, args: dict) -> None:
        """存储工具调用映射。

        :param tool_call_id: 工具调用ID
        :param name: 工具名称
        :param args: 工具参数
        """
        with self._lock:
            current_time = time.time()

            # 如果已存在，先删除
            if tool_call_id in self._data:
                del self._data[tool_call_id]
                del self._timestamps[tool_call_id]

            # 如果达到最大容量，删除最旧的条目
            while len(self._data) >= self.max_size:
                oldest_key = next(iter(self._data))
                del self._data[oldest_key]
                del self._timestamps[oldest_key]

            # 存储新条目
            self._data[tool_call_id] = {
                "name": name,
                "args": args,
                "created_at": current_time,
            }
            self._timestamps[tool_call_id] = current_time

    def get(self, tool_call_id: str) -> Optional[Dict[str, Any]]:
        """获取工具调用映射。

        :param tool_call_id: 工具调用ID
        :return: 工具调用信息，如果不存在或已过期则返回None
        """
        with self._lock:
            current_time = time.time()

            if tool_call_id not in self._data:
                return None

            # 检查是否过期
            if current_time - self._timestamps[tool_call_id] > self.ttl_seconds:
                del self._data[tool_call_id]
                del self._timestamps[tool_call_id]
                return None

            # 更新LRU顺序
            result = self._data[tool_call_id]
            self._data.move_to_end(tool_call_id)

            return result

    def cleanup_expired(self) -> int:
        """清理过期条目。

        :return: 清理的条目数量
        """
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key
                for key, timestamp in self._timestamps.items()
                if current_time - timestamp > self.ttl_seconds
            ]

            for key in expired_keys:
                del self._data[key]
                del self._timestamps[key]

            return len(expired_keys)


# 全局映射管理器实例
_mapping_manager: Optional[ToolCallMappingManager] = None
_manager_lock = threading.Lock()


def get_mapping_manager() -> ToolCallMappingManager:
    """获取全局映射管理器实例（单例模式）。

    :return: 映射管理器实例
    """
    global _mapping_manager

    if _mapping_manager is None:
        with _manager_lock:
            if _mapping_manager is None:
                _mapping_manager = ToolCallMappingManager()

    return _mapping_manager


def format_tool_result_for_ai(tool_call_id: str, result_content: str) -> str:
    """格式化工具调用结果供AI理解。

    :param tool_call_id: 工具调用ID
    :param result_content: 工具执行结果
    :return: 格式化后的结果文本
    """
    manager = get_mapping_manager()
    tool_info = manager.get(tool_call_id)

    if not tool_info:
        return (
            f"Tool execution result:\n<tool_result>\n{result_content}\n</tool_result>"
        )

    return f"""Tool execution result:
- Tool name: {tool_info["name"]}
- Execution result:
<tool_result>
{result_content}
</tool_result>"""


def preprocess_messages(messages: list[dict]) -> list[dict]:
    """预处理消息，转换工具类型消息为AI可理解格式。

    将tool角色的消息转换为user角色，并格式化工具调用结果。
    将assistant角色中的tool_calls转换为文本内容。

    :param messages: 原始消息列表
    :return: 处理后的消息列表
    """
    processed_messages = []

    for message in messages:
        if not isinstance(message, dict):
            processed_messages.append(message)
            continue

        role = message.get("role")

        # 处理 tool 角色消息 - 转换为 user 角色
        if role == "tool":
            tool_call_id = message.get("tool_call_id")
            content = message.get("content", "")

            if tool_call_id and content:
                formatted_content = format_tool_result_for_ai(tool_call_id, content)
                processed_messages.append(
                    {"role": "user", "content": formatted_content}
                )
            else:
                # 如果缺少必要信息，保持原样
                processed_messages.append(message)

        # 处理 assistant 角色的 tool_calls - 转换为文本内容
        elif role == "assistant" and "tool_calls" in message and message["tool_calls"]:
            tool_calls = message.get("tool_calls", [])
            original_content = message.get("content") or ""

            # 格式化tool_calls为文本
            tool_calls_text = format_assistant_tool_calls(tool_calls)

            # 合并原始内容和工具调用
            final_content = f"{original_content}\n{tool_calls_text}".strip()

            # 创建新消息，保留其他字段
            processed_message = {"role": "assistant", "content": final_content}

            # 复制其他字段（除了tool_calls）
            for key, value in message.items():
                if key not in ["role", "content", "tool_calls"]:
                    processed_message[key] = value

            processed_messages.append(processed_message)

        else:
            # 其他消息保持原样
            processed_messages.append(message)

    return processed_messages


def format_assistant_tool_calls(tool_calls: list[dict]) -> str:
    """将assistant的tool_calls格式化为文本。

    :param tool_calls: 工具调用列表
    :return: 格式化后的文本
    """
    import json

    formatted_parts = []

    for tool_call in tool_calls:
        tool_call_id = tool_call.get("id", "")
        function_info = tool_call.get("function", {})
        name = function_info.get("name", "")
        arguments_json = function_info.get("arguments", "{}")

        try:
            args_dict = json.loads(arguments_json)
        except (json.JSONDecodeError, TypeError):
            args_dict = {"raw_arguments": arguments_json}

        # 格式化为易读的文本
        args_text = json.dumps(args_dict, ensure_ascii=False, indent=2)
        
        formatted_parts.append(f"""Tool Call: {name}
ID: {tool_call_id}
Arguments:
{args_text}""")
    
    return "\n\n".join(formatted_parts)