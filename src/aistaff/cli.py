"""Dòng lệnh: aistaff <lệnh> --store config/stores/<quán>

  validate   kiểm tra cấu hình quán (menu, combo, ưu đãi, tài khoản)
  chat       trò chuyện bằng bàn phím (thử kịch bản không cần micro)
  serve      chạy kiosk server (giao diện http://<ip>:8000, quản lý /admin)
  qr         tạo mã VietQR (in ra terminal / lưu PNG)
  hotwords   in danh sách hotword sinh từ menu (cho ASR)
  prerender  tổng hợp sẵn giọng nói cho các câu cố định (phản hồi tức thì trên máy yếu)
  voice-file chạy thử pipeline giọng nói với 1 file WAV (VAD -> ASR -> hội thoại -> TTS)
  bench      đo tốc độ NLU + hội thoại trên thiết bị
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path


def _now_fn(cfg, at: str | None):
    if not at:
        return None
    from zoneinfo import ZoneInfo

    t = datetime.fromisoformat(at).replace(tzinfo=ZoneInfo(cfg.store.timezone))
    return lambda: t


def cmd_validate(a) -> int:
    from .config import load_store
    from .promotions import PromotionEngine

    cfg = load_store(a.store)
    eng = PromotionEngine(cfg)
    print(f"✓ {cfg.store.name}: {len(cfg.menu.items)} món, {len(cfg.menu.combos)} combo, {len(cfg.promotions)} ưu đãi")
    for c in cfg.menu.combos:
        print(f"  combo {c.name}: {c.price:,}đ (giá lẻ {cfg.menu.combo_value(c):,}đ)")
    print("  ưu đãi đang chạy lúc này:", ", ".join(p.name for p in eng.active()) or "không có")
    p = cfg.store.payment
    print(f"  nhận tiền: BIN {p.bank_bin} ({p.bank_name}) TK {p.account_number} - {p.account_name}; xác nhận: {p.confirm_mode}")
    return 0


def cmd_chat(a) -> int:
    from .config import load_store
    from .dialog import DialogManager
    from .storage import Storage

    cfg = load_store(a.store)
    dm = DialogManager(cfg, Storage(a.db), now_fn=_now_fn(cfg, a.at))
    s = dm.new_session()
    r = dm.greet(s)
    print(f"\n🤖 {r.text}\n")
    lines = a.say or []
    while True:
        try:
            text = lines.pop(0) if a.say is not None else input("🧑 ")
        except (EOFError, KeyboardInterrupt, IndexError):
            break
        if a.say is not None:
            print(f"🧑 {text}")
        if text.strip() in ("/q", "/quit", "exit"):
            break
        if text.strip() == "/paid" and s.order_code:
            r = dm.payment_received(s)
        else:
            r = dm.handle(s, text)
        print(f"🤖 {r.text}")
        if a.debug:
            print("   [nlu]", json.dumps({k: v for k, v in (r.nlu or {}).items() if v}, ensure_ascii=False))
            print(f"   [state={r.state} intent={r.intent} {r.latency_ms} ms]")
        if r.qr:
            from .vietqr import to_terminal

            print(to_terminal(r.qr["payload"]))
            print("   (gõ /paid để giả lập ngân hàng báo đã nhận tiền)")
        print()
        if r.end:
            s = dm.new_session()
            if a.say is None:
                print(f"🤖 {dm.greet(s).text}\n")
    return 0


def cmd_serve(a) -> int:
    import uvicorn

    from .kiosk.server import create_app

    speech = True if a.speech else (False if a.no_speech else None)
    app = create_app(a.store, a.db, a.data, speech=speech)
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")
    return 0


def cmd_qr(a) -> int:
    from . import vietqr
    from .config import load_store

    cfg = load_store(a.store)
    p = cfg.store.payment
    payload = vietqr.build_payload(p.bank_bin, p.account_number, a.amount, a.content)
    print(payload)
    if a.png:
        vietqr.to_png(payload, a.png)
        print("Đã lưu", a.png)
    else:
        print(vietqr.to_terminal(payload))
    return 0


def cmd_hotwords(a) -> int:
    from .config import load_store
    from .speech.asr import menu_hotwords

    print("\n".join(menu_hotwords(load_store(a.store).menu)))
    return 0


def _fixed_phrases(dm) -> list[str]:
    """Câu cố định hay nói -> dựng sẵn âm thanh."""
    from .speech.tts import split_sentences

    s = dm.new_session(seed=0)
    out: list[str] = []
    for i in range(6):  # nhiều biến thể lời chào
        s.rng.seed(i)
        s.announced.clear()
        out += split_sentences(dm.greet(s).speech, 110)
    for t in ["gợi ý món", "abc xyz", "có khuyến mãi gì không", "thực đơn", "chốt đơn", "hướng dẫn"]:
        s2 = dm.new_session(seed=1)
        dm.greet(s2)
        out += split_sentences(dm.handle(s2, t).speech, 110)
    return list(dict.fromkeys(out))


def cmd_prerender(a) -> int:
    from .config import load_store
    from .dialog import DialogManager
    from .speech.engine import SpeechEngine

    cfg = load_store(a.store)
    eng = SpeechEngine(cfg, data_dir=a.data)
    dm = DialogManager(cfg)
    phrases = _fixed_phrases(dm)
    t0 = time.perf_counter()
    for p in phrases:
        eng.tts.get(p)
    print(f"Đã dựng sẵn {len(phrases)} câu ({eng.tts.misses} mới) trong {time.perf_counter() - t0:.1f}s -> {eng.tts.dir}")
    return 0


def cmd_voice_file(a) -> int:
    from .config import load_store
    from .dialog import DialogManager
    from .speech.audio import read_wav, resample
    from .speech.engine import SpeechEngine

    cfg = load_store(a.store)
    eng = SpeechEngine(cfg, data_dir=a.data)
    dm = DialogManager(cfg, now_fn=_now_fn(cfg, a.at))
    s = dm.new_session()
    dm.greet(s)
    for wav in a.wav:
        x, sr = read_wav(wav)
        x = resample(x, sr, 16000)
        vad = eng.new_vad()
        segs = []
        for i in range(0, len(x), 1600):  # mô phỏng micro: khung 100 ms
            segs += vad.accept(x[i : i + 1600])
        segs += vad.flush()
        for seg in segs or [x]:
            res = eng.asr.transcribe(seg)
            t0 = time.perf_counter()
            r = dm.handle(s, res.text)
            t_dlg = (time.perf_counter() - t0) * 1000
            first = r.speech.split(". ")[0]
            path, ms = eng.tts.get(first)
            print(f"[{Path(wav).name}] ASR {res.latency_ms:.0f} ms: {res.text!r}")
            print(f"  -> {r.intent} ({t_dlg:.1f} ms) | TTS câu đầu {ms:.0f} ms -> {path}")
            print(f"  🤖 {r.text}")
    return 0


def cmd_bench(a) -> int:
    from .config import load_store
    from .dialog import DialogManager

    cfg = load_store(a.store)
    dm = DialogManager(cfg)
    utts = ["cho tôi hai tô phở bò tái và một ly trà đá", "gợi ý món cay không có hải sản", "thêm một phần cầm tấm sườn bì chả",
            "có khuyến mãi gì không", "bỏ trà đá", "nhà có 4 người dưới 80 nghìn một người", "chốt đơn"]
    n = 0
    t0 = time.perf_counter()
    for _ in range(a.rounds):
        s = dm.new_session(seed=1)
        dm.greet(s)
        for u in utts:
            dm.handle(s, u)
            n += 1
    el = time.perf_counter() - t0
    print(f"{n} lượt hội thoại trong {el:.2f}s -> {el / n * 1000:.2f} ms/lượt (NLU + gợi ý + ưu đãi + tính tiền)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aistaff", description="Nhân viên AI gọi món bằng giọng nói tiếng Việt")
    ap.add_argument("--store", default="config/stores/quan-ngon", help="thư mục cấu hình quán")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    c = sub.add_parser("chat")
    c.add_argument("--db", default="data/aistaff.db")
    c.add_argument("--at", help="giả lập thời điểm, vd '2026-11-03 15:00' (thử ưu đãi theo giờ)")
    c.add_argument("--say", nargs="*", help="chạy kịch bản không tương tác")
    c.add_argument("--debug", action="store_true")
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--db", default="data/aistaff.db")
    sv.add_argument("--data", default="data")
    g = sv.add_mutually_exclusive_group()
    g.add_argument("--speech", action="store_true", help="bật giọng nói (ghi đè store.yaml)")
    g.add_argument("--no-speech", action="store_true")
    q = sub.add_parser("qr")
    q.add_argument("--amount", type=int)
    q.add_argument("--content", default="")
    q.add_argument("--png")
    sub.add_parser("hotwords")
    pr = sub.add_parser("prerender")
    pr.add_argument("--data", default="data")
    vf = sub.add_parser("voice-file")
    vf.add_argument("wav", nargs="+")
    vf.add_argument("--data", default="data")
    vf.add_argument("--at")
    b = sub.add_parser("bench")
    b.add_argument("--rounds", type=int, default=50)
    a = ap.parse_args(argv)
    fn = {"validate": cmd_validate, "chat": cmd_chat, "serve": cmd_serve, "qr": cmd_qr, "hotwords": cmd_hotwords,
          "prerender": cmd_prerender, "voice-file": cmd_voice_file, "bench": cmd_bench}[a.cmd]
    return fn(a)


if __name__ == "__main__":
    sys.exit(main())
