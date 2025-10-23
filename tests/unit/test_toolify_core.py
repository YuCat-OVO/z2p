"""Toolify Core 模块单元测试。"""

import json
import pytest

from src.z2p_svc.services.toolify.core import (
    ToolCallMappingManager,
    ToolifyCore,
    generate_random_trigger_signal,
    get_toolify_core,
)


@pytest.mark.unit
class TestGenerateRandomTriggerSignal:
    """测试随机触发信号生成。"""

    def test_signal_format(self):
        """测试信号格式正确。"""
        signal = generate_random_trigger_signal()
        assert signal.startswith("<Function_")
        assert signal.endswith("_Start/>")
        assert len(signal) == len("<Function_XXXX_Start/>")

    def test_signal_uniqueness(self):
        """测试生成的信号是唯一的。"""
        signals = [generate_random_trigger_signal() for _ in range(100)]
        assert len(set(signals)) > 90  # 至少90%是唯一的


@pytest.mark.unit
class TestToolCallMappingManager:
    """测试工具调用映射管理器。"""

    def test_store_and_get(self):
        """测试存储和获取映射。"""
        manager = ToolCallMappingManager()
        manager.store("call_123", "search", {"query": "test"})
        
        result = manager.get("call_123")
        assert result is not None
        assert result["name"] == "search"
        assert result["args"] == {"query": "test"}

    def test_get_nonexistent(self):
        """测试获取不存在的映射。"""
        manager = ToolCallMappingManager()
        result = manager.get("nonexistent")
        assert result is None

    def test_update_existing(self):
        """测试更新已存在的映射。"""
        manager = ToolCallMappingManager()
        manager.store("call_123", "search", {"query": "old"})
        manager.store("call_123", "search", {"query": "new"})
        
        result = manager.get("call_123")
        assert result["args"] == {"query": "new"}

    def test_max_size_limit(self):
        """测试大小限制。"""
        manager = ToolCallMappingManager(max_size=3)
        
        manager.store("call_1", "tool1", {})
        manager.store("call_2", "tool2", {})
        manager.store("call_3", "tool3", {})
        manager.store("call_4", "tool4", {})
        
        # 最旧的应该被移除
        assert manager.get("call_1") is None
        assert manager.get("call_4") is not None

    def test_lru_behavior(self):
        """测试LRU行为。"""
        manager = ToolCallMappingManager(max_size=3)
        
        manager.store("call_1", "tool1", {})
        manager.store("call_2", "tool2", {})
        manager.store("call_3", "tool3", {})
        
        # 访问call_1，使其成为最近使用
        manager.get("call_1")
        
        # 添加新条目，call_2应该被移除
        manager.store("call_4", "tool4", {})
        
        assert manager.get("call_1") is not None
        assert manager.get("call_2") is None
        assert manager.get("call_4") is not None


@pytest.mark.unit
class TestToolifyCore:
    """测试 Toolify 核心类。"""

    def test_initialization(self):
        """测试初始化。"""
        core = ToolifyCore()
        assert core.mapping_manager is not None
        assert core.trigger_signal.startswith("<Function_")

    def test_store_and_get_mapping(self):
        """测试存储和获取工具调用映射。"""
        core = ToolifyCore()
        core.store_tool_call_mapping("call_123", "search", {"query": "test"})
        
        result = core.get_tool_call_mapping("call_123")
        assert result is not None
        assert result["name"] == "search"

    def test_format_tool_result_with_mapping(self):
        """测试格式化工具结果（有映射）。"""
        core = ToolifyCore()
        core.store_tool_call_mapping("call_123", "search", {"query": "test"})
        
        formatted = core.format_tool_result_for_ai("call_123", "result content")
        assert "Tool execution result:" in formatted
        assert "Tool name: search" in formatted
        assert "<tool_result>" in formatted
        assert "result content" in formatted

    def test_format_tool_result_without_mapping(self):
        """测试格式化工具结果（无映射）。"""
        core = ToolifyCore()
        formatted = core.format_tool_result_for_ai("unknown", "result content")
        assert "Tool execution result:" in formatted
        assert "<tool_result>" in formatted
        assert "result content" in formatted

    def test_format_assistant_tool_calls(self):
        """测试格式化助手工具调用。"""
        core = ToolifyCore()
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "search",
                    "arguments": json.dumps({"query": "test"})
                }
            }
        ]
        
        formatted = core.format_assistant_tool_calls_for_ai(tool_calls)
        assert core.trigger_signal in formatted
        assert "<function_calls>" in formatted
        assert "<function_call>" in formatted
        assert "<tool>search</tool>" in formatted
        assert "<query>" in formatted

    def test_preprocess_tool_message(self):
        """测试预处理 tool 角色消息。"""
        core = ToolifyCore()
        core.store_tool_call_mapping("call_123", "search", {})
        
        messages = [
            {"role": "tool", "tool_call_id": "call_123", "content": "result"}
        ]
        
        processed = core.preprocess_messages(messages)
        assert len(processed) == 1
        assert processed[0]["role"] == "user"
        assert "Tool execution result:" in processed[0]["content"]

    def test_preprocess_assistant_with_tool_calls(self):
        """测试预处理带 tool_calls 的 assistant 消息。"""
        core = ToolifyCore()
        messages = [
            {
                "role": "assistant",
                "content": "Let me search",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search", "arguments": "{}"}
                    }
                ]
            }
        ]
        
        processed = core.preprocess_messages(messages)
        assert len(processed) == 1
        assert processed[0]["role"] == "assistant"
        assert "Let me search" in processed[0]["content"]
        assert core.trigger_signal in processed[0]["content"]
        assert "tool_calls" not in processed[0]

    def test_preprocess_regular_messages(self):
        """测试预处理普通消息。"""
        core = ToolifyCore()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ]
        
        processed = core.preprocess_messages(messages)
        assert processed == messages

    def test_convert_parsed_tools_to_openai_format(self):
        """测试转换解析的工具为 OpenAI 格式。"""
        core = ToolifyCore()
        parsed_tools = [
            {"name": "search", "args": {"query": "test"}},
            {"name": "calculator", "args": {"expr": "1+1"}}
        ]
        
        tool_calls = core.convert_parsed_tools_to_openai_format(parsed_tools)
        assert len(tool_calls) == 2
        assert tool_calls[0]["type"] == "function"
        assert tool_calls[0]["function"]["name"] == "search"
        assert "call_" in tool_calls[0]["id"]
        
        # 验证映射已存储
        result = core.get_tool_call_mapping(tool_calls[0]["id"])
        assert result is not None
        assert result["name"] == "search"


@pytest.mark.unit
class TestGetToolifyCore:
    """测试获取 Toolify 核心单例。"""

    def test_singleton(self):
        """测试单例模式。"""
        core1 = get_toolify_core()
        core2 = get_toolify_core()
        assert core1 is core2

    def test_returns_toolify_core(self):
        """测试返回 ToolifyCore 实例。"""
        core = get_toolify_core()
        assert isinstance(core, ToolifyCore)