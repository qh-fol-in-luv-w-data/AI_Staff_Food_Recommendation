# Bước 4 — Hiểu ý khách (NLU), hội thoại, gợi ý món & ưu đãi

> **Lưu ý (11/2026):** hệ thống chỉ dùng **model mã nguồn mở chạy trên thiết bị**. Các dịch vụ AI đám mây nhắc trong tài liệu này chỉ để đối chiếu, không được dùng. Phương pháp đang dùng: [CORE-AI-RESEARCH → Phương pháp đang dùng trong hệ thống](CORE-AI-RESEARCH.md#phương-pháp-đang-dùng-trong-hệ-thống).

> Câu hỏi: làm sao để AI **hiểu đúng món + số lượng + khẩu vị**, **gợi ý có lý do**, **chủ động giới thiệu ưu đãi**,
> mà vẫn chạy ~1 ms trên CPU yếu và **không bao giờ tính sai tiền**?

## 4.1. LLM hay luật? — so sánh có số liệu

| Tiêu chí | LLM cục bộ 1–4B trên Pi 5 | LLM cloud | **NLU luật + so khớp mờ (chọn)** |
|----------|---------------------------|-----------|-----------------------------------|
| Tốc độ | ~2–11 token/s → câu trả lời 3–15 s | 0,5–2 s + mạng | **0,8 ms/lượt** (đo `aistaff bench`: 210 lượt / 0,18 s) |
| RAM | 2–4 GB | 0 | ~30 MB |
| Đúng tiền | Có thể "bịa" giá/ưu đãi | Có thể "bịa" | **Tất định, có test** |
| Đổi menu | Sửa prompt | Sửa prompt | Sửa YAML, tự cập nhật |
| Câu lạ ngoài phạm vi | Tốt | Tốt | Trung bình → **dùng LLM làm dự phòng** |
| Chi phí | Phần cứng đắt hơn | Theo token | 0đ |

**Thiết kế lai:** NLU luật xử lý ~mọi câu gọi món. Chỉ khi ý định = `unknown` và bật `llm_fallback`, câu được gửi cho
LLM để **viết lại thành câu lệnh chuẩn** ("cho 2 phở bò tái", "gợi ý món cay"). Câu đó lại đi qua NLU luật. Kết quả:
LLM không bao giờ chạm vào giá tiền/giỏ hàng (xem `src/aistaff/llm.py`). LLM dùng được với mọi máy chủ chuẩn OpenAI
(llama.cpp, Ollama, vLLM; hoặc dịch vụ cloud khi có mạng).

## 4.2. NLU tiếng Việt (`src/aistaff/nlu.py`)

**Chuẩn hoá:** NFC, chữ thường, `55.000đ` → `55000`, `50k` → `50000`, tạo song song bản **có dấu** và **không dấu**
(khách gõ không dấu, ASR sai dấu).

**Nhận món (MenuMatcher):**
1. Mỗi món/combo có tên + `aliases` (cách gọi dân dã: "phở tái", "nem rán", "bạc xỉu", "côm bô gia đình"…).
2. Trượt cửa sổ n-gram trên câu, so với tên món bằng `rapidfuzz` (C++): điểm = TB(độ giống bản không dấu, bản có dấu).
3. Ràng buộc chống nhận nhầm: chữ đầu phải gần giống ("có 4 người" ≠ "combo 4 người"), tên ngắn phải khớp chặt hơn
   ("gì cay" ≠ "mì cay"), từ chức năng không được nằm trong tên món ("combo đó" ≠ "combo đôi").
4. Chọn các đoạn không chồng nhau, ưu tiên điểm cao + dài hơn ("phở bò tái" thắng "phở bò").
5. **Món chung chung** ("cho 2 phở", "phở bò", "combo", "đồ uống") → AI hỏi lại kèm nút chọn, khách chỉ cần nói phần khác
   ("tái", "gà", "món thứ hai").

**Số lượng:** đọc số tiếng Việt đầy đủ (`hai mươi lăm`, `một trăm linh năm`, `hai lăm`, `băm lăm`, `một triệu hai`,
`hai nghìn rưỡi`…), lượng từ (tô, ly, dĩa, phần, suất…), lỗi ASR (`hài ly` → 2), số đứng sau món (`trà đá hai ly`).

**Tuỳ chọn & ghi chú:** `tô lớn` (+10.000đ theo menu), `không hành`, `ít đường nhiều đá` → ghi chú cho bếp,
không biến thành "kiêng hành" toàn cục.

**Khẩu vị & ràng buộc** (cho gợi ý): vị thích/không thích (cay, ngọt, chua, đậm đà, béo, có xử lý phủ định "không ăn được cay",
"ít cay"), thanh đạm, ăn chay ("không ăn thịt"), kiêng/dị ứng (bò, heo, hải sản → tự mở rộng tôm/cua/mực/cá…),
món nước/khô, nóng/mát, đói/ăn nhẹ, ngân sách ("dưới 80 nghìn một người"), số người ("đi 2 người", "cả nhà"), rẻ/sang.

**Ý định (intent):** gọi món, gọi chung chung, chọn theo thứ tự ("món thứ hai", "combo đó"), bớt/bỏ, sửa số lượng,
đổi món, hỏi gợi ý, nêu khẩu vị, hỏi thực đơn, hỏi ưu đãi, hỏi giá, hỏi thông tin món ("có cay không"), xem đơn,
chốt đơn, trả tiền mặt/chuyển khoản, huỷ đơn, đồng ý/từ chối, nhắc lại, cảm ơn, chào.

## 4.3. Hội thoại (máy trạng thái, `src/aistaff/dialog.py`)

```
idle ─chạm/nói─► chào (giới thiệu ưu đãi) ─► ordering ◄──────────────┐
                                     │  "gợi ý" (chưa có khẩu vị)    │
                                     ├─► asking_pref ─► gợi ý 3 món ─┤
                                     │  gọi món ─► thêm + nhắc ưu đãi/upsell ─┤
                                     │  "chốt đơn" / "không" (sau "cần thêm gì không?")
                                     ▼
                              confirm_order (đọc lại đơn + tiền + hỏi QR/tiền mặt)
                                     │ "đúng rồi"/"quét mã"        │ "tiền mặt"
                                     ▼                              ▼
                     awaiting_payment (QR, đếm ngược)        awaiting_cash
                                     │ ngân hàng báo có tiền / nhân viên xác nhận
                                     ▼
                                 done (cảm ơn + số thứ tự) ─► idle
```

- **Hỏi khẩu vị đúng 1 lần** khi khách nhờ gợi ý mà chưa nói sở thích (yêu cầu R4); nếu khách nói "gì cũng được"
  → gợi ý món bán chạy.
- **Màn hình chạm và giọng nói dùng chung 1 phiên**: khách có thể bấm "+ Thêm" rồi nói "chốt đơn".
- Đang hiện QR mà khách muốn thêm món → tự huỷ QR cũ, sửa đơn, tạo QR mới (không lệch tiền).
- Hết hạn QR, khách bỏ đi giữa chừng → tự xử lý (`tick()` mỗi giây).
- Mỗi câu trả lời có `text` (màn hình) và `speech` (đọc, đã chuẩn hoá số/tiền).

## 4.4. Gợi ý món (`src/aistaff/recommender.py`)

Không cần dữ liệu lịch sử (quán mới vẫn dùng được), giải thích được:

1. **Lọc cứng:** món chay; thành phần kiêng/dị ứng; ngân sách/người (combo chia theo số người); vị "không ăn được";
   nhóm món khách hỏi; món nước/khô.
2. **Chấm điểm:** vị thích × độ đậm của vị · thanh đạm · món nước/khô · nóng/mát · no/nhẹ · **bán chạy** ·
   **đang có ưu đãi** · **combo đúng số người** (+ "tiết kiệm X nghìn") · `boost` quán muốn đẩy · trừ món đã gọi.
3. **Đa dạng:** mỗi nhóm 1 món (trừ khi khách hỏi đúng nhóm), món chính trước, đồ uống/tráng miệng khi khách hỏi.
4. **Lý do bằng lời:** "vị cay, món bán chạy", "vừa cho 2 người, tiết kiệm 21 nghìn", "đang có ưu đãi".
5. **Trung thực:** nếu không món nào đáp ứng vị khách thích (vd món cay đều có hải sản mà khách dị ứng) thì AI nói rõ
   "món vị cay hợp yêu cầu thì quán chưa có, em gợi ý mấy món gần nhất".
6. **Upsell nhẹ nhàng:** sau khi gọi món chính mà chưa có đồ uống → mời 1 đồ uống hợp (ưu tiên món đang khuyến mãi,
   `pairs_with`), mỗi món chỉ mời 1 lần.

## 4.5. Ưu đãi & tính tiền (`src/aistaff/promotions.py`)

Các loại: giảm % hoá đơn (có trần), giảm tiền hoá đơn, giảm % / tiền theo món-nhóm-combo, mua X tặng Y
(tặng thêm hoặc giảm trong giỏ), hoá đơn từ N tặng món. Lịch theo **thứ trong tuần + khung giờ + ngày hiệu lực**
(múi giờ quán).

- **Chọn phương án lợi nhất cho khách:** ưu đãi `stackable` cộng dồn với nhau; ưu đãi độc quyền đứng riêng; engine
  thử mọi phương án và chọn tổng lợi ích (giảm + giá trị quà) lớn nhất.
- Giảm % làm tròn xuống bội số `discount_rounding` (mặc định 1.000đ). VAT cộng thêm nếu giá chưa gồm VAT.
- **AI bắt buộc giới thiệu ưu đãi** (yêu cầu R6) ở 4 thời điểm: lời chào (2 ưu đãi ưu tiên cao nhất), khi gợi ý
  (món đang ưu đãi được cộng điểm + nói lý do), **khi khách sắp đạt điều kiện** ("gọi thêm 25.000đ nữa là được giảm 10%",
  "thêm 1 trà tắc nữa là được tặng 1 ly") và khi đọc lại đơn (đã giảm bao nhiêu, tặng gì). Khách hỏi "có khuyến mãi gì"
  → đọc toàn bộ ưu đãi đang chạy.

## 4.6. Kiểm thử

98 test tự động (`pytest`): số tiếng Việt, NLU (lỗi ASR, không dấu, chống nhận nhầm), ưu đãi theo giờ/ngày,
gợi ý (chay, dị ứng, ngân sách, combo theo số người), VietQR, thanh toán, hội thoại đầy đủ, WebSocket server,
và đầu-cuối giọng nói thật (tự bỏ qua nếu chưa tải model).
