"""Máy chủ kiosk chạy ngay trên thiết bị edge.

  Trình duyệt (Chromium kiosk / tablet) <--WebSocket--> FastAPI
     - gửi chữ gõ, thao tác chạm, hoặc âm thanh micro PCM16 16 kHz (trình duyệt tự khử vọng AEC)
     - nhận câu trả lời, giỏ hàng, gợi ý, mã QR, link âm thanh TTS để phát
  VAD -> ASR -> NLU/Dialog -> TTS chạy trong thread pool để không chặn event loop.
  /webhooks/sepay nhận báo có tiền -> đẩy màn hình "đã thanh toán" tới đúng phiên khách.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import StoreConfig, load_store
from ..dialog import DialogManager, Reply, Session
from ..payments import PaymentEvent, PaymentHub
from ..storage import Storage

log = logging.getLogger("aistaff.kiosk")
STATIC = Path(__file__).parent / "static"


@dataclass
class Ctx:
    session: Session
    sockets: set = field(default_factory=set)
    vad: object | None = None
    listening: bool = False
    speaking: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Kiosk:
    def __init__(self, cfg: StoreConfig, storage: Storage, data_dir: Path, speech=None, llm=None, now_fn=None):
        self.cfg = cfg
        self.storage = storage
        self.data_dir = data_dir
        self.speech = speech
        self.dm = DialogManager(cfg, storage, now_fn=now_fn, llm=llm)
        self.payments = PaymentHub(cfg, storage, on_paid=self._on_paid)
        self.ctxs: dict[str, Ctx] = {}
        self.by_order: dict[str, str] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

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

    def _on_paid(self, ev: PaymentEvent) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._notify_paid(ev)))

    async def _notify_paid(self, ev: PaymentEvent) -> None:
        sid = self.by_order.get(ev.order_code)
        c = self.ctxs.get(sid) if sid else None
        if not c or c.session.order_code != ev.order_code:
            log.info("Đơn %s đã thanh toán (không còn phiên trên màn hình)", ev.order_code)
            return
        async with c.lock:
            reply = self.dm.payment_received(c.session, ev.amount)
        await self.push_reply(c, reply)

    # ------------------------------------------------------------------ xử lý đầu vào
    async def on_text(self, c: Ctx, text: str) -> None:
        async with c.lock:
            reply = await asyncio.to_thread(self.dm.handle, c.session, text)
        await self.push_reply(c, reply)

    async def on_action(self, c: Ctx, action: dict) -> None:
        async with c.lock:
            reply = await asyncio.to_thread(self.dm.handle_action, c.session, action)
        await self.push_reply(c, reply)

    async def on_audio(self, c: Ctx, pcm: bytes) -> None:
        if not (self.speech and c.vad and c.listening):
            return
        import numpy as np

        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments = c.vad.accept(x)  # type: ignore[attr-defined]
        speaking = c.vad.is_speaking()  # type: ignore[attr-defined]
        if speaking != c.speaking:
            c.speaking = speaking
            await self.send(c, {"type": "vad", "speaking": speaking})
        for seg in segments:
            await self._utterance(c, seg)

    async def _utterance(self, c: Ctx, seg) -> None:
        if len(seg) < 16000 * 0.3:
            return
        res = await asyncio.to_thread(self.speech.asr.transcribe, seg)  # type: ignore[union-attr]
        await self.send(c, {"type": "asr", "text": res.text, "latency_ms": round(res.latency_ms, 1)})
        if res.text.strip():
            await self.on_text(c, res.text)

    async def end_audio(self, c: Ctx) -> None:
        if not (self.speech and c.vad):
            return
        for seg in c.vad.flush():  # type: ignore[attr-defined]
            await self._utterance(c, seg)

    # ------------------------------------------------------------------ nền
    async def background(self) -> None:
        import httpx

        poll = self.cfg.store.payment.confirm_mode == "sepay_polling"
        interval = self.cfg.store.payment.sepay.poll_interval_seconds
        client = httpx.Client() if poll else None
        last_poll = 0.0
        while True:
            await asyncio.sleep(1)
            try:
                for c in list(self.ctxs.values()):
                    r = self.dm.tick(c.session)
                    if r:
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


def create_app(store_dir: str | Path, db_path: str | Path = "data/aistaff.db", data_dir: str | Path = "data",
               speech: bool | None = None, now_fn=None) -> FastAPI:
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
    k = Kiosk(cfg, storage, data, engine, llm, now_fn=now_fn)

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

    def admin_guard(request: Request, pin: str | None) -> None:
        want = os.environ.get("ADMIN_PIN")
        if want:
            if pin != want:
                raise HTTPException(401, "Sai mã PIN quản lý")
        elif not _is_local(request.client.host if request.client else None):
            raise HTTPException(403, "Đặt biến môi trường ADMIN_PIN để quản lý từ xa")

    @app.get("/", response_class=HTMLResponse)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page() -> FileResponse:
        return FileResponse(STATIC / "admin.html")

    @app.get("/healthz")
    def health() -> dict:
        return {"ok": True, "store": cfg.store.id, "speech": bool(engine), "llm": bool(llm), "sessions": len(k.ctxs)}

    @app.get("/api/config")
    def public_config() -> dict:
        st = cfg.store
        promos = [{"id": p.id, "name": p.name, "pitch": p.pitch} for p in k.dm.engine.active()]
        entries = []
        for e in cfg.menu.entries():
            d = {"id": e.id, "name": e.name, "price": e.price, "kind": e.kind, "category": e.category,
                 "description": getattr(e, "description", ""), "unit": getattr(e, "unit", "phần"),
                 "best_seller": e.best_seller, "vegetarian": e.is_vegetarian, "spicy": e.taste.cay,
                 "options": [o.model_dump() for o in e.options],
                 "promos": [p.name for p in k.dm.engine.promos_for_entry(e.id)]}
            if e.kind == "combo":
                d["serves"] = e.serves  # type: ignore[union-attr]
            entries.append(d)
        cats = [{"id": c.id, "name": c.name} for c in cfg.menu.categories]
        if cfg.menu.combos:
            cats.insert(0, {"id": "combo", "name": "Combo"})
        return {"store": {"id": st.id, "name": st.name, "short_name": st.display_name, "address": st.address,
                          "phone": st.phone, "assistant": st.assistant.name, "allow_cash": st.payment.allow_cash},
                "categories": cats, "entries": entries, "promotions": promos, "speech": bool(engine)}

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
                    await k.on_text(c, data["text"][:500])
                elif t == "action":
                    await k.on_action(c, data.get("action") or {})
                elif t == "start":
                    async with c.lock:
                        k.dm.reset(c.session)
                        reply = k.dm.greet(c.session)
                    await k.push_reply(c, reply)
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

    return app


def app_from_env() -> FastAPI:
    """Cho `uvicorn aistaff.kiosk.server:app_from_env --factory`."""
    return create_app(os.environ.get("AISTAFF_STORE", "config/stores/quan-ngon"),
                      os.environ.get("AISTAFF_DB", "data/aistaff.db"), os.environ.get("AISTAFF_DATA", "data"))
