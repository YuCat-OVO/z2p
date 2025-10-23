"""测试 Toolify 提示词生成模块。"""

import pytest
from src.z2p_svc.services.toolify.prompt import (
    generate_tools_prompt,
    inject_tool_prompt,
    TRIGGER_SIGNAL
)


class TestGenerateToolsPrompt:
    """测试工具提示词生成。"""
    
    def test_generate_single_tool(self):
        """测试生成单个工具的提示词。"""
        tools = [{
            "function": {
                "name": "get_weather",
                "description": "获取天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "城市名称"
                        }
                    },
                    "required": ["location"]
                }
            }
        }]
        
        result = generate_tools_prompt(tools)
        
        assert "get_weather" in result
        assert "获取天气信息" in result
        assert "location" in result
        assert "城市名称" in result
    
    def test_generate_multiple_tools(self):
        """测试生成多个工具的提示词。"""
        tools = [
            {
                "function": {
                    "name": "tool1",
                    "description": "工具1",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "function": {
                    "name": "tool2",
                    "description": "工具2",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        
        result = generate_tools_prompt(tools)
        
        assert "tool1" in result
        assert "tool2" in result
        assert "工具1" in result
        assert "工具2" in result
    
    def test_empty_tools(self):
        """测试空工具列表。"""
        result = generate_tools_prompt([])
        assert result == ""


class TestInjectToolPrompt:
    """测试工具提示词注入。"""
    
    def test_inject_to_empty_messages(self):
        """测试注入到空消息列表。"""
        messages = []
        tools = [{
            "function": {
                "name": "test_tool",
                "description": "测试工具",
                "parameters": {"type": "object", "properties": {}}
            }
        }]
        
        result = inject_tool_prompt(messages, tools)
        
        assert len(result) == 1
        assert result[0]["role"] == "system"
        assert "test_tool" in result[0]["content"]
        assert TRIGGER_SIGNAL in result[0]["content"]
    
    def test_inject_to_existing_system_message(self):
        """测试注入到已有 system 消息。"""
        messages = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "你好"}
        ]
        tools = [{
            "function": {
                "name": "test_tool",
                "description": "测试工具",
                "parameters": {"type": "object", "properties": {}}
            }
        }]
        
        result = inject_tool_prompt(messages, tools)
        
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert "你是一个助手" in result[0]["content"]
        assert "test_tool" in result[0]["content"]
    
    def test_inject_to_user_messages(self):
        """测试注入到用户消息列表。"""
        messages = [
            {"role": "user", "content": "你好"}
        ]
        tools = [{
            "function": {
                "name": "test_tool",
                "description": "测试工具",
                "parameters": {"type": "object", "properties": {}}
            }
        }]
        
        result = inject_tool_prompt(messages, tools)
        
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
    
    def test_no_injection_without_tools(self):
        """测试没有工具时不注入。"""
        messages = [{"role": "user", "content": "你好"}]
        
        result = inject_tool_prompt(messages, [])
        
        assert result == messages