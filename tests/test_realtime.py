"""Vòng hội thoại thời gian thực ở kiosk: stream chữ -> câu -> TTS, câu đệm, ngắt lời, dự phòng bộ luật.

LLM được thay bằng ScriptedProvider (kịch bản cố định) để kiểm tra logic của kiosk; xem test_local_llm.py
và test_agent.py cho phần giao thức với LLM local / Claude.
"""

import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aistaff.agent import ProviderError
from aistaff.kiosk.realtime import cut_sentences, is_backchannel, looks_like_echo, strip_lead_da
from aistaff.kiosk.server import Kiosk, create_app
from aistaff.speech.asr import ASRResult
from aistaff.textnorm import tts_normalize

from .conftest import STORE, TUE_HAPPY
from .fakes import ScriptedProvider


# ============================================================ cắt câu & lọc
def test_cut_sentences():
    sents, rest = cut_sentences("Dạ, em lên món ngay. Anh dùng thêm", first=True, final=False)
    assert sents == ["Dạ, em lên món ngay."] and rest == " Anh dùng thêm"
    # câu đầu dài: cắt sớm ở dấu phẩy để phát nhanh
    sents, rest = cut_sentences("Dạ vâng, phở bò tái ở quán mình, nước dùng hầm", first=True, final=False)
    assert sents == ["Dạ vâng, phở bò tái ở quán mình,"]
    # không cắt ở dấu chấm trong số tiền
    sents, rest = cut_sentences("Tổng 115.000đ ạ", first=False, final=False)
    assert sents == [] and rest == "Tổng 115.000đ ạ"
    sents, rest = cut_sentences("x " * 120, first=False, final=False)
    assert sents and len(sents[0]) <= 170
    assert cut_sentences("ạ", first=False, final=True) == (["ạ"], "")


def test_text_filters():
    assert strip_lead_da("Dạ, em thêm rồi ạ.") == "Em thêm rồi ạ." and strip_lead_da("Dạ vâng ạ.") == ""
    assert is_backchannel("ừ") and is_backchannel("vâng vâng") and not is_backchannel("ừ cho anh trà đá")
    assert looks_like_echo("em thêm một tô phở", "Dạ, em thêm một tô phở bò tái rồi ạ.")
    assert not looks_like_echo("cho anh thêm trà đá", "Dạ, em thêm một tô phở bò tái rồi ạ.")


# ============================================================ kiosk với giọng nói giả lập (không cần model)
class FakeWS:
    def __init__(self):
        self.msgs = []

    async def send_text(self, data):
        self.msgs.append(json.loads(data))

    def of(self, kind):
        return [m for m in self.msgs if m["type"] == kind]


class FakeTTS:
    dir = Path("/nonexistent")

    def __init__(self):
        self.said = []

    def get(self, text):
        self.said.append(text)
        return Path(f"/nonexistent/{len(self.said)}.wav"), 1.0


class FakeASR:
    def __init__(self):
        self.text = ""

    def transcribe(self, samples, sample_rate=16000):
        return ASRResult(self.text, len(samples) / 16000, 3.0)


class FakeSpeech:
    def __init__(self):
        self.tts = FakeTTS()
        self.asr = FakeASR()

    def new_vad(self):
        return None


@pytest.fixture
def fast_cfg(cfg):
    c = cfg.model_copy(deep=True)
    c.store.conversation.filler_delay_ms = 20
    c.store.conversation.barge_in_min_ms = 100
    return c


def make_kiosk(cfg, storage, tmp_path, script, delay=0.0, speech=True, first_delay=0.0):
    p = ScriptedProvider(script, delay=delay, first_delay=first_delay)
    k = Kiosk(cfg, storage, tmp_path, speech=FakeSpeech() if speech else None, now_fn=lambda: TUE_HAPPY, provider=p)
    c = k.ctx(None)
    ws = FakeWS()
    c.sockets.add(ws)
    return k, c, ws, p


