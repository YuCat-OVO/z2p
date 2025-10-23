"""Toolify XML 解析器。

解析模型响应中的工具调用 XML 格式。
"""

import re
import json
from typing import List, Dict, Any, Optional

from ...logger import get_logger

logger = get_logger(__name__)


def parse_tool_calls_xml(xml_string: str, trigger_signal: str = "<tool_call>") -> Optional[List[Dict[str, Any]]]:
    """解析 XML 格式的工具调用。
    
    :param xml_string: 包含 XML 的响应字符串
    :param trigger_signal: 触发信号字符串
    :return: 解析出的工具调用列表，格式为 [{"name": "tool_name", "args": {...}}, ...]
    """
    if not xml_string or trigger_signal not in xml_string:
        return None
    
    # 查找 function_calls 标签
    calls_match = re.search(r"<function_calls>([\s\S]*?)</function_calls>", xml_string)
    if not calls_match:
        logger.warning("[TOOLIFY] 未找到 function_calls 标签")
        return None
    
    calls_content = calls_match.group(1)
    
    # 解析所有 function_call 块
    results = []
    call_blocks = re.findall(r"<function_call>([\s\S]*?)</function_call>", calls_content)
    
    for block in call_blocks:
        # 提取 tool 名称
        tool_match = re.search(r"<tool>(.*?)</tool>", block)
        if not tool_match:
            continue
        
        name = tool_match.group(1).strip()
        args = {}
        
        # 提取 args 块
        args_match = re.search(r"<args>([\s\S]*?)</args>", block)
        if args_match:
            args_content = args_match.group(1)
            # 匹配参数标签
            arg_matches = re.findall(r"<([^\s>/]+)>([\s\S]*?)</\1>", args_content)
            
            for k, v in arg_matches:
                # 尝试解析为 JSON
                try:
                    args[k] = json.loads(v)
                except:
                    args[k] = v
        
        results.append({"name": name, "args": args})
    
    return results if results else None


def convert_to_openai_tool_calls(parsed_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将解析的工具调用转换为 OpenAI 格式。
    
    :param parsed_tools: 解析出的工具调用列表
    :return: OpenAI 格式的 tool_calls 列表
    """
    import uuid
    
    tool_calls = []
    for tool in parsed_tools:
        tool_calls.append({
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {
                "name": tool["name"],
                "arguments": json.dumps(tool["args"], ensure_ascii=False)
            }
        })
    
    return tool_calls