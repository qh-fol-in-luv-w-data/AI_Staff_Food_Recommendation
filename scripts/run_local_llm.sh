#!/usr/bin/env bash
# Chạy LLM local cho kiosk ngay trên thiết bị: llama.cpp `llama-server` (API tương thích OpenAI, có gọi công cụ).
# Kiosk (store.yaml -> conversation.provider: local hoặc auto) nói chuyện với nó qua http://127.0.0.1:8080/v1
#
# Cách dùng:
#   scripts/run_local_llm.sh                                   # model mặc định bên dưới
#   scripts/run_local_llm.sh <hf-user>/<repo>-GGUF:Q4_K_M       # model GGUF khác trên Hugging Face
#   LLAMA_SERVER=/opt/llama/llama-server scripts/run_local_llm.sh
#
# Cần: bản build llama.cpp (https://github.com/ggml-org/llama.cpp/releases, chọn đúng CPU/GPU của máy),
#      Internet lần đầu để tải model (lưu cache ở ~/.cache/llama.cpp), sau đó chạy offline.
# Chọn model: cần model "instruct" có hỗ trợ tool calling trong chat template, nói tiếng Việt tốt.
#   - Mặc định Qwen3-4B-Instruct-2507 (Q4_K_M, khoảng 2,5 GB, cần khoảng 4 GB RAM): cân bằng chất lượng / tốc độ.
#   - Máy yếu hơn: model 1,5-2B (nhanh hơn khoảng 2 lần, gọi công cụ kém chính xác hơn).
#   - Nên chấm thử cả dòng Qwen3.5 nhỏ / Gemma 4 (xem docs/CORE-AI-RESEARCH.md) trên chính kịch bản gọi món.
#   Model có chế độ "suy nghĩ" (vd Qwen3 bản gốc) thì tắt đi cho nhanh, trong store.yaml:
#     conversation.local.extra_body: {chat_template_kwargs: {enable_thinking: false}}
set -euo pipefail

MODEL="${1:-${LOCAL_LLM_HF:-unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M}}"
PORT="${LOCAL_LLM_PORT:-8080}"
CTX="${LOCAL_LLM_CTX:-16384}"          # system prompt + menu + công cụ khoảng 5-6 nghìn token, còn lại cho hội thoại
THREADS="${LOCAL_LLM_THREADS:-$(nproc)}"
BIN="${LLAMA_SERVER:-$(command -v llama-server || true)}"

if [ -z "$BIN" ]; then
  echo "Chưa tìm thấy llama-server." >&2
  echo "Tải bản build sẵn tại https://github.com/ggml-org/llama.cpp/releases rồi đặt LLAMA_SERVER=/đường/dẫn/llama-server" >&2
  exit 1
fi

# --jinja        : dùng chat template của model -> gọi công cụ (tool calling) đúng định dạng
# --parallel 1   : một kiosk một luồng, giữ nguyên KV cache của phần đầu prompt giữa các lượt / các khách
# --cache-reuse  : tái dùng KV cache kể cả khi đoạn giữa prompt thay đổi
exec "$BIN" -hf "$MODEL" --jinja -c "$CTX" --parallel 1 -t "$THREADS" \
  --host 127.0.0.1 --port "$PORT" --cache-reuse 256
