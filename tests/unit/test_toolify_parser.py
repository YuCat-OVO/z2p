"""测试 Toolify XML 解析器模块。"""

import pytest
from src.z2p_svc.services.toolify.parser import (
    parse_tool_calls_xml,
    convert_to_openai_tool_calls
)


class TestParseToolCallsXml:
    """测试 XML 解析功能。"""
    
    def test_parse_single_tool_call(self):
        """测试解析单个工具调用。"""
        xml = """<tool_call>
<function_calls>
    <function_call>
        <tool>get_weather</tool>
        <args>
            <location>北京</location>
        </args>
    </function_call>
</function_calls>"""
        
        result = parse_tool_calls_xml(xml)
        
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "get_weather"
        assert result[0]["args"]["location"] == "北京"
    
    def test_parse_multiple_tool_calls(self):
        """测试解析多个工具调用。"""
        xml = """<tool_call>
<function_calls>
    <function_call>
        <tool>tool1</tool>
        <args>
            <param1>value1</param1>
        </args>
    </function_call>
    <function_call>
        <tool>tool2</tool>
        <args>
            <param2>value2</param2>
        </args>
    </function_call>
</function_calls>"""
        
        result = parse_tool_calls_xml(xml)
        
        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "tool1"
        assert result[1]["name"] == "tool2"
    
    def test_parse_with_json_args(self):
        """测试解析包含 JSON 参数的工具调用。"""
        xml = """<tool_call>
<function_calls>
    <function_call>
        <tool>search</tool>
        <args>
            <keywords>["Python", "测试"]</keywords>
            <limit>10</limit>
        </args>
    </function_call>
</function_calls>"""
        
        result = parse_tool_calls_xml(xml)
        
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["args"]["keywords"] == ["Python", "测试"]
        assert result[0]["args"]["limit"] == 10
    
    def test_parse_no_trigger_signal(self):
        """测试没有触发信号时返回 None。"""
        xml = "<function_calls></function_calls>"
        
        result = parse_tool_calls_xml(xml)
        
        assert result is None
    
    def test_parse_no_function_calls_tag(self):
        """测试没有 function_calls 标签时返回 None。"""
        xml = "<tool_call>some content"
        
        result = parse_tool_calls_xml(xml)
        
        assert result is None
    
    def test_parse_empty_function_calls(self):
        """测试空的 function_calls 标签。"""
        xml = "<tool_call><function_calls></function_calls>"
        
        result = parse_tool_calls_xml(xml)
        
        assert result is None
    
    def test_parse_tool_without_args(self):
        """测试没有参数的工具调用。"""
        xml = """<tool_call>
<function_calls>
    <function_call>
        <tool>no_args_tool</tool>
    </function_call>
</function_calls>"""
        
        result = parse_tool_calls_xml(xml)
        
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "no_args_tool"
        assert result[0]["args"] == {}


class TestConvertToOpenAIToolCalls:
    """测试转换为 OpenAI 格式。"""
    
    def test_convert_single_tool(self):
        """测试转换单个工具。"""
        parsed = [
            {"name": "get_weather", "args": {"location": "北京"}}
        ]
        
        result = convert_to_openai_tool_calls(parsed)
        
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "get_weather"
        assert '"location": "北京"' in result[0]["function"]["arguments"] or \
               '"location":"北京"' in result[0]["function"]["arguments"]
        assert "id" in result[0]
        assert result[0]["id"].startswith("call_")
    
    def test_convert_multiple_tools(self):
        """测试转换多个工具。"""
        parsed = [
            {"name": "tool1", "args": {"arg1": "val1"}},
            {"name": "tool2", "args": {"arg2": "val2"}}
        ]
        
        result = convert_to_openai_tool_calls(parsed)
        
        assert len(result) == 2
        assert result[0]["function"]["name"] == "tool1"
        assert result[1]["function"]["name"] == "tool2"
        # 确保每个工具调用有唯一的 ID
        assert result[0]["id"] != result[1]["id"]
    
    def test_convert_empty_args(self):
        """测试转换没有参数的工具。"""
        parsed = [
            {"name": "no_args", "args": {}}
        ]
        
        result = convert_to_openai_tool_calls(parsed)
        
        assert len(result) == 1
        assert result[0]["function"]["arguments"] == "{}"