def test_filler_then_streamed_sentences(fast_cfg, storage, tmp_path):
    long = "Dạ, phở bò tái nước dùng hầm xương 12 tiếng, thịt mềm. Anh dùng thử nhé?"
    k, c, ws, _ = make_kiosk(fast_cfg, storage, tmp_path, [[long]], delay=0.01, first_delay=0.15)

    async def scenario():
        await k.start(c)
        await k.on_user(c, "phở bò có ngon không em")
        await c.turn

    asyncio.run(scenario())
    tts = [m for m in ws.of("tts") if m.get("turn")]
    assert tts[0]["filler"] is True  # LLM chưa kịp nói -> "Dạ" đệm phát trước
    turn_said = k.speech.tts.said[-len(tts):]
    assert turn_said[0] in [tts_normalize(f) for f in k.fillers]
    assert not turn_said[1].lower().startswith("dạ")  # đã đệm "Dạ" thì bỏ "Dạ," ở câu đầu
    assert "".join(m["text"] for m in ws.of("assistant_delta")) == long
    end = ws.of("assistant_end")[-1]
    assert end["text"] == long and end["state"] == "ordering"
    assert [m["seq"] for m in tts] == list(range(len(tts)))


def test_barge_in_cancels_turn_and_notes_agent(fast_cfg, storage, tmp_path):
    np = pytest.importorskip("numpy")
    k, c, ws, p = make_kiosk(fast_cfg, storage, tmp_path,
                             [["Dạ, quán mình có phở, bún, cơm tấm, món nào cũng ngon. " * 6], ["Dạ, trà đá đây ạ."]],
                             delay=0.02)

    async def scenario():
        await k.start(c)
        await k.on_user(c, "quán có món gì")
        await asyncio.sleep(0.15)
        assert not c.turn.done()
        # khách nói chen: chỉ "ừ" -> không ngắt
        c.speaking, c.speech_t0 = True, time.monotonic() - 1
        k.speech.asr.text = "ừ"
        await k._partial(c, np.zeros(8000, dtype=np.float32))
        assert not c.turn.done()
        # tiếng vọng của chính Mai -> không ngắt
        k.speech.asr.text = "quán mình có phở bún cơm tấm"
        await k._partial(c, np.zeros(8000, dtype=np.float32))
        assert not c.turn.done()
        # khách thật sự nói chen -> Mai dừng
        k.speech.asr.text = "cho anh một trà đá"
        await k._partial(c, np.zeros(8000, dtype=np.float32))
        assert c.turn.done() and c.barged
        c.speaking = False
        await k.on_user(c, "cho anh một trà đá")
        await c.turn

    asyncio.run(scenario())
    assert ws.of("stop_audio") and ws.of("asr_partial")[-1]["text"] == "cho anh một trà đá"
    last_user = p.calls[-1]["messages"][-1]["content"]
    notes = [b["text"] for b in last_user if b["type"] == "text"]
    assert any("Khách ngắt lời" in n for n in notes) and notes[-1] == "cho anh một trà đá"


def test_touch_action_becomes_note(fast_cfg, storage, tmp_path):
    k, c, ws, p = make_kiosk(fast_cfg, storage, tmp_path, [["Dạ, anh dùng thêm gì nữa không ạ?"]], speech=False)

    async def scenario():
        await k.start(c)
        await k.on_action(c, {"type": "add", "entry_id": "tra-tac", "qty": 2})
        await k.on_user(c, "vậy thôi")
        await c.turn

    asyncio.run(scenario())
    assert c.session.cart.qty_of("tra-tac") == 2 and ws.of("reply")
    user = p.calls[0]["messages"][-1]["content"]
    assert user[0]["text"].startswith("[Hệ thống: Khách bấm thêm 2 Trà tắc trên màn hình.")
    assert "Mâm hiện có: 2 ly Trà tắc" in user[0]["text"] and user[1]["text"] == "vậy thôi"


# ============================================================ qua WebSocket
def recv_until(ws, kind, limit=60):
    seen = []
    for _ in range(limit):
        m = json.loads(ws.receive_text())
        seen.append(m)
        if m["type"] == kind:
            return m, seen
    raise AssertionError(f"không thấy {kind}: {[x['type'] for x in seen]}")


