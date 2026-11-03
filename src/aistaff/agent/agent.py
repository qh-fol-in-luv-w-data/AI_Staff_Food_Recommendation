"""ConversationAgent: một cuộc nói chuyện với một khách, do Claude dẫn dắt.

Vòng lặp mỗi lượt khách nói:
  lời khách (+ ghi chú hệ thống) -> Claude stream chữ (đọc ngay) -> nếu gọi công cụ: chạy ToolBox
  (tất định) -> trả kết quả -> Claude nói tiếp ... cho tới khi Claude ngừng gọi công cụ.

Quy tắc lịch sử (bắt buộc với preserved thinking của Claude):
- system prompt và danh sách tools dựng MỘT LẦN, giữ nguyên từng byte cả phiên.
- Lịch sử chỉ NỐI THÊM: nội dung assistant đưa lại nguyên vẹn (kể cả khối thinking), không sửa/xoá lượt cũ.
- Lượt assistant có tool_use và tin nhắn tool_result tương ứng được ghi CÙNG LÚC (không có await ở giữa),
  nên huỷ lượt (khách nói chen) ở bất kỳ điểm nào cũng để lại lịch sử hợp lệ.
- Lượt bị huỷ trước khi model trả lời xong: tin nhắn user cuối vẫn mở, lời khách tiếp theo được nối vào nó.
- Sự kiện ngoài lời khách (bấm màn hình, khách ngắt lời, QR hết hạn...) đi vào lượt user kế tiếp dưới dạng
  "[Hệ thống: ...]" thay vì sửa system prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from ..config import StoreConfig
from ..dialog import DialogManager, Session
from .prompt import build_system_prompt
from .provider import ProviderError, StepResult, TextCallback, block_attr, block_type
from .tools import ToolBox

log = logging.getLogger("aistaff.agent")

EventCallback = Callable[[dict], Awaitable[None]]

ARRIVAL_NOTE = "Khách vừa bước tới kiosk."
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
_BRACKETS = re.compile(r"[\[\]]")
_SPACES = re.compile(r"\s+")


def clean_customer_text(text: str, limit: int = 500) -> str:
    """Lời khách (ASR hoặc gõ): bỏ ngoặc vuông để khách không giả được ghi chú hệ thống."""
    return _SPACES.sub(" ", _BRACKETS.sub(" ", text or "")).strip()[:limit]


def _fallback_boundary(content: list[Any]) -> int:
    idx = -1
    for i, b in enumerate(content):
        if block_type(b) == "fallback":
            idx = i
    return idx


def echo_content(content: list[Any]) -> list[Any]:
    """Nội dung assistant đưa lại vào lịch sử.

    Bình thường: nguyên vẹn. Sau fallback giữa chừng (model chính từ chối, model dự phòng nói tiếp): trước mốc
    `fallback` cuối chỉ giữ khối text (bỏ thinking/tool_use của lượt bị từ chối); bỏ chính khối mốc; sau mốc giữ hết.
    """
    idx = _fallback_boundary(content)
    if idx < 0:
        return list(content)
    return [b for i, b in enumerate(content) if (i < idx and block_type(b) == "text") or i > idx]


def tool_calls(content: list[Any]) -> list[Any]:
    """Các tool_use cần chạy: chỉ những khối sau mốc fallback cuối (nếu có)."""
    idx = _fallback_boundary(content)
    return [b for i, b in enumerate(content) if i > idx and block_type(b) == "tool_use"]


@dataclass
class TurnResult:
    text: str
    steps: int = 0
    tools: list[str] = field(default_factory=list)
    model: str = ""
    usage: dict = field(default_factory=dict)
    ttft_ms: float | None = None
    refused: bool = False


class ConversationAgent:
    def __init__(self, cfg: StoreConfig, dm: DialogManager, session: Session, provider: Any,
                 now: datetime | None = None):
        self.cfg = cfg
        self.conv = cfg.store.conversation
        self.dm = dm
        self.s = session
        self.provider = provider
        self.toolbox = ToolBox(dm, session)
        # Dựng một lần cho cả phiên - không được đổi giữa chừng
        self.system = build_system_prompt(cfg, now or dm.now_fn())
        self.tools = self.toolbox.specs()
        self.messages: list[dict] = []
        self._notes: list[str] = []
        self.totals: dict[str, int] = {k: 0 for k in USAGE_KEYS} | {"requests": 0}
        self.turn_tools: list[str] = []      # công cụ đã chạy trong lượt hiện tại (kể cả lượt bị huỷ/lỗi)
        a = cfg.store.assistant
        self.refusal_reply = (f"Dạ, chuyện này {a.self_pronoun} xin phép không hỗ trợ được ạ. "
                              f"Mình quay lại chọn món nhé, {a.customer_pronoun} muốn dùng gì ạ?")

    # ================================================================== lịch sử
    def seed_greeting(self, greeting: str) -> None:
        """Lời chào do kiosk nói sẵn (từ mẫu, phát ngay từ cache TTS) -> ghi vào lịch sử cho model biết."""
        if self.messages:
            return
        self.messages = [
            {"role": "user", "content": [{"type": "text", "text": f"[Hệ thống: {ARRIVAL_NOTE}]"}]},
            {"role": "assistant", "content": [{"type": "text", "text": greeting}]},
        ]

    def note(self, text: str) -> None:
        """Ghi chú hệ thống, gửi kèm lượt khách nói tiếp theo."""
        text = _SPACES.sub(" ", text).strip()
        if text:
            self._notes.append(text)

    @property
    def pending_notes(self) -> list[str]:
        return list(self._notes)

    def _push_user(self, blocks: list[dict]) -> None:
        if not self.messages:
            blocks = [{"type": "text", "text": f"[Hệ thống: {ARRIVAL_NOTE}]"}, *blocks]
        if self.messages and self.messages[-1]["role"] == "user":
            # Lượt trước bị huỷ trước khi model trả lời: chưa có gì sinh ra sau tin nhắn này -> nối tiếp vào đó
            last = self.messages[-1]
            if isinstance(last["content"], str):
                last["content"] = [{"type": "text", "text": last["content"]}]
            last["content"].extend(blocks)
        else:
            self.messages.append({"role": "user", "content": blocks})

    def _add_usage(self, res: StepResult) -> None:
        self.totals["requests"] += 1
        for k in USAGE_KEYS:
            self.totals[k] += int(res.usage.get(k, 0) or 0)

    # ================================================================== một lượt
    async def turn(self, text: str | None, on_text: TextCallback, on_event: EventCallback,
                   on_step: Callable[[], Awaitable[None]] | None = None) -> TurnResult:
        """Khách vừa nói `text` (có thể rỗng nếu chỉ có ghi chú hệ thống). Có thể bị huỷ (CancelledError) bất cứ lúc nào.

        on_text: từng mẩu chữ (đọc ngay); on_event: sự kiện màn hình từ công cụ; on_step: hết một bước của model
        (để bộ đọc phát luôn câu cuối của bước đó trong lúc chờ công cụ / bước sau).
        """
        self.turn_tools = []
        blocks = [{"type": "text", "text": f"[Hệ thống: {n}]"} for n in self._notes]
        said = clean_customer_text(text or "")
        if said:
            blocks.append({"type": "text", "text": said})
        if not blocks:
            raise ValueError("lượt trống: không có lời khách hay ghi chú")
        self._notes = []
        self._push_user(blocks)

        parts: list[str] = []
        fresh_step = [False]

        async def _text(delta: str) -> None:
            if fresh_step[0]:  # chữ của bước mới: ngăn cách với câu của bước trước
                fresh_step[0] = False
                if parts and not parts[-1][-1:].isspace() and not delta[:1].isspace():
                    delta = " " + delta
            parts.append(delta)
            await on_text(delta)

        result = TurnResult(text="")
        max_steps = self.conv.max_steps_per_turn
        for step in range(1, max_steps + 2):
            last_chance = step > max_steps  # đã gọi công cụ quá nhiều: bắt model trả lời bằng lời
            fresh_step[0] = True
            res = await self.provider.step(self.system, self.tools, self.messages, _text,
                                           tool_choice={"type": "none"} if last_chance else None)
            # ---- từ đây tới khi ghi xong lịch sử: KHÔNG await (huỷ lượt không thể chen vào giữa) ----
            self._add_usage(res)
            result.steps, result.model = step, res.model
            for k, v in res.usage.items():
                result.usage[k] = result.usage.get(k, 0) + v
            if result.ttft_ms is None and res.ttft_ms is not None:
                result.ttft_ms = res.ttft_ms
            if res.stop_reason == "refusal":
                # Cả chuỗi model (kể cả dự phòng) đều từ chối: bỏ phần dở, trả lời an toàn rồi quay lại gọi món
                log.warning("LLM từ chối lượt này (stop_reason=refusal)")
                self.messages.append({"role": "assistant", "content": [{"type": "text", "text": self.refusal_reply}]})
                result.refused = True
                result.text = self.refusal_reply
                return result
            content = echo_content(res.content) or [{"type": "text", "text": "Dạ."}]
            calls = tool_calls(res.content)
            self.messages.append({"role": "assistant", "content": content})
            if not calls:
                if on_step:
                    await on_step()
                break
            results = []
            for c in calls:
                cid, name, args = block_attr(c, "id"), block_attr(c, "name"), block_attr(c, "input")
                if res.stop_reason == "max_tokens":  # tham số bị cắt ngang: không chạy
                    out, err = '{"error": "tham số bị cắt do quá dài, hãy gọi lại ngắn gọn hơn"}', True
                else:
                    out, err = self.toolbox.run(name, args)
                    self.turn_tools.append(name)
                r: dict = {"type": "tool_result", "tool_use_id": cid, "content": out}
                if err:
                    r["is_error"] = True
                results.append(r)
            self.messages.append({"role": "user", "content": results})
            # ---- lịch sử đã hợp lệ; giờ mới đọc nốt câu dở và đẩy sự kiện (giỏ, gợi ý, QR...) ra màn hình ----
            if on_step:
                await on_step()
            for ev in self.toolbox.drain_events():
                await on_event(ev)
        result.text = "".join(parts)
        result.tools = list(self.turn_tools)
        return result

    async def prewarm(self) -> dict | None:
        fn = getattr(self.provider, "prewarm", None)
        if fn is None:
            return None
        try:
            return await fn(self.system, self.tools)
        except ProviderError as e:
            log.info("prewarm bỏ qua: %s", e)
            return None


__all__ = ["ConversationAgent", "ProviderError", "TurnResult", "clean_customer_text", "echo_content", "tool_calls"]
