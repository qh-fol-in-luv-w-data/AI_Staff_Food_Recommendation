#!/usr/bin/env bash
# Tải model giọng nói tiếng Việt chạy offline (~120 MB) vào thư mục models/
#   ASR : sherpa-onnx Zipformer tiếng Việt 30M INT8 (26 MB nén)  - train ~6.000 giờ
#   ASR2: (tuỳ chọn, --asr-large) Zipformer tiếng Việt INT8 70.000 giờ (60 MB nén)
#   TTS : Piper vi_VN-vais1000-medium (67 MB nén) hoặc bản INT8 (--tts-int8, 21 MB nén)
#   VAD : Silero VAD (0.6 MB)
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="${MODELS_DIR:-models}"
BASE="https://github.com/k2-fsa/sherpa-onnx/releases/download"
ASR="sherpa-onnx-zipformer-vi-30M-int8-2026-02-09"
TTS="vits-piper-vi_VN-vais1000-medium"
for a in "$@"; do
  case "$a" in
    --asr-large) ASR="sherpa-onnx-zipformer-vi-int8-2025-04-20" ;;
    --tts-int8)  TTS="vits-piper-vi_VN-vais1000-medium-int8" ;;
    *) echo "Tuỳ chọn không hợp lệ: $a"; exit 1 ;;
  esac
done
mkdir -p "$DEST"
fetch() {  # fetch <release> <name>
  local rel="$1" name="$2"
  if [ -d "$DEST/$name" ]; then echo "✓ đã có $name"; return; fi
  echo "↓ tải $name ..."
  curl -fL --retry 4 --retry-delay 2 -o "$DEST/$name.tar.bz2" "$BASE/$rel/$name.tar.bz2"
  tar xjf "$DEST/$name.tar.bz2" -C "$DEST" && rm "$DEST/$name.tar.bz2"
}
fetch asr-models "$ASR"
fetch tts-models "$TTS"
[ -f "$DEST/silero_vad.onnx" ] || curl -fL --retry 4 -o "$DEST/silero_vad.onnx" "$BASE/asr-models/silero_vad.onnx"
echo
echo "Xong. Đặt trong store.yaml:"
echo "  speech: { enabled: true, asr_model: \"$ASR\", tts_voice: \"$TTS\" }"
du -sh "$DEST"/* 2>/dev/null || true
