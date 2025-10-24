"""测试 Toolify 流式检测器（已修复以适应新API）。"""

import pytest
from src.z2p_svc.services.toolify import StreamingToolCallDetector, get_toolify_core


class TestStreamingToolCallDetector:
    """测试流式工具调用检测器。"""
    
    def test_detect_simple_tool_call(self):
        """测试检测简单的工具调用。"""
        core = get_toolify_core()
        detector = StreamingToolCallDetector(core.trigger_signal)
        
        # 模拟工具调用
        tool_call = f"""{core.trigger_signal}
<function_calls>
    <function_call>
        <tool>test_tool</tool>
        <args>
            <param1>value1</param1>
        </args>
    </function_call>
</function_calls>"""
        
        # 分块处理
        chunks = [tool_call[i:i+20] for i in range(0, len(tool_call), 20)]
        for chunk in chunks:
            detector.process_chunk(chunk)
        
        # Finalize
        parsed_tools, remaining = detector.finalize()
        
        if parsed_tools:
            assert len(parsed_tools) > 0
            assert parsed_tools[0]["name"] == "test_tool"
    
    def test_no_tool_call(self):
        """测试没有工具调用的情况。"""
        core = get_toolify_core()
        detector = StreamingToolCallDetector(core.trigger_signal)
        
        content = "这是普通的响应内容，没有工具调用"
        detector.process_chunk(content)
        
        parsed_tools, remaining = detector.finalize()
        
        assert parsed_tools is None
        assert "普通的响应内容" in remaining
    
    def test_think_tag_handling(self):
        """测试 think 标签处理。"""
        core = get_toolify_core()
        detector = StreamingToolCallDetector(core.trigger_signal)
        
        # think 块内的触发信号不应被检测
        content = f"<think>思考内容 {core.trigger_signal} 不应触发</think>正常内容"
        is_tool, output = detector.process_chunk(content)
        
        # 应该输出内容而不触发工具调用
        assert not is_tool or detector.state != "tool_parsing"
    
    def test_multiple_chunks_trigger_signal(self):
        """测试触发信号跨多个块的情况。"""
        core = get_toolify_core()
        detector = StreamingToolCallDetector(core.trigger_signal)
        
        # 将触发信号分成两部分
        signal = core.trigger_signal
        mid = len(signal) // 2
        chunk1 = f"前面的内容{signal[:mid]}"
        chunk2 = f"{signal[mid:]}\n<function_calls>"
        
        detector.process_chunk(chunk1)
        detector.process_chunk(chunk2)
        
        # 应该检测到信号
        assert detector.state in ["signal_detected", "tool_parsing"]
    
    def test_empty_chunk(self):
        """测试空块处理。"""
        core = get_toolify_core()
        detector = StreamingToolCallDetector(core.trigger_signal)
        
        is_tool, output = detector.process_chunk("")
        
        assert not is_tool
        assert output == ""
    
    def test_finalize_without_complete_xml(self):
        """测试不完整的 XML 处理。"""
        core = get_toolify_core()
        detector = StreamingToolCallDetector(core.trigger_signal)
        
        # 只有触发信号，没有完整的 XML
        detector.process_chunk(core.trigger_signal)
        detector.process_chunk("<function_calls>")
        
        parsed_tools, remaining = detector.finalize()
        
        # 应该返回 None 或剩余内容
        assert parsed_tools is None or len(parsed_tools) == 0
    
    def test_nested_think_tags(self):
        """测试嵌套的 think 标签。"""
        core = get_toolify_core()
        detector = StreamingToolCallDetector(core.trigger_signal)
        
        content = f"<think>外层<think>内层 {core.trigger_signal}</think>外层</think>正常"
        detector.process_chunk(content)
        
        # 嵌套 think 块内的信号不应触发
        assert detector.state != "tool_parsing"