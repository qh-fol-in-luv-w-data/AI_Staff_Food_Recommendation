"""Gọi Claude (Anthropic API) theo kiểu streaming cho hội thoại giọng nói.

- Streaming: chữ chảy ra tới đâu đọc tới đó (on_text), không đợi hết câu trả lời.
- Prompt caching: breakpoint tường minh ở cuối system prompt (cache cả tools + system, dùng chung giữa các
  phiên trong cùng buổi) + cache tự động ở cấp request (cache dần lịch sử hội thoại của phiên).
- effort "low": ít suy nghĩ nhất -> câu đầu ra nhanh nhất, hợp với giọng nói.
- Fallback phía server (`fallbacks: "default"`): nếu bộ lọc an toàn từ chối nhầm, API tự chạy lại trên
  model dự phòng Anthropic khuyến nghị -> khách không bị "im lặng". Không áp dụng cho Haiku.
- Lỗi mạng / hết hạn mức / sai key -> ProviderError để kiosk chuyển sang bộ luật offline.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..config import Conversation

log = logging.getLogger("aistaff.agent")

TextCallback = Callable[[str], Awaitable[None]]

# Các model có fallback phía server ("default", beta server-side-fallback-2026-07-01). Haiku 5.5 không có.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ProviderError(RuntimeError):
    """LLM không dùng được lúc này. kind: network | timeout | rate_limit | overloaded | auth | bad_request | server | bad_json."""

    def __init__(self, message: str, kind: str = "server"):
        super().__init__(message)
        self.kind = kind

    @property
    def persistent(self) -> bool:
        """Lỗi không tự hết sau vài giây (sai key, request sai) -> nghỉ LLM lâu hơn."""
        return self.kind in ("auth", "bad_request")


@dataclass
class StepResult:
    content: list[Any]                  # khối nội dung trả về, đưa lại NGUYÊN VẸN vào lịch sử
    stop_reason: str | None
    model: str = ""
    usage: dict = field(default_factory=dict)
    ttft_ms: float | None = None        # thời gian tới chữ đầu tiên
    total_ms: float = 0.0


def block_type(b: Any) -> str:
    return b.get("type", "") if isinstance(b, dict) else getattr(b, "type", "")


def block_attr(b: Any, name: str, default: Any = None) -> Any:
    return b.get(name, default) if isinstance(b, dict) else getattr(b, name, default)


def _usage_dict(u: Any) -> dict:
    if u is None:
        return {}
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    return {k: int(getattr(u, k, 0) or 0) for k in keys}


class AnthropicProvider:
    kind = "claude"
    prewarm_ttl = 240  # prompt cache mặc định sống 5 phút

    def __init__(self, conv: Conversation, api_key: str | None = None, client: Any = None):
        import anthropic
        import httpx2  # thư viện HTTP của SDK; lỗi khi đang đọc stream có thể không được SDK bọc lại

        self._a = anthropic
        self._http_errors = (httpx2.HTTPError,)
        self.conv = conv
        self.model = conv.model
        if client is None:
            timeout = anthropic.Timeout(conv.request_timeout_seconds, connect=min(4.0, conv.request_timeout_seconds))
            client = anthropic.AsyncAnthropic(api_key=api_key or os.environ.get(conv.api_key_env), timeout=timeout,
                                              max_retries=1)
        self.client = client

    @staticmethod
    def available(conv: Conversation) -> bool:
        if not os.environ.get(conv.api_key_env):
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    # ------------------------------------------------------------------ tham số request (giữ cố định trong phiên)
    def params(self, system: str, tools: list[dict], messages: list, max_tokens: int, auto_cache: bool = True) -> dict:
        p: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": tools,
            "messages": messages,
            "output_config": {"effort": self.conv.effort},
        }
        if auto_cache:
            p["cache_control"] = {"type": "ephemeral"}
        if self.model in FALLBACK_MODELS:
            p["betas"] = [FALLBACK_BETA]
            p["fallbacks"] = "default"
        return p

    def _error(self, e: Exception) -> ProviderError:
        a = self._a
        if isinstance(e, a.APITimeoutError):
            return ProviderError(f"hết thời gian chờ: {e}", "timeout")
        if isinstance(e, a.APIConnectionError):
            return ProviderError(f"mất kết nối: {e}", "network")
        if isinstance(e, a.RateLimitError):
            return ProviderError("vượt hạn mức gọi API", "rate_limit")
        if isinstance(e, (a.AuthenticationError, a.PermissionDeniedError)):
            return ProviderError("API key không hợp lệ hoặc không có quyền", "auth")
        if isinstance(e, a.APIStatusError):
            code = getattr(e, "status_code", 0) or 0
            if code == 529:
                return ProviderError("máy chủ quá tải", "overloaded")
            if 400 <= code < 500:
                return ProviderError(f"request không hợp lệ ({code}): {e}", "bad_request")
            return ProviderError(f"lỗi máy chủ ({code})", "server")
        return ProviderError(str(e), "server")

    # ------------------------------------------------------------------ một bước (một lượt trả lời của model)
    async def step(self, system: str, tools: list[dict], messages: list, on_text: TextCallback,
                   tool_choice: dict | None = None) -> StepResult:
        p = self.params(system, tools, messages, self.conv.max_tokens)
        if tool_choice:
            p["tool_choice"] = tool_choice
        bad_json = 0
        while True:
            t0 = time.perf_counter()
            ttft = None
            try:
                async with self.client.beta.messages.stream(**p) as stream:
                    async for event in stream:
                        if event.type == "text" and event.text:
                            if ttft is None:
                                ttft = (time.perf_counter() - t0) * 1000
                            await on_text(event.text)
                    msg = await stream.get_final_message()
            except ValueError as e:
                # JSON tham số công cụ hỏng tới mức SDK không đọc được: chưa có tool_use_id để trả lời
                # -> gửi lại đúng request này (giới hạn số lần). Lỗi API không phải ValueError.
                bad_json += 1
                log.warning("tool JSON không đọc được (lần %d): %s", bad_json, e)
                if bad_json > 1:
                    raise ProviderError("model trả tham số công cụ không đọc được", "bad_json") from e
                continue
            except self._a.APIError as e:
                raise self._error(e) from e
            except self._http_errors as e:
                raise ProviderError(f"mất kết nối khi đang nhận dữ liệu: {e}", "network") from e
            break
        res = StepResult(content=list(msg.content), stop_reason=msg.stop_reason, model=getattr(msg, "model", self.model),
                         usage=_usage_dict(getattr(msg, "usage", None)), ttft_ms=ttft,
                         total_ms=(time.perf_counter() - t0) * 1000)
        log.info("LLM %s stop=%s ttft=%sms total=%.0fms usage=%s", res.model, res.stop_reason,
                 f"{ttft:.0f}" if ttft is not None else "-", res.total_ms, res.usage)
        return res

    async def prewarm(self, system: str, tools: list[dict]) -> dict:
        """Ghi sẵn prompt cache (tools + system) bằng request max_tokens=0, không streaming.

        Breakpoint chỉ ở system (không bật cache tự động, vì sẽ khoá cache vào tin nhắn giả).
        Cùng effort/beta với request thật để cache trúng.
        """
        p = self.params(system, tools, [{"role": "user", "content": "warmup"}], max_tokens=0, auto_cache=False)
        try:
            msg = await self.client.beta.messages.create(**p)
        except self._a.APIError as e:
            raise self._error(e) from e
        except self._http_errors as e:
            raise ProviderError(f"mất kết nối: {e}", "network") from e
        u = _usage_dict(getattr(msg, "usage", None))
        log.info("prewarm cache: %s", u)
        return u
