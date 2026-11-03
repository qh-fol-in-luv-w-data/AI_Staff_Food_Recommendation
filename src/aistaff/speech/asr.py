"""Nhận dạng giọng nói tiếng Việt offline bằng sherpa-onnx (Zipformer transducer, INT8).

Đo trên CPU x86 4 nhân (xem docs/02-nhan-dang-giong-noi-asr.md):
  zipformer-vi-30M-int8: RTF ~0.03, ~50 ms/câu 1.5 s, RAM ~170 MB, WER 10.6% -> 6.1% khi bật hotwords.
Hotwords = tên món + alias + từ khoá ("chốt đơn", "thanh toán") sinh TỰ ĐỘNG từ menu.yaml,
giúp ASR ưu tiên nghe đúng tên món của quán (contextual biasing), không cần train lại model.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Menu
from ..textnorm import has_diacritics, normalize

KEYWORDS = ["CHỐT ĐƠN", "THANH TOÁN", "TÍNH TIỀN", "GỢI Ý", "KHUYẾN MÃI", "ƯU ĐÃI", "TIỀN MẶT", "CHUYỂN KHOẢN",
            "QUÉT MÃ", "HỦY ĐƠN", "MANG VỀ", "KHÔNG CAY", "ĂN CHAY", "THỰC ĐƠN", "COMBO", "THÊM", "BỚT"]


def menu_hotwords(menu: Menu) -> list[str]:
    """Tên món + alias có dấu (ASR xuất chữ IN HOA có dấu) + từ khoá gọi món."""
    out: list[str] = []
    for e in menu.entries():
        for s in [e.name, *e.aliases]:
            if has_diacritics(s) or s.isascii() and s.lower().startswith("combo"):
                w = normalize(s).upper()
                if w and w not in out:
                    out.append(w)
        for o in e.options:
            for s in [o.name, *o.aliases]:
                w = normalize(s).upper()
                if has_diacritics(s) and w not in out:
                    out.append(w)
    for c in menu.categories:
        w = normalize(c.name).upper()
        if w not in out:
            out.append(w)
    return out + [k for k in KEYWORDS if k not in out]


@dataclass
class ASRResult:
    text: str
    duration: float
    latency_ms: float


class SherpaASR:
    def __init__(self, model_dir: str | Path, hotwords: list[str] | None = None, hotwords_score: float = 2.0,
                 num_threads: int = 2, cache_dir: str | Path = "data"):
        import sherpa_onnx

        d = Path(model_dir)
        if not d.exists():
            raise FileNotFoundError(f"Chưa có model ASR: {d}. Chạy scripts/download_models.sh")

        def pick(prefix: str) -> str:
            fs = sorted(d.glob(f"{prefix}*.int8.onnx")) or sorted(d.glob(f"{prefix}*.onnx"))
            if not fs:
                raise FileNotFoundError(f"Không thấy {prefix}*.onnx trong {d}")
            return str(fs[0])

        kw: dict = dict(decoding_method="greedy_search")
        if hotwords and (d / "bpe.model").exists():
            cache = Path(cache_dir)
            cache.mkdir(parents=True, exist_ok=True)
            vocab = cache / f"{d.name}.bpe.vocab"
            if not vocab.exists():
                import sentencepiece as spm  # chỉ cần lần đầu

                sp = spm.SentencePieceProcessor(model_file=str(d / "bpe.model"))
                with open(vocab, "w", encoding="utf-8") as f:
                    for i in range(sp.get_piece_size()):
                        f.write(f"{sp.id_to_piece(i)}\t{sp.get_score(i)}\n")
            hw = cache / "hotwords.txt"
            hw.write_text("\n".join(hotwords) + "\n", encoding="utf-8")
            kw = dict(decoding_method="modified_beam_search", max_active_paths=4, hotwords_file=str(hw),
                      hotwords_score=hotwords_score, modeling_unit="bpe", bpe_vocab=str(vocab))
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=pick("encoder"), decoder=pick("decoder"), joiner=pick("joiner"), tokens=str(d / "tokens.txt"),
            num_threads=num_threads, sample_rate=16000, feature_dim=80, **kw,
        )
        self.sample_rate = 16000
        self._lock = threading.Lock()  # nhận dạng tạm (partial) và câu chốt có thể chạy chồng nhau

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> ASRResult:
        from .audio import resample

        x = resample(samples, sample_rate, 16000)
        t0 = time.perf_counter()
        with self._lock:
            st = self.recognizer.create_stream()
            st.accept_waveform(16000, x)
            self.recognizer.decode_stream(st)
            text = st.result.text.strip()
        return ASRResult(text=text.lower(), duration=len(x) / 16000, latency_ms=(time.perf_counter() - t0) * 1000)


class VADSegmenter:
    """Cắt câu nói bằng Silero VAD: nhận luồng PCM 16 kHz, trả về từng đoạn khi khách ngừng nói."""

    def __init__(self, model_path: str | Path, min_silence: float = 0.5, threshold: float = 0.5, max_speech: float = 15.0):
        import sherpa_onnx

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Chưa có model VAD: {model_path}")
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = str(model_path)
        cfg.silero_vad.threshold = threshold
        cfg.silero_vad.min_silence_duration = min_silence
        cfg.silero_vad.min_speech_duration = 0.25
        cfg.silero_vad.max_speech_duration = max_speech
        cfg.sample_rate = 16000
        self.window = cfg.silero_vad.window_size
        self.vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
        self._buf = np.zeros(0, dtype=np.float32)

    def accept(self, samples: np.ndarray) -> list[np.ndarray]:
        """Đưa thêm âm thanh vào; trả về danh sách câu nói đã kết thúc."""
        self._buf = np.concatenate([self._buf, samples.astype(np.float32)])
        while len(self._buf) >= self.window:
            self.vad.accept_waveform(self._buf[: self.window])
            self._buf = self._buf[self.window :]
        out = []
        while not self.vad.empty():
            out.append(np.array(self.vad.front.samples, dtype=np.float32))
            self.vad.pop()
        return out

    def is_speaking(self) -> bool:
        return bool(self.vad.is_speech_detected())

    def flush(self) -> list[np.ndarray]:
        self.vad.flush()
        out = []
        while not self.vad.empty():
            out.append(np.array(self.vad.front.samples, dtype=np.float32))
            self.vad.pop()
        self._buf = np.zeros(0, dtype=np.float32)
        return out

    def reset(self) -> None:
        self.vad.reset()
        self._buf = np.zeros(0, dtype=np.float32)
