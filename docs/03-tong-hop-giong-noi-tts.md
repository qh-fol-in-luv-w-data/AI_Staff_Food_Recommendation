# Bước 3 — Tổng hợp giọng nói tiếng Việt (TTS / Text-to-Speech)

> **Lưu ý (11/2026):** hệ thống chỉ dùng **model mã nguồn mở chạy trên thiết bị**. Các dịch vụ AI đám mây nhắc trong tài liệu này chỉ để đối chiếu, không được dùng. Phương pháp đang dùng: [CORE-AI-RESEARCH → Phương pháp đang dùng trong hệ thống](CORE-AI-RESEARCH.md#phương-pháp-đang-dùng-trong-hệ-thống).

> Câu hỏi: giọng nào **nghe rõ, tự nhiên vừa đủ**, **phát ngay** khi khách vừa nói xong, chạy offline, chi phí 0đ?

## 3.1. Các lựa chọn

| Lựa chọn | Kích thước | Tốc độ CPU | Chất lượng | Bản quyền / phí |
|----------|-----------|-----------|------------|-----------------|
| **Piper `vi_VN-vais1000-medium`** (VITS) | 63 MB (fp32) / 21 MB nén (INT8) | RTF ~0,065 | Rõ, giọng nữ, hơi "máy" | Model: dữ liệu VAIS-1000 CC BY 4.0; runtime `piper-tts` GPL-3.0 |
| Piper `vi_VN-25hours_single-low`, `vivos-x_low` | 33–67 MB | nhanh hơn | thấp hơn | như trên |
| Giọng Piper cộng đồng (fine-tune từ vais1000, nhiều giọng miền Bắc) | ~60 MB | như Piper | khá hơn | kiểm tra license từng repo |
| VITS/F5-TTS/XTTS tiếng Việt (viXTTS, VieNeu…) | 0,3–2 GB | chậm trên CPU, cần GPU | tự nhiên hơn, nhân bản giọng | tuỳ repo |
| Cloud (FPT.AI, Viettel AI, Google, Azure…) | – | phụ thuộc mạng | rất tự nhiên | Azure Neural ~15 USD/1 triệu ký tự; Google Neural2 ~16 USD; FPT/Viettel: liên hệ |

## 3.2. Đo thực tế (Piper, CPU x86 4 vCPU)

| Biến thể | Tải model | 3 câu (11,7 s âm thanh) | RTF |
|----------|-----------|--------------------------|-----|
| fp32 | 1,5 s | 0,78 s | **0,067** |
| INT8 | 3,6 s | 0,75 s | 0,062 |

Ví dụ: câu chào 4,7 s âm thanh được tạo trong **0,3–0,4 s**; câu 2,3 s mất 0,12 s.
INT8 nhỏ hơn 3 lần (tiết kiệm thẻ nhớ/tải về) nhưng không nhanh hơn rõ rệt. Mặc định dùng fp32, máy bộ nhớ ít dùng `--tts-int8`.

## 3.3. Ba kỹ thuật giảm độ trễ cảm nhận

1. **Tách câu, phát câu đầu trước** (`split_sentences`): server gửi link WAV câu 1 ngay khi tổng hợp xong, trong lúc
   tổng hợp câu 2… Trình duyệt phát lần lượt theo hàng đợi. Khách nghe AI trả lời sau ~0,2–0,3 s thay vì chờ cả đoạn.
2. **Cache theo nội dung câu** (`TTSCache`, khoá = hash(giọng + câu)): câu lặp lại (chào, hỏi khẩu vị, mời quét QR,
   "quý khách cần thêm gì nữa không ạ") phát **0 ms**. Cache tự lớn dần theo thời gian sử dụng.
3. **Dựng sẵn khi cài đặt** (`aistaff prerender`): tạo trước ~25 câu cố định (5–10 biến thể lời chào, câu hỏi khẩu vị,
   hướng dẫn, thực đơn…) — chạy 3,5 s trên x86.

## 3.4. Chuẩn hoá văn bản trước khi đọc (bắt buộc với tiếng Việt)

Engine phát âm (espeak-ng) đọc số/ký hiệu không chuẩn, nên hệ thống chuẩn hoá trước (`textnorm.tts_normalize`):

| Văn bản hiển thị | Câu đưa vào TTS |
|------------------|-----------------|
| `125.000đ` | một trăm hai mươi lăm nghìn đồng |
| `205.000đ` | hai trăm linh năm nghìn đồng |
| `10%` | mười phần trăm |
| `14:00` | mười bốn giờ |
| `mã QR`, `combo` | mã kiu a, com bô |

Màn hình hiển thị bản đầy đủ (giá, danh sách); giọng nói đọc bản **ngắn hơn** (chỉ lý do đầu tiên của mỗi món gợi ý)
để không bắt khách nghe quá lâu.

## 3.5. Lưu ý bản quyền khi bán thiết bị (quan trọng)

- **sherpa-onnx ≥ 2.0** không còn tích hợp espeak-ng (GPL) cho giọng Piper. Kiểm thử thực tế báo
  `phoneme_codepoints is empty, no lexicon, and no frontend available`. Vì vậy dự án dùng gói **`piper-tts` (GPL-3.0-or-later)**
  cho TTS, còn ASR vẫn dùng sherpa-onnx (Apache-2.0).
- Khi **phân phối thiết bị có cài `piper-tts`**, phải tuân thủ GPL cho thành phần đó (kèm giấy phép, cung cấp mã nguồn
  của piper-tts/espeak-ng). Mã nguồn ứng dụng của bạn tách thành dịch vụ riêng, gọi qua API, không trộn mã với thư viện GPL.
- Phương án **tránh GPL hoàn toàn**: dựng sẵn toàn bộ câu trên máy build (âm thanh đầu ra không chịu GPL) và chỉ dùng
  cache trên thiết bị, chấp nhận một số câu động (số tiền, tên món) ghép từ các đoạn dựng sẵn; hoặc dùng TTS cloud.
- Dữ liệu VAIS-1000 (giọng vais1000) theo **CC BY 4.0** → cần ghi công nguồn dữ liệu trong tài liệu sản phẩm.
- Nên hỏi ý kiến luật sư sở hữu trí tuệ trước khi thương mại hoá.

## 3.6. Kết luận bước 3

| Hạng mục | Quyết định |
|----------|------------|
| Giọng | `vits-piper-vi_VN-vais1000-medium` (fp32), tuỳ chọn INT8 |
| Runtime | `piper-tts` (onnxruntime CPU), khoá tuần tự trong 1 tiến trình |
| Độ trễ | câu đầu 170–300 ms (x86), cache 0 ms |
| Nâng cấp chất lượng | Fine-tune Piper từ checkpoint vais1000 bằng ~1–2 giờ thu âm giọng nhân viên thật của quán (thương hiệu riêng) |

### Nguồn
- Piper voices (vi_VN vais1000): https://huggingface.co/rhasspy/piper-voices/tree/main/vi/vi_VN/vais1000
- piper-tts (PyPI, GPL-3.0): https://pypi.org/project/piper-tts/
- sherpa-onnx TTS models release: https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models
- Giá TTS cloud (tổng hợp bên thứ ba): https://inventivehq.com/tools/developer/tts-stt-api-cost-calculator · https://diyai.io/ai-tools/audio-generation/google-cloud-text-to-speech-pricing/
- FPT.AI TTS: https://docs.fpt.ai/docs/vi/speech/documentation/text-to-speech
