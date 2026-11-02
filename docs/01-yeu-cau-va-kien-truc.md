# Bước 1 — Phân tích yêu cầu & chọn kiến trúc

> Mục tiêu của bước này: chốt **kiến trúc rẻ nhất mà vẫn đạt yêu cầu tốc độ**, trước khi chọn từng model.
> Nghiên cứu chi tiết từng phương pháp AI (để duyệt hướng nâng cấp) nằm ở [CORE-AI-RESEARCH.md](CORE-AI-RESEARCH.md).

## 1.1. Yêu cầu (tách nhỏ từ đề bài)

| # | Yêu cầu | Ràng buộc kỹ thuật rút ra |
|---|---------|---------------------------|
| R1 | Cấu hình menu gồm **món lẻ + combo** | File cấu hình dễ sửa (YAML), kiểm tra lỗi khi khởi động |
| R2 | AI **chào khách bằng giọng nói tiếng Việt**, rồi mời gọi món | TTS tiếng Việt, câu chào phát ngay (không chờ) |
| R3 | **Nghe khách nói** và xử lý | ASR tiếng Việt + VAD (biết khi khách nói xong) |
| R4 | **Hỏi khẩu vị** và **gợi ý món** khi khách nhờ giới thiệu | NLU hiểu sở thích + bộ gợi ý có lý do |
| R5 | Khách chọn món thì AI **xác nhận đã biết** | NLU nhận món + số lượng + ghi chú, đọc lại |
| R6 | Có **chương trình ưu đãi**, AI **phải giới thiệu** | Engine ưu đãi + câu giới thiệu tự động |
| R7 | **Tính tiền** sau khi chốt đơn | Tính tiền tất định (không để AI "đoán" giá) |
| R8 | **Hiện mã QR** để quét thanh toán và chốt đơn | VietQR động (có số tiền + mã đơn), xác nhận đã nhận tiền |
| R9 | **Lưu thông tin quán**, đơn hàng | CSDL cục bộ |
| R10 | **Tốc độ nhanh** | Ngân sách độ trễ < ~1,5 s từ lúc khách ngừng nói tới lúc AI bắt đầu nói |
| R11 | Chạy trên **edge device** bán cho quán / máy bán hàng | Chạy offline, RAM thấp, CPU ARM, chi phí phần cứng thấp, cài đặt 1 lệnh |
| R12 | **Tối ưu chi phí** | Không trả phí theo lượt dùng (cloud API) nếu tránh được |

## 1.2. Ba hướng kiến trúc đã cân nhắc

| Hướng | Mô tả | Ưu | Nhược | Chi phí vận hành |
|-------|-------|----|-------|------------------|
| **A. Toàn cloud** | Gửi âm thanh lên STT cloud, LLM cloud sinh câu trả lời, TTS cloud | Chất lượng giọng cao, ít code | Cần Internet ổn định; mỗi lượt +300–800 ms mạng; **trả tiền theo phút/ký tự**; LLM có thể "bịa" giá; gửi giọng nói khách ra ngoài (dữ liệu cá nhân) | Cao, tăng theo số đơn |
| **B. LLM cục bộ** | ASR + LLM 2–4B + TTS chạy hết trên máy | Không phí theo lượt, hội thoại tự nhiên | Cần phần cứng mạnh (Jetson/RK3588 NPU, RAM 8–16 GB); Pi 5 chỉ ~2–11 token/s → trả lời chậm vài giây | Phần cứng đắt hơn 2–3 lần |
| **C. Lai, ưu tiên edge (CHỌN)** | ASR + TTS chạy offline; **NLU luật + so khớp mờ** (≈1 ms) điều khiển máy trạng thái bán hàng; giá/ưu đãi/QR tính bằng code; LLM chỉ là **tuỳ chọn dự phòng** cho câu khó | Nhanh nhất, rẻ nhất, chạy offline, không bịa giá, RAM < 1 GB | Phải viết luật NLU tiếng Việt (đã làm); câu ngoài phạm vi gọi món kém tự nhiên hơn LLM | ≈ 0đ/lượt |

**Lý do chọn C:** domain gọi món là **hẹp và có cấu trúc** (món, số lượng, khẩu vị, chốt đơn, thanh toán).
Bài toán này không cần một LLM "biết mọi thứ". Một máy trạng thái tất định cộng NLU chuyên biệt cho kết quả
**chính xác hơn về tiền**, **nhanh hơn 1.000 lần** (≈1 ms so với vài giây) và cho phép chạy trên phần cứng rẻ nhất.

## 1.3. Kiến trúc đã triển khai

