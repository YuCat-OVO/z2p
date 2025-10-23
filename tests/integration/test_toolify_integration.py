"""Toolify 集成测试。

测试 Toolify 模块在实际场景中的集成工作。
"""

import pytest
from src.z2p_svc.models import ChatRequest, Message, Tool, ToolFunction


class TestToolifyIntegration:
    """测试 Toolify 完整流程的集成。"""
    
    def test_chat_request_with_tools(self):
        """测试带工具的聊天请求模型。"""
        tools = [
            Tool(
                type="function",
                function=ToolFunction(
                    name="get_weather",
                    description="获取天气信息",
                    parameters={
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "城市"}
                        },
                        "required": ["location"]
                    }
                )
            )
        ]
        
        request = ChatRequest(
            model="glm-4.6",
            messages=[Message(role="user", content="北京天气如何？")],
            tools=tools
        )
        
        assert request.tools is not None
        assert len(request.tools) == 1
        assert request.tools[0].function.name == "get_weather"
    
    def test_chat_request_without_tools(self):
        """测试不带工具的聊天请求。"""
        request = ChatRequest(
            model="glm-4.6",
            messages=[Message(role="user", content="你好")]
        )
        
        assert request.tools is None
    
    def test_message_with_tool_calls(self):
        """测试带工具调用的消息。"""
        message = Message(
            role="assistant",
            content=None,
            tool_calls=[{
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"location": "北京"}'
                }
            }]
        )
        
        assert message.tool_calls is not None
        assert len(message.tool_calls) == 1
        assert message.content is None
    
    def test_message_with_tool_result(self):
        """测试带工具结果的消息。"""
        message = Message(
            role="tool",
            content="北京今天晴天，温度20度",
            tool_call_id="call_123"
        )
        
        assert message.role == "tool"
        assert message.tool_call_id == "call_123"
        assert message.content is not None


class TestToolifyScenarios:
    """测试不同的 Toolify 使用场景。"""
    
    def test_scenario_no_tools_no_suffix(self):
        """场景1：无 tools，无后缀 - 正常聊天。"""
        request = ChatRequest(
            model="glm-4.6",
            messages=[Message(role="user", content="你好")]
        )
        
        # 应该不启用 toolify
        enable_toolify = request.tools is not None and len(request.tools) > 0
        assert enable_toolify is False
    
    def test_scenario_no_tools_with_search_suffix(self):
        """场景2：无 tools，有 -search 后缀 - MCP 搜索功能。"""
        request = ChatRequest(
            model="glm-4.6-search",
            messages=[Message(role="user", content="最新新闻")]
        )
        
        # 应该不启用 toolify，但模型后缀会启用 MCP 搜索
        enable_toolify = request.tools is not None and len(request.tools) > 0
        assert enable_toolify is False
        assert "-search" in request.model
    
    def test_scenario_with_tools_no_suffix(self):
        """场景3：有 tools，无后缀 - Toolify 工具调用。"""
        tools = [
            Tool(
                type="function",
                function=ToolFunction(
                    name="calculator",
                    description="计算器",
                    parameters={"type": "object", "properties": {}}
                )
            )
        ]
        
        request = ChatRequest(
            model="glm-4.6",
            messages=[Message(role="user", content="1+1等于多少？")],
            tools=tools
        )
        
        # 应该启用 toolify
        enable_toolify = request.tools is not None and len(request.tools) > 0
        assert enable_toolify is True
    
    def test_scenario_with_tools_and_search_suffix(self):
        """场景4：有 tools，有 -search 后缀 - MCP + Toolify 同时工作。"""
        tools = [
            Tool(
                type="function",
                function=ToolFunction(
                    name="calculator",
                    description="计算器",
                    parameters={"type": "object", "properties": {}}
                )
            )
        ]
        
        request = ChatRequest(
            model="glm-4.6-search",
            messages=[Message(role="user", content="搜索并计算")],
            tools=tools
        )
        
        # 应该同时启用 toolify 和 MCP 搜索
        enable_toolify = request.tools is not None and len(request.tools) > 0
        assert enable_toolify is True
        assert "-search" in request.model


class TestToolifyEdgeCases:
    """测试 Toolify 的边缘情况。"""
    
    def test_empty_tools_list(self):
        """测试空的工具列表。"""
        request = ChatRequest(
            model="glm-4.6",
            messages=[Message(role="user", content="你好")],
            tools=[]
        )
        
        # 空列表应该不启用 toolify
        enable_toolify = request.tools is not None and len(request.tools) > 0
        assert enable_toolify is False
    
    def test_tool_with_complex_parameters(self):
        """测试复杂参数的工具。"""
        tool = Tool(
            type="function",
            function=ToolFunction(
                name="complex_tool",
                description="复杂工具",
                parameters={
                    "type": "object",
                    "properties": {
                        "nested": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"}
                            }
                        },
                        "array": {
                            "type": "array",
                            "items": {"type": "number"}
                        }
                    },
                    "required": ["nested"]
                }
            )
        )
        
        request = ChatRequest(
            model="glm-4.6",
            messages=[Message(role="user", content="测试")],
            tools=[tool]
        )
        
        assert request.tools is not None
        assert request.tools[0].function.parameters["properties"]["nested"]["type"] == "object"
        assert request.tools[0].function.parameters["properties"]["array"]["type"] == "array"
    
    def test_tool_choice_parameter(self):
        """测试 tool_choice 参数。"""
        tools = [
            Tool(
                type="function",
                function=ToolFunction(
                    name="tool1",
                    description="工具1",
                    parameters={"type": "object", "properties": {}}
                )
            )
        ]
        
        # 测试字符串形式的 tool_choice
        request1 = ChatRequest(
            model="glm-4.6",
            messages=[Message(role="user", content="测试")],
            tools=tools,
            tool_choice="auto"
        )
        assert request1.tool_choice == "auto"
        
        # 测试字典形式的 tool_choice
        request2 = ChatRequest(
            model="glm-4.6",
            messages=[Message(role="user", content="测试")],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "tool1"}}
        )
        assert isinstance(request2.tool_choice, dict)