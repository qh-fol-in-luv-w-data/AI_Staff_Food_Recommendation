"""AI hội thoại thời gian thực: LLM dẫn dắt cuộc nói chuyện, công cụ tất định lo giỏ hàng & tiền.

  khách nói -> ASR (trên máy) -> ConversationAgent (Claude, streaming) --gọi công cụ--> ToolBox
                                         │ chữ chảy ra từng câu                       (giỏ, gợi ý, QR)
                                         ▼
                                  TTS (trên máy) -> loa      (khách nói chen -> huỷ lượt, Mai dừng nói)
"""

from .agent import ConversationAgent, ProviderError
from .prompt import build_system_prompt
from .tools import ToolBox

__all__ = ["ConversationAgent", "ProviderError", "ToolBox", "build_system_prompt"]
