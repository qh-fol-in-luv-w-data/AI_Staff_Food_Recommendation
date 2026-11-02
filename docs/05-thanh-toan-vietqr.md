# Bước 5 — Tính tiền, mã VietQR & xác nhận thanh toán

> Câu hỏi: hiện **mã QR quét được bằng mọi app ngân hàng**, tiền vào thẳng tài khoản quán, **phí thấp nhất**,
> và biết **chắc chắn khách đã trả** để chốt đơn.

## 5.1. Vì sao VietQR

- Chuẩn QR chuyển khoản liên ngân hàng của NAPAS dựa trên **EMVCo Merchant-Presented Mode**; hầu hết app ngân hàng/ví
  ở Việt Nam quét được.
- Chuyển nhanh NAPAS 247 → tiền vào **thẳng tài khoản quán** trong vài giây, không qua trung gian giữ tiền,
  không phí MDR như quẹt thẻ.
- **Tạo offline 100%**: không cần gọi API nào để sinh mã (`src/aistaff/vietqr.py`), hiển thị dạng SVG (không cần thư viện ảnh).

## 5.2. Cấu trúc mã (đã kiểm thử)

```
00 02 01                         Payload Format Indicator
01 02 12                         12 = QR động (có số tiền, dùng 1 lần) · 11 = QR tĩnh
38 LL                            Merchant Account Information (NAPAS)
   00 10 A000000727              GUID NAPAS
   01 LL                         Đơn vị thụ hưởng
      00 06 970436               BIN ngân hàng (vd Vietcombank)
      01 LL 0123456789           Số tài khoản
   02 08 QRIBFTTA                Dịch vụ chuyển tới TÀI KHOẢN (QRIBFTTC = tới THẺ)
53 03 704                        VND
54 LL 125000                     Số tiền (số nguyên)
58 02 VN
62 LL 08 LL DH01000123           Nội dung chuyển khoản = mã đơn (≤ 25 ký tự, không dấu)
63 04 XXXX                       CRC-16/CCITT-FALSE (kiểm tra bằng giá trị chuẩn "123456789" → 0x29B1)
```

Ví dụ payload thật do hệ thống sinh (125.000đ, đơn DH01000123):
`00020101021238540010A00000072701240006970436011001234567890208QRIBFTTA530370454061250005802VN62140810DH0100012363049C36`

**Mã đơn** = `tiền tố` + `số kiosk (2 số)` + `số thứ tự (6 số)` → nhiều kiosk dùng chung 1 tài khoản không bị trùng.
Nội dung chỉ chữ in hoa + số để không app ngân hàng nào cắt/đổi ký tự.

## 5.3. Xác nhận đã nhận tiền — 3 mức

| Chế độ | Cách hoạt động | Cần gì | Chi phí | Khi nào dùng |
|--------|----------------|--------|---------|--------------|
| `manual` (mặc định) | Nhân viên thấy thông báo app ngân hàng → bấm **"Đã nhận tiền"** ở `/admin` (điện thoại cùng mạng LAN) | Không cần Internet trên kiosk | 0đ | Quán nhỏ có người đứng quầy |
| `sepay_webhook` | SePay đọc biến động số dư → POST JSON về `/webhooks/sepay`, header `Authorization: Apikey <KEY>` | URL công khai HTTPS (vd Cloudflare Tunnel), tài khoản SePay | Theo gói SePay | Tự động hoàn toàn, nhiều kiosk |
| `sepay_polling` | Kiosk tự gọi API giao dịch SePay mỗi 4 s **chỉ khi có đơn chờ** | Internet chiều ra (4G/Wi-Fi), API token | Theo gói SePay | Máy bán hàng sau NAT/4G, không mở được cổng |

Đối soát (`src/aistaff/payments.py`):
1. Ghi giao dịch với khoá duy nhất `(provider, txn_id)` → webhook gửi lại nhiều lần **không cộng tiền 2 lần**.
2. Tìm mã đơn trong nội dung (chịu được ngân hàng chèn thêm chữ: `MBVCB.123.DH01000123 thanh toan`, `dh 01 000123`).
3. Số tiền ≥ tổng đơn → `paid`; thiếu → `underpaid` (ghi log để nhân viên xử lý); không thấy mã → `unmatched`.
4. Đẩy màn hình "Thanh toán thành công + số thứ tự" tới đúng phiên khách qua WebSocket.

