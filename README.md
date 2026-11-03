# AI Staff — Nhân viên AI gọi món bằng giọng nói tiếng Việt (chạy offline trên edge device)

Kiosk / máy bán hàng có **nhân viên AI nói chuyện tiếng Việt thời gian thực**: chào khách, trò chuyện tự nhiên,
giới thiệu ưu đãi, hỏi khẩu vị, gợi ý món, nhận món bằng giọng nói hoặc chạm màn hình (khách nói chen thì Mai dừng
lại nghe), đọc lại đơn, tính tiền (tự áp dụng ưu đãi có lợi nhất) và hiện **mã VietQR** để khách quét thanh toán.
Đơn được chốt khi ngân hàng báo đã nhận tiền.

- **Tai và miệng chạy trên thiết bị**: nhận dạng giọng nói, tổng hợp giọng nói, VAD (không cần GPU, RAM ~350 MB).
- **Bộ não hội thoại**: LLM chạy trên máy (llama.cpp / Ollama, 0đ/lượt, không cần Internet) hoặc Claude trên cloud
  (thông minh hơn, cần Internet + API key). Giá, ưu đãi, tổng tiền, mã QR luôn do code tất định tính → AI không bịa được giá.
- Mất mạng / LLM lỗi → tự chuyển sang bộ luật offline (bản v0.1), khách vẫn gọi món được.

```
Khách: "Gợi ý cho anh món gì ngon đi"
AI   : "Dạ, quý khách thích món nước hay khô, vị cay, chua ngọt hay thanh đạm, có kiêng gì không ạ? ..."
Khách: "Anh thích ăn cay, đi 2 người"
AI   : "Dạ, em gợi ý: 1. Bún bò Huế 60.000đ - vị cay, món bán chạy; 2. Mì cay hải sản ...; 3. ..."
Khách: "Lấy món thứ nhất, thêm hai trà tắc"
AI   : "Dạ, em đã thêm ... Đơn đã được tặng 1 Trà tắc nhờ ưu đãi 'Trà tắc mua 2 tặng 1' rồi ạ ..."
Khách: "Chốt đơn" → AI đọc lại đơn + tổng tiền → "Đúng rồi" → màn hình hiện VietQR (đúng số tiền + mã đơn)
→ ngân hàng báo có tiền → "Dạ, quán đã nhận được 90.000đ. Đơn số 12 đang được chuẩn bị ạ!"
```

## Tính năng

