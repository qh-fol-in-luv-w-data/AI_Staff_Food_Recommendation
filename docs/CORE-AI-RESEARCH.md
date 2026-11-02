# Nghiên cứu Core AI: Nhân viên AI gọi món (chi tiết từng phương pháp)

> **Trạng thái: ĐỀ XUẤT ĐỂ DUYỆT.** Tài liệu này chỉ là nghiên cứu. Chưa có thay đổi nào trong code core
> (ASR, NLU, hội thoại, gợi ý, ưu đãi, TTS) được làm theo các đề xuất dưới đây.
> Mỗi phần kết thúc bằng **Đề xuất** và **Cần quyết định**. Danh sách quyết định tổng hợp ở [§14](#14-lộ-trình-và-các-quyết-định-cần-duyệt).
>
> Quy ước độ tin cậy số liệu: **[đo]** = tự đo trong dự án · **[công bố]** = số do tác giả/nhà cung cấp công bố ·
> **[ước tính]** = suy luận, cần đo lại trên thiết bị thật · **[cần kiểm chứng]** = nguồn chưa rõ hoặc mâu thuẫn.

## Mục lục

0. [Tóm tắt điều hành](#0-tóm-tắt-điều-hành)
1. [Bức tranh tổng thể & nguyên tắc thiết kế](#1-bức-tranh-tổng-thể--nguyên-tắc-thiết-kế)
2. [M1. Thu âm & tiền xử lý âm thanh (micro, khử vọng, khử ồn)](#2-m1-thu-âm--tiền-xử-lý-âm-thanh)
3. [M2. Phát hiện giọng nói & kết thúc lượt nói (VAD, end-of-turn, nói chen)](#3-m2-phát-hiện-giọng-nói--kết-thúc-lượt-nói)
4. [M3. Kích hoạt hội thoại (chạm, từ đánh thức, cảm biến)](#4-m3-kích-hoạt-hội-thoại)
5. [M4. Nhận dạng giọng nói (ASR) & ưu tiên tên món](#5-m4-nhận-dạng-giọng-nói-asr)
6. [M5. Chuẩn hoá văn bản (ITN/TN) & phục hồi dấu](#6-m5-chuẩn-hoá-văn-bản-itntn--phục-hồi-dấu)
7. [M6. Hiểu ngôn ngữ (NLU): ý định + thực thể](#7-m6-hiểu-ngôn-ngữ-nlu)
8. [M7. Quản lý hội thoại & chiến lược xác nhận](#8-m7-quản-lý-hội-thoại--chiến-lược-xác-nhận)
9. [M8. Gợi ý món & bán thêm (upsell)](#9-m8-gợi-ý-món--bán-thêm)
10. [M9. Tối ưu ưu đãi & "nhắc khéo" khách gọi thêm](#10-m9-tối-ưu-ưu-đãi--nhắc-khéo)
11. [M10. Tổng hợp giọng nói (TTS)](#11-m10-tổng-hợp-giọng-nói-tts)
12. [M11. LLM: vai trò, mô hình, an toàn](#12-m11-llm-vai-trò-mô-hình-an-toàn)
13. [M12. Đánh giá, dữ liệu & vòng lặp cải tiến](#13-m12-đánh-giá-dữ-liệu--vòng-lặp-cải-tiến)
14. [Lộ trình & các quyết định cần duyệt](#14-lộ-trình-và-các-quyết-định-cần-duyệt)
15. [Tài liệu tham khảo](#15-tài-liệu-tham-khảo)

---

## 0. Tóm tắt điều hành

**Hiện trạng v0.1 (đã chạy, đã đo):** pipeline hoàn toàn offline trên CPU. Micro trình duyệt (WebRTC AEC) → Silero VAD
→ ASR Zipformer-vi-30M INT8 + hotwords tự sinh từ menu → NLU luật + so khớp mờ → máy trạng thái hội thoại → gợi ý
content-based → engine ưu đãi tất định → TTS Piper + cache. Kết quả đo trên CPU x86 4 vCPU **[đo]**:

| Chỉ số | Giá trị |
|--------|---------|
| ASR 1 câu 1,5–2,5 s | 40–75 ms (RTF ≈ 0,03) |
| WER câu gọi món (40 câu giọng tổng hợp) | 11,0% (greedy) → 8,0% (hotwords) |
| ASR + NLU hiểu đúng món & ý định | 37/40 câu = 92,5% |
| NLU + hội thoại + tính tiền | 0,8 ms/lượt |
| TTS câu đầu | 170–300 ms (cache: 0 ms) |
| RAM toàn server | ~350 MB |

**Ba điểm yếu lớn nhất** (theo thứ tự ảnh hưởng tới trải nghiệm thật ở quán):

1. **Tiếng ồn quán + khách đứng xa micro.** Mọi số đo trên là giọng tổng hợp, sạch. Quán thật ồn 65–80 dB, có nhạc,
   tiếng bát đĩa, nhiều người nói cùng lúc. → Ưu tiên **phần cứng micro có khử vọng/khử ồn + bộ test giọng thật** (M1, M12).
2. **Kết thúc lượt nói cố định 0,5 s.** Khách Việt hay ngập ngừng giữa câu ("cho anh… ờ… hai tô phở"), dễ bị cắt.
   → Đề xuất **endpointing thích ứng có dùng NLU** (M2), gần như không tốn thêm tài nguyên.
3. **NLU luật chưa có bộ dữ liệu đo.** Chưa biết tỉ lệ câu lạ thực tế. → Đề xuất **tự sinh dữ liệu có nhiễu ASR**
   (TTS → ASR) để đo và huấn luyện bộ phân loại phụ, trước khi cân nhắc LLM (M6, M12).

**Không đề xuất** đưa LLM vào đường xử lý chính trên thiết bị giá rẻ: Pi 5 chỉ đạt khoảng 2–11 token/s, chậm hơn
luồng hiện tại hàng nghìn lần, và LLM có thể sai tiền. LLM có ROI cao ở chỗ khác: **nhập menu từ ảnh/PDF** khi
cài đặt cho quán mới, và **dự phòng** cho câu khó khi có Internet (M11).

---

## 1. Bức tranh tổng thể & nguyên tắc thiết kế

```
 [Micro] → M1 tiền xử lý → M2 VAD/kết thúc lượt → M4 ASR (+hotwords) → M5 ITN → M6 NLU → M7 hội thoại
                                                                                  │        │
                                                     M8 gợi ý ◄──────────────────┘        ├─► M9 ưu đãi/tính tiền (tất định)
                                                                                           ▼
 [Loa] ◄── M10 TTS (+cache) ◄── câu trả lời (mẫu câu)                    VietQR / SQLite
 M3 kích hoạt (chạm / từ đánh thức / cảm biến)   M11 LLM (tuỳ chọn, dự phòng)   M12 đánh giá & dữ liệu
```

**Nguyên tắc (giữ nguyên khi nâng cấp):**

- **P1. Đường tiền là tất định.** Giá, ưu đãi, tổng tiền, nội dung QR chỉ do code tính. Model AI chỉ được đề xuất
  *ý định* và *thực thể*, sau đó được kiểm tra với menu thật.
- **P2. Edge-first, cloud là tuỳ chọn.** Mọi chức năng bán hàng phải chạy khi mất mạng. Riêng xác nhận chuyển khoản
  tự động cần mạng chiều ra.
- **P3. Rẻ trước, đắt sau, có cổng tin cậy (confidence gating).** Luật (≈1 ms) → mô hình nhỏ (≈10–50 ms) → LLM (giây).
  Chỉ đi tầng sau khi tầng trước không chắc chắn.
- **P4. Đo trước khi đổi.** Mọi đề xuất đi kèm thí nghiệm và tiêu chí chấp nhận.
- **P5. Riêng tư theo thiết kế.** Không lưu âm thanh. Log văn bản có thời hạn. Thông báo rõ cho khách (xem M12).

**Ngân sách độ trễ mục tiêu** (từ lúc khách ngừng nói tới lúc AI bắt đầu nói): ≤ 1,2 s trên Pi 5. Phân bổ: chờ kết thúc
lượt 350–600 ms · ASR ≤ 250 ms · NLU/hội thoại ≤ 10 ms · TTS câu đầu ≤ 400 ms (hoặc 0 ms nếu cache).

---

## 2. M1. Thu âm & tiền xử lý âm thanh

### 2.1. Bài toán

Kiosk đặt ở quầy quán ăn. Khách đứng cách màn hình 40–80 cm. Nguồn nhiễu: nhạc, quạt, bếp, bát đĩa, người khác nói,
và **chính loa của kiosk** (tiếng Mai nói vọng lại micro, gọi là echo). ASR rất nhạy với nhiễu: WER thường tăng mạnh khi
SNR < 10 dB. Đây là phần "không thấy" nhưng quyết định chất lượng cảm nhận.

### 2.2. Các phương pháp

| Phương pháp | Cách hoạt động | Ưu | Nhược | Chi phí edge |
|-------------|----------------|----|-------|--------------|
| **Micro mảng có DSP phần cứng** (chip XMOS/loa-mic hội nghị USB) | Beamforming + khử vọng (AEC) + khử ồn chạy trên chip của micro | Hiệu quả nhất, không tốn CPU, hỗ trợ khách nói chen (barge-in) | Tốn tiền phần cứng (vài chục USD) | 0 CPU |
| **WebRTC APM** (AEC3 + NS + AGC2) | Trình duyệt Chromium tự xử lý khi `echoCancellation/noiseSuppression/autoGainControl = true` | Miễn phí, đã bật trong v0.1 | AEC phần mềm kém hơn phần cứng khi loa to và gần micro | Thấp |
| **SpeexDSP AEC** | Bộ lọc thích nghi kinh điển | Rất nhẹ, chạy native ngoài trình duyệt | Chất lượng thấp hơn AEC3 | Rất thấp |
| **RNNoise** (Xiph) | Mạng GRU nhỏ ước lượng gain theo dải tần | Rất nhẹ, realtime trên CPU yếu | Khử ồn vừa phải; tối ưu cho 48 kHz | Rất thấp |
| **GTCRN** | Mạng siêu nhẹ (48,2K tham số, 33 MMACs/giây **[công bố]**), có bản streaming trong sherpa-onnx | Cực nhẹ, tích hợp sẵn sherpa-onnx | Chất lượng thấp hơn mô hình lớn | Rất thấp |
| **DeepFilterNet 2/3** | Lọc 2 tầng (ERB + deep filtering), khoảng 2M tham số | Chất lượng khử ồn tốt | Nặng hơn; có thể tạo méo làm hại ASR | Trung bình |
| **Beamforming phần mềm** (delay-and-sum, MVDR) | Kết hợp nhiều micro để "chĩa" về phía khách | Giảm nhiễu hướng khác | Cần mảng micro đã hiệu chuẩn | Thấp–trung bình |

**Cảnh báo quan trọng:** khử ồn "nghe dễ chịu" chưa chắc giúp ASR. Mô hình khử ồn có thể làm méo phổ, khiến WER *tăng*.
Phải đo bằng **WER sau xử lý**, không đo bằng cảm nhận tai người hay PESQ/DNSMOS.

### 2.3. Thí nghiệm đề xuất

- Thu 200 câu gọi món thật × 3 điều kiện (quán vắng / giờ cao điểm / có nhạc) × 2 khoảng cách (40 cm / 80 cm).
- So sánh WER: (a) không xử lý, (b) WebRTC APM, (c) + GTCRN, (d) micro mảng phần cứng.
- **Tiêu chí chấp nhận:** cấu hình được chọn phải giảm WER ≥ 20% tương đối ở điều kiện giờ cao điểm so với (a).

### Đề xuất M1
1. Trong bộ vật tư chuẩn, **bắt buộc dùng loa-mic USB có AEC phần cứng** (hoặc micro mảng). Đây là khoản đầu tư có hiệu quả
   lớn nhất cho cả độ chính xác lẫn khả năng nói chen.
2. Giữ WebRTC APM. Thử GTCRN như bộ lọc *tuỳ chọn*, chỉ bật nếu thí nghiệm cho thấy WER giảm.
3. Thiết kế vật lý: micro hướng về khách, cách loa ≥ 15 cm; có vạch "đứng tại đây" trên sàn; màn hình hiện thanh âm lượng
   (đã có trong UI) để khách biết mình được nghe.

**Cần quyết định:** D1. Ngân sách micro/loa cho mỗi bộ (phần mềm thuần vs. thêm phần cứng có AEC).

---

## 3. M2. Phát hiện giọng nói & kết thúc lượt nói

### 3.1. Bài toán

Cần trả lời 3 câu hỏi theo thời gian thực: *Khách có đang nói không?* (VAD) · *Khách đã nói xong chưa?* (end-of-turn,
EOT) · *Khách có muốn ngắt lời Mai không?* (barge-in). Ngưỡng im lặng cố định là cách đơn giản nhưng phải đánh đổi:
ngưỡng ngắn thì hay cắt ngang câu ngập ngừng, ngưỡng dài thì chậm.

### 3.2. Phương pháp VAD

| Phương pháp | Mô tả | Ghi chú |
|-------------|-------|---------|
| Năng lượng + ZCR | Ngưỡng biên độ | Rất nhẹ, kém khi ồn |
| WebRTC VAD | Mô hình GMM | Nhanh, nhiều báo nhầm khi ồn |
| **Silero VAD** (đang dùng) | Mạng nhỏ, khung 512 mẫu @16 kHz (32 ms), giấy phép MIT | Chuẩn de-facto. Theo trang chất lượng của Silero, v6 đạt 0,87 accuracy trên clip ồn ESC-50 **[công bố, nguồn thứ ba trích]** |
| TEN VAD (Agora) | Khung 10–16 ms, thư viện ~306 KB, tự công bố chuyển trạng thái nhanh hơn Silero | **Giấy phép cấm dùng để cạnh tranh với sản phẩm của Agora** **[cần kiểm chứng điều khoản]**. Kết quả trên ESC-50 kém hơn Silero theo trang của Silero |

### 3.3. Phương pháp phát hiện kết thúc lượt (EOT)

| Phương pháp | Cách hoạt động | Ưu | Nhược |
|-------------|----------------|----|-------|
| **Ngưỡng im lặng cố định** (đang dùng: 0,5 s) | VAD báo im lặng đủ lâu thì kết thúc | Đơn giản | Đánh đổi cứng giữa nhanh và cắt câu |
| **EOT âm thanh**: Pipecat Smart Turn v3 | Mô hình dựa trên encoder Whisper-tiny, ~8 MB, 23 ngôn ngữ, khoảng 12 ms trên CPU hiện đại **[công bố]** | Nghe được ngữ điệu (giọng đi xuống = hết câu) | **Chưa xác nhận có tiếng Việt** trong 23 ngôn ngữ; cần đo trên Pi |
| **EOT văn bản**: LiveKit turn detector, Namo (VideoSDK) | Mô hình ngôn ngữ nhỏ đoán "câu đã trọn ý chưa" từ transcript | Namo có bản đa ngữ 23 thứ tiếng gồm tiếng Việt và bản riêng tiếng Việt **[công bố]** | Cần transcript từng phần, thêm 1 mô hình |
| **EOT dựa trên NLU của chính hệ thống** (đề xuất) | Khi im lặng đạt 300 ms: chạy ASR (≈50 ms) + NLU (≈1 ms) trên đoạn đã nói. Câu trọn ý ("cho 2 phở bò tái", "chốt đơn") thì kết thúc ngay. Câu dở dang (kết thúc bằng "và", "với", "thêm", "cho anh", số lượng chưa có món) thì chờ tối đa 1,0–1,2 s | Không thêm mô hình, tận dụng NLU chuyên ngành, rất rẻ | Tốn thêm 1 lần ASR khi câu dở dang |

**Nói chen (barge-in):** khi Mai đang nói mà VAD phát hiện khách nói liên tục ≥ 200 ms, dừng TTS và nghe. Chỉ khả thi khi
có AEC tốt (M1). Nếu không, tiếng Mai sẽ tự kích hoạt VAD. v0.1 chọn **bán song công** (tắt thu âm khi Mai nói) vì an toàn.

### 3.4. Thí nghiệm đề xuất

- Bộ test 300 lượt nói thật có đánh dấu thời điểm kết thúc. Đo: **độ trễ kết thúc lượt** (p50/p95), **tỉ lệ cắt ngang**,
  **tỉ lệ kích hoạt nhầm** do tiếng ồn.
- So sánh: ngưỡng 0,5 s cố định · ngưỡng 0,35 s · EOT-NLU · Smart Turn v3 (nếu có tiếng Việt).
- **Tiêu chí:** tỉ lệ cắt ngang ≤ 3%, độ trễ kết thúc lượt p50 ≤ 450 ms.

### Đề xuất M2
1. Giữ Silero VAD. Không dùng TEN VAD vì rủi ro giấy phép.
2. Triển khai **EOT dựa trên NLU** (gần như miễn phí) làm bước tiếp theo.
3. Đánh giá Smart Turn v3 / Namo-vi như phương án bổ sung khi đã có bộ test giọng thật.
4. Bật barge-in **chỉ** với bộ vật tư có AEC phần cứng.

**Cần quyết định:** D2. Có làm EOT-NLU ngay ở bản tiếp theo không. D3. Có cho phép nói chen (cần phần cứng AEC) không.

---

## 4. M3. Kích hoạt hội thoại

| Phương pháp | Mô tả | Ưu | Nhược |
|-------------|-------|----|-------|
| **Chạm màn hình** (đang dùng) | Khách chạm "Chạm để gọi món" | Chắc chắn, không bao giờ kích hoạt nhầm | Khách phải chủ động |
| **Cảm biến hiện diện** (PIR/mmWave/siêu âm, vài USD) | Có người đứng trước kiosk thì Mai chào trước | Tự nhiên, "nhân viên chủ động"; rất rẻ | Người đi ngang qua cũng kích hoạt (cần lọc thời gian đứng ≥ 1,5 s) |
| **Camera + phát hiện người** | Mô hình phát hiện người/khuôn mặt nhỏ | Biết khách nhìn vào màn hình | Nhạy cảm về riêng tư (hình ảnh là dữ liệu cá nhân), tốn CPU |
| **Từ đánh thức qua VAD + ASR** ("xin chào", "Mai ơi") | Ở màn hình chờ, VAD cắt đoạn, ASR offline nhận dạng (≈50 ms/đoạn), khớp cụm từ | Không cần huấn luyện, dùng lại model sẵn có | Tốn CPU khi quán ồn (nhiều đoạn), dễ nhầm với câu nói chuyện thường |
| **KWS chuyên dụng** (sherpa-onnx KWS, openWakeWord) | Mô hình nhỏ chỉ nghe từ khoá | Rất nhẹ, ít nhầm | sherpa-onnx chưa có model KWS tiếng Việt công khai **[tra cứu 11/2026]**. openWakeWord thiên về tiếng Anh; có thể tự huấn luyện "Mai ơi" bằng dữ liệu tổng hợp từ TTS tiếng Việt |

### Đề xuất M3
**Cảm biến hiện diện + chạm** là tổ hợp tốt nhất về chi phí và trải nghiệm. Từ đánh thức bằng VAD+ASR chỉ bật ở quán yên tĩnh.
Huấn luyện KWS riêng ("Mai ơi") để sau, khi có nhu cầu dùng hoàn toàn bằng giọng nói (vd máy bán hàng không người trông).

**Cần quyết định:** D4. Có thêm cảm biến hiện diện vào bộ vật tư chuẩn không.

---

## 5. M4. Nhận dạng giọng nói (ASR)

### 5.1. Đặc thù tiếng Việt trong bài toán gọi món

- **6 thanh điệu**: nhầm thanh làm đổi nghĩa (bún ↔ bốn, cơm ↔ cầm, chả ↔ trả, bò ↔ bơ).
- **Phương ngữ** Bắc/Trung/Nam ảnh hưởng nguyên âm và thanh (ví dụ hỏi/ngã ở miền Nam).
- **Từ mượn**: combo, size, topping, menu, ok, sale. Model thường nghe "combo" thành "còn một"/"có một" **[đo]**.
- **Câu ngắn, nhiều số đếm**, tên riêng của món (đặc sản, tên chế), ồn quán.

### 5.2. Các họ mô hình

| Họ | Ví dụ | Đặc điểm |
|----|-------|----------|
| CTC | wav2vec2-vi, NVIDIA parakeet-ctc-0.6b-vi | Giải mã nhanh, độc lập từng khung; cần LM ngoài để tốt |
| **Transducer (RNN-T)** | **Zipformer** (đang dùng) | Cân bằng tốc độ/độ chính xác, phù hợp streaming, hỗ trợ hotwords tốt |
| Encoder–decoder attention | Whisper, PhoWhisper | Chính xác ở model lớn; chậm; có thể "bịa" chữ khi im lặng/ồn; không streaming tự nhiên |
| ASR dựa trên LLM | Qwen3-ASR 0.6B / 1.7B | Rất mạnh đa ngôn ngữ; nặng |

### 5.3. So sánh ứng viên cho edge

| Model | Kích thước | Tiếng Việt (WER, bộ test khác nhau) | Edge CPU | Ghi chú |
|-------|-----------|-------------------------------------|----------|---------|
| **Zipformer-vi-30M INT8** (đang dùng) | 26 MB nén | 10–11% câu gọi món, 8% khi bật hotwords **[đo]** | ✅ RTF 0,03 | ~6.000 giờ huấn luyện |
| Zipformer-vi INT8 (70.000 giờ) | 60 MB nén | 12,3–12,7% câu gọi món **[đo]** | ✅ RTF 0,05 | Không tốt hơn trên domain này |
| PhoWhisper tiny/small/medium/large | 39M → 1,55B | large: 8,14 (CMV-Vi), 4,67 (VIVOS); small: 11,08 / 6,33 **[công bố]** | ⚠️ small trở lên chậm trên Pi | Encoder–decoder |
| Qwen3-ASR-0.6B / 1.7B | ~0,79 GB / ~2,04 GB (Q8) | FLEURS-vi: 9,32% / 6,15% **[công bố, bảng xếp hạng bên thứ ba]** | ❌ quá nặng cho Pi; ⚠️ Jetson | sherpa-onnx 2.x đã có cấu hình chạy Qwen3-ASR offline |
| parakeet-ctc-0.6b-vi | 600M | Mạnh trên Vietnamese Open ASR Leaderboard **[công bố]** | ❌ cần GPU | Train > 2.000–4.000 giờ (nguồn mâu thuẫn) |
| Vosk vn 0.4 | 32–78 MB | 15,70 VIVOS **[công bố]** | ✅ | Có chế độ ngữ pháp ràng buộc |

### 5.4. Kỹ thuật ưu tiên tên món (contextual biasing)

| Kỹ thuật | Cách làm | Ưu | Nhược | Trạng thái |
|----------|----------|----|-------|------------|
| **Hotword boosting** (context graph Aho-Corasick trong beam search) | Cộng điểm cho chuỗi token của tên món khi giải mã | Không cần train, đổi menu là xong | Score cao quá thì "nghe đâu cũng thấy món": WER tăng lại khi score ≥ 3 **[đo]** | ✅ đang dùng, score 1,5 |
| **LM chuyên ngành (shallow fusion / rescoring)** | Sinh vài chục nghìn câu gọi món từ mẫu câu + menu, huấn luyện n-gram/RNN-LM nhỏ, kết hợp khi giải mã | Học cả cấu trúc câu ("cho … hai tô …") chứ không chỉ tên món | Cần pipeline sinh dữ liệu; sherpa-onnx hỗ trợ LM cho một số chế độ, cần kiểm tra với model này | Đề xuất thử |
| **Giải mã ràng buộc ngữ pháp** (WFST/grammar) | Chỉ cho phép câu thuộc ngữ pháp | Chính xác trong phạm vi | Câu ngoài ngữ pháp bị ép sai | Không khuyến nghị làm đường chính |
| **Biasing thần kinh** (CLAS, TCPGen, deep biasing) | Mô-đun attention trên danh sách cụm từ, cần huấn luyện | Tốt nhất trên lý thuyết | Phải train lại model | Để sau |
| **Hậu xử lý theo ngữ âm** | Khớp mờ có trọng số theo nhầm lẫn thanh/vần ("cầm" gần "cơm") | Rẻ, đặt ở NLU | Không sửa được lỗi mất từ | ✅ dạng đơn giản (so khớp mờ) |
| **Chọn giả thuyết theo NLU** | Lấy nhiều giả thuyết (greedy + beam/N-best), chọn cái NLU phân tích ra món hợp lệ với điểm cao nhất | Tận dụng tri thức menu | Tốn thêm 1 lần giải mã | Đề xuất thử |

### 5.5. Tinh chỉnh (fine-tune) model

- **Zipformer + icefall:** fine-tune với 10–50 giờ dữ liệu trong miền (câu gọi món thật + tổng hợp từ TTS nhiều giọng,
  trộn nhiễu quán ăn). Rủi ro: quên kiến thức chung (catastrophic forgetting) → trộn dữ liệu chung, learning rate thấp.
- **Dữ liệu tổng hợp:** TTS tiếng Việt nhiều giọng (Piper + giọng cộng đồng + VieNeu) đọc 10.000 câu sinh từ mẫu, trộn
  tiếng ồn quán thu thật, mô phỏng phòng (RIR). Rẻ nhưng giọng tổng hợp khác giọng thật → phải đánh giá trên giọng thật.
- **Chi phí ước tính [ước tính]:** 1 GPU thuê vài giờ cho fine-tune nhẹ; phần đắt là thu và gán nhãn 1–3 giờ giọng thật.

### 5.6. Streaming hay offline

v0.1 dùng **offline + VAD** ("simulated streaming"): giải mã cả câu sau khi khách nói xong, chính xác hơn và đơn giản.
Streaming thật cho phép hiện chữ ngay khi khách đang nói (UI sinh động hơn) và EOT sớm hơn, nhưng **chưa thấy model
Zipformer streaming tiếng Việt chính thức** trong sherpa-onnx **[tra cứu 11/2026]**. Dự án cộng đồng *phostt* dùng
cách bộ đệm chồng lấp (overlap-buffer) với weights offline. Có thể làm "transcript tạm" bằng cách chạy lại ASR offline mỗi
600–800 ms trên đoạn đang nói (≈50 ms/lần), đủ rẻ trên Pi.

### Đề xuất M4
1. Giữ **Zipformer-vi-30M INT8** làm mặc định. Hotwords score 1,5–2,0.
2. Bổ sung **LM chuyên ngành sinh từ mẫu câu** và **chọn giả thuyết theo NLU**. Đo trên bộ test thật trước khi bật.
3. Bản cao cấp (Jetson/RK3588): đánh giá **Qwen3-ASR-0.6B** làm "ASR thứ hai" chỉ cho câu NLU không chắc chắn
   (cascade theo độ tin cậy).
4. Lập kế hoạch thu dữ liệu thật có đồng ý của khách (M12), rồi fine-tune Zipformer khi có ≥ 10 giờ.

**Cần quyết định:** D5. Mức đầu tư dữ liệu giọng thật (thu âm thí điểm 1–3 giờ). D6. Có làm bản "cao cấp" dùng ASR lớn không.

---

## 6. M5. Chuẩn hoá văn bản (ITN/TN) & phục hồi dấu

| Bài toán | Phương pháp | Đánh giá | Trạng thái |
|----------|-------------|----------|------------|
| **ITN** (lời nói → số): "một trăm hai mươi lăm nghìn" → 125000, "hai lăm" → 25, "một triệu hai" → 1.200.000 | (a) luật thủ công; (b) văn phạm WFST (NeMo-text-processing có ITN nhiều ngôn ngữ, **chưa xác nhận có tiếng Việt**); (c) seq2seq thần kinh | Domain hẹp nên luật đủ, tất định, < 0,1 ms | ✅ luật, 30 ca test |
| **TN cho TTS** (số → lời): giá tiền, %, giờ, viết tắt (QR, combo) | Luật | Cần mở rộng cho mã đơn (đọc từng nhóm số), số điện thoại | ✅ cơ bản |
| **Phục hồi dấu** cho chữ gõ không dấu | n-gram + Viterbi; dịch máy (phrase-based 97,32% độ chính xác từ); RNN mức ký tự (97,73%); Transformer/XLM-R (~97–98%) **[công bố, bộ test khác nhau]** | Chỉ cần khi trả lời câu hỏi tự do. Với gọi món, **so khớp không dấu với menu** đã đủ | Không cần |
| **Phục hồi dấu câu** | Mô hình punctuation | NLU không cần dấu câu | Không cần |

### Đề xuất M5
Giữ ITN luật. Bổ sung TN đọc mã đơn/số điện thoại. Không làm phục hồi dấu trừ khi mở rộng sang hỏi đáp tự do.

---

## 7. M6. Hiểu ngôn ngữ (NLU)

### 7.1. Định nghĩa bài toán

- **Ý định (≈30):** gọi món, gọi chung chung, chọn theo thứ tự, bớt/bỏ, sửa số lượng, đổi món, hỏi gợi ý, nêu khẩu vị,
  hỏi menu/giá/thông tin món/ưu đãi, xem đơn, chốt đơn, chọn cách trả, huỷ, đồng ý/từ chối, nhắc lại…
- **Thực thể (slot):** món (liên kết tới id trong menu), số lượng, tuỳ chọn (size), ghi chú (không hành…), vị thích/ghét,
  ăn chay, thành phần kiêng/dị ứng, món nước/khô, nóng/lạnh, ngân sách, số người, thứ tự, hình thức thanh toán, mang về.

### 7.2. Các phương pháp

| # | Phương pháp | Cách hoạt động | Ưu | Nhược | Chi phí edge |
|---|-------------|----------------|----|-------|--------------|
| a | **Luật + từ điển + so khớp mờ** (đang dùng) | Regex có/không dấu, n-gram so với tên món bằng rapidfuzz, phạm vi phủ định, ràng buộc chống nhận nhầm | 0,8 ms, tất định, sửa menu không cần train, giải thích được | Câu diễn đạt lạ dễ trượt; tốn công viết luật | ≈0 |
| b | **ML cổ điển**: TF-IDF n-gram ký tự + Logistic Regression/SVM, fastText | Phân loại ý định | Nhanh (< 1 ms), chịu lỗi chính tả/ASR tốt nhờ n-gram ký tự | Cần 50–100 câu/ý định; không tự trích thực thể | ≈0 |
| c | **Embedding câu + kNN / SetFit** | So câu khách với câu mẫu bằng vector (multilingual-e5-small ~118M tham số) | Few-shot (10–20 câu/ý định), hiểu diễn đạt khác | Model 100M+, 20–60 ms trên Pi **[ước tính]** | Trung bình |
| d | **Transformer ý định + slot chung**: JointBERT / **JointIDSF + PhoBERT** | Mã hoá câu, phân loại ý định + gán nhãn BIO cho slot, có attention ý định–slot | Trên PhoATIS: ý định 97,62%, slot F1 94,98%, cả câu 86,25% **[công bố]** | Cần vài nghìn câu gán nhãn; cần tách từ (RDRSegmenter); PhoBERT-base 135M tham số | Trung bình (ONNX INT8 ≈ 100+ MB) |
| e | **LLM** (prompt / function calling / JSON có ràng buộc ngữ pháp GBNF) | LLM nhỏ trích xuất cấu trúc | Hiểu câu tự do tốt nhất | Pi 5 chỉ 2–11 token/s **[công bố]**; có thể sai; khó đảm bảo | Cao |
| f | **Cascade có cổng tin cậy** (đề xuất) | a → (nếu không chắc) b/c → (nếu vẫn không chắc) e | Giữ tốc độ của a cho ~90% câu, tăng độ phủ | Phức tạp hơn khi vận hành | Thấp trung bình |

### 7.3. Liên kết thực thể món (entity linking)

- **Độ giống chuỗi:** Levenshtein ratio (đang dùng), token-set ratio, Jaro–Winkler.
- **Độ giống ngữ âm tiếng Việt (đề xuất):** tách âm tiết thành *phụ âm đầu / vần / thanh*, đặt chi phí thay thế theo
  **ma trận nhầm lẫn thật của ASR** (thu từ log): nhầm thanh hoặc vần gần (cơm↔cầm, bún↔bốn) rẻ hơn nhầm phụ âm đầu
  xa (bún↔mún). Chính xác hơn edit-distance ký tự thuần mà vẫn < 1 ms.
- **Embedding ngữ nghĩa** cho alias tự nhiên ("món nước có bò" → các món phở/bún bò) dùng cho gợi ý hơn là gọi món.
- **Mở rộng alias từ log:** câu khách nói + món nhân viên xác nhận → đề xuất alias mới cho chủ quán duyệt.

### 7.4. Dữ liệu: tự sinh dữ liệu có nhiễu ASR (đề xuất quan trọng)

1. **Bộ sinh câu từ mẫu + menu:** "cho {tôi|anh|em} {số} {lượng từ} {món} {ghi chú}", "{món} có {vị} không", "đi {n} người,
   {kiêng}, dưới {tiền}"… sinh 20–50 nghìn câu có nhãn ý định + slot tự động.
2. **Vòng TTS → ASR:** đọc câu bằng nhiều giọng TTS (thêm tốc độ, nhiễu quán), cho qua chính ASR của hệ thống, được cặp
   (văn bản ASR có lỗi thật, nhãn đúng). Đây là dữ liệu huấn luyện/đo **chịu lỗi ASR** mà không tốn công gán nhãn.
3. Trộn với log thật (khi có) theo tỉ lệ tăng dần.

### 7.5. Thí nghiệm đề xuất

- Ba bộ test: (i) gõ chuẩn, (ii) ASR-hoá tổng hợp, (iii) giọng thật. Đo **độ chính xác ý định**, **F1 slot**, **khớp cả khung
  (frame accuracy)**, **tỉ lệ `unknown`**, ma trận nhầm lẫn theo ý định.
- So sánh a / a+b / a+c / d trên cùng bộ test. **Tiêu chí:** khớp cả khung ≥ 92% trên giọng thật, p95 độ trễ ≤ 30 ms trên Pi 5.

### Đề xuất M6
1. Giữ **luật** làm xương sống.
2. Xây **bộ sinh dữ liệu + vòng TTS→ASR** (giá trị lớn nhất, dùng cho cả đo lường và huấn luyện).
3. Thêm **bộ phân loại n-gram ký tự** (phương án b) làm "ý kiến thứ hai" cho ý định khi luật không chắc.
4. Thêm **khoảng cách ngữ âm theo nhầm lẫn ASR** cho liên kết món.
5. Chỉ cân nhắc JointIDSF/PhoBERT khi bộ test cho thấy a+b chưa đạt tiêu chí.

**Cần quyết định:** D7. Có ưu tiên xây bộ sinh dữ liệu + benchmark NLU trước mọi nâng cấp mô hình không.

---

## 8. M7. Quản lý hội thoại & chiến lược xác nhận

### 8.1. Phương pháp quản lý hội thoại

| Phương pháp | Mô tả | Phù hợp |
|-------------|-------|---------|
| **Máy trạng thái / frame-based** (đang dùng) | Trạng thái rõ: chào → hỏi khẩu vị → gọi món → xác nhận → thanh toán | Domain giao dịch hẹp, kiểm thử được |
| Information-State Update (ISU) | Trạng thái là "bảng thông tin" (giỏ, sở thích, câu hỏi đang chờ) + luật cập nhật | Linh hoạt hơn FSM; v0.1 đã có một phần (`pending`) |
| Thống kê (POMDP / học tăng cường) | Học chính sách hỏi/xác nhận tối ưu dưới bất định | Cần mô phỏng người dùng + nhiều dữ liệu; quá mức cho v1 |
| **LLM agent + công cụ** | LLM gọi hàm `add_item`, `checkout`… | Tự nhiên; khó kiểm soát; chậm trên edge |
| **Lai "LLM đề xuất, luật quyết định"** | LLM chỉ đề xuất hành động; luật kiểm tra hợp lệ rồi thực thi | Hướng nâng cấp an toàn nếu bật LLM |

### 8.2. Chiến lược xác nhận theo độ tin cậy

- **Ngầm định** (đang dùng cho gọi món): "Dạ, em đã thêm 2 tô Phở bò tái". Khách nghe sai thì sửa ngay; nhanh.
- **Tường minh** ("Có phải quý khách gọi Phở bò tái không ạ?"): dùng khi độ tin cậy ASR/NLU thấp, hoặc món đắt/số lượng
  lớn bất thường (≥ 5 phần).
- **Luôn tường minh ở bước tiền**: đọc lại đơn + tổng tiền trước khi tạo QR (đang làm).
- **Đề xuất:** chính sách "chi phí lỗi": xác nhận tường minh khi (độ tin cậy < ngưỡng) **hoặc** (giá trị dòng ≥ X đồng)
  **hoặc** (số lượng ≥ 5). Có 2 lựa chọn gần nhau thì hỏi "Phở bò tái hay phở bò chín ạ?".

### 8.3. Phục hồi lỗi & tình huống thật

- Câu không hiểu: lần 1 hỏi lại kèm ví dụ · lần 2 đưa nút chọn · lần 3 mời chạm màn hình/gọi nhân viên (đang làm).
- Hai người nói cùng lúc, trẻ em nói chen: VAD + EOT; nếu ASR ra câu lẫn lộn thì ưu tiên hỏi lại thay vì đoán.
- Khách bỏ đi giữa chừng: hết thời gian chờ → về màn hình chờ (đang làm). Đề xuất: giữ giỏ thêm 60 s nếu cảm biến
  vẫn thấy người.
- Câu trả lời: mẫu câu (đang dùng) + nhiều biến thể để không lặp. Lợi thế phụ: câu cố định cache TTS được (0 ms).
  **Không** dùng LLM viết lại câu có chứa số tiền.

### Đề xuất M7
Giữ FSM + trạng thái chờ (ISU nhẹ). Thêm **xác nhận theo chi phí lỗi** và **hỏi lại 2 lựa chọn gần nhất** khi độ tin cậy
liên kết món thấp. Đo: tỉ lệ hoàn tất đơn, số lượt/đơn, thời gian/đơn, tỉ lệ chuyển sang chạm.

**Cần quyết định:** D8. Ngưỡng giá trị/số lượng bắt buộc xác nhận tường minh.

---

## 9. M8. Gợi ý món & bán thêm

### 9.1. Phân loại phương pháp

| Phương pháp | Cách hoạt động | Cần dữ liệu | Ưu | Nhược |
|-------------|----------------|-------------|----|-------|
| **Dựa tri thức / ràng buộc** (đang dùng) | Lọc cứng (chay, dị ứng, ngân sách, vị không ăn được) + chấm điểm theo thuộc tính, kèm lý do | Không (chỉ menu) | Chạy ngay ở quán mới, giải thích được, an toàn dị ứng | Không học từ hành vi |
| Dựa nội dung (vector vị) | Biểu diễn món bằng vector (cay, ngọt, chua, đậm, béo, nước/khô…), so cosine với hồ sơ khẩu vị | Không | Mượt hơn luật | Vẫn không học |
| Phổ biến theo ngữ cảnh | Món bán chạy theo giờ/ngày/thời tiết | Lịch sử đơn | Baseline mạnh, đơn giản | Không cá nhân hoá |
| **Luật kết hợp** (Apriori/FP-Growth) | "Hay gọi cùng": support, confidence, lift | ≥ 1–2 nghìn đơn | Upsell sát thực tế ("phở → quẩy") | Thiên về món phổ biến |
| Lọc cộng tác (item-item, ALS ngầm, BPR) | Học từ ma trận đơn–món | Nhiều đơn | Phát hiện quan hệ ẩn | Kiosk ẩn danh → chủ yếu item-item theo phiên |
| Gợi ý theo phiên (GRU4Rec, SASRec) | Mô hình chuỗi | Rất nhiều | Mạnh ở thương mại điện tử | Quá mức cho đơn 2–5 món |
| **Contextual bandit** (LinUCB, Thompson sampling) | Chọn món gợi ý/upsell theo ngữ cảnh, vừa khai thác vừa thăm dò, tối ưu tỉ lệ nhận/giá trị đơn | Học dần online | Tự cải thiện, cân bằng thử món mới | Cần đo lường cẩn thận, tránh "đẩy" quá đà |
| Learning-to-rank (LightGBM LambdaMART) | Học xếp hạng từ log gợi ý → chọn | ≥ 10 nghìn lượt gợi ý | Kết hợp mọi đặc trưng | Cần pipeline dữ liệu |
| LLM gợi ý hội thoại | LLM chọn món + giải thích | Không | Lời giải thích tự nhiên | Có thể gợi món không có, sai dị ứng → phải ràng buộc vào ứng viên do luật lọc |

### 9.2. Ngữ cảnh & ràng buộc kinh doanh nên thêm

Giờ trong ngày (sáng ưu tiên phở/cà phê), thời tiết (nóng → đồ uống lạnh; cần Internet hoặc cảm biến nhiệt), **món hết hàng**
(bắt buộc: nhân viên bật/tắt nhanh trên /admin), **tải bếp** (giờ cao điểm hạn chế gợi ý món chế biến lâu), **biên lợi nhuận**
(trọng số do chủ quán đặt, đã có `boost`), ưu đãi đang chạy (đã có).

### 9.3. Đánh giá

- Offline: hit-rate@3 / NDCG trên lịch sử đơn (món khách thực sự gọi có nằm trong 3 gợi ý không).
- Online: **tỉ lệ nhận gợi ý**, **tỉ lệ nhận upsell**, **giá trị đơn trung bình (AOV)** so với nhóm đối chứng không gợi ý
  (A/B, ví dụ 10% phiên không upsell), số lần khách từ chối liên tiếp (dấu hiệu làm phiền).
- Rào chắn đạo đức: không gợi ý món vi phạm dị ứng/kiêng (lọc cứng, có test), không upsell quá 1 lần/nhóm món, lý do
  hiển thị phải đúng sự thật.

### Đề xuất M8 (phân kỳ theo lượng dữ liệu)
- **Giai đoạn 1 (ngay):** thêm *món hết hàng*, *giờ trong ngày*, *tải bếp* vào bộ lọc/chấm điểm hiện tại.
- **Giai đoạn 2 (≥ 1–2 nghìn đơn):** upsell bằng **luật kết hợp** (FP-Growth) thay cho `pairs_with` cấu hình tay.
- **Giai đoạn 3 (≥ 10 nghìn lượt):** **Thompson sampling** chọn món upsell, có nhóm đối chứng để đo AOV thật.

**Cần quyết định:** D9. Mục tiêu tối ưu của gợi ý: hài lòng khách / giá trị đơn / biên lợi nhuận (trọng số giữa các mục tiêu).

---

## 10. M9. Tối ưu ưu đãi & "nhắc khéo"

### 10.1. Bài toán chọn ưu đãi

Cho giỏ hàng và tập ưu đãi đang hiệu lực, chọn tập con S tối đa hoá lợi ích cho khách (tiền giảm + giá trị quà), với ràng
buộc loại trừ (ưu đãi độc quyền không cộng dồn) và thứ tự áp dụng (giảm theo món trước, giảm hoá đơn sau).

- **Hiện tại:** so sánh {mọi ưu đãi cộng dồn được} với {từng ưu đãi độc quyền}. Đây là lời giải **chính xác** cho cấu trúc
  hai lớp này.
- **Tổng quát** (nhóm loại trừ tuỳ ý, giới hạn số lần dùng, ưu đãi theo khách): duyệt tập con có cắt tỉa (n ≤ 20 ưu đãi
  đồng thời là đủ nhanh) hoặc quy hoạch nguyên (ILP) nếu cấu hình phức tạp.
- Quy tắc phụ: làm tròn tiền giảm, trần giảm, ưu đãi trên combo đã giảm sẵn.

### 10.2. "Nhắc khéo": từ gợi ý số tiền sang gợi ý món cụ thể

Hiện tại AI nói "gọi thêm 25.000đ nữa là được giảm 10%". Tốt hơn là đề xuất **một món cụ thể** vừa đủ ngưỡng:

> Tìm món m (hoặc cặp món) sao cho tổng mới ≥ ngưỡng, **phần vượt ngưỡng nhỏ nhất**, và **xác suất khách nhận cao nhất**
> (điểm gợi ý M8 + món hay đi kèm). Đây là biến thể nhỏ của subset-sum/knapsack: với menu < 100 món, duyệt 1–2 món là đủ (< 1 ms).

Ví dụ: "Quý khách thêm 1 ly trà tắc 15.000đ là đủ 200.000đ để được tặng chè ba màu ạ."

### 10.3. Ràng buộc pháp lý cần đưa vào kiểm tra cấu hình

- Theo NĐ 81/2018/NĐ-CP (sửa đổi bởi NĐ 128/2024/NĐ-CP, hiệu lực 01/12/2024): mức giảm giá khuyến mại **tối đa 50%** giá
  trước khuyến mại, trừ chương trình khuyến mại tập trung do cơ quan có thẩm quyền tổ chức (tới 100%).
- **NĐ 239/2026/NĐ-CP (hiệu lực 26/6/2026)** được cho là sửa quy định xúc tiến thương mại **[cần kiểm chứng xem trần 50% có đổi không]**.
- Đề xuất: lệnh `aistaff validate` cảnh báo khi ưu đãi giảm > 50% hoặc giá trị quà vượt hạn mức, kèm ghi chú
  "đối chiếu quy định hiện hành". Đây là cảnh báo, không chặn.

### Đề xuất M9
Thêm **nhắc khéo bằng món cụ thể** và **cảnh báo pháp lý trong validate**. Mở rộng thuật toán chọn ưu đãi sang nhóm loại
trừ tổng quát khi có quán cần.

**Cần quyết định:** D10. Có muốn AI nhắc khéo bằng món cụ thể không (tăng AOV nhưng phải tránh gây khó chịu).

---

## 11. M10. Tổng hợp giọng nói (TTS)

### 11.1. Các họ phương pháp

| Họ | Ví dụ | Đặc điểm |
|----|-------|----------|
| Ghép nối (concatenative) | Ghép đoạn thu sẵn | Tự nhiên ở câu cố định, cứng ở câu động. Có thể dùng **kết hợp** cho câu cố định |
| Hai tầng thần kinh | FastSpeech2 + HiFi-GAN | Nhanh, ổn định |
| **End-to-end VITS** | **Piper** (đang dùng) | Nhẹ, RTF ≈ 0,065 trên x86 **[đo]**; chất lượng khá; giọng hơi "máy" |
| Flow matching | Matcha-TTS, F5-TTS | Chất lượng cao; F5 nhân bản giọng; nặng hơn |
| Style-based | StyleTTS2, Kokoro-82M | Kokoro rất nhẹ và tự nhiên nhưng **chưa thấy giọng tiếng Việt chính thức** **[cần kiểm chứng]** |
| TTS dựa trên LLM/codec | **VieNeu-TTS v3 Turbo** (48 kHz), XTTS-v2 | VieNeu: chạy ONNX trên CPU, âm đầu ~300 ms, RTF < 1 **[công bố]**; model ~1 GB **[công bố, blog]** |

### 11.2. Giấy phép (quan trọng khi bán thiết bị)

| Lựa chọn | Giấy phép | Dùng thương mại? |
|----------|-----------|------------------|
| Piper runtime `piper-tts` | GPL-3.0 | Được, nhưng phải tuân thủ GPL cho thành phần này (xem docs/03 §3.5) |
| Giọng vi_VN-vais1000 | Dữ liệu VAIS-1000 CC BY 4.0 | Được, cần ghi công |
| VieNeu-TTS | Blog nói Apache-2.0 cho model + dữ liệu | **Cần kiểm chứng model card** |
| Coqui XTTS-v2 / viXTTS | Coqui Public Model License | **Không** (phi thương mại) |
| Meta MMS-TTS (vie) | CC-BY-NC 4.0 | **Không** |
| Nhiều checkpoint F5-TTS | Thường phi thương mại do dữ liệu huấn luyện | **Kiểm tra từng checkpoint** |
| TTS đám mây (FPT.AI, Viettel AI, Zalo, Google, Azure) | Theo hợp đồng | Được, trả phí theo ký tự |

### 11.3. Đặc thù tiếng Việt & thương hiệu

- Thanh điệu phải chuẩn; G2P qua espeak-ng (Piper) đôi khi đọc sai từ mượn → chuẩn hoá trước (đã làm cho QR, combo).
- **Giọng vùng miền:** vais1000 là giọng nữ phía Bắc **[cần kiểm chứng]**. Quán ở TP.HCM có thể muốn giọng Nam → fine-tune
  Piper với 1–2 giờ thu âm (có hợp đồng sử dụng giọng).
- **Giọng thương hiệu:** mỗi chuỗi quán có thể có giọng riêng (dịch vụ bán thêm).
- Ngữ điệu khi đọc danh sách và giá tiền: tách câu ngắn, ngắt nghỉ sau mỗi món (đang tách câu).

### 11.4. Đánh giá

MOS (10–20 người nghe, thang 1–5, gồm khách hàng thật), **CER khứ hồi** (TTS → ASR → so chữ; đo tính dễ hiểu tự động),
RTF và độ trễ câu đầu trên Pi 5, tỉ lệ cache hit sau 1 tuần vận hành.

### Đề xuất M10
1. Giữ **Piper** làm mặc định (nhẹ, đã tích hợp, cache tốt).
2. **Đánh giá VieNeu-TTS v3 Turbo trên Pi 5** (độ trễ, RAM, MOS) **sau khi xác minh giấy phép**. Nếu đạt thì đưa vào bản cao cấp.
3. Gói "giọng thương hiệu": fine-tune Piper (giọng Nam/Bắc theo vùng).
4. Loại khỏi danh sách: XTTS, MMS (giấy phép).

**Cần quyết định:** D11. Giọng mặc định (Bắc/Nam), và có đầu tư giọng thương hiệu không.

---

## 12. M11. LLM: vai trò, mô hình, an toàn

### 12.1. Vai trò có giá trị (xếp theo ROI)

1. **Nhập menu từ ảnh/PDF (khi cài đặt cho quán mới).** LLM đa phương thức đọc ảnh menu và sinh nháp `menu.yaml`
   (tên, giá, alias, nhóm, vị ước lượng). Chủ quán duyệt lại. Rút thời gian onboarding từ hàng giờ xuống vài phút.
   Chạy trên cloud một lần, **không chạy trên thiết bị**.
2. **Dự phòng NLU** (đã thiết kế): chỉ khi ý định `unknown`. LLM viết lại thành câu lệnh chuẩn, rồi NLU luật xử lý tiếp.
3. **Khai phá log** (offline, định kỳ): gom câu `unknown`, đề xuất alias, ý định mới, mẫu câu.
4. **Hỏi đáp tự do về món** (thành phần, dị ứng) qua RAG trên dữ liệu menu. **Rủi ro cao** với câu hỏi dị ứng, nên trả lời
   bằng dữ liệu cấu trúc (`contains`, `allergens`), LLM chỉ diễn đạt.

### 12.2. Mô hình & phần cứng

| Lựa chọn | Ghi chú |
|----------|---------|
| Qwen3.5 dòng nhỏ (0,8B → 9B, Apache-2.0) **[công bố]** | Đa ngôn ngữ mạnh; cần tự đo tiếng Việt trên câu gọi món |
| Gemma 4 E2B (khoảng 1,1 GB trên di động, nhận văn bản/ảnh/âm thanh) **[công bố]** | Hợp thiết bị yếu; cần đo tiếng Việt |
| Mô hình tinh chỉnh tiếng Việt (Vistral, VyLinh, SeaLLMs…) | Tốt tiếng Việt nhưng thường ≥ 3–7B |
| Tốc độ trên Pi 5 | Llama 3.2 1B khoảng 11 token/s, Qwen2.5 3B khoảng 5,2 token/s (qua Ollama) **[công bố]** → câu JSON 30 token mất 3–6 s |
| Jetson Orin Nano Super / RK3588 (RKLLM) | 1–4B chạy được ở tốc độ hội thoại; tăng 150–250 USD/bộ |

### 12.3. An toàn (bắt buộc nếu bật LLM)

- **Giải mã có ràng buộc** (GBNF/JSON schema trong llama.cpp) để đầu ra luôn đúng cấu trúc.
- **Kiểm tra lại với menu:** mọi món/ý định LLM trả về phải ánh xạ được vào menu, nếu không thì bỏ.
- **Không bao giờ** để LLM tính tiền, áp ưu đãi, sinh nội dung QR (P1).
- Giới hạn thời gian (6 s) rồi quay về luật; ghi log để đánh giá.
- Chi phí cloud dự phòng **[ước tính]:** ~300 token vào + 20 token ra mỗi lần, chỉ cho ~5% lượt (câu `unknown`) → rất nhỏ
  so với STT/TTS cloud; điều kiện là có Internet.

### Đề xuất M11
1. Làm **công cụ nhập menu từ ảnh** (ROI cao nhất, không ảnh hưởng thiết bị).
2. Giữ LLM dự phòng **tắt mặc định**. Trước khi bật cục bộ, chấm Qwen3.5-2B và Gemma-4-E2B trên bộ test NLU (M6).
3. Không dùng LLM cho câu hỏi dị ứng nếu chưa có dữ liệu `allergens` chuẩn.

**Cần quyết định:** D12. Có làm công cụ nhập menu bằng LLM (cloud) không. D13. Có bản phần cứng cao cấp chạy LLM cục bộ không.

---

## 13. M12. Đánh giá, dữ liệu & vòng lặp cải tiến

### 13.1. Bộ chỉ số theo thành phần

| Thành phần | Chỉ số chính | Mục tiêu đề xuất |
|------------|--------------|------------------|
| M1 thu âm | WER theo điều kiện ồn/khoảng cách | Giảm ≥ 20% so với không xử lý |
| M2 VAD/EOT | Trễ kết thúc lượt p50/p95, % cắt ngang, % kích hoạt nhầm | p50 ≤ 450 ms, cắt ngang ≤ 3% |
| M4 ASR | WER, **tỉ lệ sai tên món** | Sai tên món ≤ 5% (giọng thật) |
| M6 NLU | Độ chính xác ý định, F1 slot, khớp cả khung, % unknown | Khớp khung ≥ 92%, unknown ≤ 5% |
| M7 hội thoại | **Tỉ lệ hoàn tất đơn**, số lượt/đơn, thời gian/đơn, % chuyển sang chạm | Hoàn tất ≥ 85%, ≤ 90 s/đơn |
| M8 gợi ý | Tỉ lệ nhận gợi ý/upsell, AOV so với đối chứng | Tăng AOV có ý nghĩa thống kê |
| M10 TTS | MOS, CER khứ hồi, trễ câu đầu | MOS ≥ 3,8; trễ ≤ 400 ms trên Pi 5 |
| Toàn hệ thống | Trễ "ngừng nói → AI nói" p95, sự cố/ngày | ≤ 1,5 s; 0 sai tiền |

### 13.2. Dữ liệu & quyền riêng tư

- **Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15 + NĐ 356/2025 (hiệu lực 01/01/2026):** báo chí phân tích dữ liệu sinh trắc học
  (gồm giọng nói) thuộc nhóm nhạy cảm **[cần đối chiếu văn bản gốc]**. Thiết kế hiện tại không lưu âm thanh.
- **Thu dữ liệu giọng để cải tiến** (nếu duyệt): chế độ thí điểm có **đồng ý rõ ràng** (màn hình hỏi "Cho phép ghi âm để cải
  thiện chất lượng?"), lưu mã hoá, thời hạn ngắn, chỉ ở quán thí điểm, có quy trình xoá.
- Log văn bản: mặc định giữ 30 ngày, ẩn số điện thoại nếu có.

### 13.3. Vòng lặp cải tiến (data flywheel)

```
log văn bản (unknown, hỏi lại, sửa đơn) → gom cụm hằng tuần (có thể dùng LLM offline)
  → đề xuất alias / mẫu câu / ý định mới → chủ quán hoặc đội vận hành duyệt
  → cập nhật YAML + bộ test hồi quy → phát hành qua OTA → đo lại chỉ số
```

- **Bộ test hồi quy** (đã có 99 test) bổ sung: bộ ASR-hoá tổng hợp + bộ giọng thật ẩn danh. Chạy trước mỗi lần cập nhật.
- **A/B trên kiosk:** cờ cấu hình chia phiên ngẫu nhiên (vd 90/10) cho thay đổi gợi ý/upsell, đo bằng SQLite rồi đồng bộ báo cáo.
- **Giám sát:** độ trễ p50/p95 từng khâu (đã ghi `latency_ms`), tỉ lệ unknown theo ngày, cảnh báo khi vượt ngưỡng.

**Cần quyết định:** D14. Có triển khai chế độ thu dữ liệu giọng có đồng ý ở quán thí điểm không.

---

## 14. Lộ trình và các quyết định cần duyệt

### 14.1. Lộ trình đề xuất

| Giai đoạn | Nội dung core AI | Điều kiện / chi phí |
|-----------|------------------|---------------------|
| **G1 (2–3 tuần)** | Bộ sinh dữ liệu + vòng TTS→ASR + benchmark NLU (M6) · EOT dựa trên NLU (M2) · xác nhận theo chi phí lỗi (M7) · nhắc khéo bằng món cụ thể + cảnh báo pháp lý ưu đãi (M9) · món hết hàng/giờ trong ngày (M8) | Chỉ công phát triển; không đổi phần cứng |
| **G2 (thí điểm 2–4 tuần tại 1–2 quán)** | Thu bộ test giọng thật (có đồng ý) · so sánh micro/AEC (M1) · đo EOT · khoảng cách ngữ âm + bộ phân loại n-gram (M6) · LM chuyên ngành cho ASR (M4) | Bộ micro thử nghiệm; thời gian nhân sự gán nhãn |
| **G3** | Fine-tune Zipformer (≥ 10 giờ dữ liệu) · upsell luật kết hợp (M8) · công cụ nhập menu bằng LLM (M11) · đánh giá VieNeu-TTS (M10) | GPU thuê vài giờ; API LLM cho onboarding |
| **G4 (bản cao cấp)** | Jetson/RK3588: Qwen3-ASR làm ASR thứ hai, LLM cục bộ dự phòng, barge-in với AEC phần cứng, bandit cho upsell | Phần cứng +150–250 USD/bộ |

### 14.2. Danh sách quyết định

| Mã | Câu hỏi | Lựa chọn | Khuyến nghị |
|----|---------|----------|-------------|
| D1 | Phần cứng thu âm | (a) chỉ phần mềm · (b) loa-mic USB có AEC · (c) micro mảng | **(b)** cho bộ chuẩn |
| D2 | Kết thúc lượt nói | (a) giữ 0,5 s · (b) EOT dựa trên NLU · (c) thêm mô hình Smart Turn/Namo | **(b)** ngay, (c) sau khi có test thật |
| D3 | Cho khách nói chen (barge-in) | có / không | Chỉ khi chọn D1 = (b)/(c) |
| D4 | Cảm biến hiện diện | có / không | **Có** (rẻ, tăng chủ động) |
| D5 | Dữ liệu giọng thật | 0 · 1 giờ · 3 giờ | **1–3 giờ** ở quán thí điểm |
| D6 | Bản cao cấp ASR lớn | có / không | Sau G2 |
| D7 | Ưu tiên benchmark NLU trước nâng cấp mô hình | có / không | **Có** |
| D8 | Ngưỡng xác nhận tường minh | giá trị dòng ≥ X đồng · số lượng ≥ N | Đề xuất X = 300.000đ, N = 5 |
| D9 | Mục tiêu tối ưu của gợi ý | hài lòng / AOV / biên lợi nhuận | Hài lòng + AOV, biên lợi nhuận qua `boost` |
| D10 | Nhắc khéo bằng món cụ thể | có / không | **Có**, tối đa 1 lần/đơn |
| D11 | Giọng TTS | Bắc / Nam / theo quán; giọng thương hiệu | Theo vùng của quán; giọng thương hiệu là dịch vụ thêm |
| D12 | Nhập menu bằng LLM (cloud) | có / không | **Có** |
| D13 | Phần cứng chạy LLM cục bộ | có / không | Chỉ cho bản cao cấp |
| D14 | Thu dữ liệu giọng có đồng ý | có / không | Có, giới hạn ở quán thí điểm |

---

## 15. Tài liệu tham khảo

**Số liệu tự đo của dự án:** [docs/02-nhan-dang-giong-noi-asr.md](02-nhan-dang-giong-noi-asr.md), [docs/03-tong-hop-giong-noi-tts.md](03-tong-hop-giong-noi-tts.md),
`scripts/bench_speech.py`, `aistaff bench`.

**Âm thanh, VAD, kết thúc lượt**
- Smart Turn v3 (Daily/Pipecat): https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/
- Smart Turn v3.2 ONNX: https://huggingface.co/soniqo/Smart-Turn-v3.2-ONNX
- TEN VAD: https://github.com/TEN-framework/ten-vad · so sánh Silero/TEN (bên thứ ba): https://www.cekura.ai/blogs/what-is-silero-vad
- LiveKit turn detector: https://docs.livekit.io/agents/build/turns/turn-detector · Namo turn detector: https://pypi.org/project/livekit-plugins-namo-turn-detector/
- GTCRN: https://github.com/biglinux/gtcrn (bản fork; dự án gốc của Xiaobin Rong)

**ASR**
- sherpa-onnx Zipformer models: https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/zipformer-transducer-models.html
- PhoWhisper: https://arxiv.org/abs/2406.02555 · Vietnamese Open ASR Leaderboard: https://vietaudio-team-vietnamese-asr-leaderboard.hf.space/
- Qwen3-ASR tiếng Việt (bảng xếp hạng bên thứ ba): https://models.handy.computer/languages/vi
- sherpa-onnx KWS: https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html · phostt: https://pypi.org/project/phostt/
- Zipformer (Yao et al., ICLR 2024), RNN-T (Graves 2012), CLAS (Pundak et al. 2018), TCPGen (Sun et al. 2021)

**Văn bản & NLU**
- JointIDSF / PhoATIS (VinAI): https://arxiv.org/abs/2104.02021
- NeMo text processing: https://pypi.org/project/nemo-text-processing
- Phục hồi dấu bằng dịch máy: https://ar5iv.arxiv.org/html/1709.07104 · Transformer sửa chính tả tiếng Việt: https://arxiv.org/abs/2105.13578

**TTS**
- VieNeu-TTS: https://pypi.org/project/vieneu/ · Piper voices: https://huggingface.co/rhasspy/piper-voices · VITS (Kim et al. 2021)

**LLM**
- Small LLM 2026: https://www.ertas.ai/best/best-small-llm-for-local-deployment · Qwen 3.5 small: https://toolhalla.ai/blog/qwen-3-5-small-best-llm-for-phone-2026
- LLM trên Raspberry Pi 5: https://stratospherelinuxips.readthedocs.io/en/develop/immune/research_rpi_llm_performance.html

**Gợi ý & tối ưu:** LinUCB (Li et al., WWW 2010) · Thompson sampling · FP-Growth (Han et al. 2000) · ALS ngầm (Hu, Koren,
Volinsky 2008) · BPR (Rendle et al. 2009) · LambdaMART (Burges 2010) · GRU4Rec (Hidasi et al. 2016) · SASRec (Kang & McAuley 2018)

**Pháp lý**
- Khuyến mại tối đa 50%: https://voh.com.vn/xa-hoi/muc-giam-gia-khuyen-mai-toi-da-khong-duoc-vuot-qua-50-gia-ban-hang-hoa-dich-vu-557206.html ·
  sửa đổi hạn mức: https://www.brandsvietnam.com/15536-Doanh-nghiep-duoc-khuyen-mai-den-100-gia-tri-hang-hoa ·
  https://doanhnghiephoinhap.vn/quy-dinh-han-muc-khuyen-mai-77883.html
- Luật BVDLCN 2025: https://kpmg.com/vn/vi/home/phan-tich-chuyen-sau/2025/06/vietnam-new-personal-data-protection-law.html ·
  dữ liệu sinh trắc học: https://thesaigontimes.vn/dung-dua-voi-du-lieu-sinh-trac-hoc-nguoi-dung/
