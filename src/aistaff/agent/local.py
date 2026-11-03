"""Bộ não hội thoại: LLM MÃ NGUỒN MỞ chạy ngay trên máy (hoặc máy chủ trong quán) qua API Chat Completions
tương thích OpenAI (chỉ là định dạng giao tiếp, không gọi dịch vụ nào bên ngoài).

Dùng được với: llama.cpp `llama-server --jinja` (khuyên dùng), Ollama, vLLM. Model mặc định Qwen3-4B-Instruct-2507
(Apache-2.0). Model chỉ chọn công cụ + tham số; giỏ hàng, giá, ưu đãi, mã QR vẫn do code tính.

Lịch sử hội thoại của agent giữ dạng khối (text / tool_use / tool_result) và được chuyển sang dạng
OpenAI (assistant.tool_calls + role "tool") mỗi lần gọi. System prompt + tools giống hệt nhau giữa các
phiên, nên llama.cpp (`cache_prompt`) dùng lại KV cache của phần đầu dài nhất, không phải tính lại.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

import httpx

from ..config import Conversation
from .provider import ProviderError, StepResult, TextCallback, block_attr, block_type

log = logging.getLogger("aistaff.agent")


# ---------------------------------------------------------------------- chuyển đổi định dạng
def openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t["input_schema"]}}
            for t in tools]


def openai_messages(system: str, messages: list[dict]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        if m["role"] == "assistant":
            text = "".join(block_attr(b, "text", "") for b in content if block_type(b) == "text")
            calls = [{"id": block_attr(b, "id"), "type": "function",
                      "function": {"name": block_attr(b, "name"),
                                   "arguments": json.dumps(block_attr(b, "input") or {}, ensure_ascii=False)}}
                     for b in content if block_type(b) == "tool_use"]
            msg: dict[str, Any] = {"role": "assistant", "content": text}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        texts: list[str] = []
        for b in content:
            t = block_type(b)
            if t == "tool_result":
                c = block_attr(b, "content", "")
                out.append({"role": "tool", "tool_call_id": block_attr(b, "tool_use_id"),
                            "content": c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)})
            elif t == "text":
                texts.append(block_attr(b, "text", ""))
        if texts:
            out.append({"role": "user", "content": "\n".join(texts)})
    return out


class ThinkFilter:
    """Bỏ phần <think>...</think> nếu server để lẫn vào nội dung (model "biết suy nghĩ" như Qwen3)
    - tuyệt đối không đọc phần suy nghĩ ra loa. Chịu được thẻ bị cắt giữa hai mẩu stream."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self.inside = False
        self.pending = ""

    def feed(self, s: str) -> str:
        s = self.pending + s
        self.pending = ""
        out = []
        while s:
            tag = self.CLOSE if self.inside else self.OPEN
            i = s.find(tag)
            if i >= 0:
                if not self.inside:
                    out.append(s[:i])
                s = s[i + len(tag):]
                self.inside = not self.inside
                continue
            keep = 0  # đuôi có thể là đầu của thẻ, giữ lại chờ mẩu sau
            for k in range(min(len(tag) - 1, len(s)), 0, -1):
                if tag.startswith(s[-k:]):
                    keep = k
                    break
            body = s[: len(s) - keep]
            if not self.inside:
                out.append(body)
            self.pending = s[len(s) - keep:]
            break
        return "".join(out)

    def flush(self) -> str:
        rest, self.pending = ("" if self.inside else self.pending), ""
        return rest


