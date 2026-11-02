# AI Staff — Nhân viên AI gọi món bằng giọng nói tiếng Việt (chạy offline trên edge device)

Kiosk / máy bán hàng có **nhân viên AI nói tiếng Việt**: chào khách, giới thiệu ưu đãi, hỏi khẩu vị, gợi ý món,
nhận món bằng giọng nói hoặc chạm màn hình, đọc lại đơn, tính tiền (tự áp dụng ưu đãi có lợi nhất) và hiện
**mã VietQR** để khách quét thanh toán. Đơn được chốt khi ngân hàng báo đã nhận tiền.

Toàn bộ chạy **trên thiết bị** (Raspberry Pi 5 / mini PC / RK3588), không cần GPU, **0đ phí theo lượt**,
RAM ~350 MB cho server + model.

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
- **Giao diện kiosk** web (HTML/JS thuần, chạy offline): trò chuyện + nút micro, thực đơn chạm, giỏ hàng, QR, màn hình cảm ơn;
  chạy được cả trên tablet/điện thoại.
- LLM **tuỳ chọn** làm dự phòng cho câu khó (API chuẩn OpenAI: llama.cpp/Ollama/cloud) — không bao giờ chạm vào giá tiền.

## Chạy thử nhanh (không cần model, gõ phím)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
aistaff validate                               # kiểm tra cấu hình quán mẫu
aistaff chat --at "2026-11-03 15:00"           # trò chuyện; gõ /paid để giả lập đã nhận tiền
aistaff serve --no-speech                      # mở http://localhost:8000  (quản lý: /admin)
```

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
| Từ lúc khách ngừng nói → AI bắt đầu nói | ≈ 0,7–0,9 s (gồm 0,5 s chờ im lặng) |
| RAM server + model | ~350 MB |
| ASR + NLU hiểu đúng món & ý định (40 câu thử) | 92,5% (WER chữ 8–10%) |

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
  llm.py                      LLM dự phòng (tuỳ chọn)
  speech/                     ASR, VAD, TTS, cache
  kiosk/                      FastAPI + WebSocket + giao diện web (static/)
  cli.py                      lệnh aistaff
scripts/                      tải model, cài đặt edge, benchmark giọng nói
deploy/                       systemd, autostart Chromium kiosk
tests/                        98 test (pytest)
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
