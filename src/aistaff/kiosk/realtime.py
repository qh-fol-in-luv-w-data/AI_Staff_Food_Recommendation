"""Phần "miệng" của hội thoại thời gian thực: chữ LLM chảy ra -> cắt câu -> TTS tuần tự -> loa.

- Câu đầu được cắt sớm (tới dấu phẩy đầu tiên) để khách nghe phản hồi nhanh nhất.
- Trong lúc câu trước đang phát, câu sau đã được tổng hợp xong (pipeline).
- Huỷ được bất cứ lúc nào (khách nói chen): ngừng tổng hợp, trình duyệt dừng phát.
- Ghi lại câu nào khách đã thực sự nghe (trình duyệt báo) để báo cho LLM khi bị ngắt lời.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from ..textnorm import fold, tts_normalize

if TYPE_CHECKING:  # pragma: no cover
    from .server import Ctx, Kiosk

log = logging.getLogger("aistaff.kiosk")

_END = re.compile(r"[.!?…]+[\"'”)\]]*(?=\s)|\n")
_SOFT = re.compile(r"[,;:–—](?=\s)")
_LEAD_DA = re.compile(r"^\s*dạ(\s*vâng)?\s*[,.!…]*\s*", re.IGNORECASE)

FIRST_MIN = 10    # câu đầu: cắt ở dấu phẩy nếu đã đủ ~10 ký tự
SOFT_MAX = 90     # câu dài: cắt ở dấu phẩy sau ~90 ký tự
HARD_MAX = 170    # không có dấu câu: cắt ở khoảng trắng

BACKCHANNELS = {"ừ", "ừm", "ờ", "à", "ồ", "dạ", "vâng", "ok", "oke", "okay", "uh", "um", "hử", "hả", "ừa", "ờm", "ơ"}


def cut_sentences(buf: str, first: bool, final: bool) -> tuple[list[str], str]:
    """Tách các câu đã hoàn chỉnh khỏi bộ đệm. Trả về (các câu, phần còn lại)."""
    out: list[str] = []
    while True:
        m = _END.search(buf)
        if m:
            sent, buf = buf[: m.end()].strip(), buf[m.end():]
            if sent:
                out.append(sent)
            continue
        is_first = first and not out
        m = None
        for sm in _SOFT.finditer(buf):
            if sm.end() >= (FIRST_MIN if is_first else SOFT_MAX):
                m = sm
                break
        if m:
            sent, buf = buf[: m.end()].strip(), buf[m.end():]
            if sent:
                out.append(sent)
            continue
        if len(buf) > HARD_MAX:
            cut = buf.rfind(" ", 0, HARD_MAX)
            cut = cut if cut > 40 else HARD_MAX
            out.append(buf[:cut].strip())
            buf = buf[cut:]
            continue
        break
    if final and buf.strip():
        out.append(buf.strip())
        buf = ""
    return out, buf


def strip_lead_da(text: str) -> str:
    """Đã phát "Dạ" đệm rồi thì bỏ "Dạ," ở đầu câu thật để khỏi nghe "Dạ... Dạ"."""
    rest = _LEAD_DA.sub("", text, count=1)
    if re.sub(r"[\W_]+", "", rest.lower()) in ("", "ạ", "à", "ạa"):
        return ""
    return rest[:1].upper() + rest[1:]


def is_backchannel(text: str) -> bool:
    """'ừ', 'dạ', 'vâng vâng'... nói chen khi Mai đang nói: chỉ là đệm, không phải ý mới."""
    words = [w for w in re.split(r"\W+", text.lower()) if w]
    return 0 < len(words) <= 2 and all(w in BACKCHANNELS for w in words)


def looks_like_echo(text: str, spoken: str) -> bool:
    """Micro thu lại chính giọng Mai (khử vọng không tốt): phần lớn từ trùng với câu Mai vừa nói."""
    words = fold(text).split()
    if not words or not spoken:
        return False
    said = set(fold(spoken).split())
    hit = sum(1 for w in words if w in said)
    return hit / len(words) >= 0.7


class SpeechOut:
    """Một lượt nói của Mai (một `turn`)."""

    def __init__(self, k: "Kiosk", c: "Ctx", turn: int):
        self.k, self.c, self.turn = k, c, turn
        self.full = ""                   # toàn bộ chữ (hiển thị)
        self._buf = ""                   # chữ chưa đưa đi đọc
        self.sentences: list[str] = []   # câu đã đưa đi đọc
        self.clips: list[str] = []       # chữ của từng file âm thanh đã gửi (theo seq), "" = câu đệm
        self.heard_seq = -1              # trình duyệt báo đã phát tới clip nào
        self.filler_used = False
        self.closed = False
        self._q: asyncio.Queue = asyncio.Queue()
        self._worker: asyncio.Task | None = asyncio.create_task(self._run()) if k.speech else None

    # ------------------------------------------------------------------ đầu vào
    async def feed(self, delta: str) -> None:
        if self.closed or not delta:
            return
        self.full += delta
        await self.k.send(self.c, {"type": "assistant_delta", "turn": self.turn, "text": delta})
        self._buf += delta
        sents, self._buf = cut_sentences(self._buf, first=not self.sentences, final=False)
        for x in sents:
            self._say(x)

    async def flush(self) -> None:
        """Hết một bước của model: đọc luôn phần còn lại (vd câu trước khi gọi công cụ)."""
        if self.closed:
            return
        sents, self._buf = cut_sentences(self._buf, first=not self.sentences, final=True)
        for x in sents:
            self._say(x)

    def filler(self, text: str) -> bool:
        """Câu đệm ("Dạ.") khi LLM chưa kịp trả lời. Chỉ khi chưa có câu nào được đưa đi đọc."""
        if self.closed or self.sentences or self.filler_used or not self._worker:
            return False
        self.filler_used = True
        self._q.put_nowait(("filler", text))
        return True

    def _say(self, sent: str) -> None:
        if self.filler_used and not self.sentences:
            spoken = strip_lead_da(sent)
        else:
            spoken = sent
        self.sentences.append(sent)
        if self._worker and spoken.strip():
            self._q.put_nowait(("say", spoken))

    # ------------------------------------------------------------------ kết thúc / huỷ
    async def finish(self) -> None:
        await self.flush()
        if self._worker:
            self._q.put_nowait(None)
            await self._worker

    def cancel(self) -> None:
        self.closed = True
        if self._worker and not self._worker.done():
            self._worker.cancel()

    @property
    def active(self) -> bool:
        return not self.closed and (self._worker is not None and not self._worker.done())

    def heard_text(self) -> str:
        """Phần Mai đã nói ra loa (theo báo cáo phát của trình duyệt)."""
        return " ".join(t for t in self.clips[: self.heard_seq + 1] if t).strip()

    def recent_spoken(self) -> str:
        return " ".join(self.clips[-3:])

    # ------------------------------------------------------------------ TTS tuần tự
    async def _run(self) -> None:
        seq = 0
        tts = self.k.speech.tts  # type: ignore[union-attr]
        while True:
            item = await self._q.get()
            if item is None:
                return
            kind, text = item
            try:
                path, ms = await asyncio.to_thread(tts.get, tts_normalize(text))
            except Exception as e:  # TTS lỗi thì vẫn hiện chữ, không làm hỏng lượt
                log.warning("TTS lỗi: %s", e)
                continue
            if self.closed:
                return
            if path:
                self.clips.append("" if kind == "filler" else text)
                await self.k.send(self.c, {"type": "tts", "turn": self.turn, "reply_id": f"t{self.turn}", "seq": seq,
                                           "url": f"/tts/{path.name}", "filler": kind == "filler",
                                           "synth_ms": round(ms, 1)})
                seq += 1


def cart_brief(summary: dict[str, Any]) -> str:
    items = ", ".join(summary.get("items") or []) or "trống"
    return f"Mâm hiện có: {items}; tổng {summary.get('total', '0đ')}."