Các lựa chọn khác: **payOS (Casso)** tạo link/QR + webhook có chữ ký checksum; **Casso** webhook giao dịch;
**API ngân hàng trực tiếp** (cần hợp đồng doanh nghiệp). Kiến trúc `PaymentHub` cho phép thêm adapter mới dễ dàng.

> ⚠️ Kiểm tra lại tên trường và endpoint với tài liệu SePay hiện hành trước khi chạy thật (SePay có API v1 `userapi/…`
> và v2). Webhook payload đã đối chiếu: `id, gateway, transactionDate, accountNumber, code, content, transferType,
> transferAmount, accumulated, subAccount, referenceCode, description`.

## 5.4. Bảo mật

- Webhook: so khớp API key bằng `hmac.compare_digest`; nên bật thêm lọc IP SePay hoặc chuyển sang HMAC-SHA256.
- `/admin`: bắt buộc `ADMIN_PIN` khi truy cập từ máy khác (chỉ localhost được miễn).
- Không lưu thông tin thẻ/tài khoản khách. Khoá API để trong biến môi trường, không ghi vào YAML.
- QR động hết hạn sau `qr_expire_minutes`; sửa đơn → QR cũ bị huỷ trong CSDL (giao dịch đến muộn vẫn được ghi nhận
  để đối soát thủ công).

## 5.5. Mã BIN ngân hàng thường dùng

| Ngân hàng | BIN | Ngân hàng | BIN |
|-----------|-----|-----------|-----|
| Vietcombank | 970436 | VPBank | 970432 |
| VietinBank | 970415 | TPBank | 970423 |
| BIDV | 970418 | Sacombank | 970403 |
| Agribank | 970405 | VIB | 970441 |
| MBBank | 970422 | HDBank | 970437 |
| Techcombank | 970407 | SHB | 970443 |
| ACB | 970416 | MSB | 970426 |

Danh sách đầy đủ hơn trong `vietqr.BANK_BINS`. **Đối chiếu với danh sách BIN của NAPAS/VietQR trước khi dùng**
(một số trang tổng hợp trên mạng ghi sai mã). Cách chắc nhất: quét thử QR với app ngân hàng của chủ quán và kiểm tra
tên chủ tài khoản hiện ra đúng.

## 5.6. Hoá đơn điện tử (lưu ý pháp lý khi bán cho quán)

Theo NĐ 70/2025/NĐ-CP (sửa NĐ 123/2020), từ 01/06/2025 hộ kinh doanh doanh thu từ 1 tỷ đồng/năm phải dùng
**hoá đơn điện tử khởi tạo từ máy tính tiền**; Nghị quyết 198/2025/QH15 bỏ thuế khoán từ 01/01/2026.
Kiosk này **chưa** phát hành hoá đơn điện tử. Khi bán cho quán thuộc diện bắt buộc, cần tích hợp API của nhà cung cấp
hoá đơn điện tử có kết nối cơ quan thuế (hook tại thời điểm `mark_paid`). Đối chiếu văn bản gốc và hướng dẫn của cơ quan thuế.

### Nguồn
- Giải thích cấu trúc VietQR (tag 38, QRIBFTTA): https://viblo.asia/p/tao-ma-qrcode-chuyen-tien-ngan-hang-7ymJXnd5Vkq · https://github.com/duyquoc1508/napas-qr
- SePay webhooks: https://developer.sepay.vn/vi/sepay-webhooks/tich-hop-webhook · xác thực: https://developer.sepay.vn/vi/sepay-webhooks/xac-thuc
- SePay API giao dịch: https://docs.sepay.vn/api-giao-dich.html · API v2: https://developer.sepay.vn/vi/sepay-api/v2/bat-dau-nhanh
- Casso/payOS xác nhận thanh toán: https://developer.casso.vn/v1/thuc-hanh/tich-hop-xac-nhan-thanh-toan
- Hoá đơn máy tính tiền (NĐ 70/2025): https://www.meinvoice.vn/tin-tuc/31627/ho-khoan-doanh-thu-tren-1-ty-phai-su-dung-hoa-don-dien-tu-may-tinh-tien/ · https://thoibaotaichinhvietnam.vn/ho-ca-nhan-kinh-doanh-chu-dong-ra-soat-doanh-thu-ap-dung-hoa-don-dien-tu-tu-may-tinh-tien-175242.html
