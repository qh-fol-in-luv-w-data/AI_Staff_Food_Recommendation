"""Giao diện chung giữa agent và "bộ não" LLM.

Hệ thống chỉ dùng model mã nguồn mở chạy trên thiết bị (xem local.py: llama.cpp / Ollama / vLLM qua API
tương thích OpenAI). Agent không phụ thuộc server cụ thể: mỗi provider chỉ cần
  step(system, tools, messages, on_text, tool_choice) -> StepResult   (stream chữ qua on_text)
  prewarm(system, tools)                                               (tuỳ chọn: tính sẵn phần đầu prompt)
và báo lỗi bằng ProviderError để kiosk chuyển sang bộ luật offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

TextCallback = Callable[[str], Awaitable[None]]


class ProviderError(RuntimeError):
    """LLM không dùng được lúc này. kind: network | timeout | rate_limit | overloaded | auth | bad_request | server | bad_json."""

    def __init__(self, message: str, kind: str = "server"):
        super().__init__(message)
        self.kind = kind

    @property
    def persistent(self) -> bool:
        """Lỗi không tự hết sau vài giây (cấu hình sai, request sai) -> nghỉ LLM lâu hơn."""
        return self.kind in ("auth", "bad_request")


@dataclass
class StepResult:
    content: list[Any]                  # khối nội dung: {"type": "text"} / {"type": "tool_use", id, name, input}
    stop_reason: str | None             # end_turn | tool_use | max_tokens
    model: str = ""
    usage: dict = field(default_factory=dict)
    ttft_ms: float | None = None        # thời gian tới chữ đầu tiên
    total_ms: float = 0.0


def block_type(b: Any) -> str:
    return b.get("type", "") if isinstance(b, dict) else getattr(b, "type", "")


def block_attr(b: Any, name: str, default: Any = None) -> Any:
    return b.get(name, default) if isinstance(b, dict) else getattr(b, name, default)
