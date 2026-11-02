# Bước 6 — Chọn phần cứng edge & tối ưu chi phí

> Câu hỏi: **thiết bị rẻ nhất** chạy mượt hệ thống là gì, tổng chi phí 1 bộ kiosk bao nhiêu, và so với dùng cloud thì sao?

## 6.1. Hệ thống cần bao nhiêu tài nguyên? (đo thực tế)

| Thành phần | RAM | Đĩa |
|------------|-----|-----|
| Server (FastAPI) + ASR Zipformer-30M + Piper TTS + VAD + SQLite | **~350 MB đỉnh** (275 MB sau khởi động) | Model 113 MB + mã nguồn + venv ~600 MB |
| Trình duyệt kiosk (Chromium) | ~300–500 MB | – |
| Hệ điều hành (Raspberry Pi OS / Debian) | ~300 MB | ~4 GB |
| **Tổng** | **< 1,2 GB** | **< 8 GB** |

Khởi động server: 2,7 s. CPU: ASR + TTS dùng 2 luồng, mỗi lượt hội thoại chỉ chiếm CPU vài trăm ms.
→ **Không cần GPU/NPU, không cần 8–16 GB RAM** (khác hẳn khi phải chạy LLM cục bộ). Đây là chỗ tiết kiệm chi phí lớn nhất
trong bối cảnh RAM tăng giá mạnh năm 2026.

## 6.2. Bối cảnh giá phần cứng 2026

- Khủng hoảng giá RAM (do nhu cầu AI) khiến **Raspberry Pi tăng giá nhiều lần trong 2026**. Tháng 2/2026: Pi 5 4 GB 85 USD,
  8 GB 125 USD. Báo cáo 10/2026 (Phoronix): Pi 5 2 GB 77,5 USD, 4 GB 110 USD, 8 GB 180 USD; bản 1 GB vẫn 45 USD.
  Các nguồn có chênh lệch → **kiểm tra giá tại thời điểm mua**.
- Mini PC Intel N100/N150 cũng tăng giá (một mẫu N100 từ 159 → 247 USD trong ~1 năm), nay ngang Pi 5 cấu hình tương đương.
- Jetson Orin Nano Super: 249–299 USD (67 TOPS INT8). Orange Pi 5 Plus (RK3588, NPU 6 TOPS): ~130–160 USD bản 16 GB.

## 6.3. So sánh thiết bị

| Thiết bị | Giá board (USD, 2026) | Chạy hệ thống này | LLM cục bộ | Nhận xét |
|----------|----------------------|-------------------|------------|----------|
| **Raspberry Pi 5 2 GB** | ~77,5 | ✅ đủ (RAM < 1,2 GB) | ❌ | Rẻ nhất; dùng SSD/thẻ nhớ A2 tốt, tản nhiệt chủ động |
| **Raspberry Pi 5 4 GB** (khuyến nghị) | ~85–110 | ✅ dư địa thoải mái | ❌ (chỉ LLM ~1B, chậm) | Hệ sinh thái lớn, linh kiện dễ mua tại VN |
| Mini PC Intel N100/N150 8–16 GB | ~160–250 | ✅ nhanh hơn Pi 5 | ⚠️ 1–4B chậm | Có sẵn vỏ, SSD, nguồn; x86 dễ cài |
| Orange Pi 5 / 5 Plus (RK3588) | ~100–160 | ✅ | ⚠️ qua NPU (RKLLM) | Mạnh, nhưng hỗ trợ phần mềm kém đồng đều hơn |
| Jetson Orin Nano Super 8 GB | 249–299 | ✅ | ✅ 1–4B nhanh | Chỉ đáng khi bắt buộc hội thoại tự do bằng LLM cục bộ |
| Tablet Android cũ làm màn hình + 1 máy chủ nhỏ cho cả quán | tablet 60–150/máy | ✅ (1 server, nhiều màn hình) | – | Quán nhiều bàn: mỗi bàn 1 tablet, server dùng chung |

Ước tính tốc độ trên Pi 5 (Cortex-A76 2,4 GHz) chậm hơn CPU x86 dùng để đo khoảng 2–3 lần:
ASR ~100–250 ms/câu, TTS câu đầu ~0,4–0,8 s (cache: 0 ms) → tổng thời gian từ lúc khách ngừng nói tới lúc AI nói ≈ 1,0–1,6 s.
**Phải đo lại trên máy thật:** `aistaff bench`, `aistaff voice-file <wav>`, `python scripts/bench_speech.py`.

