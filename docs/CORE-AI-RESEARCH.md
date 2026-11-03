# Nghiên cứu Core AI: Nhân viên AI gọi món (chi tiết từng phương pháp)

> **Chính sách: hệ thống chỉ dùng model mã nguồn mở, chạy ngay trên thiết bị.** Không gọi API AI đám mây nào.
> Bảng "đang dùng gì, vì sao, ở đâu trong code" nằm ngay dưới mục lục: [Phương pháp đang dùng trong hệ thống](#phương-pháp-đang-dùng-trong-hệ-thống).
>
> **Cập nhật 2026-11-03: đã đổi hướng theo yêu cầu "AI nói chuyện thời gian thực với khách".** LLM mã nguồn mở
> (Qwen3-4B-Instruct qua llama.cpp) nay nằm trên đường xử lý chính, bộ luật cũ chỉ còn làm dự phòng. Kiến trúc,
> chọn model theo phần cứng, độ trễ: [§16](#16-hội-thoại-thời-gian-thực-bằng-llm-đã-triển-khai). Kết luận "không đưa
> LLM vào đường chính" ở §0 và §12 là của bản v0.1, giữ lại để đối chiếu.
>
> **Trạng thái các phần M1–M12: ĐỀ XUẤT ĐỂ DUYỆT.** Ngoài §16, các đề xuất dưới đây chưa được làm trong code.
> Mỗi phần kết thúc bằng **Đề xuất** và **Cần quyết định**. Danh sách quyết định tổng hợp ở [§14](#14-lộ-trình-và-các-quyết-định-cần-duyệt).
>
> Quy ước độ tin cậy số liệu: **[đo]** = tự đo trong dự án · **[công bố]** = số do tác giả/nhà cung cấp công bố ·
> **[ước tính]** = suy luận, cần đo lại trên thiết bị thật · **[cần kiểm chứng]** = nguồn chưa rõ hoặc mâu thuẫn.

## Mục lục

- [Phương pháp đang dùng trong hệ thống](#phương-pháp-đang-dùng-trong-hệ-thống) (bảng tổng hợp, chỉ mã nguồn mở)
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
16. [Hội thoại thời gian thực bằng LLM (đã triển khai)](#16-hội-thoại-thời-gian-thực-bằng-llm-đã-triển-khai)

---

## Phương pháp đang dùng trong hệ thống

Bảng này là "sự thật" của bản hiện tại: mỗi khâu dùng phương pháp nào, model/thư viện mã nguồn mở nào (giấy phép),
nằm ở file nào và đã đo được gì. Phần nghiên cứu chi tiết từng phương pháp ở §2–§13, kiến trúc hội thoại ở §16.

### Nguyên tắc chọn

1. **Chỉ model mã nguồn mở, chạy trên thiết bị.** Không gửi giọng nói hay lời khách ra ngoài. Mạng chỉ cần để tải model
   lần đầu và (tuỳ chọn) nhận báo có tiền từ ngân hàng/SePay. SePay là dịch vụ thanh toán, không phải model AI.
2. **Giấy phép:** ưu tiên giấy phép OSI (Apache-2.0, MIT, BSD), chấp nhận GPL cho thành phần chạy riêng (Piper).
   Model "mở trọng số" kèm điều khoản riêng (Llama Community License, Gemma Terms of Use) không dùng mặc định.
   Giấy phép phi thương mại (CC BY-NC, Coqui CPML, Qwen Research) bị loại vì thiết bị để bán.
3. **Đường tiền tất định (P1):** model chỉ chọn ý định / công cụ; giá, ưu đãi, tổng tiền, mã QR do code tính.

### Bảng 1. Phương pháp đang dùng (theo thứ tự trong pipeline)

| # | Khâu | Phương pháp đang dùng | Model / thư viện (giấy phép) | Code | Số liệu |
|---|------|-----------------------|------------------------------|------|---------|
| 1 | Thu âm, khử vọng, khử ồn | Khử vọng (AEC), khử ồn (NS), tự chỉnh âm lượng (AGC) của trình duyệt; AudioWorklet hạ mẫu 16 kHz, PCM16, gửi qua WebSocket | WebRTC trong Chromium (BSD-3) | `web/src/lib/audio.ts` | Chưa đo trong quán ồn |
| 2 | Phát hiện giọng nói, chốt câu | VAD theo khung 32 ms; im lặng 0,5 s là hết câu; câu dài nhất 15 s | **Silero VAD** (MIT) chạy qua **sherpa-onnx** (Apache-2.0) | `speech/asr.py` (`VADSegmenter`) | Trễ chốt câu 500 ms (cấu hình) |
| 3 | Nhận dạng giọng nói (ASR) | Transducer (RNN-T) giải mã cả câu sau VAD; modified beam search + **hotwords** (context graph) sinh tự động từ tên món/alias, score 1,5 | **Zipformer-vi 30M INT8** (`hynt/Zipformer-30M-RNNT-6000h`, giấy phép **cần kiểm chứng trên trang model**) + sherpa-onnx | `speech/asr.py` | WER 11,0% → 8,0% nhờ hotwords; 40–75 ms/câu; RTF ≈ 0,03 **[đo, giọng tổng hợp]** |
| 4 | Phụ đề khi khách đang nói | Chạy lại ASR offline trên đoạn đang nói mỗi 0,6 s ("transcript tạm") | như #3 | `kiosk/server.py` (`_partial`) | Khoảng 50 ms/lần **[ước tính theo RTF]** |
| 5 | Khách nói chen (barge-in) | Ngắt lời khi: khách nói ≥ 300 ms **và** ASR tạm ra chữ **và** không phải từ đệm ("ừ, dạ, vâng…") **và** không phải tiếng vọng (≥ 70% từ trùng câu Mai vừa nói). Ngắt thì huỷ lượt LLM, dừng loa, báo LLM khách đã nghe tới đâu | Luật | `kiosk/realtime.py`, `kiosk/server.py` | Chưa đo với giọng thật |
| 6 | Chuẩn hoá văn bản | Luật: chữ thường, NFC, bỏ dấu để so khớp, đọc số tiếng Việt ↔ chữ số, "50k" → 50000; chuẩn hoá câu cho TTS ("55.000đ" → "năm mươi lăm nghìn đồng", "QR" → "kiu a") | Không dùng model | `textnorm.py` | — |
| 7 | **Hiểu ý & dẫn dắt hội thoại** (chế độ chính) | **Agent LLM gọi công cụ** (function calling), stream từng mẩu chữ; system prompt tĩnh (tính cách + quy tắc + thực đơn) + ghi chú hệ thống đầu phiên (giờ, ưu đãi đang chạy); lịch sử chỉ nối thêm; tối đa 6 bước công cụ mỗi lượt; lọc `<think>` | **Qwen3-4B-Instruct-2507**, GGUF Q4_K_M (Apache-2.0), chạy bằng **llama.cpp** `llama-server --jinja` (MIT). Thay được bằng Ollama (MIT) / vLLM (Apache-2.0) | `agent/agent.py`, `agent/prompt.py`, `agent/local.py` | **Chưa đo với model thật** (§16.7) |
| 8 | Thao tác nghiệp vụ | 7 công cụ tất định, kiểm tra lại mọi tham số (id món giới hạn trong menu, số lượng 1–20…): `add_to_cart`, `update_cart_item`, `recommend_dishes`, `show_dish`, `review_order`, `place_order`, `cancel_order` | Không dùng model | `agent/tools.py` | Test tự động |
| 9 | Hiểu ý (dự phòng, chế độ `rules`) | NLU luật: ý định + thực thể, so khớp mờ tên món, đọc số lượng/khẩu vị/kiêng; máy trạng thái hội thoại | **rapidfuzz** (MIT) | `nlu.py`, `dialog.py` | Hiểu đúng 37/40 câu (92,5%); 0,8 ms/lượt **[đo]** |
| 10 | Gợi ý món & bán thêm | Content-based: lọc cứng (chay, thành phần kiêng, ngân sách/người, vị không ăn được) → chấm điểm (vị thích, món nước/khô, bán chạy, đang ưu đãi, combo đúng số người, `boost` của quán) → đa dạng hoá theo nhóm; upsell đồ uống / món đi kèm | Không dùng model | `recommender.py` | < 1 ms |
| 11 | Ưu đãi | Engine luật: điều kiện giờ/thứ/hoá đơn/món/combo; thử các tổ hợp, chọn phương án có lợi nhất cho khách; gợi ý "sắp đạt điều kiện" | Không dùng model | `promotions.py` | — |
| 12 | Tổng hợp giọng nói (TTS) | VITS end-to-end; cache WAV theo câu; dựng sẵn câu cố định; **cắt câu khi chữ LLM đang chảy** (câu đầu cắt ở dấu phẩy để phát sớm, câu sau tổng hợp trong lúc câu trước đang phát); câu đệm "Dạ." sau 650 ms và "chờ em một chút" sau thêm 3,5 s nếu LLM còn chậm | **Piper** `piper-tts` (GPL-3.0), giọng **vi_VN-vais1000-medium** (dữ liệu VAIS-1000, CC BY 4.0), ONNX Runtime (MIT) | `speech/tts.py`, `kiosk/realtime.py` | Câu đầu 170–300 ms; câu có trong cache 0 ms **[đo]** |
| 13 | Thanh toán | VietQR theo chuẩn EMVCo/NAPAS, CRC16, sinh offline; xác nhận tiền thủ công / SePay webhook / SePay polling | **segno** (BSD-3) vẽ QR | `vietqr.py`, `payments.py` | — |

Tài nguyên trên thiết bị: phần giọng nói + server khoảng 350 MB RAM **[đo]**; Qwen3-4B Q4_K_M thêm khoảng 2,5 GB file và
khoảng 3,5–4,5 GB RAM với ngữ cảnh 16K **[ước tính]**.

### Bảng 2. Phương pháp đã nghiên cứu nhưng chưa dùng hoặc bị loại

| Khâu | Phương pháp / model | Trạng thái | Lý do |
|------|---------------------|------------|-------|
| VAD | TEN VAD | Loại | Điều khoản cấm dùng để cạnh tranh với sản phẩm của Agora (§3) |
| Chốt câu | EOT thích ứng theo NLU; model Smart Turn / Namo | Đề xuất (D2) | Giảm cắt ngang khi khách ngập ngừng; cần bộ test giọng thật |
| ASR | Zipformer-vi 70.000 giờ (`zzasdf/viet_iter3_pseudo_label`) | Không dùng | WER trên câu gọi món không tốt hơn bản 30M **[đo]** |
| ASR | PhoWhisper, Qwen3-ASR, parakeet-ctc-0.6b-vi, Vosk | Không dùng | Chậm / nặng / cần GPU trên thiết bị rẻ, hoặc WER kém hơn (§5.3). Giấy phép từng model **cần kiểm chứng** trước khi dùng |
| ASR | LM chuyên ngành sinh từ mẫu câu, chọn giả thuyết theo NLU, fine-tune Zipformer | Đề xuất (§5.4–5.5) | Cần dữ liệu và bộ test thật |
| NLU | Bộ phân loại PhoBERT / model nhỏ | Không làm | LLM đã đảm nhận phần hiểu ý; bộ luật chỉ còn là dự phòng |
| LLM | Qwen3-1,7B, dòng Qwen3.5 nhỏ (Apache-2.0) | Dự phòng cho máy yếu | Nhanh hơn khoảng 2 lần, gọi công cụ kém chính xác hơn **[ước tính]**; cần chấm bằng kịch bản M12 |
| LLM | Vistral-7B, SeaLLMs, Arcee-VyLinh-3B | Chưa dùng | Tiếng Việt tốt nhưng 3–7B chậm trên CPU; giấy phép **cần kiểm chứng** (VyLinh dựa trên Qwen2.5-3B: giấy phép gốc phi thương mại) |
| LLM | Llama 3.x, Gemma | Không dùng mặc định | Điều khoản riêng, không phải giấy phép OSI (Gemma 4: **cần kiểm chứng**) |
| LLM | API LLM đám mây (OpenAI, Claude, Gemini…) | Loại | Không phải mã nguồn mở, gửi lời khách ra ngoài, cần Internet |
| TTS | VieNeu-TTS | Đánh giá sau | Chất lượng cao, model khoảng 1 GB; giấy phép **cần kiểm chứng** |
| TTS | Kokoro-82M (Apache-2.0), Matcha-TTS | Chưa dùng | Chưa có giọng tiếng Việt chính thức |
| TTS | XTTS-v2 / viXTTS (CPML), MMS-TTS (CC BY-NC), checkpoint F5-TTS (thường phi thương mại) | Loại | Giấy phép không cho dùng thương mại |
| TTS | TTS đám mây (FPT.AI, Viettel AI, Zalo, Google, Azure) | Loại | Không phải mã nguồn mở, cần Internet |
| Gợi ý | Lọc cộng tác, bandit, học từ lịch sử đơn | Để sau (M8) | Cần dữ liệu đơn thật |
| Cài đặt quán | Nhập menu từ ảnh bằng VLM mã nguồn mở (họ Qwen-VL) | Đề xuất (D12) | Chạy một lần trên máy tính lúc cài đặt; giấy phép kiểm theo từng kích thước model |

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
- **P2. Chỉ model mã nguồn mở, chạy trên thiết bị.** Mọi chức năng bán hàng phải chạy khi mất mạng; không gọi API AI
  đám mây. Riêng xác nhận chuyển khoản tự động cần mạng chiều ra.
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
| TTS đám mây (FPT.AI, Viettel AI, Zalo, Google, Azure) | Theo hợp đồng | **Loại**: không phải mã nguồn mở (chính sách hệ thống) |

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

1. **Nhập menu từ ảnh/PDF (khi cài đặt cho quán mới).** VLM mã nguồn mở (họ Qwen-VL) đọc ảnh menu và sinh nháp
   `menu.yaml` (tên, giá, alias, nhóm, vị ước lượng). Chủ quán duyệt lại. Rút thời gian onboarding từ hàng giờ xuống
   vài phút. Chạy một lần trên máy tính của bên cài đặt, **không chạy trên thiết bị**.
2. **Dự phòng NLU** (đã thiết kế): chỉ khi ý định `unknown`. LLM viết lại thành câu lệnh chuẩn, rồi NLU luật xử lý tiếp.
3. **Khai phá log** (offline, định kỳ): gom câu `unknown`, đề xuất alias, ý định mới, mẫu câu.
4. **Hỏi đáp tự do về món** (thành phần, dị ứng) qua RAG trên dữ liệu menu. **Rủi ro cao** với câu hỏi dị ứng, nên trả lời
   bằng dữ liệu cấu trúc (`contains`, `allergens`), LLM chỉ diễn đạt.

### 12.2. Mô hình & phần cứng

| Lựa chọn | Ghi chú |
|----------|---------|
| **Qwen3-4B-Instruct-2507** (Apache-2.0) — **đang dùng** | Gọi công cụ tốt, tiếng Việt khá; GGUF Q4_K_M khoảng 2,5 GB |
| Qwen3.5 dòng nhỏ (0,8B → 9B, Apache-2.0) **[công bố]** | Đa ngôn ngữ mạnh; cần tự đo tiếng Việt trên câu gọi món |
| Gemma 4 E2B (khoảng 1,1 GB trên di động, nhận văn bản/ảnh/âm thanh) **[công bố]** | Hợp thiết bị yếu; điều khoản Gemma riêng (**cần kiểm chứng** có phải giấy phép mở không) |
| Mô hình tinh chỉnh tiếng Việt (Vistral, VyLinh, SeaLLMs…) | Tốt tiếng Việt nhưng thường ≥ 3–7B |
| Tốc độ trên Pi 5 | Llama 3.2 1B khoảng 11 token/s, Qwen2.5 3B khoảng 5,2 token/s (qua Ollama) **[công bố]** → câu JSON 30 token mất 3–6 s |
| Jetson Orin Nano Super / RK3588 (RKLLM) | 1–4B chạy được ở tốc độ hội thoại; tăng 150–250 USD/bộ |

### 12.3. An toàn (bắt buộc nếu bật LLM)

- **Giải mã có ràng buộc** (GBNF/JSON schema trong llama.cpp) để đầu ra luôn đúng cấu trúc.
- **Kiểm tra lại với menu:** mọi món/ý định LLM trả về phải ánh xạ được vào menu, nếu không thì bỏ.
- **Không bao giờ** để LLM tính tiền, áp ưu đãi, sinh nội dung QR (P1).
- Giới hạn thời gian (6 s) rồi quay về luật; ghi log để đánh giá.
- Chỉ chạy LLM mã nguồn mở trên thiết bị (hoặc máy chủ trong quán), không có chi phí theo token.

### Đề xuất M11
1. Làm **công cụ nhập menu từ ảnh** bằng VLM mã nguồn mở (ROI cao nhất, không ảnh hưởng thiết bị).
2. (Bản v0.1, đã thay bằng §16) LLM chỉ làm dự phòng cho bộ luật. Nay LLM là bộ não chính; vẫn cần chấm Qwen3-4B,
   Qwen3.5 nhỏ trên bộ kịch bản gọi món (M12) để chọn model theo phần cứng.
3. Không dùng LLM cho câu hỏi dị ứng nếu chưa có dữ liệu `allergens` chuẩn.

**Cần quyết định:** D12. Có làm công cụ nhập menu bằng VLM mã nguồn mở không. D13. Phần cứng chạy LLM cho chế độ hội thoại (§16.3).

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
| D12 | Nhập menu bằng VLM mã nguồn mở (chạy lúc cài đặt) | có / không | **Có** |
| D13 | Phần cứng chạy LLM hội thoại | CPU thường / mini PC mạnh / Jetson-Mac (GPU) | Mini PC mạnh hoặc GPU cho cảm giác thời gian thực (§16.3); máy yếu dùng chế độ `rules` |
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

---

## 16. Hội thoại thời gian thực bằng LLM (đã triển khai)

### 16.1. Vì sao đổi

Bản v0.1 là "chọn món bằng giọng nói": mỗi câu được NLU luật đoán ý định rồi máy trạng thái trả lời theo mẫu.
Chính xác và nhanh, nhưng không *nói chuyện* được: khách hỏi vòng vo, đổi ý giữa chừng, đùa, hỏi "món nào hợp
trẻ con", nói chen khi Mai đang nói, thì hệ thống cứng nhắc. Yêu cầu mới là một nhân viên AI trò chuyện tự nhiên,
thời gian thực, và chỉ dùng model mã nguồn mở. Vì vậy một LLM mã nguồn mở chạy trên máy được đưa vào giữa pipeline,
còn mọi thứ dính tới **tiền** vẫn do code tất định làm.

### 16.2. Kiến trúc

```
micro ──PCM16──▶ Silero VAD ──▶ ASR Zipformer-vi ──▶ ConversationAgent ──stream chữ──▶ cắt câu ──▶ TTS Piper ──▶ loa
   │               │  đang nói: ASR tạm 0,6 s/lần → phụ đề     │   ▲ gọi công cụ   (câu đầu cắt ở dấu phẩy,     │
   │               │                                           ▼   │ kết quả         câu sau tổng hợp khi câu     │
   │               └─ khách nói chen ≥ 300 ms, có chữ thật,  ToolBox (tất định)       trước đang phát)            │
   │                  không phải "ừ/dạ", không phải tiếng    giỏ hàng · gợi ý · xem món ·                          │
   │                  vọng → huỷ lượt, dừng loa, ghi chú     phiếu gọi món · tạo đơn + VietQR · huỷ               │
   │                                                  ▲                                                          │
   │                         LLM: Qwen3-4B-Instruct (Apache-2.0) trên llama.cpp `llama-server` (cùng máy)          │
   └── chạm màn hình → thao tác tất định + ghi chú "[Hệ thống: khách bấm ...]" cho lượt LLM kế tiếp ◀───────────────┘
        server LLM chưa chạy / lỗi → bộ luật offline v0.1 trả lời thay (nghỉ LLM 30 s rồi thử lại)
```

| Thành phần | Cách làm | File |
|---|---|---|
| Prompt | Tính cách Mai, quy tắc nói (1–2 câu ngắn, câu đầu thật ngắn, không markdown, đọc giá "55 nghìn"), quy tắc nghiệp vụ, toàn bộ thực đơn. **Không chứa gì đổi theo giờ** → giống nhau mọi phiên | `agent/prompt.py` |
| Ghi chú đầu phiên | Giờ hiện tại + ưu đãi đang chạy, gửi trong lượt đầu tiên | `prompt.arrival_note` |
| Công cụ | 7 công cụ tất định; kiểm tra lại mọi tham số, trả lỗi để model tự sửa; JSON hỏng → báo `INVALID_JSON` cho model gọi lại | `agent/tools.py` |
| Vòng lặp | Lịch sử chỉ nối thêm; lượt có gọi công cụ và kết quả công cụ ghi cùng lúc, nên huỷ lượt ở bất kỳ đâu vẫn hợp lệ; lượt bị ngắt thì lời khách sau nối vào cùng tin nhắn | `agent/agent.py` |
| Kết nối LLM | API Chat Completions tương thích OpenAI (chỉ là định dạng, server chạy trên máy): stream chữ, ghép mảnh tham số công cụ, lọc `<think>`, map lỗi để chuyển sang bộ luật | `agent/local.py` |
| Miệng | Cắt câu khi chữ đang chảy, TTS tuần tự, câu đệm, trình duyệt báo câu nào đã phát để biết khách nghe tới đâu khi ngắt lời | `kiosk/realtime.py` |
| Tai | Phụ đề tạm; lọc "ừ/dạ" và tiếng vọng trước khi coi là ngắt lời | `kiosk/server.py` |

**Vì sao LLM không thể bịa giá:** model chỉ chọn công cụ và tham số. Giá, ưu đãi, tổng tiền, mã QR do code tính rồi
trả lại cho model đọc. Prompt cấm tự tính tiền; nếu model vẫn đọc sai số, màn hình (phiếu gọi món, QR) vẫn đúng vì lấy
từ công cụ. Món có thành phần khách kiêng bị lọc ngay trong `recommend_dishes`, không phụ thuộc model.

### 16.3. Chọn model mã nguồn mở theo phần cứng

Model mặc định: **Qwen3-4B-Instruct-2507**, GGUF Q4_K_M (Apache-2.0, bản không có chế độ "suy nghĩ" nên trả lời ngay),
chạy bằng `scripts/run_local_llm.sh` (llama-server `--jinja`, ngữ cảnh 16K, 1 luồng, giữ KV cache) hoặc dịch vụ
`deploy/aistaff-llm.service`. Tất cả số trong bảng là **[ước tính]**, phải đo lại bằng `aistaff chat --llm --debug`.

| Phần cứng | Model gợi ý | Một lượt có gọi công cụ | Đánh giá |
|---|---|---|---|
| Raspberry Pi 5 8 GB | Qwen3-1,7B Q4 | khoảng 10–20 s | Không đạt "thời gian thực" → dùng chế độ `rules` |
| Mini PC Intel N100/N150 16 GB | Qwen3-1,7B (hoặc 4B) Q4 | khoảng 5–10 s (4B: 10–20 s) | Dùng được, khách phải chờ; câu đệm giúp đỡ im lặng |
| Mini PC 8 nhân đời mới (DDR5, AVX-512) | Qwen3-4B Q4 | khoảng 4–8 s | Tạm được |
| Jetson Orin Nano Super 8 GB (GPU) | Qwen3-4B Q4 | khoảng 2–4 s | Khuyên dùng cho bản "hội thoại" |
| Mac mini dòng M (Metal) | Qwen3-4B / 8B Q4 | khoảng 1–3 s | Tốt nhất trong nhóm thiết bị để bàn |

Một lượt gọi món điển hình có 2 bước (gọi công cụ, rồi nói kết quả): mỗi bước tốn thời gian tính phần prompt mới
(vài chục tới vài trăm token) và sinh 30–60 token.

Những phương pháp đã dùng để giảm độ trễ khi chạy trên máy:
- **System prompt + công cụ cố định** cho mọi phiên → llama.cpp dùng lại KV cache của phần đầu (khoảng 5–6 nghìn token
  **[ước tính]**), chỉ tính phần mới mỗi lượt. Phần đầu được **làm ấm ngay khi kiosk khởi động** (CPU có thể mất 1–3 phút
  **[ước tính]**, khách đầu tiên khỏi chờ).
- **Lịch sử chỉ nối thêm** (không sửa lượt cũ) để KV cache không bị mất giữa cuộc nói chuyện.
- **Nói trước khi xong:** prompt cho phép một câu xác nhận ngắn trước khi gọi công cụ; câu đầu cắt ở dấu phẩy; câu
  đệm "Dạ." sau 650 ms và "chờ em một chút" sau thêm 3,5 s.
- `max_tokens` 400, nhiệt độ 0,5; tắt chế độ suy nghĩ với model hybrid (`extra_body`).

Hướng cải tiến chưa làm: rút gọn kết quả công cụ (ít token hơn), speculative decoding trong llama.cpp (model nháp nhỏ),
ràng buộc ngữ pháp/JSON cho tham số công cụ, fine-tune LoRA một model 1,5–2B trên hội thoại gọi món tổng hợp để máy yếu
cũng gọi công cụ đúng, chạy trên NPU RK3588 (RKLLM, cần chuyển đổi model).

### 16.4. Ngân sách độ trễ (một lượt "cho anh 2 tô phở bò")

| Bước | Thời gian |
|---|---|
| Khách ngừng nói → VAD chốt câu | 500 ms (cấu hình) **[đo]** |
| ASR cả câu | 40–75 ms **[đo, CPU x86]** |
| LLM tới chữ đầu | theo phần cứng ở §16.3 **[ước tính]**; "Dạ." đệm từ cache ở 650 ms |
| TTS câu đầu | 170–300 ms **[đo]** |
| **Khách nghe phản hồi** | "Dạ." ở khoảng 1,2 s; câu trả lời thật tuỳ phần cứng (GPU khoảng 2–4 s) **[ước tính]** |

### 16.5. Chi phí

Không có chi phí theo lượt (không gọi dịch vụ AI nào). Chi phí nằm ở phần cứng: thiết bị đủ mạnh để chạy LLM 4B
(xem bảng §16.3 và docs/06), cộng điện năng. Máy yếu vẫn bán được với chế độ `rules` (bản v0.1, 0,8 ms/lượt).

### 16.6. Rủi ro & cách kiểm soát

- **Model nhỏ hiểu sai / gọi sai công cụ:** công cụ kiểm tra tham số và trả lỗi để model sửa; mâm và tiền luôn hiện trên
  màn hình để khách thấy; chọn model theo số đo M12.
- **Sai tiền / bịa món:** không thể qua công cụ (giá do code tính, id món giới hạn bằng `enum`).
- **Khách "giả" lệnh hệ thống bằng lời nói:** lời khách bị bỏ ký tự `[` `]` nên không giả được dòng `[Hệ thống: ...]`.
- **Dị ứng:** lọc theo thành phần ngay trong công cụ. Vẫn cần trường `allergens` chuẩn trước khi cho AI trả lời câu hỏi dị ứng.
- **Server LLM chưa chạy / treo / lỗi:** bộ luật offline trả lời thay; lượt LLM đã kịp đổi mâm thì không chạy lại bằng luật (tránh thêm trùng).
- **Tiếng vọng làm Mai tự ngắt lời mình:** cần micro/trình duyệt có khử vọng; thêm lọc "ừ/dạ" và so khớp với câu Mai vừa nói.
  Môi trường ồn hoặc loa to: tắt `barge_in` (micro tạm dừng khi Mai nói, như v0.1).
- **Riêng tư:** giọng nói và lời khách không rời thiết bị; không lưu âm thanh.

### 16.7. Trạng thái kiểm thử

- **[đo]** 132 test tự động qua: công cụ, vòng lặp agent (huỷ giữa chừng, giới hạn bước, tham số bị cắt), giao thức với
  server LLM tương thích OpenAI (qua HTTP giả lập: stream chữ, ghép tham số công cụ, lọc `<think>`, lỗi kết nối), vòng
  giọng nói của kiosk (câu đệm, câu đệm thứ hai, ngắt lời, lọc "ừ" và tiếng vọng), luồng WebSocket tới VietQR, dự phòng
  bộ luật; giao diện kiểm tra bằng trình duyệt headless. Phần LLM trong các test này là **kịch bản cố định**.
- **Chưa chạy với model thật:** chính sách mạng của môi trường phát triển chặn huggingface.co (không tải được file GGUF),
  và việc chạy file `llama-server` tải về bị chặn. Việc tiếp theo: trên máy thật, chạy `scripts/run_local_llm.sh` rồi
  `aistaff chat --llm --debug` với bộ kịch bản gọi món ở M12; đo tỉ lệ hoàn tất đơn, độ trễ chữ đầu, số lần gọi công cụ
  sai; so sánh Qwen3-4B, Qwen3-1,7B, Qwen3.5 nhỏ trên từng phần cứng ở §16.3.
