"""Xác nhận thanh toán VietQR.

3 chế độ (store.yaml -> payment.confirm_mode):
  manual        Nhân viên xem app ngân hàng rồi bấm "Đã nhận tiền" ở /admin. Chi phí 0đ, chạy offline.
  sepay_webhook SePay (đọc biến động số dư ngân hàng) POST về /webhooks/sepay. Cần URL public
                (vd Cloudflare Tunnel) - xác thực header "Authorization: Apikey <KEY>".
  sepay_polling Thiết bị tự gọi API SePay mỗi vài giây khi có đơn chờ thanh toán. Chỉ cần Internet
                chiều ra (không mở cổng, không cần IP tĩnh) -> hợp với kiosk sau NAT/4G.
Đối soát: tìm mã đơn (vd DH01000123) trong nội dung chuyển khoản + kiểm tra số tiền >= tổng đơn.
Chống trùng: mỗi giao dịch (provider, txn_id) chỉ được ghi nhận 1 lần.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
from dataclasses import dataclass
from typing import Callable

from .config import StoreConfig
from .storage import Storage

log = logging.getLogger("aistaff.payments")


@dataclass
class PaymentEvent:
    order_code: str
    amount: int
    provider: str
    txn_id: str


class PaymentHub:
    def __init__(self, cfg: StoreConfig, storage: Storage, on_paid: Callable[[PaymentEvent], None] | None = None):
        self.cfg = cfg
        self.pay = cfg.store.payment
        self.storage = storage
        self.on_paid = on_paid
        self._code_re = re.compile(rf"{self.pay.order_prefix}\s*-?\s*(\d{{2}})\s*(\d{{6}})", re.IGNORECASE)

    # ------------------------------------------------------------------ đối soát
    def find_code(self, content: str) -> str | None:
        m = self._code_re.search(content or "")
        return f"{self.pay.order_prefix}{m.group(1)}{m.group(2)}" if m else None

    def process_transaction(self, provider: str, txn_id: str, amount: int, content: str, raw: dict,
                            code_hint: str | None = None) -> str:
        """Trả về: 'paid' | 'duplicate' | 'unmatched' | 'underpaid' | 'already_paid'."""
        if not self.storage.record_payment(provider, txn_id, amount, content, raw):
            return "duplicate"
        code = (code_hint or "").upper() or self.find_code(content)
        if code and not code.startswith(self.pay.order_prefix):
            code = self.find_code(code) or code
        order = self.storage.get_order(code) if code else None
        if not order:
            log.warning("Giao dịch %s %sđ không khớp đơn nào: %r", txn_id, amount, content)
            return "unmatched"
        self.storage.link_payment(provider, txn_id, order.code)
        if order.status == "paid":
            return "already_paid"
        if amount < order.total:
            log.warning("Đơn %s chuyển thiếu: %s < %s", order.code, amount, order.total)
            return "underpaid"
        if self.storage.mark_paid(order.code, f"{provider}:{txn_id}"):
            if self.on_paid:
                self.on_paid(PaymentEvent(order.code, amount, provider, txn_id))
            return "paid"
        return "already_paid"

    def confirm_manual(self, code: str, staff: str = "staff") -> bool:
        order = self.storage.get_order(code)
        if not order:
            return False
        if self.storage.mark_paid(order.code, f"manual:{staff}"):
            if self.on_paid:
                self.on_paid(PaymentEvent(order.code, order.total, "manual", staff))
            return True
        return False

    # ------------------------------------------------------------------ SePay webhook
    def sepay_webhook(self, authorization: str | None, body: dict) -> tuple[int, dict]:
        key = os.environ.get(self.pay.sepay.webhook_api_key_env, "")
        if not key:
            return 503, {"success": False, "message": "webhook chưa cấu hình API key"}
        expected = f"Apikey {key}"
        if not authorization or not hmac.compare_digest(authorization.strip(), expected):
            return 401, {"success": False, "message": "unauthorized"}
        if body.get("transferType") != "in":
            return 200, {"success": True, "message": "ignored"}
        try:
            amount = int(float(body.get("transferAmount", 0)))
        except (TypeError, ValueError):
            return 400, {"success": False, "message": "transferAmount không hợp lệ"}
        content = f"{body.get('content') or ''} {body.get('description') or ''}"
        result = self.process_transaction("sepay", str(body.get("id")), amount, content, body, body.get("code"))
        return 200, {"success": True, "result": result}

    # ------------------------------------------------------------------ SePay polling
    def sepay_poll_once(self, client) -> list[str]:
        """Gọi API danh sách giao dịch SePay 1 lần (client = httpx.Client). Trả về các kết quả xử lý."""
        token = os.environ.get(self.pay.sepay.api_token_env, "")
        if not token:
            return []
        if not self.storage.list_orders("pending_payment", limit=1):
            return []  # không có đơn chờ -> không gọi API (tiết kiệm quota)
        r = client.get(self.pay.sepay.api_url, params={"account_number": self.pay.account_number, "limit": 20},
                       headers={"Authorization": f"Bearer {token}"}, timeout=8)
        r.raise_for_status()
        out = []
        for t in r.json().get("transactions", []):
            amount = int(float(t.get("amount_in") or 0))
            if amount <= 0:
                continue
            out.append(self.process_transaction("sepay", str(t.get("id")), amount,
                                                t.get("transaction_content") or "", t, t.get("code")))
        return out