@pytest.fixture
def rt_client(tmp_path, monkeypatch):
    monkeypatch.delenv("ADMIN_PIN", raising=False)
    p = ScriptedProvider()
    app = create_app(STORE, tmp_path / "t.db", tmp_path, speech=False, now_fn=lambda: TUE_HAPPY, provider=p)
    with TestClient(app) as c:
        yield c, p


def test_ws_realtime_order_to_payment(rt_client):
    client, p = rt_client
    p.add([("tool", "add_to_cart", {"item_id": "pho-bo-tai", "quantity": 2}),
           ("tool", "add_to_cart", {"item_id": "tra-da", "quantity": 1})],
          ["Dạ, em thêm 2 tô phở bò tái và 1 trà đá rồi ạ."],
          [("tool", "review_order", {})],
          ["Dạ, tổng của anh là 103 nghìn 500 đồng. Anh quét QR hay trả tiền mặt ạ?"],
          [("tool", "place_order", {"payment_method": "vietqr"})],
          ["Dạ, mời anh quét mã QR trên màn hình ạ."])
    cfgd = client.get("/api/config").json()["conversation"]
    assert cfgd["engine"] == "llm" and cfgd["brain"] == "scripted:scripted"
    with client.websocket_connect("/ws") as ws:
        recv_until(ws, "session")
        ws.send_text(json.dumps({"type": "start"}))
        recv_until(ws, "reply")
        ws.send_text(json.dumps({"type": "text", "text": "cho anh hai tô phở bò tái với một trà đá"}))
        end, seen = recv_until(ws, "assistant_end")
        kinds = [m["type"] for m in seen]
        assert kinds[0] == "assistant_start" and "assistant_delta" in kinds and "cart" in kinds
        assert end["cart"]["subtotal"] == 115000 and end["tools"] == ["add_to_cart", "add_to_cart"]
        ws.send_text(json.dumps({"type": "text", "text": "tính tiền"}))
        end, seen = recv_until(ws, "assistant_end")
        assert end["state"] == "confirm_order"
        ws.send_text(json.dumps({"type": "text", "text": "quét mã"}))
        end, seen = recv_until(ws, "assistant_end")
        st = [m for m in seen if m["type"] == "state" and m.get("qr")][0]
        code = st["qr"]["code"]
        assert end["state"] == "awaiting_payment" and st["qr"]["amount"] == end["cart"]["total"]
        assert client.post(f"/api/admin/orders/{code}/paid").json()["ok"]
        paid, _ = recv_until(ws, "reply")
        assert paid["intent"] == "paid" and paid["state"] == "done"
    health = client.get("/healthz").json()
    assert health["conversation"] == "llm" and health["brain"] == "scripted:scripted"


def test_ws_llm_failure_falls_back_to_rules(rt_client):
    client, p = rt_client
    p.add(ProviderError("mất mạng", "network"))
    with client.websocket_connect("/ws") as ws:
        recv_until(ws, "session")
        ws.send_text(json.dumps({"type": "start"}))
        recv_until(ws, "reply")
        ws.send_text(json.dumps({"type": "text", "text": "cho tôi hai tô phở bò tái"}))
        end, _ = recv_until(ws, "assistant_end")
        assert end["error"] == "network"
        r, _ = recv_until(ws, "reply")  # bộ luật offline trả lời thay
        assert r["cart"]["subtotal"] == 110000
        # đang trong thời gian nghỉ LLM: đi thẳng bộ luật, không gọi LLM
        n = len(p.calls)
        ws.send_text(json.dumps({"type": "text", "text": "thêm một trà đá"}))
        r, seen = recv_until(ws, "reply")
        assert r["cart"]["subtotal"] == 115000 and len(p.calls) == n
        assert "assistant_start" not in [m["type"] for m in seen]
    assert client.get("/healthz").json()["conversation"] == "llm-offline"
