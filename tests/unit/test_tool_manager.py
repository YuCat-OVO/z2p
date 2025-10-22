"""工具调用管理器单元测试。

测试工具调用映射管理和消息预处理功能。
"""

import pytest
import time

from src.z2p_svc.services.chat.tool_manager import (
    ToolCallMappingManager,
    get_mapping_manager,
    format_tool_result_for_ai,
    preprocess_messages,
    format_assistant_tool_calls,
)


@pytest.mark.unit
class TestToolCallMappingManager:
    """ToolCallMappingManager 类测试。"""

    def test_store_and_get(self):
        """测试存储和获取工具调用映射。"""
        manager = ToolCallMappingManager()

        manager.store("tool_123", "search", {"query": "test"})
        result = manager.get("tool_123")

        assert result is not None
        assert result["name"] == "search"
        assert result["args"] == {"query": "test"}
        assert "created_at" in result

    def test_get_nonexistent(self):
        """测试获取不存在的映射。"""
        manager = ToolCallMappingManager()

        result = manager.get("nonexistent")

        assert result is None

    def test_update_existing(self):
        """测试更新已存在的映射。"""
        manager = ToolCallMappingManager()

        manager.store("tool_123", "search", {"query": "test1"})
        manager.store("tool_123", "search", {"query": "test2"})

        result = manager.get("tool_123")
        assert result is not None
        assert result["args"] == {"query": "test2"}

    def test_max_size_limit(self):
        """测试最大容量限制。"""
        manager = ToolCallMappingManager(max_size=3)

        manager.store("tool_1", "func1", {})
        manager.store("tool_2", "func2", {})
        manager.store("tool_3", "func3", {})
        manager.store("tool_4", "func4", {})

        # 最旧的应该被删除
        assert manager.get("tool_1") is None
        assert manager.get("tool_4") is not None

    def test_ttl_expiration(self):
        """测试TTL过期。"""
        manager = ToolCallMappingManager(ttl_seconds=1)

        manager.store("tool_123", "search", {"query": "test"})

        # 立即获取应该成功
        assert manager.get("tool_123") is not None

        # 等待过期
        time.sleep(1.1)

        # 过期后应该返回None
        assert manager.get("tool_123") is None

    def test_cleanup_expired(self):
        """测试清理过期条目。"""
        manager = ToolCallMappingManager(ttl_seconds=1)

        manager.store("tool_1", "func1", {})
        manager.store("tool_2", "func2", {})

        time.sleep(1.1)

        count = manager.cleanup_expired()

        assert count == 2
        assert manager.get("tool_1") is None
        assert manager.get("tool_2") is None

    def test_lru_ordering(self):
        """测试LRU顺序更新。"""
        manager = ToolCallMappingManager(max_size=3)

        manager.store("tool_1", "func1", {})
        manager.store("tool_2", "func2", {})
        manager.store("tool_3", "func3", {})

        # 访问tool_1，使其成为最近使用
        manager.get("tool_1")

        # 添加新条目，tool_2应该被删除（最少使用）
        manager.store("tool_4", "func4", {})

        assert manager.get("tool_1") is not None
        assert manager.get("tool_2") is None
        assert manager.get("tool_3") is not None
        assert manager.get("tool_4") is not None


@pytest.mark.unit
class TestGlobalMappingManager:
    """全局映射管理器测试。"""

    def test_singleton_pattern(self):
        """测试单例模式。"""
        manager1 = get_mapping_manager()
        manager2 = get_mapping_manager()

        assert manager1 is manager2


@pytest.mark.unit
class TestFormatToolResultForAI:
    """format_tool_result_for_ai 函数测试。"""

    def test_with_mapping(self):
        """测试有映射信息的格式化。"""
        manager = get_mapping_manager()
        manager.store("tool_123", "search", {"query": "test"})

        result = format_tool_result_for_ai("tool_123", "搜索结果")

        assert "Tool execution result:" in result
        assert "Tool name: search" in result
        assert "搜索结果" in result
        assert "<tool_result>" in result

    def test_without_mapping(self):
        """测试没有映射信息的格式化。"""
        result = format_tool_result_for_ai("nonexistent", "结果内容")

        assert "Tool execution result:" in result
        assert "结果内容" in result
        assert "<tool_result>" in result
        # 不应该包含工具名称
        assert "Tool name:" not in result


@pytest.mark.unit
class TestPreprocessMessages:
    """preprocess_messages 函数测试。"""

    def test_convert_tool_role_to_user(self):
        """测试将tool角色转换为user角色。"""
        manager = get_mapping_manager()
        manager.store("tool_123", "search", {"query": "test"})

        messages = [{"role": "tool", "tool_call_id": "tool_123", "content": "搜索结果"}]

        result = preprocess_messages(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "Tool name: search" in result[0]["content"]
        assert "搜索结果" in result[0]["content"]

    def test_convert_assistant_tool_calls(self):
        """测试转换assistant的tool_calls。"""
        messages = [
            {
                "role": "assistant",
                "content": "我将调用工具",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": '{"query": "test"}',
                        },
                    }
                ],
            }
        ]

        result = preprocess_messages(messages)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert "我将调用工具" in result[0]["content"]
        assert "Tool Call: search" in result[0]["content"]
        assert "call_123" in result[0]["content"]
        assert "tool_calls" not in result[0]

    def test_preserve_other_messages(self):
        """测试保留其他类型的消息。"""
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
            {"role": "system", "content": "系统提示"},
        ]

        result = preprocess_messages(messages)

        assert len(result) == 3
        assert result[0] == messages[0]
        assert result[1] == messages[1]
        assert result[2] == messages[2]

    def test_empty_messages(self):
        """测试空消息列表。"""
        result = preprocess_messages([])

        assert result == []

    def test_tool_message_without_mapping(self):
        """测试没有映射的tool消息。"""
        messages = [{"role": "tool", "tool_call_id": "unknown", "content": "结果"}]

        result = preprocess_messages(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "结果" in result[0]["content"]


@pytest.mark.unit
class TestFormatAssistantToolCalls:
    """format_assistant_tool_calls 函数测试。"""

    def test_single_tool_call(self):
        """测试单个工具调用格式化。"""
        tool_calls = [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "search", "arguments": '{"query": "test"}'},
            }
        ]

        result = format_assistant_tool_calls(tool_calls)

        assert "Tool Call: search" in result
        assert "call_123" in result
        assert "query" in result
        assert "test" in result

    def test_multiple_tool_calls(self):
        """测试多个工具调用格式化。"""
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "search", "arguments": '{"query": "test1"}'},
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "calculator", "arguments": '{"expr": "1+1"}'},
            },
        ]

        result = format_assistant_tool_calls(tool_calls)

        assert "Tool Call: search" in result
        assert "Tool Call: calculator" in result
        assert "call_1" in result
        assert "call_2" in result

    def test_invalid_json_arguments(self):
        """测试无效JSON参数。"""
        tool_calls = [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "test", "arguments": "invalid json"},
            }
        ]
        
        result = format_assistant_tool_calls(tool_calls)
        
        assert "Tool Call: test" in result
        assert "call_123" in result
        # 应该包含原始参数
        assert "raw_arguments" in result