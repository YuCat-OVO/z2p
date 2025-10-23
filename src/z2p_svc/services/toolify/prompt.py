"""Toolify 提示词生成模块。

生成工具调用的系统提示词，将 OpenAI tools 定义注入到消息中。
"""

import json
from typing import List, Dict, Any

from ...logger import get_logger

logger = get_logger(__name__)

TRIGGER_SIGNAL = "<tool_call>"


def generate_tools_prompt(tools: List[Dict[str, Any]]) -> str:
    """生成工具定义的提示词。
    
    :param tools: 工具定义列表（OpenAI 格式）
    :return: 格式化的工具描述文本
    """
    tools_list = []
    for i, tool in enumerate(tools):
        func = tool.get("function", {})
        name = func.get("name", "")
        description = func.get("description", "")
        schema = func.get("parameters", {}) or {}
        props = schema.get("properties", {}) or {}
        required = schema.get("required", []) or []
        
        # 构建参数描述
        params_desc = []
        for p_name, p_info in props.items():
            p_info = p_info or {}
            p_type = p_info.get("type", "any")
            is_req = "必需" if p_name in required else "可选"
            p_desc = p_info.get("description", "")
            params_desc.append(f"  - {p_name} ({p_type}, {is_req}): {p_desc}")
        
        params_text = "\n".join(params_desc) if params_desc else "  无参数"
        
        tools_list.append(
            f"{i + 1}. {name}\n"
            f"   描述: {description}\n"
            f"   参数:\n{params_text}"
        )
    
    return "\n\n".join(tools_list)


def inject_tool_prompt(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将工具定义注入到消息列表中。
    
    :param messages: 原始消息列表
    :param tools: 工具定义列表
    :return: 注入工具提示词后的消息列表
    """
    if not tools:
        return messages
    
    tools_desc = generate_tools_prompt(tools)
    
    system_prompt = f"""你可以使用以下工具来帮助回答问题：

{tools_desc}

当需要使用工具时，请严格按照以下格式输出：

{TRIGGER_SIGNAL}
<function_calls>
    <function_call>
        <tool>工具名称</tool>
        <args>
            <参数名>参数值</参数名>
        </args>
    </function_call>
</function_calls>

注意：
1. 触发信号 {TRIGGER_SIGNAL} 必须单独占一行
2. 可以在一个 <function_calls> 中包含多个 <function_call>
3. 参数名必须与工具定义中的完全一致
4. 在 </function_calls> 后不要添加任何文本"""
    
    # 查找是否已有 system 消息
    new_messages = []
    system_found = False
    
    for msg in messages:
        if msg.get("role") == "system":
            # 合并到现有 system 消息
            existing_content = msg.get("content", "")
            msg["content"] = f"{existing_content}\n\n{system_prompt}"
            system_found = True
        new_messages.append(msg)
    
    # 如果没有 system 消息，添加一个
    if not system_found:
        new_messages.insert(0, {"role": "system", "content": system_prompt})
    
    logger.info(f"[TOOLIFY] 已注入工具提示词，工具数量: {len(tools)}")
    return new_messages