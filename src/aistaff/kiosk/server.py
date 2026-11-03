"""Máy chủ kiosk chạy ngay trên thiết bị edge.

  Trình duyệt (Chromium kiosk / tablet) <--WebSocket--> FastAPI
     - gửi chữ gõ, thao tác chạm, hoặc âm thanh micro PCM16 16 kHz (trình duyệt tự khử vọng AEC)
     - nhận chữ AI đang nói (stream), giỏ hàng, gợi ý, mã QR, link âm thanh TTS để phát

Hai chế độ hội thoại (store.yaml -> conversation.engine):
  llm   (mặc định) : AI nói chuyện tự nhiên thời gian thực.
                     micro -> VAD -> ASR (trên máy, có phụ đề tạm khi khách đang nói) -> Claude stream
                     -> câu đầu đọc ngay -> TTS (trên máy) -> loa. Khách nói chen -> Mai dừng lại nghe.
                     Giỏ hàng / giá / ưu đãi / QR do công cụ tất định xử lý (agent/tools.py).
  rules            : bộ luật offline (NLU + dialog), cũng là phương án dự phòng khi mất mạng / lỗi API.
/webhooks/sepay nhận báo có tiền -> đẩy màn hình "đã thanh toán" tới đúng phiên khách.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import random
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import StoreConfig, load_store
from ..dialog import DialogManager, Reply, Session
from ..payments import PaymentEvent, PaymentHub
from ..storage import Storage
from .realtime import SpeechOut, cart_brief, is_backchannel, looks_like_echo

log = logging.getLogger("aistaff.kiosk")
STATIC = Path(__file__).parent / "static"
WEBUI = Path(__file__).parent / "webui"  # bản build React (web/ -> npm run build)
SR = 16000


@dataclass
class Ctx:
    session: Session
    sockets: set = field(default_factory=set)
    vad: object | None = None
    listening: bool = False
    speaking: bool = False               # VAD: khách đang nói
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # ---- hội thoại thời gian thực
    agent: Any = None                     # ConversationAgent của khách hiện tại
    turn: asyncio.Task | None = None      # lượt AI đang trả lời
    out: SpeechOut | None = None          # lượt AI đang nói
    turn_seq: int = 0
    playing: bool = False                 # trình duyệt báo đang phát âm thanh
    play_at: float = 0.0
    speech_t0: float = 0.0                # lúc khách bắt đầu nói (VAD)
    spoke_over: bool = False              # khách bắt đầu nói khi Mai đang nói
    barged: bool = False
    live: list = field(default_factory=list)   # âm thanh câu đang nói (cho phụ đề tạm)
    live_len: int = 0
    partial_len: int = 0
    partial_busy: bool = False
    partial_text: str = ""
    preroll: deque = field(default_factory=lambda: deque(maxlen=12))


def _log_task_error(t: asyncio.Task) -> None:
    if not t.cancelled() and t.exception() is not None:
        log.error("tác vụ nền lỗi: %r", t.exception(), exc_info=t.exception())


class Kiosk:
    def __init__(self, cfg: StoreConfig, storage: Storage, data_dir: Path, speech=None, llm=None, now_fn=None,
                 provider: Any = None):
        self.cfg = cfg
        self.conv = cfg.store.conversation
        self.storage = storage
        self.data_dir = data_dir
        self.speech = speech
        self.dm = DialogManager(cfg, storage, now_fn=now_fn, llm=llm)
        self.payments = PaymentHub(cfg, storage, on_paid=self._on_paid)
        self.ctxs: dict[str, Ctx] = {}
        self.by_order: dict[str, str] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self.provider = provider if self.conv.engine == "llm" else None
        self.llm_down_until = 0.0
        self.llm_error = ""
        self._warm: dict[int, float] = {}
        a = cfg.store.assistant
        self.fillers = ["Dạ.", "Dạ vâng.", f"Dạ, {a.self_pronoun} nghe ạ."]

    # ------------------------------------------------------------------ chế độ
    @property
    def realtime(self) -> bool:
        """Có bộ não LLM (có thể đang tạm nghỉ vì mất mạng)."""
        return self.provider is not None

    def llm_ready(self) -> bool:
        return self.provider is not None and time.time() >= self.llm_down_until

    def mode(self) -> str:
        if self.provider is None:
            return "rules"
        return "llm" if self.llm_ready() else "llm-offline"

    # ------------------------------------------------------------------ phiên
    def ctx(self, sid: str | None) -> Ctx:
        if sid and sid in self.ctxs:
            return self.ctxs[sid]
        s = self.dm.new_session(sid)
        c = Ctx(session=s)
        if self.speech:
            c.vad = self.speech.new_vad()
        self.ctxs[s.id] = c
        return c

    async def send(self, c: Ctx, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False)
        async with c.send_lock:
            for ws in list(c.sockets):
                try:
                    await ws.send_text(data)
                except Exception:
                    c.sockets.discard(ws)

    async def push_reply(self, c: Ctx, reply: Reply) -> None:
        if reply.order and reply.order.get("code"):
            self.by_order[reply.order["code"]] = c.session.id
        rid = f"{time.time():.3f}"
        await self.send(c, {"type": "reply", "id": rid, **reply.to_dict()})
        if self.speech and reply.speech:
            from ..speech.tts import split_sentences

            for i, sent in enumerate(split_sentences(reply.speech, max_len=110)):
                path, ms = await asyncio.to_thread(self.speech.tts.get, sent)
                if path:
                    await self.send(c, {"type": "tts", "reply_id": rid, "seq": i, "url": f"/tts/{path.name}",
                                        "synth_ms": round(ms, 1)})

    async def sync(self, c: Ctx) -> None:
        """Gửi lại trạng thái giỏ/phiên (sau khi một lượt bị huỷ giữa chừng)."""
        s = c.session
        await self.send(c, {"type": "cart", "cart": self.dm._cart_dict(s), "state": s.state})

    def _on_paid(self, ev: PaymentEvent) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._notify_paid(ev)))

    async def _notify_paid(self, ev: PaymentEvent) -> None:
        sid = self.by_order.get(ev.order_code)
        c = self.ctxs.get(sid) if sid else None
        if not c or c.session.order_code != ev.order_code:
            log.info("Đơn %s đã thanh toán (không còn phiên trên màn hình)", ev.order_code)
            return
        await self.interrupt(c, note=False)
        async with c.lock:
            reply = self.dm.payment_received(c.session, ev.amount)
        c.agent = None  # cuộc nói chuyện với khách này đã xong
        await self.push_reply(c, reply)

    # ================================================================== hội thoại thời gian thực
    def _new_agent(self, c: Ctx, greeting: str | None = None) -> None:
        from ..agent import ConversationAgent

        c.agent = ConversationAgent(self.cfg, self.dm, c.session, self.provider)
        if greeting:
            c.agent.seed_greeting(greeting)
        if self.conv.prewarm_cache and self.llm_ready():
            asyncio.ensure_future(self._prewarm(c.agent)).add_done_callback(_log_task_error)

    async def _prewarm(self, agent: Any) -> None:
        key = hash(agent.system)
        if time.time() - self._warm.get(key, 0) < 240:  # cache (TTL 5 phút) vẫn còn ấm
            return
        self._warm[key] = time.time()
        await agent.prewarm()

    @staticmethod
    def _playing(c: Ctx) -> bool:
        return c.playing and time.monotonic() - c.play_at < 25

    def _busy(self, c: Ctx) -> bool:
        """Mai đang nghĩ hoặc đang nói."""
        return (c.turn is not None and not c.turn.done()) or self._playing(c)

    async def start(self, c: Ctx) -> None:
        await self.interrupt(c, note=False)
        async with c.lock:
            self.dm.reset(c.session)
            reply = self.dm.greet(c.session)
        c.agent = None
        if self.realtime:
            self._new_agent(c, greeting=reply.text)
        await self.push_reply(c, reply)

    async def interrupt(self, c: Ctx, note: bool = True) -> None:
        """Dừng lượt AI đang nghĩ/nói (khách nói chen, bấm màn hình, khách mới...)."""
        t, out = c.turn, c.out
        running = t is not None and not t.done()
        if not running and not self._playing(c):
            return
        if running:
            t.cancel()  # type: ignore[union-attr]
            await asyncio.wait({t})  # type: ignore[arg-type]  # đợi lượt cũ dừng hẳn (không nhận lỗi của nó)
        if out:
            out.cancel()
        c.playing = False
        await self.send(c, {"type": "stop_audio", "turn": out.turn if out else None})
        if running:
            await self.sync(c)
        if note and c.agent and out:
            heard = out.heard_text()
            if running and not out.full:
                c.agent.note("Khách nói tiếp khi Mai chưa kịp trả lời.")
            elif heard and heard != out.full.strip():
                c.agent.note(f'Khách ngắt lời khi Mai đang nói; khách mới nghe tới: "{heard}".')
            elif not heard:
                c.agent.note("Khách ngắt lời ngay khi Mai vừa bắt đầu nói, chưa nghe được gì.")

    async def on_user(self, c: Ctx, text: str) -> None:
        """Một câu khách nói (ASR) hoặc gõ."""
        text = text.strip()
        if not text:
            return
        if not self.realtime:
            await self.on_text(c, text)
            return
        await self.interrupt(c)
        if not self.llm_ready():
            await self._rules_turn(c, text)
            return
        c.turn = asyncio.create_task(self._llm_turn(c, text))
        c.turn.add_done_callback(_log_task_error)

    async def _rules_turn(self, c: Ctx, text: str, why: str = "") -> None:
        async with c.lock:
            reply = self.dm.handle(c.session, text)
        if c.agent:
            c.agent.note(f'Khi AI tạm mất kết nối{why}, khách nói "{text}" và Mai (chế độ dự phòng) đã trả lời: '
                         f'"{reply.text}". {cart_brief(c.agent.toolbox.cart_summary())}')
        await self.push_reply(c, reply)

    async def _llm_turn(self, c: Ctx, text: str) -> None:
        s = c.session
        if s.state == "done":  # đơn trước đã thanh toán: khách mới / đơn mới
            self.dm.reset(s)
            c.agent = None
        if c.agent is None:
            self._new_agent(c)
        if s.state == "idle":
            s.state = "ordering"
        s.turns += 1
        s.updated_at = time.time()
        c.turn_seq += 1
        out = c.out = SpeechOut(self, c, c.turn_seq)
        await self.send(c, {"type": "assistant_start", "turn": out.turn})
        filler = asyncio.ensure_future(self._filler(out)) if (self.conv.filler and self.speech) else None
        t0 = time.perf_counter()
        try:
            res = await c.agent.turn(text, out.feed, lambda ev: self._tool_event(c, ev), on_step=out.flush)
        except asyncio.CancelledError:
            out.cancel()
            raise
        except Exception as e:  # noqa: BLE001 - mất mạng / lỗi API / lỗi bất ngờ -> dự phòng
            await self._llm_failed(c, out, text, e)
            return
        finally:
            if filler:
                filler.cancel()
        if res.refused:
            out.cancel()
            await self.send(c, {"type": "stop_audio", "turn": out.turn})
            c.turn_seq += 1
            out = c.out = SpeechOut(self, c, c.turn_seq)
            await self.send(c, {"type": "assistant_start", "turn": out.turn, "replace": True})
            await out.feed(res.text)
        await out.finish()
        s.updated_at = time.time()
        self._warm[hash(c.agent.system)] = time.time()
        await self.send(c, {"type": "assistant_end", "turn": out.turn, "text": out.full, "state": s.state,
                            "cart": self.dm._cart_dict(s), "tools": res.tools,
                            "latency_ms": {"first_text": res.ttft_ms, "total": round((time.perf_counter() - t0) * 1000)}})

    async def _filler(self, out: SpeechOut) -> None:
        await asyncio.sleep(self.conv.filler_delay_ms / 1000)
        if not out.full:
            out.filler(random.choice(self.fillers))

    async def _tool_event(self, c: Ctx, ev: dict) -> None:
        if ev.get("type") == "state" and ev.get("order") and ev["order"].get("code"):
            self.by_order[ev["order"]["code"]] = c.session.id
        await self.send(c, ev)

    async def _llm_failed(self, c: Ctx, out: SpeechOut, text: str, err: Exception) -> None:
        from ..agent import ProviderError

        kind = err.kind if isinstance(err, ProviderError) else type(err).__name__
        if isinstance(err, ProviderError):
            log.warning("LLM lỗi (%s): %s -> dùng bộ luật offline", kind, err)
            self.llm_down_until = time.time() + (300 if err.persistent else 30)
        else:
            log.exception("Lỗi bất ngờ trong lượt hội thoại: %s", err)
            self.llm_down_until = time.time() + 30
        self.llm_error = kind
        await out.finish()  # phần đã nói dở (nếu có) vẫn đọc hết
        await self.send(c, {"type": "assistant_end", "turn": out.turn, "text": out.full, "state": c.session.state,
                            "cart": self.dm._cart_dict(c.session), "error": kind})
        if not self.conv.fallback_to_rules:
            msg = f"Dạ, hệ thống đang chậm một chút, {self.dm.cp} nói lại giúp {self.dm.sp} nhé."
            await self.push_reply(c, self.dm._reply(c.session, msg, intent="llm_error"))
            return
        if c.agent and c.agent.turn_tools:
            # Lượt này đã kịp đổi mâm: không chạy lại bằng bộ luật (tránh thêm món trùng), chỉ báo lại mâm
            summary = c.agent.toolbox.cart_summary()
            msg = f"Dạ, {self.dm.sp} đã cập nhật mâm trên màn hình, tổng {summary['total']} ạ."
            reply = self.dm._reply(c.session, msg, intent="llm_partial")
            c.agent.note(f'AI tạm mất kết nối giữa chừng; Mai đã nói: "{msg}". {cart_brief(summary)}')
            await self.push_reply(c, reply)
            return
        await self._rules_turn(c, text, why=f" ({kind})")

    # ------------------------------------------------------------------ thao tác chạm khi đang hội thoại
    def _describe_action(self, action: dict, reply: Reply) -> str:
        kind = action.get("type")
        name = ""
        if action.get("entry_id"):
            try:
                name = self.dm.menu.get(action["entry_id"]).name
            except KeyError:
                name = action["entry_id"]
        what = {
            "add": f"Khách bấm thêm {action.get('qty', 1)} {name} trên màn hình.",
            "remove": f"Khách bấm bỏ {name} trên màn hình.",
            "set_qty": f"Khách chỉnh số lượng {name} thành {action.get('qty')} trên màn hình.",
            "checkout": "Khách bấm Thanh toán: màn hình đang hiện phiếu gọi món.",
            "confirm": f"Khách bấm xác nhận đơn, thanh toán bằng {'tiền mặt' if action.get('method') == 'cash' else 'mã QR'}.",
            "edit": "Khách bấm Sửa món.",
            "recommend": "Khách bấm nút gợi ý món.",
            "cancel": "Khách bấm huỷ đơn.",
        }.get(kind or "", f"Khách thao tác trên màn hình: {kind}.")
        said = f' Mai (tự động) đã nói: "{reply.text}".' if reply.text else ""
        return f"{what}{said}"

    # ------------------------------------------------------------------ xử lý đầu vào (chế độ bộ luật)
    async def on_text(self, c: Ctx, text: str) -> None:
        async with c.lock:
            reply = await asyncio.to_thread(self.dm.handle, c.session, text)
        await self.push_reply(c, reply)

    async def on_action(self, c: Ctx, action: dict) -> None:
        if not self.realtime:
            async with c.lock:
                reply = await asyncio.to_thread(self.dm.handle_action, c.session, action)
            await self.push_reply(c, reply)
            return
        kind = action.get("type")
        if kind == "greet":
            await self.start(c)
            return
        await self.interrupt(c, note=False)
        s = c.session
        if s.state == "done" and kind != "reset":
            c.agent = None
        try:
            async with c.lock:
                reply = self.dm.handle_action(s, action)
        except (KeyError, ValueError, TypeError) as e:
            log.info("thao tác không hợp lệ %s: %s", action, e)
            return
        if kind == "reset":
            c.agent = None
        elif kind == "cancel" and c.agent is not None:
            c.agent.note(self._describe_action(action, reply) + " Mâm đã trống.")
        elif c.agent is not None:
            c.agent.note(self._describe_action(action, reply) + " " + cart_brief(c.agent.toolbox.cart_summary()))
        await self.push_reply(c, reply)

    # ------------------------------------------------------------------ âm thanh micro
    async def on_audio(self, c: Ctx, pcm: bytes) -> None:
        if not (self.speech and c.vad and c.listening):
            return
        import numpy as np

        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments = c.vad.accept(x)  # type: ignore[attr-defined]
        speaking = c.vad.is_speaking()  # type: ignore[attr-defined]
        if speaking and not c.speaking:  # khách bắt đầu nói
            c.speech_t0 = time.monotonic()
            c.spoke_over = self._busy(c)
            c.barged = False
            c.live = list(c.preroll)
            c.live_len = sum(len(a) for a in c.live)
            c.partial_len = c.live_len
            c.partial_text = ""
        if speaking != c.speaking:
            c.speaking = speaking
            await self.send(c, {"type": "vad", "speaking": speaking})
        if speaking:
            c.live.append(x)
            c.live_len += len(x)
            if self.realtime:
                await self._while_speaking(c)
        else:
            c.preroll.append(x)
        for seg in segments:
            c.live, c.live_len, c.partial_len = [], 0, 0
            await self._utterance(c, seg)

    async def _while_speaking(self, c: Ctx) -> None:
        import numpy as np

        dur_ms = (time.monotonic() - c.speech_t0) * 1000
        want_barge = self.conv.barge_in and not c.barged and self._busy(c) and dur_ms >= self.conv.barge_in_min_ms
        step = int(0.6 * SR)
        if not c.partial_busy and c.live and (want_barge or (self.conv.partial_asr and c.live_len - c.partial_len >= step)):
            c.partial_busy = True
            c.partial_len = c.live_len
            asyncio.ensure_future(self._partial(c, np.concatenate(c.live)))

    async def _partial(self, c: Ctx, samples) -> None:
        try:
            res = await asyncio.to_thread(self.speech.asr.transcribe, samples)  # type: ignore[union-attr]
        except Exception as e:  # noqa: BLE001
            log.debug("partial ASR lỗi: %s", e)
            return
        finally:
            c.partial_busy = False
        text = res.text.strip()
        if not c.speaking or not text:
            return
        c.partial_text = text
        if self.conv.partial_asr:
            await self.send(c, {"type": "asr_partial", "text": text})
        # Ngắt lời: khách nói đủ lâu, có chữ thật, không phải tiếng vọng của Mai, không chỉ là "ừ/dạ"
        out = c.out
        if (self.conv.barge_in and not c.barged and self._busy(c)
                and (time.monotonic() - c.speech_t0) * 1000 >= self.conv.barge_in_min_ms
                and not is_backchannel(text) and not (out and looks_like_echo(text, out.recent_spoken()))):
            c.barged = True
            log.info("khách ngắt lời: %r", text)
            await self.interrupt(c)

    async def _utterance(self, c: Ctx, seg) -> None:
        if len(seg) < SR * 0.3:
            return
        res = await asyncio.to_thread(self.speech.asr.transcribe, seg)  # type: ignore[union-attr]
        text = res.text.strip()
        await self.send(c, {"type": "asr", "text": text, "latency_ms": round(res.latency_ms, 1)})
        if not text:
            return
        if self.realtime and c.spoke_over and not c.barged:
            # Khách nói khi Mai đang nói mà chưa tính là ngắt lời: "ừ/dạ" hoặc tiếng vọng thì bỏ qua
            out = c.out
            last_clip = out is not None and c.turn is not None and c.turn.done() and out.heard_seq >= len(out.clips) - 1
            if self._busy(c) and is_backchannel(text) and not last_clip:
                return
            if out and looks_like_echo(text, out.recent_spoken()):
                log.info("bỏ qua tiếng vọng: %r", text)
                return
        await self.on_user(c, text)

    async def end_audio(self, c: Ctx) -> None:
        if not (self.speech and c.vad):
            return
        for seg in c.vad.flush():  # type: ignore[attr-defined]
            await self._utterance(c, seg)

    def on_playback(self, c: Ctx, data: dict) -> None:
        """Trình duyệt báo tình trạng phát: {"state": "start"|"idle", "turn": n, "seq": i}."""
        st = data.get("state")
        c.play_at = time.monotonic()
        if st == "start":
            c.playing = True
            out = c.out
            if out and data.get("turn") == out.turn and isinstance(data.get("seq"), int):
                out.heard_seq = max(out.heard_seq, data["seq"])
        elif st == "idle":
            c.playing = False

    # ------------------------------------------------------------------ nền
    async def background(self) -> None:
        import httpx

        poll = self.cfg.store.payment.confirm_mode == "sepay_polling"
        interval = self.cfg.store.payment.sepay.poll_interval_seconds
        client = httpx.Client() if poll else None
        last_poll = 0.0
        if self.speech and self.realtime:  # câu đệm có sẵn trong cache -> phát tức thì
            from ..textnorm import tts_normalize

            for f in self.fillers:
                await asyncio.to_thread(self.speech.tts.get, tts_normalize(f))
        while True:
            await asyncio.sleep(1)
            try:
                for c in list(self.ctxs.values()):
                    if self._busy(c):
                        c.session.updated_at = time.time()  # đang nói chuyện thì không tính là bỏ đi
                        continue
                    r = self.dm.tick(c.session)
                    if r:
                        if r.end:  # khách bỏ đi: kết thúc cuộc nói chuyện
                            c.agent = None
                        elif c.agent is not None:
                            c.agent.note(f'Mã QR đã hết hạn, đơn chưa thanh toán; Mai đã nói: "{r.text}".')
                        await self.push_reply(c, r)
                    if not c.sockets and time.time() - c.session.updated_at > 3600:
                        self.ctxs.pop(c.session.id, None)
                self.storage.expire_overdue()
                if poll and client and time.time() - last_poll >= interval:
                    last_poll = time.time()
                    await asyncio.to_thread(self.payments.sepay_poll_once, client)
            except Exception as e:  # không để vòng nền chết
                log.warning("background: %s", e)


def _is_local(host: str | None) -> bool:
    try:
        return bool(host) and ipaddress.ip_address(host).is_loopback  # type: ignore[arg-type]
    except ValueError:
        return host in ("localhost", "testclient")


def _make_provider(cfg: StoreConfig) -> Any:
    conv = cfg.store.conversation
    if conv.engine != "llm":
        return None
    from ..agent.provider import AnthropicProvider

    if not AnthropicProvider.available(conv):
        log.warning("Chưa đặt biến môi trường %s (hoặc chưa cài gói anthropic): hội thoại dùng bộ luật offline. "
                    "Đặt API key để bật AI nói chuyện thời gian thực.", conv.api_key_env)
        return None
    return AnthropicProvider(conv)


def create_app(store_dir: str | Path, db_path: str | Path = "data/aistaff.db", data_dir: str | Path = "data",
               speech: bool | None = None, now_fn=None, provider: Any = "auto") -> FastAPI:
    """provider: "auto" = Claude nếu có API key; None = luôn dùng bộ luật; hoặc truyền provider khác (test)."""
    cfg = load_store(store_dir)
    data = Path(data_dir)
    data.mkdir(parents=True, exist_ok=True)
    storage = Storage(db_path)
    use_speech = cfg.store.speech.enabled if speech is None else speech
    engine = None
    if use_speech:
        from ..speech.engine import SpeechEngine

        engine = SpeechEngine(cfg, data_dir=data)
    llm = None
    if cfg.store.llm_fallback.enabled:
        from ..llm import LLMRewriter

        llm = LLMRewriter(cfg.store.llm_fallback)
    if isinstance(provider, str) and provider == "auto":
        provider = _make_provider(cfg)
    k = Kiosk(cfg, storage, data, engine, llm, now_fn=now_fn, provider=provider)
    log.info("Hội thoại: %s%s", k.mode(), f" ({cfg.store.conversation.model})" if k.realtime else "")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        k.loop = asyncio.get_running_loop()
        bg = asyncio.create_task(k.background())
        try:
            yield
        finally:
            bg.cancel()

    app = FastAPI(title=f"AI Staff - {cfg.store.name}", lifespan=lifespan)
    app.state.kiosk = k

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    if (WEBUI / "assets").exists():
        app.mount("/assets", StaticFiles(directory=WEBUI / "assets"), name="assets")
    media_dir = (cfg.base_dir / "images").resolve() if cfg.base_dir else None

    def admin_guard(request: Request, pin: str | None) -> None:
        want = os.environ.get("ADMIN_PIN")
        if want:
            if pin != want:
                raise HTTPException(401, "Sai mã PIN quản lý")
        elif not _is_local(request.client.host if request.client else None):
            raise HTTPException(403, "Đặt biến môi trường ADMIN_PIN để quản lý từ xa")

    @app.get("/", response_class=HTMLResponse)
    def index():
        if (WEBUI / "index.html").exists():
            return FileResponse(WEBUI / "index.html", headers={"Cache-Control": "no-cache"})
        return HTMLResponse("<h1>Giao diện chưa được build</h1><p>Chạy: <code>cd web && npm install && npm run build</code></p>",
                            status_code=503)

    @app.get("/media/{path:path}")
    def media(path: str) -> FileResponse:
        if not media_dir:
            raise HTTPException(404)
        p = (media_dir / path).resolve()
        if media_dir not in p.parents or not p.is_file():
            raise HTTPException(404)
        return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page() -> FileResponse:
        return FileResponse(STATIC / "admin.html")

    @app.get("/healthz")
    def health() -> dict:
        return {"ok": True, "store": cfg.store.id, "speech": bool(engine), "llm": bool(llm), "sessions": len(k.ctxs),
                "conversation": k.mode(), "model": cfg.store.conversation.model if k.realtime else None,
                "llm_error": k.llm_error or None}

    def _img(e) -> str:
        if not e.image:
            return ""
        return e.image if e.image.startswith(("http://", "https://", "/")) else f"/media/{e.image}"

    @app.get("/api/config")
    def public_config() -> dict:
        st = cfg.store
        conv = st.conversation
        eng = k.dm.engine
        promos = [{"id": p.id, "name": p.name, "pitch": p.pitch, "type": p.type, "reward": eng.reward_text(p),
                   "min_subtotal": p.min_subtotal} for p in eng.active()]
        entries = []
        for e in cfg.menu.entries():
            d = {"id": e.id, "name": e.name, "price": e.price, "kind": e.kind, "category": e.category,
                 "description": getattr(e, "description", ""), "unit": getattr(e, "unit", "phần"),
                 "best_seller": e.best_seller, "vegetarian": e.is_vegetarian, "spicy": e.taste.cay,
                 "taste": e.taste.model_dump(), "style": e.style, "temp": e.temp, "portion": e.portion,
                 "contains": list(e.contains), "pairs_with": list(e.pairs_with), "image": _img(e),
                 "options": [o.model_dump() for o in e.options],
                 "promos": [p.name for p in eng.promos_for_entry(e.id)]}
            if e.kind == "combo":
                d["serves"] = e.serves  # type: ignore[union-attr]
                d["value"] = cfg.menu.combo_value(e)  # type: ignore[arg-type]
                d["items"] = [{"id": p.item, "name": cfg.menu.item(p.item).name, "qty": p.qty}
                              for p in e.items]  # type: ignore[union-attr]
            entries.append(d)
        cats = [{"id": c.id, "name": c.name} for c in cfg.menu.categories]
        if cfg.menu.combos:
            cats.insert(0, {"id": "combo", "name": "Combo"})
        return {"store": {"id": st.id, "name": st.name, "short_name": st.display_name, "address": st.address,
                          "phone": st.phone, "assistant": st.assistant.name, "allow_cash": st.payment.allow_cash,
                          "customer_pronoun": st.assistant.customer_pronoun,
                          "qr_expire_minutes": st.payment.qr_expire_minutes},
                "categories": cats, "entries": entries, "promotions": promos, "speech": bool(engine),
                "conversation": {"engine": "llm" if k.realtime else "rules",
                                 "barge_in": bool(k.realtime and conv.barge_in),
                                 "partial_asr": bool(conv.partial_asr)}}

    @app.get("/tts/{name}")
    def tts_file(name: str) -> FileResponse:
        if not engine or "/" in name or not name.endswith(".wav"):
            raise HTTPException(404)
        p = engine.tts.dir / name
        if not p.exists():
            raise HTTPException(404)
        return FileResponse(p, media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400"})

    @app.post("/webhooks/sepay")
    async def sepay_webhook(request: Request, authorization: str | None = Header(default=None)) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"success": False, "message": "JSON không hợp lệ"}, status_code=400)
        code, resp = k.payments.sepay_webhook(authorization, body)
        return JSONResponse(resp, status_code=code)

    @app.get("/api/admin/orders")
    def admin_orders(request: Request, status: str | None = None, pin: str | None = None) -> list[dict]:
        admin_guard(request, pin)
        return [o.to_dict() for o in storage.list_orders(status, limit=100)]

    @app.post("/api/admin/orders/{code}/paid")
    def admin_paid(code: str, request: Request, pin: str | None = None) -> dict:
        admin_guard(request, pin)
        ok = k.payments.confirm_manual(code)
        if not ok and not storage.get_order(code):
            raise HTTPException(404, "Không có đơn này")
        return {"ok": ok, "order": storage.get_order(code).to_dict()}  # type: ignore[union-attr]

    @app.post("/api/admin/orders/{code}/cancel")
    def admin_cancel(code: str, request: Request, pin: str | None = None) -> dict:
        admin_guard(request, pin)
        return {"ok": storage.set_status(code.upper(), "cancelled")}

    @app.get("/api/admin/stats")
    def admin_stats(request: Request, pin: str | None = None) -> dict:
        admin_guard(request, pin)
        return {**storage.stats(), "payments": storage.payments(20)}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        c = k.ctx(ws.query_params.get("session"))
        c.sockets.add(ws)
        await ws.send_text(json.dumps({"type": "session", "session_id": c.session.id, "state": c.session.state,
                                       "speech": bool(engine)}, ensure_ascii=False))
        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    await k.on_audio(c, msg["bytes"])
                    continue
                data = json.loads(msg.get("text") or "{}")
                t = data.get("type")
                if t == "text" and data.get("text", "").strip():
                    await k.on_user(c, data["text"][:500])
                elif t == "action":
                    await k.on_action(c, data.get("action") or {})
                elif t == "start":
                    await k.start(c)
                elif t == "playback":
                    k.on_playback(c, data)
                elif t == "listen":
                    c.listening = bool(data.get("on")) and bool(engine)
                    if c.vad and c.listening:
                        c.vad.reset()  # type: ignore[attr-defined]
                    if not c.listening:
                        await k.end_audio(c)
                    await k.send(c, {"type": "listening", "on": c.listening})
                elif t == "ping":
                    await ws.send_text('{"type":"pong"}')
        except WebSocketDisconnect:
            pass
        finally:
            c.sockets.discard(ws)
            if not c.sockets:  # màn hình tắt / mất kết nối: dừng lượt đang chạy, khỏi tốn token
                c.playing = False
                await k.interrupt(c, note=False)

    return app


def app_from_env() -> FastAPI:
    """Cho `uvicorn aistaff.kiosk.server:app_from_env --factory`."""
    return create_app(os.environ.get("AISTAFF_STORE", "config/stores/quan-ngon"),
                      os.environ.get("AISTAFF_DB", "data/aistaff.db"), os.environ.get("AISTAFF_DATA", "data"))
