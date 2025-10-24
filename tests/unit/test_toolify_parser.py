"""测试 Toolify XML 解析器（已修复以适应新API）。"""

import pytest
from src.z2p_svc.services.toolify import parse_tool_calls_xml, convert_to_openai_tool_calls, get_toolify_core


class TestParseToolCallsXml:
    """测试 XML 解析功能。"""
    
    def test_parse_single_tool_call(self):
        """测试解析单个工具调用。"""
        core = get_toolify_core()
        xml = f"""{core.trigger_signal}
<function_calls>
    <function_call>
        <tool>test_tool</tool>
        <args>
            <param1>value1</param1>
        </args>
    </function_call>
</function_calls>"""
        
        result = parse_tool_calls_xml(xml, core.trigger_signal)
        
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "test_tool"
        assert result[0]["args"]["param1"] == "value1"
    
    def test_parse_multiple_tool_calls(self):
        """测试解析多个工具调用。"""
        core = get_toolify_core()
        xml = f"""{core.trigger_signal}
<function_calls>
    <function_call>
        <tool>tool1</tool>
        <args><param>value1</param></args>
    </function_call>
    <function_call>
        <tool>tool2</tool>
        <args><param>value2</param></args>
    </function_call>
</function_calls>"""
        
        result = parse_tool_calls_xml(xml, core.trigger_signal)
        
        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "tool1"
        assert result[1]["name"] == "tool2"
    
    def test_parse_with_json_args(self):
        """测试解析 JSON 格式的参数。"""
        core = get_toolify_core()
        xml = f"""{core.trigger_signal}
<function_calls>
    <function_call>
        <tool>test_tool</tool>
        <args>
            <list_param>["item1", "item2"]</list_param>
            <number_param>42</number_param>
        </args>
    </function_call>
</function_calls>"""
        
        result = parse_tool_calls_xml(xml, core.trigger_signal)
        
        assert result is not None
        assert isinstance(result[0]["args"]["list_param"], list)
        assert result[0]["args"]["number_param"] == 42
    
    def test_parse_no_trigger_signal(self):
        """测试没有触发信号的情况。"""
        core = get_toolify_core()
        xml = """<function_calls>
    <function_call>
        <tool>test_tool</tool>
        <args></args>
    </function_call>
</function_calls>"""
        
        result = parse_tool_calls_xml(xml, core.trigger_signal)
        
        assert result is None
    
    def test_parse_no_function_calls_tag(self):
        """测试没有 function_calls 标签的情况。"""
        core = get_toolify_core()
        xml = f"{core.trigger_signal}\n这是普通文本"
        
        result = parse_tool_calls_xml(xml, core.trigger_signal)
        
        assert result is None
    
    def test_parse_empty_function_calls(self):
        """测试空的 function_calls 标签。"""
        core = get_toolify_core()
        xml = f"{core.trigger_signal}\n<function_calls></function_calls>"
        
        result = parse_tool_calls_xml(xml, core.trigger_signal)
        
        assert result is None or len(result) == 0
    
    def test_parse_tool_without_args(self):
        """测试没有参数的工具调用。"""
        core = get_toolify_core()
        xml = f"""{core.trigger_signal}
<function_calls>
    <function_call>
        <tool>test_tool</tool>
        <args></args>
    </function_call>
</function_calls>"""
        
        result = parse_tool_calls_xml(xml, core.trigger_signal)
        
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "test_tool"
        assert result[0]["args"] == {}


class TestConvertToOpenAIToolCalls:
    """测试转换为 OpenAI 格式。"""
    
    def test_convert_single_tool(self):
        """测试转换单个工具。"""
        parsed_tools = [
            {"name": "test_tool", "args": {"param": "value"}}
        ]
        
        result = convert_to_openai_tool_calls(parsed_tools)
        
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "test_tool"
        assert "id" in result[0]
    
    def test_convert_multiple_tools(self):
        """测试转换多个工具。"""
        parsed_tools = [
            {"name": "tool1", "args": {}},
            {"name": "tool2", "args": {}}
        ]
        
        result = convert_to_openai_tool_calls(parsed_tools)
        
        assert len(result) == 2
        assert result[0]["function"]["name"] == "tool1"
        assert result[1]["function"]["name"] == "tool2"
    
    def test_convert_empty_args(self):
        """测试转换空参数。"""
        parsed_tools = [
            {"name": "test_tool", "args": {}}
        ]
        
        result = convert_to_openai_tool_calls(parsed_tools)
        
        assert len(result) == 1
        assert result[0]["function"]["arguments"] == "{}"