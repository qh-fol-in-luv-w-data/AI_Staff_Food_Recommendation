"""Provider giả lập thay Claude trong test (không cần mạng / API key).

Kịch bản = danh sách các bước; mỗi bước là list khối:
  "chữ"                      -> khối text (được stream từng mẩu qua on_text)
  ("tool", tên, tham số)     -> khối tool_use
  ("thinking",)              -> khối thinking (để kiểm tra được đưa lại nguyên vẹn)
  ("fallback",)              -> mốc fallback (model chính từ chối giữa chừng, model dự phòng nói tiếp)
hoặc một Exception (ví dụ ProviderError) để giả lập lỗi, hoặc hàm(messages) -> bước.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any

from aistaff.agent.provider import StepResult


class ScriptedProvider:
    kind = "scripted"
    model = "scripted"

    def __init__(self, script: list[Any] | None = None, chunk: int = 7, delay: float = 0.0, stop_reasons: dict | None = None,
                 first_delay: float = 0.0):
        self.script = list(script or [])
        self.chunk = chunk
        self.delay = delay
        self.first_delay = first_delay  # giả lập thời gian chờ chữ đầu tiên (TTFT)
        self.stop_reasons = stop_reasons or {}
        self.calls: list[dict] = []
        self.prewarms = 0
        self.n = 0

    def add(self, *steps: Any) -> None:
        self.script.extend(steps)

    async def step(self, system: str, tools: list[dict], messages: list, on_text, tool_choice: dict | None = None) -> StepResult:
        self.calls.append({"system": system, "tools": copy.deepcopy(tools), "messages": copy.deepcopy(messages),
                           "tool_choice": tool_choice})
        if not self.script:
            raise AssertionError("ScriptedProvider: hết kịch bản")
        item = self.script.pop(0)
        if self.first_delay:
            await asyncio.sleep(self.first_delay)
        if callable(item):
            item = item(messages)
        if isinstance(item, BaseException):
            raise item
        stop = None
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], str) and item[1] in (
                "end_turn", "tool_use", "max_tokens", "refusal"):
            item, stop = item
        content: list[dict] = []
        for b in item:
            if isinstance(b, str):
                for i in range(0, len(b), self.chunk):
                    if self.delay:
                        await asyncio.sleep(self.delay)
                    await on_text(b[i:i + self.chunk])
                content.append({"type": "text", "text": b})
            elif b[0] == "tool":
                self.n += 1
                content.append({"type": "tool_use", "id": f"toolu_{self.n:03d}", "name": b[1], "input": b[2]})
            elif b[0] == "thinking":
                content.append({"type": "thinking", "thinking": "", "signature": f"sig{self.n}"})
            elif b[0] == "fallback":
                content.append({"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}})
        if stop is None:
            stop = "tool_use" if any(c["type"] == "tool_use" for c in content) else "end_turn"
        return StepResult(content=content, stop_reason=stop, model="scripted",
                          usage={"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 3000,
                                 "cache_creation_input_tokens": 0}, ttft_ms=5.0, total_ms=10.0)

    async def prewarm(self, system: str, tools: list[dict]) -> dict:
        self.prewarms += 1
        return {"cache_creation_input_tokens": 3000}
