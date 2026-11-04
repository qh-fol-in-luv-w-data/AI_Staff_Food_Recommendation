# Giao diện kiosk (React)

Mã nguồn giao diện khách hàng. Bản build nằm sẵn trong `src/aistaff/kiosk/webui/` nên thiết bị edge
**chỉ cần Python**, không cần Node. Chỉ build lại khi sửa giao diện.

```bash
cd web
npm install
npm run dev      # http://localhost:5173, tự proxy /api /ws /tts /media sang server :8000
npm run build    # tsc + vite build -> ../src/aistaff/kiosk/webui
```

Chạy server song song: `aistaff serve --no-speech` (hoặc `--speech`).
Xem minh hoạ toàn bộ món: `http://localhost:8000/?gallery`. Thiết bị yếu: thêm `?lite` để tắt hiệu ứng nền.

## Thiết kế: "Mâm sơn mài"

Quy trình: lập kế hoạch token → rà để tránh kiểu thiết kế "mặc định" → dựng → chụp màn hình tự phê bình
(Playwright).

- **Ý tưởng:** thực đơn là mâm sơn mài nhìn từ trên xuống, mỗi món là bát/đĩa sứ viền lam Bát Tràng.
  Điểm nhấn duy nhất: bát nóng bốc khói trên nền sơn then, điểm vàng lá.
- **Màu:** sơn then `#1b120d` · son `#9e2b1d` · vàng lá `#d9ad55`/`#f3d58f` · vỏ trứng `#f1e7d0` ·
  men lam `#2d4f8e` · ngọc `#5aa688` (giảm giá, thành công).
- **Chữ:** Cormorant Garamond (tên món, giá, tiêu đề, luôn dùng số thẳng hàng) + Be Vietnam Pro (giao diện,
  do người Việt thiết kế, dấu chuẩn). Font tự host trong `src/fonts/` (OFL-1.1), chỉ bộ Latin + tiếng Việt.
- **Chuyển động trả lời hành động:** chạm bát → bát nhấc lên phóng to (shared layout); thêm món → món bay
  vào mâm (từ chỗ chạm, hoặc từ quả cầu của Mai khi gọi bằng giọng nói); chốt đơn → phiếu giấy vỏ trứng
  trượt lên; thanh toán xong → con dấu son đóng xuống + lá vàng bung ra.
- **Chuyển động nền (tiết chế):** khói bát, lá vàng trôi trong quả cầu của Mai (phản ứng theo âm lượng
  micro/TTS), ánh kim chạy qua chữ vàng. Tôn trọng `prefers-reduced-motion`; `?lite` tắt hết.
- **Tránh:** nhãn IN HOA, chuỗi "A · B · C", mũi tên trong nút, thẻ bo góc giống hệt nhau có bóng xám.

## Minh hoạ món ăn (`src/art/DishArt.tsx`)

Vẽ bằng SVG, không cần ảnh: công thức riêng cho món mẫu, món mới **tự suy hình** từ thuộc tính trong
`menu.yaml` (món nước/khô/đồ uống, thành phần, độ cay). Quán có ảnh chụp thật thì thêm `image: pho.webp`
vào món và đặt file vào `config/stores/<quán>/images/`, ảnh sẽ thay minh hoạ.

## Cấu trúc

```
src/store.tsx            trạng thái + WebSocket + âm thanh (TTS, micro), hiệu ứng bay vào mâm
src/components/          Assistant (Mai), Menu, Tray (mâm), DishDetail, Sheets (phiếu, QR, cảm ơn), Stage
src/art/DishArt.tsx      bộ vẽ món
src/lib/                 socket, audio (AudioWorklet PCM16 16 kHz), định dạng
```
