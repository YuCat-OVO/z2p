"""测试 Toolify 流式检测器模块。"""

import pytest
from src.z2p_svc.services.toolify.detector import StreamingToolCallDetector


class TestStreamingToolCallDetector:
    """测试流式工具调用检测器。"""
    
    def test_detect_simple_tool_call(self):
        """测试检测简单的工具调用。"""
        detector = StreamingToolCallDetector()
        
        # 模拟流式输入
        chunks = [
            "这是一些文本 ",
            "<tool_call>",
            "<function_calls>",
            "<function_call>",
            "<tool>test</tool>",
            "<args><param>value</param></args>",
            "</function_call>",
            "</function_calls>"
        ]
        
        outputs = []
        for chunk in chunks:
            is_tool, output = detector.process_chunk(chunk)
            if output:
                outputs.append(output)
        
        # 应该输出触发信号之前的内容
        assert "这是一些文本 " in "".join(outputs)
        
        # Finalize 应该返回解析的工具
        parsed, remaining = detector.finalize()
        assert parsed is not None
        assert len(parsed) == 1
        assert parsed[0]["name"] == "test"
    
    def test_no_tool_call(self):
        """测试没有工具调用的情况。"""
        detector = StreamingToolCallDetector()
        
        chunks = ["这是", "普通", "文本"]
        
        outputs = []
        for chunk in chunks:
            is_tool, output = detector.process_chunk(chunk)
            if output:
                outputs.append(output)
        
        parsed, remaining = detector.finalize()
        
        assert parsed is None
        # 所有内容应该被输出或在 remaining 中
        total_output = "".join(outputs) + remaining
        assert "这是普通文本" in total_output
    
    def test_think_tag_handling(self):
        """测试 <think> 标签处理。"""
        detector = StreamingToolCallDetector()
        
        # <think> 标签内的触发信号应该被忽略
        chunks = [
            "文本 ",
            "<think>",
            "思考中 <tool_call> 这不是真的工具调用",
            "</think>",
            " 继续文本"
        ]
        
        outputs = []
        for chunk in chunks:
            is_tool, output = detector.process_chunk(chunk)
            if output:
                outputs.append(output)
        
        parsed, remaining = detector.finalize()
        
        # 不应该检测到工具调用
        assert parsed is None
    
    def test_multiple_chunks_trigger_signal(self):
        """测试触发信号跨多个块的情况。"""
        detector = StreamingToolCallDetector()
        
        # 触发信号被分割
        chunks = [
            "文本 <tool",
            "_call><function_calls>",
            "<function_call><tool>test</tool></function_call>",
            "</function_calls>"
        ]
        
        for chunk in chunks:
            detector.process_chunk(chunk)
        
        parsed, remaining = detector.finalize()
        
        assert parsed is not None
        assert len(parsed) == 1
    
    def test_empty_chunk(self):
        """测试空块处理。"""
        detector = StreamingToolCallDetector()
        
        is_tool, output = detector.process_chunk("")
        
        assert is_tool is False
        assert output == ""
    
    def test_finalize_without_complete_xml(self):
        """测试不完整的 XML。"""
        detector = StreamingToolCallDetector()
        
        chunks = [
            "<tool_call>",
            "<function_calls>",
            "<function_call>"  # 不完整
        ]
        
        for chunk in chunks:
            detector.process_chunk(chunk)
        
        parsed, remaining = detector.finalize()
        
        # 应该返回 None 和缓冲的内容
        assert parsed is None
        assert remaining != ""
    
    def test_nested_think_tags(self):
        """测试嵌套的 <think> 标签。"""
        detector = StreamingToolCallDetector()
        
        chunks = [
            "<think>",
            "外层 <think>内层</think> 外层",
            "</think>",
            " <tool_call><function_calls></function_calls>"
        ]
        
        for chunk in chunks:
            detector.process_chunk(chunk)
        
        parsed, remaining = detector.finalize()
        
        # 嵌套 think 标签后的工具调用应该被检测
        # 但由于 function_calls 是空的，应该返回 None
        assert parsed is None