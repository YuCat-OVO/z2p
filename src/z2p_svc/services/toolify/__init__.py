"""Toolify 模块：实现 OpenAI 工具调用的模拟。

通过提示词注入和响应解析来模拟 OpenAI 的 tools API。
"""

from .core import ToolifyCore, get_toolify_core, generate_random_trigger_signal
from .detector import StreamingToolCallDetector
from .parser import parse_tool_calls_xml, convert_to_openai_tool_calls, remove_think_blocks
from .prompt import (
    generate_function_prompt,
    generate_tools_prompt,
    get_function_call_prompt_template,
    inject_tool_prompt,
    safe_process_tool_choice,
    TRIGGER_SIGNAL,
)

__all__ = [
    "ToolifyCore",
    "get_toolify_core",
    "generate_random_trigger_signal",
    "StreamingToolCallDetector",
    "parse_tool_calls_xml",
    "convert_to_openai_tool_calls",
    "remove_think_blocks",
    "generate_function_prompt",
    "generate_tools_prompt",
    "get_function_call_prompt_template",
    "inject_tool_prompt",
    "safe_process_tool_choice",
    "TRIGGER_SIGNAL",
]