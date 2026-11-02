"""Ghép ASR + VAD + TTS theo cấu hình quán (dùng cho kiosk server và vòng lặp micro tại chỗ)."""

from __future__ import annotations

from pathlib import Path

from ..config import StoreConfig
from .asr import SherpaASR, VADSegmenter, menu_hotwords
from .tts import PiperTTS, TTSCache


class SpeechEngine:
    def __init__(self, cfg: StoreConfig, data_dir: str | Path = "data", root: str | Path | None = None):
        sp = cfg.store.speech
        root = Path(root) if root else Path.cwd()
        models = Path(sp.models_dir)
        models = models if models.is_absolute() else root / models
        self.models = models
        self.min_silence = sp.vad_min_silence
        self.hotwords = menu_hotwords(cfg.menu)
        self.asr = SherpaASR(models / sp.asr_model, hotwords=self.hotwords, hotwords_score=sp.hotwords_score,
                             num_threads=sp.num_threads, cache_dir=data_dir)
        self.tts = TTSCache(PiperTTS(models / sp.tts_voice, sp.tts_speed), Path(data_dir) / "tts_cache")
        self.vad_model = models / "silero_vad.onnx"
        if not self.vad_model.exists():
            raise FileNotFoundError(f"Chưa có {self.vad_model}. Chạy scripts/download_models.sh")

    def new_vad(self) -> VADSegmenter:
        return VADSegmenter(self.vad_model, min_silence=self.min_silence)