```
 ┌────────────────────── Thiết bị edge (Pi 5 / mini PC / RK3588) ───────────────────────┐
 │                                                                                       │
 │  Micro ──► Trình duyệt kiosk (Chromium, AEC khử vọng) ──PCM16 16kHz/WebSocket──┐      │
 │  Loa   ◄── phát WAV ◄─────────────────────────────────────────────────┐        │      │
 │  Màn hình cảm ứng: thực đơn, giỏ hàng, mã QR  ◄── JSON ──┐             │        ▼      │
 │                                                          │   ┌──────────────────────┐ │
 │                                                          │   │ VAD (Silero, 0.6 MB) │ │
 │                                                          │   └─────────┬────────────┘ │
 │                                                          │             ▼              │
 │                                                          │   ┌──────────────────────┐ │
 │                                                          │   │ ASR Zipformer-vi 30M │ │  hotwords = tên món
 │                                                          │   │ INT8 (sherpa-onnx)   │◄┼─ sinh từ menu.yaml
 │                                                          │   └─────────┬────────────┘ │
 │                                                          │             ▼ text         │
 │  ┌───────────── Lõi tất định (Python, ≈1 ms/lượt) ───────┴─────────────────────────┐  │
 │  │ NLU tiếng Việt: intent + món (so khớp mờ chịu lỗi ASR) + số lượng + khẩu vị     │  │
 │  │ Dialog manager (máy trạng thái): chào → hỏi khẩu vị → gợi ý → gọi món → upsell   │  │
 │  │   → chốt đơn → QR → chờ tiền → cảm ơn                                            │  │
 │  │ Recommender (lọc + chấm điểm + lý do) · Promotion engine (chọn ưu đãi lợi nhất) │  │
 │  │ VietQR (EMVCo/NAPAS, CRC16) · SQLite (quán, đơn, giao dịch)                     │  │
 │  └───────────────┬──────────────────────────────────────────────┬──────────────────┘  │
 │                  ▼ câu trả lời                                   │                     │
 │       ┌─────────────────────────┐   cache WAV (câu lặp lại 0 ms) │  (tuỳ chọn)         │
 │       │ TTS Piper vi_VN (VITS)  │──────────────────────────────►│  LLM dự phòng        │
 │       └─────────────────────────┘                                │  (llama.cpp/cloud)  │
 └──────────────────────────────────────────────────────────────────┼─────────────────────┘
                                                                    │ Internet (tuỳ chọn)
                                   SePay / ngân hàng ──webhook/API──┘  xác nhận đã nhận tiền
```

## 1.4. Ngân sách độ trễ (từ lúc khách ngừng nói → AI bắt đầu nói)

| Khâu | Đo trên CPU x86 4 nhân | Ước tính Pi 5 (chậm hơn ~2–3 lần, cần đo lại) | Cách tối ưu đã áp dụng |
|------|------------------------|------------------------------------|------------------------|
| VAD chờ im lặng | 500 ms (cấu hình) | 500 ms | Giảm `vad_min_silence` còn 0,35–0,4 s nếu quán yên tĩnh |
| ASR 1 câu ~1,5–2,5 s | 27–75 ms (lần đầu ~165 ms) | ~100–250 ms | Model 30M INT8, VAD cắt sẵn đoạn |
| NLU + hội thoại + tính tiền | 0,8–3 ms (tạo QR ~30–55 ms) | ~3–10 ms | Luật + rapidfuzz (C++) |
| TTS câu đầu tiên | 170–300 ms (cache: 0 ms) | ~400–800 ms (cache: 0 ms) | Tách câu, phát câu đầu trước; cache; prerender |
| **Tổng** | **≈ 0,7–0,9 s** | **≈ 1,0–1,6 s** | |

Số liệu chi tiết ở [02-nhan-dang-giong-noi-asr.md](02-nhan-dang-giong-noi-asr.md) và [03-tong-hop-giong-noi-tts.md](03-tong-hop-giong-noi-tts.md).
Đo lại trên thiết bị thật bằng `aistaff bench` và `python scripts/bench_speech.py`.

## 1.5. Các quyết định chính (tóm tắt)

| Thành phần | Chọn | Lý do chính |
|------------|------|-------------|
| ASR | sherpa-onnx **Zipformer-vi-30M INT8** + hotwords từ menu | Nhẹ (26 MB), nhanh (RTF 0,03); hotwords giảm WER 11% → 8%; NLU hiểu đúng 92,5% câu gọi món từ đầu ra ASR |
| VAD | Silero VAD | 0,6 MB, chuẩn công nghiệp |
| TTS | **Piper vi_VN-vais1000-medium** + cache + prerender | RTF 0,065 trên CPU; giọng nữ miền Bắc rõ; câu lặp lại phát tức thì |
| NLU | Luật + từ điển + so khớp mờ (rapidfuzz) | ≈1 ms, không cần GPU, sửa menu không cần train |
| Gợi ý | Content-based scoring có lý do | Không cần dữ liệu lịch sử; giải thích được |
| Ưu đãi | Engine tất định, tự chọn phương án lợi nhất | Không sai tiền; tự nhắc "gọi thêm X để được ưu đãi" |
| Thanh toán | VietQR động (EMVCo/NAPAS) tự sinh offline | Phí 0đ, mọi app ngân hàng quét được |
| Xác nhận tiền | Thủ công / SePay webhook / SePay polling | Từ 0đ (offline) đến tự động hoàn toàn |
| CSDL | SQLite (WAL) | 1 file, không cần server DB |
| Giao diện | Web (FastAPI + WebSocket + HTML/JS thuần) chạy Chromium kiosk | Không cần CDN, chạy cả trên tablet/điện thoại |
| LLM | Tắt mặc định; bật tuỳ chọn qua API chuẩn OpenAI | Chỉ trả chi phí khi thật sự cần |
