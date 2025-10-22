"""消息转换器单元测试。

测试消息格式转换功能。
"""

import pytest

from src.z2p_svc.models import Message
from src.z2p_svc.services.chat.converter import convert_messages


@pytest.mark.unit
class TestConvertMessages:
    """convert_messages 函数测试。"""
    
    def test_simple_text_message(self):
        """测试简单文本消息转换。"""
        messages = [
            Message(role="user", content="你好")
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "user"
        assert result.messages[0]["content"] == "你好"
        assert result.last_user_message_text == "你好"
        assert result.file_urls == []
    
    def test_multiple_text_messages(self):
        """测试多条文本消息。"""
        messages = [
            Message(role="system", content="你是助手"),
            Message(role="user", content="第一条消息"),
            Message(role="assistant", content="回复"),
            Message(role="user", content="第二条消息")
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 4
        assert result.last_user_message_text == "第二条消息"
        assert result.file_urls == []
    
    def test_image_url_extraction(self):
        """测试图片URL提取。"""
        messages = [
            Message(role="user", content=[
                {"type": "text", "text": "看这张图"},
                {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        assert result.messages[0]["content"] == "看这张图"
        assert result.last_user_message_text == "看这张图"
        assert len(result.file_urls) == 1
        assert result.file_urls[0] == "https://example.com/image.png"
    
    def test_base64_image_extraction(self):
        """测试Base64图片提取。"""
        base64_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        
        messages = [
            Message(role="user", content=[
                {"type": "text", "text": "分析图片"},
                {"type": "image_url", "image_url": {"url": base64_url}}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.file_urls) == 1
        assert result.file_urls[0] == base64_url
        assert result.last_user_message_text == "分析图片"
    
    def test_file_url_extraction(self):
        """测试文件URL提取。"""
        messages = [
            Message(role="user", content=[
                {"type": "text", "text": "查看文件"},
                {"type": "file", "url": "https://example.com/document.pdf"}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.file_urls) == 1
        assert result.file_urls[0] == "https://example.com/document.pdf"
    
    def test_multiple_files(self):
        """测试多个文件。"""
        messages = [
            Message(role="user", content=[
                {"type": "text", "text": "多个文件"},
                {"type": "image_url", "image_url": {"url": "https://example.com/img1.png"}},
                {"type": "image_url", "image_url": {"url": "https://example.com/img2.jpg"}},
                {"type": "file", "url": "https://example.com/doc.pdf"}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.file_urls) == 3
        assert "img1.png" in result.file_urls[0]
        assert "img2.jpg" in result.file_urls[1]
        assert "doc.pdf" in result.file_urls[2]
    
    def test_tool_use_conversion(self):
        """测试工具调用转换。"""
        messages = [
            Message(role="assistant", content=[
                {"type": "tool_use", "id": "tool_123", "name": "search", "input": {"query": "test"}}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        assert "tool_calls" in result.messages[0]
        assert len(result.messages[0]["tool_calls"]) == 1
        assert result.messages[0]["tool_calls"][0]["id"] == "tool_123"
        assert result.messages[0]["tool_calls"][0]["function"]["name"] == "search"
    
    def test_tool_result_conversion(self):
        """测试工具结果转换。"""
        messages = [
            Message(role="user", content=[
                {"type": "tool_result", "tool_use_id": "tool_123", "content": "搜索结果"}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "tool"
        assert result.messages[0]["tool_call_id"] == "tool_123"
        assert result.messages[0]["content"] == "搜索结果"
    
    def test_tool_result_with_list_content(self):
        """测试工具结果包含列表内容。"""
        messages = [
            Message(role="user", content=[
                {
                    "type": "tool_result",
                    "tool_use_id": "tool_456",
                    "content": [
                        {"type": "text", "text": "结果1"},
                        {"type": "text", "text": "结果2"}
                    ]
                }
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        assert result.messages[0]["content"] == "结果1结果2"
    
    def test_empty_messages(self):
        """测试空消息列表。"""
        messages = []
        
        result = convert_messages(messages)
        
        assert result.messages == []
        assert result.file_urls == []
        assert result.last_user_message_text == ""
    
    def test_message_without_text(self):
        """测试没有文本的消息。"""
        messages = [
            Message(role="user", content=[
                {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}}
            ])
        ]
        
        result = convert_messages(messages)
        
        # 没有文本内容，但有文件
        assert len(result.file_urls) == 1
        assert result.last_user_message_text == ""
    
    def test_mixed_content_types(self):
        """测试混合内容类型。"""
        messages = [
            Message(role="user", content=[
                {"type": "text", "text": "分析这些"},
                {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
                {"type": "file", "url": "https://example.com/doc.pdf"}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert result.messages[0]["content"] == "分析这些"
        assert len(result.file_urls) == 2
        assert result.last_user_message_text == "分析这些"
    
    def test_assistant_message_with_text(self):
        """测试助手消息。"""
        messages = [
            Message(role="assistant", content="我是助手的回复")
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "assistant"
        assert result.messages[0]["content"] == "我是助手的回复"
        # 助手消息不更新 last_user_message_text
        assert result.last_user_message_text == ""
    
    def test_system_message(self):
        """测试系统消息。"""
        messages = [
            Message(role="system", content="系统提示")
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "system"
        assert result.messages[0]["content"] == "系统提示"
    
    def test_empty_image_url(self):
        """测试空图片URL。"""
        messages = [
            Message(role="user", content=[
                {"type": "text", "text": "测试"},
                {"type": "image_url", "image_url": {"url": ""}}
            ])
        ]
        
        result = convert_messages(messages)
        
        # 空URL不应该被添加
        assert len(result.file_urls) == 0
    
    def test_missing_image_url_field(self):
        """测试缺少URL字段。"""
        messages = [
            Message(role="user", content=[
                {"type": "text", "text": "测试"},
                {"type": "image_url", "image_url": {}}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.file_urls) == 0
    
    def test_tool_use_with_empty_input(self):
        """测试工具调用包含空输入。"""
        messages = [
            Message(role="assistant", content=[
                {"type": "tool_use", "id": "tool_789", "name": "calculator", "input": {}}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        assert "tool_calls" in result.messages[0]
        # 空输入应该被序列化为 "{}"
        assert result.messages[0]["tool_calls"][0]["function"]["arguments"] == "{}"
    
    def test_tool_use_with_none_input(self):
        """测试工具调用包含None输入。"""
        messages = [
            Message(role="assistant", content=[
                {"type": "tool_use", "id": "tool_999", "name": "test", "input": None}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        # None 应该被转换为空字典
        assert result.messages[0]["tool_calls"][0]["function"]["arguments"] == "{}"
    
    def test_unicode_content(self):
        """测试Unicode内容。"""
        messages = [
            Message(role="user", content="你好世界 🌍 emoji测试")
        ]
        
        result = convert_messages(messages)
        
        assert result.messages[0]["content"] == "你好世界 🌍 emoji测试"
        assert result.last_user_message_text == "你好世界 🌍 emoji测试"
    
    def test_long_message(self):
        """测试长消息。"""
        long_text = "测试" * 1000
        messages = [
            Message(role="user", content=long_text)
        ]
        
        result = convert_messages(messages)
        
        assert result.messages[0]["content"] == long_text
        assert result.last_user_message_text == long_text
    
    def test_special_characters(self):
        """测试特殊字符。"""
        special_text = "测试\n换行\t制表符\"引号'单引号\\反斜杠"
        messages = [
            Message(role="user", content=special_text)
        ]
        
        result = convert_messages(messages)
        
        assert result.messages[0]["content"] == special_text
    
    def test_tool_result_empty_content_list(self):
        """测试工具结果包含空内容列表。"""
        messages = [
            Message(role="user", content=[
                {"type": "tool_result", "tool_use_id": "tool_empty", "content": []}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        assert result.messages[0]["content"] == ""
    
    def test_multiple_tool_calls(self):
        """测试多个工具调用。"""
        messages = [
            Message(role="assistant", content=[
                {"type": "tool_use", "id": "tool_1", "name": "search", "input": {"q": "test1"}},
                {"type": "tool_use", "id": "tool_2", "name": "calculator", "input": {"expr": "1+1"}}
            ])
        ]
        
        result = convert_messages(messages)
        
        assert len(result.messages) == 1
        assert len(result.messages[0]["tool_calls"]) == 2
        assert result.messages[0]["tool_calls"][0]["id"] == "tool_1"
        assert result.messages[0]["tool_calls"][1]["id"] == "tool_2"