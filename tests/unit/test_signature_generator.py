"""签名生成器单元测试。

测试签名生成功能。
"""

import pytest
from unittest.mock import patch
import time

from src.z2p_svc.signature_generator import generate_signature


@pytest.mark.unit
class TestGenerateSignature:
    """generate_signature 函数测试。"""

    def test_basic_signature_generation(self):
        """测试基本签名生成。"""
        request_params = "requestId,test123,timestamp,1234567890,user_id,user001"
        content = "测试内容"

        with patch("time.time", return_value=1234567890.123):
            result = generate_signature(request_params, content)

        assert "signature" in result
        assert "timestamp" in result
        assert isinstance(result["signature"], str)
        assert isinstance(result["timestamp"], str)  # 时间戳返回字符串
        assert len(result["signature"]) > 0
        assert result["timestamp"] == "1234567890123"

    def test_signature_consistency(self):
        """测试相同输入产生相同签名。"""
        request_params = "requestId,test123,timestamp,1234567890,user_id,user001"
        content = "测试内容"

        with patch("time.time", return_value=1234567890.123):
            result1 = generate_signature(request_params, content)
            result2 = generate_signature(request_params, content)

        assert result1["signature"] == result2["signature"]
        assert result1["timestamp"] == result2["timestamp"]

    def test_different_params_different_signature(self):
        """测试不同参数产生不同签名。"""
        content = "测试内容"

        with patch("time.time", return_value=1234567890.123):
            result1 = generate_signature(
                "requestId,test1,timestamp,123,user_id,user1", content
            )
            result2 = generate_signature(
                "requestId,test2,timestamp,456,user_id,user2", content
            )

        assert result1["signature"] != result2["signature"]

    def test_different_content_different_signature(self):
        """测试不同内容产生不同签名。"""
        request_params = "requestId,test123,timestamp,1234567890,user_id,user001"

        with patch("time.time", return_value=1234567890.123):
            result1 = generate_signature(request_params, "内容1")
            result2 = generate_signature(request_params, "内容2")

        assert result1["signature"] != result2["signature"]

    def test_empty_content(self):
        """测试空内容。"""
        request_params = "requestId,test123,timestamp,1234567890,user_id,user001"

        with patch("time.time", return_value=1234567890.123):
            result = generate_signature(request_params, "")

        assert "signature" in result
        assert len(result["signature"]) > 0

    def test_timestamp_format(self):
        """测试时间戳格式。"""
        request_params = "requestId,test123,timestamp,1234567890,user_id,user001"
        content = "测试"

        with patch("time.time", return_value=1234567890.123456):
            result = generate_signature(request_params, content)

        # 时间戳应该是毫秒级字符串
        assert isinstance(result["timestamp"], str)
        assert result["timestamp"] == "1234567890123"

    def test_unicode_content(self):
        """测试Unicode内容。"""
        request_params = "requestId,test123,timestamp,1234567890,user_id,user001"
        content = "测试内容 🎉 emoji"

        with patch("time.time", return_value=1234567890.123):
            result = generate_signature(request_params, content)

        assert "signature" in result
        assert len(result["signature"]) > 0

    def test_long_content(self):
        """测试长内容。"""
        request_params = "requestId,test123,timestamp,1234567890,user_id,user001"
        content = "测试" * 1000  # 4000字符

        with patch("time.time", return_value=1234567890.123):
            result = generate_signature(request_params, content)

        assert "signature" in result
        assert len(result["signature"]) > 0

    def test_special_characters_in_params(self):
        """测试参数中的特殊字符。"""
        request_params = "requestId,test-123_abc,timestamp,1234567890,user_id,user@001"
        content = "测试"

        with patch("time.time", return_value=1234567890.123):
            result = generate_signature(request_params, content)
        
        assert "signature" in result
        assert len(result["signature"]) > 0