# Bước 7 — Triển khai, vận hành, pháp lý & lộ trình

> **Lưu ý (11/2026):** hệ thống chỉ dùng **model mã nguồn mở chạy trên thiết bị**. Các dịch vụ AI đám mây nhắc trong tài liệu này chỉ để đối chiếu, không được dùng. Phương pháp đang dùng: [CORE-AI-RESEARCH → Phương pháp đang dùng trong hệ thống](CORE-AI-RESEARCH.md#phương-pháp-đang-dùng-trong-hệ-thống).

## 7.1. Cài đặt lên thiết bị (1 lệnh)

```bash
git clone <repo> ai-staff && cd ai-staff
sudo bash scripts/install_edge.sh config/stores/<ma-quan>
```

Script sẽ: cài gói hệ thống → tạo venv → `pip install -e .[speech]` → tải model (~120 MB) → kiểm tra cấu hình →
dựng sẵn giọng nói → cài dịch vụ `systemd` (tự khởi động lại khi lỗi) → tự mở Chromium toàn màn hình khi bật máy
(cho phép micro, tự phát âm thanh).

Hoặc Docker (arm64/amd64): xem `Dockerfile`.

## 7.2. Cấu hình cho từng quán

Mỗi quán = 1 thư mục `config/stores/<ma-quan>/` gồm 3 file YAML (xem mẫu `quan-ngon`):

| File | Nội dung |
|------|----------|
| `store.yaml` | Tên quán, địa chỉ, số kiosk, tên & cách xưng hô của AI, VAT, tài khoản nhận tiền (BIN + số TK), chế độ xác nhận, giọng nói, LLM dự phòng |
| `menu.yaml` | Nhóm món, món lẻ (giá, alias, vị 0–3, món nước/khô, nóng/lạnh, thành phần, chay, bán chạy, boost, món ăn kèm, size), combo (món con + giá + số người) |
| `promotions.yaml` | Ưu đãi (loại, giá trị, điều kiện, lịch theo thứ/giờ/ngày, cộng dồn, câu giới thiệu, ngưỡng nhắc) |

Sau khi sửa: `aistaff --store config/stores/<ma-quan> validate` (bắt lỗi: giá âm, combo trỏ món không tồn tại,
BIN sai, trùng mã…) rồi `sudo systemctl restart aistaff`.

**Mẹo tăng độ chính xác:** xem log câu khách nói trong bảng `turns` (SQLite) → câu nào AI không hiểu thì thêm vào
`aliases` của món tương ứng. Hotword ASR tự cập nhật theo alias.

## 7.3. Vận hành hằng ngày

- `/admin` (trên điện thoại cùng mạng, nhập `ADMIN_PIN`): danh sách đơn, xác nhận "Đã nhận tiền", doanh thu 24h,
  tiền đã giảm cho khách, món bán chạy.
- Theo dõi: `GET /healthz`, `journalctl -u aistaff -f`.
- Sao lưu: file `data/aistaff.db` (SQLite) - sao lưu hằng ngày bằng `sqlite3 data/aistaff.db ".backup backup.db"`.
- Cập nhật phần mềm: `git pull && .venv/bin/pip install -e .[speech] && sudo systemctl restart aistaff`.

## 7.4. Pháp lý cần lưu ý (không phải tư vấn pháp lý)

1. **Dữ liệu cá nhân** — Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15 và Nghị định 356/2025/NĐ-CP có hiệu lực từ
   01/01/2026; báo chí phân tích dữ liệu sinh trắc học (trong đó có giọng nói) thuộc nhóm nhạy cảm.
   Thiết kế hiện tại: **xử lý âm thanh hoàn toàn trên thiết bị, không lưu file ghi âm, không gửi giọng nói ra ngoài**;
   chỉ lưu văn bản câu nói để cải thiện NLU (có thể tắt). Nên: dán thông báo "Kiosk sử dụng micro để nhận lệnh gọi món,
   không ghi âm", có chính sách xoá log định kỳ, và tham vấn luật sư trước khi thương mại hoá.
2. **Hoá đơn điện tử** — Xem [05-thanh-toan-vietqr.md §5.6](05-thanh-toan-vietqr.md): quán thuộc diện bắt buộc cần tích hợp
   hoá đơn điện tử khởi tạo từ máy tính tiền.
3. **Bản quyền phần mềm/model** — sherpa-onnx (Apache-2.0), model Zipformer (kiểm tra license từng model trên trang gốc),
   Piper runtime `piper-tts` (GPL-3.0), dữ liệu giọng VAIS-1000 (CC BY 4.0). Xem [03-tong-hop-giong-noi-tts.md §3.5](03-tong-hop-giong-noi-tts.md).

## 7.5. Lộ trình phát triển đề xuất

| Giai đoạn | Việc | Mục tiêu đo được |
|-----------|------|------------------|
| Thí điểm (2–4 tuần) | Lắp 1–2 kiosk tại quán thật, chế độ `manual` | Tỷ lệ đơn hoàn tất bằng giọng nói, % câu `unknown`, thời gian/đơn |
| Cải thiện NLU | Bổ sung alias/hotword từ log thật | `unknown` < 5% |
| Tự động hoá thanh toán | Bật SePay webhook/polling | 0 thao tác nhân viên cho đơn chuyển khoản |
| Giọng thương hiệu | Fine-tune Piper bằng giọng nhân viên | Điểm hài lòng giọng nói |
| ASR tại chỗ | Fine-tune Zipformer với câu gọi món thật (có đồng ý) | WER câu gọi món < 5% |
| Mở rộng | Nhiều quán/chuỗi: đồng bộ menu & báo cáo về cloud (tuỳ chọn) | Quản lý tập trung |
| Hội thoại tự do | Bật LLM dự phòng (Jetson/RK3588 cục bộ hoặc cloud) | Hiểu được câu ngoài kịch bản |

### Nguồn
- Luật BVDLCN 2025 (KPMG): https://kpmg.com/vn/vi/home/phan-tich-chuyen-sau/2025/06/vietnam-new-personal-data-protection-law.html
- Nghị định 356/2025/NĐ-CP: https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Nghi-dinh-356-2025-ND-CP-huong-dan-Luat-Bao-ve-du-lieu-ca-nhan-687428.aspx
- Dữ liệu sinh trắc học là dữ liệu nhạy cảm (Saigon Times): https://thesaigontimes.vn/dung-dua-voi-du-lieu-sinh-trac-hoc-nguoi-dung/
