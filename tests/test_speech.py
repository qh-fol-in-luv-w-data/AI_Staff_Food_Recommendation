"""Kiểm thử giọng nói thật (tự bỏ qua nếu chưa tải model: scripts/download_models.sh)."""

from pathlib import Path

import pytest

from .conftest import ROOT

MODELS = ROOT / "models"
need = pytest.mark.skipif(
    not (MODELS / "sherpa-onnx-zipformer-vi-30M-int8-2026-02-09").exists()
    or not (MODELS / "vits-piper-vi_VN-vais1000-medium").exists()
    or not (MODELS / "silero_vad.onnx").exists(),
    reason="chưa tải model giọng nói",
)


def test_hotwords_from_menu(cfg):
    pytest.importorskip("numpy")
    from aistaff.speech.asr import menu_hotwords

    hw = menu_hotwords(cfg.menu)
    assert "PHỞ BÒ TÁI" in hw and "CƠM TẤM SƯỜN BÌ CHẢ" in hw and "CHỐT ĐƠN" in hw


@need
def test_tts_asr_roundtrip(cfg, tmp_path, monkeypatch):
    import numpy as np

    from aistaff.nlu import NLU
    from aistaff.speech.audio import read_wav, resample
    from aistaff.speech.engine import SpeechEngine

    monkeypatch.chdir(ROOT)
    eng = SpeechEngine(cfg, data_dir=tmp_path)
    path, ms = eng.tts.get("cho tôi hai tô phở bò tái và một ly trà đá")
    assert path and Path(path).stat().st_size > 10000
    x, sr = read_wav(str(path))
    x = resample(x, sr, 16000)
    stream = np.concatenate([np.zeros(8000, np.float32), x, np.zeros(16000, np.float32)])
    vad = eng.new_vad()
    segs = []
    for i in range(0, len(stream), 1600):
        segs += vad.accept(stream[i : i + 1600])
    segs += vad.flush()
    assert segs
    res = eng.asr.transcribe(max(segs, key=len))
    r = NLU(cfg.menu).parse(res.text)
    assert [(m.entry_id, m.qty) for m in r.items] == [("pho-bo-tai", 2), ("tra-da", 1)], res.text
    assert eng.tts.get("cho tôi hai tô phở bò tái và một ly trà đá")[1] == 0.0  # lần 2 lấy từ cache