class LocalProvider:
    kind = "local"
    prewarm_ttl = 6 * 3600  # KV cache của llama-server giữ phần đầu tới khi bị prompt khác thay thế

    def __init__(self, conv: Conversation, client: httpx.AsyncClient | None = None):
        self.conv = conv
        self.cfg = conv.llm
        self.base = self.cfg.base_url.rstrip("/")
        self.model = self.cfg.model
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(self.cfg.timeout_seconds, connect=3.0))

    def _headers(self) -> dict:
        key = os.environ.get(self.cfg.api_key_env)
        return {"Authorization": f"Bearer {key}"} if key else {}

    def body(self, system: str, tools: list[dict], messages: list, max_tokens: int, stream: bool = True) -> dict:
        b: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages(system, messages),
            "tools": openai_tools(tools),
            "temperature": self.cfg.temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if stream:
            b["stream_options"] = {"include_usage": True}
        b.update(self.cfg.extra_body)
        return b

    @staticmethod
    def _status_error(code: int, text: str) -> ProviderError:
        if code in (401, 403):
            return ProviderError(f"LLM local từ chối truy cập ({code})", "auth")
        if code == 429:
            return ProviderError("LLM local đang bận", "rate_limit")
        if code == 503:
            return ProviderError("LLM local chưa sẵn sàng (đang nạp model?)", "overloaded")
        if 400 <= code < 500:
            return ProviderError(f"request không hợp lệ ({code}): {text[:300]}", "bad_request")
        return ProviderError(f"LLM local lỗi ({code}): {text[:300]}", "server")

    async def step(self, system: str, tools: list[dict], messages: list, on_text: TextCallback,
                   tool_choice: dict | None = None) -> StepResult:
        body = self.body(system, tools, messages, self.cfg.max_tokens)
        if tool_choice and tool_choice.get("type") == "none":
            body["tool_choice"] = "none"
        t0 = time.perf_counter()
        ttft = None
        text_parts: list[str] = []
        calls: dict[int, dict] = {}
        finish = None
        usage: dict = {}
        model = self.model
        think = ThinkFilter()

        async def emit(s: str) -> None:
            nonlocal ttft
            if not s:
                return
            if ttft is None:
                ttft = (time.perf_counter() - t0) * 1000
            text_parts.append(s)
            await on_text(s)

        try:
            async with self.client.stream("POST", f"{self.base}/chat/completions", json=body, headers=self._headers()) as r:
                if r.status_code >= 400:
                    raise self._status_error(r.status_code, (await r.aread()).decode("utf-8", "replace"))
                async for line in r.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        raise ProviderError(f"LLM local báo lỗi: {chunk['error']}", "server")
                    model = chunk.get("model") or model
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for ch in chunk.get("choices") or []:
                        d = ch.get("delta") or {}
                        if d.get("content"):
                            await emit(think.feed(d["content"]))
                        for tc in d.get("tool_calls") or []:
                            slot = calls.setdefault(int(tc.get("index", len(calls))), {"id": None, "name": "", "args": ""})
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name") and not slot["name"]:
                                slot["name"] = fn["name"]
                            if fn.get("arguments"):
                                slot["args"] += fn["arguments"]
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
        except ProviderError:
            raise
        except httpx.TimeoutException as e:
            raise ProviderError(f"LLM local quá chậm / hết thời gian chờ: {e}", "timeout") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"không kết nối được LLM local {self.base}: {e}", "network") from e
        await emit(think.flush())

        content: list[dict] = []
        text = "".join(text_parts)
        if text:
            content.append({"type": "text", "text": text})
        for i in sorted(calls):
            slot = calls[i]
            if not slot["name"]:
                continue
            try:
                args: Any = json.loads(slot["args"]) if slot["args"].strip() else {}
            except json.JSONDecodeError:
                args = slot["args"]  # chuỗi hỏng -> ToolBox trả lỗi INVALID_JSON để model gọi lại
            content.append({"type": "tool_use", "id": slot["id"] or f"call_{uuid.uuid4().hex[:12]}",
                            "name": slot["name"], "input": args})
        has_tool = any(b["type"] == "tool_use" for b in content)
        stop = "tool_use" if has_tool else ("max_tokens" if finish == "length" else "end_turn")
        if has_tool and finish == "length":
            stop = "max_tokens"
        u = {"input_tokens": int(usage.get("prompt_tokens", 0) or 0), "output_tokens": int(usage.get("completion_tokens", 0) or 0),
             "cache_read_input_tokens": int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0),
             "cache_creation_input_tokens": 0}
        res = StepResult(content=content, stop_reason=stop, model=model, usage=u, ttft_ms=ttft,
                         total_ms=(time.perf_counter() - t0) * 1000)
        log.info("LLM local %s stop=%s ttft=%sms total=%.0fms usage=%s", model, stop,
                 f"{ttft:.0f}" if ttft is not None else "-", res.total_ms, u)
        return res

    async def prewarm(self, system: str, tools: list[dict]) -> dict:
        """Cho server tính sẵn phần đầu (system + tools) vào KV cache: lần đầu trên CPU có thể mất hàng chục giây,
        các lượt sau chỉ còn tính phần mới. Nên gọi ngay khi kiosk khởi động."""
        body = self.body(system, tools, [{"role": "user", "content": [{"type": "text", "text": "xin chào"}]}],
                         max_tokens=1, stream=False)
        t0 = time.perf_counter()
        try:
            # lần đầu trên CPU có thể mất vài phút (tính cả phần đầu prompt) -> chờ lâu hơn request thường
            r = await self.client.post(f"{self.base}/chat/completions", json=body, headers=self._headers(),
                                       timeout=httpx.Timeout(max(600.0, self.cfg.timeout_seconds), connect=3.0))
        except httpx.HTTPError as e:
            raise ProviderError(f"không kết nối được LLM local {self.base}: {e}", "network") from e
        if r.status_code >= 400:
            raise self._status_error(r.status_code, r.text)
        u = r.json().get("usage") or {}
        out = {"prompt_tokens": u.get("prompt_tokens"), "ms": round((time.perf_counter() - t0) * 1000)}
        log.info("prewarm LLM local: %s", out)
        return out
