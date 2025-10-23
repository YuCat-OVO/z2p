"""Toolify 核心功能模块。

提供工具调用的主要功能：映射管理、消息预处理、格式转换。
"""

import json
import secrets
import string
import uuid
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from ...logger import get_logger

logger = get_logger(__name__)


def generate_random_trigger_signal() -> str:
    """生成随机的触发信号。
    
    :return: 随机触发信号，如 <Function_AB1c_Start/>
    """
    chars = string.ascii_letters + string.digits
    random_str = "".join(secrets.choice(chars) for _ in range(4))
    return f"<Function_{random_str}_Start/>"


class ToolCallMappingManager:
    """工具调用映射管理器（简化版，无TTL）。"""

    def __init__(self, max_size: int = 1000):
        """初始化映射管理器。
        
        :param max_size: 最大存储条目数
        """
        self.max_size = max_size
        self._data: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def store(self, tool_call_id: str, name: str, args: dict) -> None:
        """存储工具调用映射。
        
        :param tool_call_id: 工具调用ID
        :param name: 工具名称
        :param args: 工具参数
        """
        if tool_call_id in self._data:
            del self._data[tool_call_id]

        while len(self._data) >= self.max_size:
            oldest_key = next(iter(self._data))
            del self._data[oldest_key]
            logger.debug(f"[TOOLIFY] 因大小限制移除最旧条目: {oldest_key}")

        self._data[tool_call_id] = {"name": name, "args": args}
        logger.debug(f"[TOOLIFY] 存储工具调用映射: {tool_call_id} -> {name}")

    def get(self, tool_call_id: str) -> Optional[Dict[str, Any]]:
        """获取工具调用映射。
        
        :param tool_call_id: 工具调用ID
        :return: 工具信息字典或None
        """
        if tool_call_id not in self._data:
            return None

        result = self._data[tool_call_id]
        self._data.move_to_end(tool_call_id)
        return result


class ToolifyCore:
    """Toolify 核心类 - 管理工具调用功能。"""

    def __init__(self):
        """初始化 Toolify 核心。"""
        self.mapping_manager = ToolCallMappingManager()
        self.trigger_signal = generate_random_trigger_signal()
        logger.info(f"[TOOLIFY] 核心已初始化，触发信号: {self.trigger_signal}")

    def store_tool_call_mapping(self, tool_call_id: str, name: str, args: dict):
        """存储工具调用ID与调用内容的映射。
        
        :param tool_call_id: 工具调用ID
        :param name: 工具名称
        :param args: 工具参数
        """
        self.mapping_manager.store(tool_call_id, name, args)

    def get_tool_call_mapping(self, tool_call_id: str) -> Optional[Dict[str, Any]]:
        """获取工具调用ID对应的调用内容。
        
        :param tool_call_id: 工具调用ID
        :return: 工具信息字典或None
        """
        return self.mapping_manager.get(tool_call_id)

    def format_tool_result_for_ai(self, tool_call_id: str, result_content: str) -> str:
        """格式化工具调用结果供AI理解。
        
        :param tool_call_id: 工具调用ID
        :param result_content: 工具执行结果
        :return: 格式化后的结果文本
        """
        tool_info = self.get_tool_call_mapping(tool_call_id)
        if not tool_info:
            return f"Tool execution result:\n<tool_result>\n{result_content}\n</tool_result>"

        return f"""Tool execution result:
- Tool name: {tool_info['name']}
- Execution result:
<tool_result>
{result_content}
</tool_result>"""

    def format_assistant_tool_calls_for_ai(self, tool_calls: List[Dict[str, Any]]) -> str:
        """将助手的工具调用格式化为AI可读的字符串格式。
        
        :param tool_calls: OpenAI 格式的 tool_calls 列表
        :return: XML 格式的工具调用字符串
        """
        xml_calls_parts = []
        for tool_call in tool_calls:
            function_info = tool_call.get("function", {})
            name = function_info.get("name", "")
            arguments_json = function_info.get("arguments", "{}")

            try:
                args_dict = json.loads(arguments_json)
            except (json.JSONDecodeError, TypeError):
                args_dict = {"raw_arguments": arguments_json}

            args_parts = []
            for key, value in args_dict.items():
                json_value = json.dumps(value, ensure_ascii=False)
                args_parts.append(f"<{key}>{json_value}</{key}>")

            args_content = "\n".join(args_parts)
            xml_call = f"<function_call>\n<tool>{name}</tool>\n<args>\n{args_content}\n</args>\n</function_call>"
            xml_calls_parts.append(xml_call)

        all_calls = "\n".join(xml_calls_parts)
        return f"{self.trigger_signal}\n<function_calls>\n{all_calls}\n</function_calls>"

    def preprocess_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """预处理消息，转换工具类型消息为AI可理解格式。
        
        :param messages: OpenAI格式的消息列表
        :return: 处理后的消息列表
        """
        processed_messages = []

        for message in messages:
            if not isinstance(message, dict):
                processed_messages.append(message)
                continue

            # 处理 tool 角色消息
            if message.get("role") == "tool":
                tool_call_id = message.get("tool_call_id")
                content = message.get("content")

                if tool_call_id and content:
                    formatted_content = self.format_tool_result_for_ai(tool_call_id, content)
                    processed_messages.append({"role": "user", "content": formatted_content})
                    logger.debug(f"[TOOLIFY] 转换tool消息为user消息: tool_call_id={tool_call_id}")
                continue

            # 处理 assistant 角色的 tool_calls
            if message.get("role") == "assistant" and message.get("tool_calls"):
                tool_calls = message.get("tool_calls", [])
                formatted_tool_calls_str = self.format_assistant_tool_calls_for_ai(tool_calls)

                original_content = message.get("content") or ""
                final_content = f"{original_content}\n{formatted_tool_calls_str}".strip()

                processed_message = {"role": "assistant", "content": final_content}
                # 复制其他字段（除了tool_calls）
                for key, value in message.items():
                    if key not in ["role", "content", "tool_calls"]:
                        processed_message[key] = value

                processed_messages.append(processed_message)
                logger.debug("[TOOLIFY] 转换assistant的tool_calls为content")
                continue

            processed_messages.append(message)

        return processed_messages

    def convert_parsed_tools_to_openai_format(self, parsed_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将解析出的工具调用转换为OpenAI格式的tool_calls。
        
        :param parsed_tools: 解析出的工具列表 [{"name": "tool_name", "args": {...}}, ...]
        :return: OpenAI格式的tool_calls列表
        """
        tool_calls = []
        for tool in parsed_tools:
            tool_call_id = f"call_{uuid.uuid4().hex}"
            self.store_tool_call_mapping(tool_call_id, tool["name"], tool["args"])
            tool_calls.append({
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "arguments": json.dumps(tool["args"])
                }
            })

        logger.debug(f"[TOOLIFY] 转换了 {len(tool_calls)} 个工具调用")
        return tool_calls


# 全局单例
_toolify_core_instance: Optional[ToolifyCore] = None


def get_toolify_core() -> ToolifyCore:
    """获取 Toolify 核心单例。
    
    :return: ToolifyCore 实例
    """
    global _toolify_core_instance
    if _toolify_core_instance is None:
        _toolify_core_instance = ToolifyCore()
    return _toolify_core_instance