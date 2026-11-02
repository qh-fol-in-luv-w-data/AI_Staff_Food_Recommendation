"""Tiện ích âm thanh thuần numpy (không phụ thuộc thư viện nặng)."""

from __future__ import annotations

import io
import wave

import numpy as np


def pcm16_to_float(buf: bytes) -> np.ndarray:
    return np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0


def float_to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def resample(x: np.ndarray, sr: int, target: int = 16000) -> np.ndarray:
    """Đổi tần số lấy mẫu bằng nội suy tuyến tính (đủ tốt cho ASR, rất nhanh)."""
    if sr == target or len(x) == 0:
        return x.astype(np.float32)
    n = int(round(len(x) * target / sr))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def wav_bytes(samples: np.ndarray, sr: int) -> bytes:
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(float_to_pcm16(samples))
    return bio.getvalue()


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path) as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError("Chỉ hỗ trợ WAV 16-bit PCM")
    x = pcm16_to_float(raw)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr
