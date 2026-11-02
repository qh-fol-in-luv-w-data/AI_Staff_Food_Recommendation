"""Đo tốc độ + độ chính xác giọng nói NGAY TRÊN THIẾT BỊ (tái lập số liệu trong docs/02 và docs/03).

  python scripts/bench_speech.py [--store config/stores/quan-ngon] [--threads 2] [--wav-dir thu_muc_wav_that]

1) TTS Piper đọc các câu gọi món mẫu (đo RTF TTS)
2) ASR Zipformer nhận dạng lại: greedy vs beam + hotwords từ menu (đo WER, RTF, độ trễ)
3) Đưa kết quả ASR qua NLU (đo tỉ lệ hiểu đúng món + ý định)
Có thể thêm file WAV giọng thật: đặt tên <số>.wav và file <số>.txt chứa câu đúng.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PHRASES = [
    "cho tôi hai tô phở bò tái và một ly trà đá",
    "tôi muốn ăn món gì cay cay không có thịt bò",
    "thêm một phần cơm tấm sườn bì chả",
    "có món chay nào không em",
    "thôi chốt đơn đi",
    "cho anh một combo gia đình với hai ly trà tắc",
    "bún bò huế có cay không",
    "bỏ bớt một ly cà phê sữa đá",
    "có khuyến mãi gì không",
    "trả tiền mặt nhé",
]


def wer(ref: str, hyp: str) -> tuple[int, int]:
    r, h = ref.lower().split(), hyp.lower().split()
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)], len(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(ROOT / "config/stores/quan-ngon"))
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--wav-dir", help="thư mục WAV giọng thật (kèm .txt)")
    a = ap.parse_args()

    import numpy as np

    from aistaff.config import load_store
    from aistaff.nlu import NLU
    from aistaff.speech.asr import SherpaASR, menu_hotwords
    from aistaff.speech.audio import read_wav, resample
    from aistaff.speech.tts import PiperTTS

    cfg = load_store(a.store)
    sp = cfg.store.speech
    models = ROOT / sp.models_dir
    tts = PiperTTS(models / sp.tts_voice)
    tests: list[tuple[str, np.ndarray]] = []
    t_tts = dur = 0.0
    for text in PHRASES:
        t0 = time.perf_counter()
        x = tts.synthesize(text)
        t_tts += time.perf_counter() - t0
        dur += len(x) / tts.sample_rate
        tests.append((text, resample(x, tts.sample_rate, 16000)))
    print(f"TTS  {sp.tts_voice}: {t_tts:.2f}s cho {dur:.1f}s âm thanh -> RTF {t_tts / dur:.3f}")
    if a.wav_dir:
        for w in sorted(Path(a.wav_dir).glob("*.wav")):
            txt = w.with_suffix(".txt")
            if txt.exists():
                x, sr = read_wav(str(w))
                tests.append((txt.read_text(encoding="utf-8").strip().lower(), resample(x, sr, 16000)))

    nlu = NLU(cfg.menu)
    for label, hot in [("greedy", None), ("beam+hotwords", menu_hotwords(cfg.menu))]:
        asr = SherpaASR(models / sp.asr_model, hotwords=hot, hotwords_score=sp.hotwords_score, num_threads=a.threads,
                        cache_dir=ROOT / "data")
        E = N = 0
        lat, audio, same = [], 0.0, 0
        for ref, x in tests:
            r = asr.transcribe(x)
            e, n = wer(ref, r.text)
            E, N = E + e, N + n
            lat.append(r.latency_ms)
            audio += r.duration
            a_ref, a_hyp = nlu.parse(ref), nlu.parse(r.text)
            same += (a_ref.intent, [m.entry_id for m in a_ref.items]) == (a_hyp.intent, [m.entry_id for m in a_hyp.items])
            if e:
                print(f"   [{label}] {ref!r} -> {r.text!r}")
        print(f"ASR  {sp.asr_model} [{label}, {a.threads} luồng]: WER {E / N * 100:.1f}% | "
              f"RTF {sum(lat) / 1000 / audio:.3f} | trễ TB {np.mean(lat):.0f} ms | NLU hiểu đúng {same}/{len(tests)} câu")


if __name__ == "__main__":
    main()