## 6.4. Bảng vật tư 1 bộ kiosk (ước tính, tham khảo)

| Hạng mục | Lựa chọn tiết kiệm | Ghi chú |
|----------|-------------------|---------|
| Bo mạch | Raspberry Pi 5 4 GB | hoặc 2 GB để tối đa tiết kiệm |
| Lưu trữ | microSD A2 32–64 GB hoặc SSD NVMe nhỏ (HAT) | SSD bền hơn cho chạy 24/7 |
| Nguồn + tản nhiệt + vỏ | Nguồn chính hãng 27 W, quạt chủ động | Bếp nóng → tản nhiệt là bắt buộc |
| Màn hình | Cảm ứng 10,1–15,6" HDMI/USB | Kiosk đứng hoặc gắn tường |
| Âm thanh | **Loa-mic hội nghị USB có khử vọng (AEC)** hoặc micro mảng | Quan trọng nhất cho độ chính xác ASR nơi ồn |
| Vỏ kiosk / chân đứng | Gia công địa phương | Máy bán hàng: tích hợp sẵn vào thân máy |

Tổng vật tư thường rơi vào khoảng **200–400 USD/bộ** tuỳ màn hình và vỏ (giá biến động, cần báo giá thực tế).
Phần mềm: **0đ phí theo lượt** (không thuê bao STT/TTS/LLM).

## 6.5. Edge vs Cloud — chi phí vận hành mỗi quán

Giả định: 100 đơn/ngày, mỗi đơn khách nói ~1 phút, AI nói ~1.500 ký tự.

| Hạng mục | Cloud (giá niêm yết tham khảo) | Edge (hệ thống này) |
|----------|-------------------------------|---------------------|
| Speech-to-Text | ~0,016 USD/phút × 3.000 phút ≈ **48 USD/tháng** | 0 |
| Text-to-Speech | ~15 USD/1 triệu ký tự × 4,5 triệu ≈ **67 USD/tháng** (giảm được nhờ cache) | 0 |
| LLM | theo token | 0 (tắt) |
| Internet | bắt buộc, ổn định | không bắt buộc (trừ khi xác nhận tiền tự động) |
| Độ trễ mạng | +0,3–0,8 s mỗi lượt | 0 |
| **Tổng/tháng** | **≈ 115 USD+/quán** | **≈ 0 USD** (chỉ điện ~5–10 W) |

→ Bộ kiosk edge **hoàn vốn so với cloud sau ~2–4 tháng** ở mức 100 đơn/ngày, và không lộ giọng nói khách ra ngoài.
Phương án lai hợp lý: edge mặc định, chỉ dùng cloud cho (a) xác nhận chuyển khoản tự động (SePay), (b) LLM dự phòng
cho câu khó nếu quán muốn.

## 6.6. Mô hình kinh doanh gợi ý khi bán cho quán

- Bán thiết bị trọn gói (phần cứng + cài đặt + cấu hình menu) + phí bảo trì/cập nhật menu theo tháng.
- Gói "chỉ phần mềm" cho quán đã có máy POS/tablet (chạy server trên mini PC, tablet làm màn hình).
- Dịch vụ cộng thêm: thu âm giọng thương hiệu riêng (fine-tune Piper), tích hợp hoá đơn điện tử, báo cáo bán hàng.

### Nguồn
- Giá Raspberry Pi 2026: https://www.phoronix.com/news/Raspberry-Pi-5-2GB-Price-77.50 · https://www.omgubuntu.co.uk/2026/02/raspberry-pi-annouce-more-price-rises · https://www.tomshardware.com/raspberry-pi/component-shortages-drive-raspberry-pi-prices-up-by-up-to-23-percent-escalating-lpddr4-lpddr5-costs-trigger-the-third-price-hike-of-the-year
- Mini PC vs Pi 2026: https://www.jeffgeerling.com/blog/2026/raspberry-pi-cheaper-than-mini-pc/
- Jetson Orin Nano Super: https://www.notebookcheck.net/The-Nvidia-Jetson-Orin-Nano-Super-a-powerful-generative-AI-SBC-is-now-available-worldwide-for-249.934029.0.html
- Các lựa chọn thay thế Pi 2026: https://www.wemustbegeeks.com/raspberry-pi-alternatives-2026/
- Tốc độ LLM trên Pi 5: https://stratospherelinuxips.readthedocs.io/en/develop/immune/research_rpi_llm_performance.html
- Giá STT/TTS cloud: xem nguồn ở [02](02-nhan-dang-giong-noi-asr.md) và [03](03-tong-hop-giong-noi-tts.md)
