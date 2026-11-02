"""Tổng hợp giọng nói tiếng Việt offline (Piper VITS, giọng vi_VN-vais1000) + bộ đệm (cache) âm thanh.

- Piper: RTF ~0.065 trên CPU x86 (câu 4.7 s mất ~0.3 s). Model 63 MB (fp32) / 21 MB (int8).
- Cache theo nội dung câu: câu lặp lại (chào hỏi, hỏi khẩu vị, mời quét QR...) phát ngay 0 ms.
- `prerender` sinh sẵn các câu cố định lúc cài đặt -> thiết bị yếu vẫn phản hồi tức thì.
- Phiên bản sherpa-onnx >= 2.0 không còn kèm espeak-ng, nên dùng gói `piper-tts` (GPL-3.0)
  chạy như 1 thành phần độc lập. Muốn tránh GPL hoàn toàn: dùng cache dựng sẵn hoặc TTS đám mây.
"""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import numpy as np

from .audio import pcm16_to_float, wav_bytes


class PiperTTS:
    def __init__(self, voice_dir: str | Path, speed: float = 1.0):
        from piper import PiperVoice
        from piper.config import SynthesisConfig

        d = Path(voice_dir)
        onnx = sorted(d.glob("*.onnx"))
        if not onnx:
            raise FileNotFoundError(f"Chưa có giọng Piper trong {d}. Chạy scripts/download_models.sh")
        cfg = Path(str(onnx[0]) + ".json")
        self.voice = PiperVoice.load(str(onnx[0]), config_path=str(cfg) if cfg.exists() else None)
        self.sample_rate = self.voice.config.sample_rate
        self.syn = SynthesisConfig(length_scale=1.0 / max(0.3, speed))
        self.voice_id = d.name + f"@{speed:g}"
        self._lock = threading.Lock()  # onnxruntime session dùng chung -> tuần tự hoá

    def synthesize(self, text: str) -> np.ndarray:
        with self._lock:
            chunks = list(self.voice.synthesize(text, syn_config=self.syn))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate([pcm16_to_float(c.audio_int16_bytes) for c in chunks])


class TTSCache:
    """Cache WAV trên đĩa theo hash(giọng + câu). Dùng chung cho server và prerender."""

    def __init__(self, engine: PiperTTS | None, cache_dir: str | Path = "data/tts_cache"):
        self.engine = engine
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def key(self, text: str) -> str:
        vid = self.engine.voice_id if self.engine else "none"
        return hashlib.sha1(f"{vid}|{text.strip()}".encode("utf-8")).hexdigest()[:20]

    def path(self, text: str) -> Path:
        return self.dir / f"{self.key(text)}.wav"

    def get(self, text: str) -> tuple[Path | None, float]:
        """Trả về (đường dẫn WAV, thời gian tổng hợp ms). Tổng hợp nếu chưa có trong cache."""
        p = self.path(text)
        if p.exists():
            self.hits += 1
            return p, 0.0
        if self.engine is None or not text.strip():
            return None, 0.0
        t0 = time.perf_counter()
        audio = self.engine.synthesize(text)
        if len(audio) == 0:
            return None, 0.0
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(wav_bytes(audio, self.engine.sample_rate))
        tmp.replace(p)
        self.misses += 1
        return p, (time.perf_counter() - t0) * 1000


def split_sentences(text: str, max_len: int = 160) -> list[str]:
    """Tách câu để phát câu đầu sớm (giảm độ trễ cảm nhận) thay vì đợi tổng hợp cả đoạn."""
    import re

    parts = [p.strip() for p in re.split(r"(?<=[.!?;:])\s+|\n+", text) if p.strip()]
    out: list[str] = []
    for p in parts:
        while len(p) > max_len:
            cut = p.rfind(",", 0, max_len)
            cut = cut if cut > 40 else max_len
            out.append(p[: cut + 1].strip())
            p = p[cut + 1 :].strip()
        if p:
            out.append(p)
    return out
