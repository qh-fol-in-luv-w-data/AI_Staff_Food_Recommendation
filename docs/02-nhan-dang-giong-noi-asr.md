# Bước 2 — Nhận dạng giọng nói tiếng Việt (ASR / Speech-to-Text)

> Câu hỏi: model nào **nghe tiếng Việt đủ đúng** cho câu gọi món, **chạy offline trên CPU ARM**, với chi phí 0đ/lượt?

## 2.1. Các lựa chọn đã khảo sát (11/2026)

| Lựa chọn | Kích thước | Ghi chú tiếng Việt | Chạy edge CPU? | Phí |
|----------|-----------|--------------------|----------------|-----|
| **sherpa-onnx Zipformer-vi-30M INT8** (2026-02-09) | 26 MB nén | Từ `hynt/Zipformer-30M-RNNT-6000h`, train ~6.000 giờ tiếng Việt | ✅ rất nhẹ, có Python/C/Android | 0đ |
| sherpa-onnx Zipformer-vi INT8 (2025-04-20) | 60 MB nén (256 MB bản fp32) | Train ~70.000 giờ | ✅ | 0đ |
| PhoWhisper (VinAI) tiny/base/small/medium/large | 39M → 1,55B tham số | WER large: 8,14 (CMV-Vi), 4,67 (VIVOS); small: 11,08 / 6,33 | ⚠️ small trở lên chậm trên Pi; Whisper không streaming | 0đ |
| NVIDIA parakeet-ctc-0.6b-Vietnamese | 600M | Mạnh trên leaderboard tiếng Việt | ❌ cần GPU để nhanh | 0đ |
| Vosk vn 0.4 (small 32 MB / lớn 78 MB) | 32–78 MB | WER 15,70 trên VIVOS (bản lớn) | ✅ | 0đ |
| Cloud (Google, Azure, FPT.AI, Viettel AI…) | – | Chất lượng tốt | Cần Internet, +độ trễ mạng | Google ~0,016 USD/phút (chuẩn); FPT.AI/Viettel: liên hệ báo giá |

Loại sớm: Whisper/PhoWhisper (mô hình seq2seq lớn, không streaming, dễ "bịa" chữ khi im lặng); parakeet (cần GPU);
cloud (phí theo phút + phụ thuộc mạng). Hai ứng viên Zipformer được đo kỹ.

## 2.2. Thí nghiệm đo thực tế

**Môi trường:** Intel Xeon 2,8 GHz, 4 vCPU, sherpa-onnx 2.0.1, onnxruntime CPU.
**Dữ liệu:** 8 câu gọi món điển hình × 2 tốc độ đọc (16 câu), sinh bằng TTS Piper (giọng vais1000) rồi resample 16 kHz.
Thêm 3 file giọng người thật trong bộ test của model. Script tái lập: `python scripts/bench_speech.py`.

### Kết quả (greedy search, không hotwords)

| Model | Luồng | Tải model | RTF | Độ trễ TB / câu 1,5 s | RAM (RSS) | WER |
|-------|-------|-----------|-----|------------------------|-----------|-----|
| Zipformer-vi-30M INT8 | 1 | 1,8 s | 0,038 | 58 ms | ~167 MB | 10,6% |
| Zipformer-vi-30M INT8 | **2** | 1,4 s | **0,030** | **46 ms** | ~168 MB | 10,6% |
| Zipformer-vi-30M INT8 | 4 | 1,2 s | 0,058 | 90 ms | ~184 MB | 10,6% |
| Zipformer-vi-70kh INT8 | 1 | 1,6 s | 0,049 | 75 ms | ~220 MB | 10,6% |
| Zipformer-vi-70kh INT8 | 2 | 2,1 s | 0,049 | 76 ms | ~223 MB | 10,6% |

→ 2 luồng là tối ưu (4 luồng chậm hơn do tranh chấp). Model 30M nhanh hơn ~40%, nhẹ hơn, độ chính xác tương đương trên câu gọi món.

### Lỗi điển hình (đúng chỗ khó nhất: tên món)

```
REF: thêm một phần cơm tấm sườn bì chả      HYP: thêm một phần cầm tấm sườn bì chả
REF: cho anh một combo gia đình ...          HYP: cho anh một còn một gia đình ...
REF: bún bò huế có cay không                 HYP: bò huế có cây không
REF: thôi chốt đơn đi                        HYP: thôi chốt đơn vị
```

### Tối ưu 1: Hotwords (contextual biasing) sinh tự động từ menu

sherpa-onnx cho phép "cộng điểm" cho cụm từ cho trước khi giải mã (`modified_beam_search` + `hotwords_file`).
Hệ thống tự sinh danh sách hotword = **tên món + alias + từ khoá gọi món** (111 cụm từ với menu mẫu) mỗi lần khởi động
(`aistaff hotwords` để xem). Đổi menu → hotword tự cập nhật, **không cần train lại**.

**Thí nghiệm A** (16 câu, danh sách hotword rút gọn 13 cụm từ):

| Model | Giải mã | WER | RTF |
|-------|---------|-----|-----|
| 30M INT8 | greedy | 10,6% | 0,033 |
| 30M INT8 | beam 4 | 9,8% | 0,044 |
| 30M INT8 | beam 4 + hotwords 1,5 | 7,6% | 0,039 |
| 30M INT8 | beam 4 + hotwords 2,5 | 6,1% | 0,035 |
| 70kh INT8 | beam 4 + hotwords 2,5 | 9,1% | 0,045 |

