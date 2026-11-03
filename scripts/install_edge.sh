#!/usr/bin/env bash
# Cài đặt trên thiết bị edge (Raspberry Pi 5 / Orange Pi 5 / mini PC Intel N100-N150, Debian/Ubuntu 64-bit)
#   sudo bash scripts/install_edge.sh [thu-muc-cau-hinh-quan]
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STORE="${1:-config/stores/quan-ngon}"
RUN_USER="${SUDO_USER:-$USER}"
echo "==> Cài gói hệ thống"
apt-get update
apt-get install -y python3-venv python3-dev libportaudio2 curl bzip2
apt-get install -y chromium || apt-get install -y chromium-browser || true
echo "==> Tạo môi trường Python"
sudo -u "$RUN_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/pip" install -U pip
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/pip" install -e "$APP_DIR[speech]"
echo "==> Tải model giọng nói"
sudo -u "$RUN_USER" bash "$APP_DIR/scripts/download_models.sh"
LLAMA_BIN="${LLAMA_SERVER:-$(command -v llama-server || true)}"
if [ -n "$LLAMA_BIN" ]; then
  echo "==> Cài dịch vụ LLM mã nguồn mở cho hội thoại (llama-server: $LLAMA_BIN)"
  sed -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@USER@|$RUN_USER|g" -e "s|@LLAMA_SERVER@|$LLAMA_BIN|g" \
    "$APP_DIR/deploy/aistaff-llm.service" > /etc/systemd/system/aistaff-llm.service
  systemctl daemon-reload
  systemctl enable --now aistaff-llm.service   # lần đầu tải model GGUF (cần Internet), sau đó chạy offline
else
  echo "==> Chưa có llama-server: kiosk dùng bộ luật offline cho tới khi cài LLM."
  echo "    Cài llama.cpp (https://github.com/ggml-org/llama.cpp/releases) rồi chạy lại: sudo LLAMA_SERVER=/đường/dẫn/llama-server bash $0 $STORE"
fi
echo "==> Kiểm tra cấu hình + dựng sẵn giọng nói cho câu cố định"
cd "$APP_DIR"
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/aistaff" --store "$STORE" validate
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/aistaff" --store "$STORE" prerender || true
echo "==> Cài dịch vụ systemd"
sed -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@USER@|$RUN_USER|g" -e "s|@STORE@|$STORE|g" \
  "$APP_DIR/deploy/aistaff.service" > /etc/systemd/system/aistaff.service
systemctl daemon-reload
systemctl enable --now aistaff.service
echo "==> Tự mở giao diện kiosk khi đăng nhập màn hình"
AUTOSTART="/home/$RUN_USER/.config/autostart"
mkdir -p "$AUTOSTART"
cp "$APP_DIR/deploy/aistaff-kiosk.desktop" "$AUTOSTART/"
chown -R "$RUN_USER" "$AUTOSTART"
echo
echo "Hoàn tất. Giao diện: http://localhost:8000  |  Quản lý: http://<ip-thiết-bị>:8000/admin"
echo "Nhớ đổi ADMIN_PIN trong /etc/systemd/system/aistaff.service rồi: sudo systemctl restart aistaff"
