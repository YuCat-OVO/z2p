"""Toolify 流式检测器。

用于在流式响应中检测工具调用。
"""

from typing import Optional, List, Dict, Any, Tuple

from .parser import parse_tool_calls_xml
from ...logger import get_logger

logger = get_logger(__name__)

TRIGGER_SIGNAL = "<tool_call>"


class StreamingToolCallDetector:
    """流式工具调用检测器。
    
    检测流式响应中的工具调用触发信号，并缓冲内容直到完整的工具调用被接收。
    """
    
    def __init__(self, trigger_signal: str = TRIGGER_SIGNAL):
        """初始化检测器。
        
        :param trigger_signal: 触发信号字符串
        """
        self.trigger_signal = trigger_signal
        self.buffer = ""
        self.state = "detecting"  # detecting, buffering
        self.in_think = False
        self.think_depth = 0
    
    def process_chunk(self, content: str) -> Tuple[bool, str]:
        """处理流式内容块。
        
        :param content: 新的内容块
        :return: (is_tool_detected, content_to_yield) - 是否检测到工具调用，以及应该输出的内容
        """
        if not content:
            return False, ""
        
        self.buffer += content
        
        # 如果已经在缓冲工具调用，继续累积
        if self.state == "buffering":
            return False, ""
        
        # 更新 think 标签状态
        self._update_think_state()
        
        # 在非 think 块中检测触发信号
        if not self.in_think and self.trigger_signal in self.buffer:
            # 检测到触发信号，开始缓冲
            logger.info("[TOOLIFY] 检测到工具调用触发信号")
            self.state = "buffering"
            
            # 输出触发信号之前的内容
            idx = self.buffer.find(self.trigger_signal)
            content_before = self.buffer[:idx]
            self.buffer = self.buffer[idx:]
            return True, content_before
        
        # 正常输出内容，但保留一小部分以防触发信号跨块
        if len(self.buffer) > len(self.trigger_signal):
            output = self.buffer[:-len(self.trigger_signal)]
            self.buffer = self.buffer[-len(self.trigger_signal):]
            return False, output
        
        return False, ""
    
    def _update_think_state(self):
        """更新 think 标签状态。"""
        # 简化版：只检测 <think> 和 </think>
        self.think_depth = self.buffer.count("<think>") - self.buffer.count("</think>")
        self.in_think = self.think_depth > 0
    
    def finalize(self) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """流结束时的最终处理。
        
        :return: (parsed_tools, remaining_content) - 解析出的工具调用和剩余内容
        """
        if self.state == "buffering":
            # 尝试解析工具调用
            parsed = parse_tool_calls_xml(self.buffer, self.trigger_signal)
            if parsed:
                logger.info(f"[TOOLIFY] 成功解析 {len(parsed)} 个工具调用")
                return parsed, ""
            else:
                logger.warning("[TOOLIFY] 解析工具调用失败，返回原始内容")
                return None, self.buffer
        
        # 返回缓冲区中剩余的内容
        return None, self.buffer