**Thí nghiệm B** (40 câu = 10 câu gọi món × 2 tốc độ đọc × 2 lần sinh ngẫu nhiên; danh sách hotword **tự sinh đầy đủ
111 cụm từ** từ menu — đúng như khi chạy thật):

| hotwords_score | 0 (greedy) | **1,5** | 2,0 | 2,5 | 3,0 | 4,0 |
|----------------|-----------|---------|-----|-----|-----|-----|
| WER (30M INT8) | 11,0% | **8,0%** | 8,3% | 8,7% | 9,3% | 10,7% |

→ Hotwords giảm **~25–40% lỗi** gần như không tốn thêm thời gian; score quá cao (≥ 3) lại phản tác dụng
(ASR "nghe đâu cũng thấy tên món"). Mặc định: `hotwords_score: 1.5`.
Model 70.000 giờ **không** tốt hơn trên câu gọi món (WER 12,3–12,7%), lại chậm hơn → giữ model 30M làm mặc định.

> Lưu ý: dữ liệu thử là giọng TTS (giọng "máy", khó hơn giọng người ở một số âm như "chay"/"chè"). Cần đo lại với
> giọng khách thật tại quán: `python scripts/bench_speech.py --wav-dir <thư mục wav + txt>`.

### Tối ưu 2: NLU chịu lỗi ASR

Phần còn lại do NLU xử lý: so khớp mờ trên cả bản có dấu và không dấu (`cầm tấm sườn bì chả` → **Cơm tấm sườn bì chả**,
điểm 94,7), bảng nhầm lẫn số đếm (`hài ly` → 2 ly), từ khoá chốt đơn chịu lỗi (`chốt đơn vị`, `chốt lần đi` → chốt đơn).
Riêng từ mượn "combo" (model nghe thành "còn một", "có một", "cơm bô"…) có luật sửa riêng, chỉ áp dụng khi đứng
trước tên combo và sau động từ gọi món/số lượng ("cho anh một còn một gia đình" → combo gia đình).

**Kết quả đầu-cuối (ASR → NLU) trên 40 câu thí nghiệm B: hiểu đúng ý định + đúng món 37/40 câu (92,5%)**, dù WER chữ là
8–10%: NLU "sửa" được phần lớn lỗi chữ. Luồng mua hàng đầy đủ bằng giọng nói (gọi món → thêm món → hỏi khuyến mãi →
chốt đơn → xác nhận) chạy đúng 5/5 bước (`tests/test_speech.py`, `aistaff voice-file`).

## 2.3. VAD — biết khi nào khách nói xong

- **Silero VAD** (0,6 MB) qua sherpa-onnx, khung 512 mẫu (32 ms).
- `vad_min_silence: 0.5` s: im lặng 0,5 s coi như hết câu. Quán yên tĩnh có thể giảm 0,35 s (nhanh hơn), quán ồn tăng 0,7 s.
- `max_speech_duration: 15` s chống treo khi ồn liên tục.
- Trình duyệt kiosk bật **echoCancellation + noiseSuppression** (WebRTC AEC) nên micro ít thu lại tiếng loa.
  Mặc định **bán song công**: khi AI đang nói thì tạm dừng gửi âm thanh (tránh tự nghe chính mình).
  Dùng micro mảng có AEC phần cứng (loa-mic hội nghị USB) nếu muốn khách nói chen ngang (barge-in).

## 2.4. Kết luận bước 2

| Hạng mục | Quyết định |
|----------|------------|
| Model | `sherpa-onnx-zipformer-vi-30M-int8-2026-02-09` (mặc định), tuỳ chọn `--asr-large` (70.000 giờ) cho quán nhiều giọng địa phương |
| Giải mã | `modified_beam_search`, 4 đường, hotwords tự sinh từ menu, score 1.5 |
| Luồng | 2 |
| Tài nguyên | ~170 MB RAM, ~33 MB đĩa |
| Chi phí | 0đ/lượt, chạy không cần Internet |

**Hướng cải thiện tiếp (khi có dữ liệu thật):** thu âm 1–2 giờ câu gọi món thật tại quán (có đồng ý của khách),
fine-tune Zipformer bằng icefall hoặc chỉ cần mở rộng alias/hotword từ log `turns` trong SQLite (ASR nghe nhầm thành gì → thêm alias).

### Nguồn
- sherpa-onnx – Zipformer transducer models: https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/zipformer-transducer-models.html
- PhoWhisper (VinAI): https://github.com/VinAIResearch/PhoWhisper · https://arxiv.org/abs/2406.02555
- Vietnamese Open ASR Leaderboard: https://vietaudio-team-vietnamese-asr-leaderboard.hf.space/
- Vosk models: https://alphacephei.com/vosk/models
- NVIDIA parakeet-ctc-0.6b-vi: https://build.nvidia.com/nvidia/parakeet-ctc-0_6b-vi/modelcard
- Giá Google Speech-to-Text (tổng hợp bên thứ ba): https://www.costbench.com/software/ai-transcription-apis/google-speech-to-text/
- FPT.AI STT pricing (liên hệ): https://docs.fpt.ai/docs/en/speech/documentation/stt-pricing