- **Hội thoại thời gian thực** (`conversation.engine: llm`): chữ của AI chảy ra và được đọc ngay từ câu đầu,
  phụ đề hiện trong lúc khách đang nói, câu đệm "Dạ." khi AI chưa kịp trả lời, khách nói chen thì dừng nói và nghe
  (lọc tiếng "ừ/dạ" và tiếng vọng), AI tự hiện thẻ gợi ý / phóng to món / phiếu gọi món / QR bằng công cụ.
  Kiến trúc, độ trễ, chi phí: [docs/CORE-AI-RESEARCH.md §16](docs/CORE-AI-RESEARCH.md#16-hội-thoại-thời-gian-thực-bằng-llm-đã-triển-khai).
- **Menu món lẻ + combo** cấu hình bằng YAML (alias cách gọi dân dã, vị 0–3, thành phần, món chay, size, món ăn kèm).
- **Giọng nói tiếng Việt offline**: ASR sherpa-onnx Zipformer-vi (hotwords tự sinh từ menu), VAD Silero, TTS Piper
  (cache + dựng sẵn câu cố định).
- **NLU tiếng Việt ~1 ms/câu**: chịu lỗi nhận dạng ("cầm tấm sườn" → cơm tấm sườn), gõ không dấu, đọc số tiếng Việt,
  số lượng, size, ghi chú ("không hành"), khẩu vị, kiêng/dị ứng, ngân sách, số người, chọn theo thứ tự, sửa/bớt/đổi món.
- **Gợi ý món có lý do** (lọc chay/dị ứng/ngân sách, chấm điểm khẩu vị, combo đúng số người, món đang ưu đãi) + upsell đồ uống.
- **Ưu đãi**: giảm %/tiền theo hoá đơn hoặc món/nhóm/combo, mua X tặng Y, hoá đơn từ N tặng món, theo thứ/giờ/ngày;
  tự chọn phương án lợi nhất; **AI chủ động giới thiệu** khi chào, khi gợi ý, khi khách sắp đạt điều kiện, khi chốt đơn.
- **Tính tiền + VietQR động** (EMVCo/NAPAS, CRC16) sinh offline; xác nhận tiền: thủ công (/admin), SePay webhook hoặc SePay polling.
- **SQLite**: thông tin quán, đơn hàng, giao dịch (chống trùng), log hội thoại dạng chữ; trang **/admin** xem doanh thu & xác nhận.
- **Giao diện kiosk React "Mâm sơn mài"** (chạy offline, bản build có sẵn trong gói Python): món ăn minh hoạ SVG
  bốc khói trên mâm sơn mài, chạm bát để phóng to xem chi tiết (vị, size, ghi chú cho bếp), món bay vào mâm, quả cầu
  của Mai phản ứng theo giọng nói, phiếu gọi món giấy vỏ trứng, QR khung vàng lá, con dấu son khi thanh toán xong.
  Bố cục kiosk ngang / kiosk dọc / tablet / điện thoại. Chi tiết thiết kế: [web/README.md](web/README.md).
- Chế độ bộ luật (`engine: rules`) vẫn còn, kèm LLM tuỳ chọn để chuẩn hoá câu khó — không bao giờ chạm vào giá tiền.

## Chạy thử nhanh (không cần model, gõ phím)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
aistaff validate                               # kiểm tra cấu hình quán mẫu
aistaff chat --at "2026-11-03 15:00"           # trò chuyện; gõ /paid để giả lập đã nhận tiền
aistaff serve --no-speech                      # mở http://localhost:8000  (quản lý: /admin)
```

## Bật AI nói chuyện (LLM)

Chọn một trong hai bộ não (`store.yaml → conversation.provider`, mặc định `auto`):

```bash
# 1) LLM chạy ngay trên máy (không cần Internet sau khi tải model; cần llama.cpp: github.com/ggml-org/llama.cpp/releases)
bash scripts/run_local_llm.sh                  # llama-server --jinja ở http://127.0.0.1:8080/v1
# 2) Claude trên cloud (mặc định claude-opus-5-5, effort low; đổi claude-haiku-5-5 để nhanh và rẻ hơn nhiều)
export ANTHROPIC_API_KEY=...                   # đặt key bằng biến môi trường, không ghi vào file cấu hình

aistaff chat --llm --debug                     # nói chuyện thử bằng bàn phím với bộ não thật (xem độ trễ, công cụ, token)
aistaff serve                                  # kiosk dùng bộ não đã chọn; /healthz cho biết đang chạy gì
```

Với Claude, fallback phía server (`fallbacks: "default"`) đang bật cho Opus 5.5, và lời khách (dạng chữ) được gửi lên
Anthropic: nên có thông báo quyền riêng tư tại kiosk. Với LLM local, dữ liệu ở lại trên máy.

## Bật giọng nói

```bash
pip install -e ".[speech]"
bash scripts/download_models.sh                # ~120 MB: ASR + TTS + VAD
aistaff serve --speech                         # hoặc đặt speech.enabled: true trong store.yaml
aistaff prerender                              # dựng sẵn câu cố định -> phản hồi tức thì
python scripts/bench_speech.py                 # đo tốc độ/độ chính xác ngay trên thiết bị
```

Cài đặt trọn gói lên thiết bị edge (systemd + Chromium kiosk tự khởi động): `sudo bash scripts/install_edge.sh config/stores/<ma-quan>`.

## Cấu hình 1 quán mới

Sao chép `config/stores/quan-ngon/` thành `config/stores/<ma-quan>/` rồi sửa:

- `store.yaml` — tên quán, cách AI xưng hô, **BIN ngân hàng + số tài khoản nhận tiền**, chế độ xác nhận, giọng nói.
- `menu.yaml` — món lẻ, combo, alias, vị, thành phần.
- `promotions.yaml` — chương trình ưu đãi + câu AI giới thiệu.

Chạy `aistaff --store config/stores/<ma-quan> validate` để bắt lỗi trước khi dùng.

## Hiệu năng đo được (CPU x86 4 vCPU; Pi 5 ước tính chậm hơn 2–3 lần)

| Khâu | Thời gian |
|------|-----------|
| ASR 1 câu 1,5–2,5 s (Zipformer-vi-30M INT8, 2 luồng) | 40–75 ms (RTF ≈ 0,03) |
| NLU + gợi ý + ưu đãi + tính tiền | 0,8 ms/lượt |
| TTS câu đầu tiên (Piper) | 170–300 ms; câu có trong cache: 0 ms |
| Từ lúc khách ngừng nói → AI bắt đầu nói (chế độ bộ luật) | ≈ 0,7–0,9 s (gồm 0,5 s chờ im lặng) |
| Như trên, chế độ LLM với Claude | ≈ 1,3–2,4 s **ước tính, chưa đo với model thật**; câu đệm "Dạ." ở ≈ 1,2 s |
| RAM server + model | ~350 MB |
| ASR + NLU hiểu đúng món & ý định (40 câu thử) | 92,5% (WER chữ 8–10%) |

## Nghiên cứu core AI (bản tổng hợp để duyệt)

**[docs/CORE-AI-RESEARCH.md](docs/CORE-AI-RESEARCH.md)**: một file duy nhất, nghiên cứu chi tiết từng phương pháp
(thu âm & khử ồn, VAD & kết thúc lượt nói, kích hoạt, ASR & ưu tiên tên món, chuẩn hoá văn bản, NLU, quản lý hội thoại,
gợi ý & upsell, tối ưu ưu đãi, TTS, LLM, đánh giá & dữ liệu). Có lộ trình và **14 quyết định cần duyệt**.
§16 mô tả kiến trúc hội thoại thời gian thực **đã triển khai**; các đề xuất M1–M12 còn lại chưa làm.

## Tài liệu research từng bước (tối ưu chi phí & yêu cầu)

1. [Yêu cầu & kiến trúc](docs/01-yeu-cau-va-kien-truc.md) — vì sao chọn kiến trúc lai ưu tiên edge, ngân sách độ trễ
2. [Nhận dạng giọng nói (ASR)](docs/02-nhan-dang-giong-noi-asr.md) — so sánh Zipformer / PhoWhisper / Vosk / cloud, số đo, hotwords
3. [Tổng hợp giọng nói (TTS)](docs/03-tong-hop-giong-noi-tts.md) — Piper, cache, prerender, lưu ý bản quyền GPL
4. [Hiểu ngôn ngữ, gợi ý, ưu đãi](docs/04-hieu-ngon-ngu-goi-y-uu-dai.md) — LLM hay luật, máy trạng thái hội thoại
5. [Thanh toán VietQR](docs/05-thanh-toan-vietqr.md) — cấu trúc mã, xác nhận tiền (thủ công/SePay), BIN, hoá đơn điện tử
6. [Phần cứng & chi phí](docs/06-phan-cung-va-chi-phi.md) — giá thiết bị 2026, bảng vật tư, edge vs cloud
7. [Triển khai, vận hành, pháp lý](docs/07-trien-khai-van-hanh-phap-ly.md) — cài đặt, quản lý, dữ liệu cá nhân, lộ trình

## Cấu trúc mã nguồn

```
config/stores/quan-ngon/      cấu hình quán mẫu (store, menu, promotions)
src/aistaff/
  config.py                   model cấu hình + kiểm tra lỗi (pydantic)
  textnorm.py                 chuẩn hoá tiếng Việt, đọc số <-> chữ, chuẩn hoá câu cho TTS
  nlu.py                      NLU: ý định, món (so khớp mờ), số lượng, khẩu vị
  recommender.py              gợi ý món + upsell
  promotions.py               engine ưu đãi + tính tiền
  cart.py · dialog.py         giỏ hàng · máy trạng thái hội thoại
  vietqr.py · payments.py     sinh VietQR · xác nhận thanh toán (thủ công/SePay)
  storage.py                  SQLite
  agent/                      AI hội thoại: prompt, công cụ tất định, vòng lặp agent, Claude (provider.py), LLM local (local.py)
  llm.py                      LLM chuẩn hoá câu cho chế độ bộ luật (tuỳ chọn)
  speech/                     ASR, VAD, TTS, cache
  kiosk/                      FastAPI + WebSocket, vòng giọng nói thời gian thực (realtime.py); webui/ = bản build React
  cli.py                      lệnh aistaff
web/                          mã nguồn giao diện React (Vite + motion), xem web/README.md
scripts/                      tải model, chạy LLM local, cài đặt edge, benchmark giọng nói
deploy/                       systemd, autostart Chromium kiosk
tests/                        140 test (pytest)
```

## Kiểm thử

```bash
pip install -e ".[dev]"          # thêm [speech] + tải model để chạy cả test giọng nói thật
pytest
```

## Giấy phép thành phần bên thứ ba

sherpa-onnx (Apache-2.0) · model Zipformer tiếng Việt (xem trang gốc từng model) · `piper-tts` (GPL-3.0-or-later) ·
giọng `vi_VN-vais1000` (dữ liệu VAIS-1000, CC BY 4.0) · Silero VAD (MIT) · FastAPI, rapidfuzz, segno, pydantic (MIT/BSD).
Đọc kỹ [docs/03 §3.5](docs/03-tong-hop-giong-noi-tts.md) trước khi phân phối thiết bị thương mại.
