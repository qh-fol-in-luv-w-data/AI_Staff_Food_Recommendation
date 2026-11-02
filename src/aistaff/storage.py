"""Lưu trữ cục bộ bằng SQLite (1 file, không cần server DB) - chạy tốt trên thẻ nhớ/SSD của thiết bị edge.

Bảng:
  stores    - thông tin quán (snapshot cấu hình)
  orders    - đơn hàng (mã đơn, trạng thái, tiền, món, ưu đãi đã áp dụng)
  payments  - giao dịch nhận được từ ngân hàng/SePay (chống trùng theo provider + txn_id)
  turns     - log hội thoại dạng text (không lưu âm thanh) để cải thiện NLU
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS stores (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  address TEXT,
  phone TEXT,
  config_json TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE,
  store_id TEXT NOT NULL,
  kiosk_no INTEGER NOT NULL DEFAULT 1,
  session_id TEXT,
  status TEXT NOT NULL,            -- pending_payment | awaiting_cash | paid | cancelled | expired
  payment_method TEXT NOT NULL,    -- vietqr | cash
  subtotal INTEGER NOT NULL,
  discount INTEGER NOT NULL,
  vat INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL,
  items_json TEXT NOT NULL,
  promotions_json TEXT NOT NULL,
  qr_payload TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  paid_at TEXT,
  payment_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  txn_id TEXT NOT NULL,
  amount INTEGER NOT NULL,
  content TEXT,
  order_code TEXT,
  matched INTEGER NOT NULL DEFAULT 0,
  raw_json TEXT,
  received_at TEXT NOT NULL,
  UNIQUE(provider, txn_id)
);
CREATE TABLE IF NOT EXISTS turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  intent TEXT,
  latency_ms REAL,
  created_at TEXT NOT NULL
);
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds") if dt else None


@dataclass
class Order:
    id: int
    code: str
    store_id: str
    status: str
    payment_method: str
    subtotal: int
    discount: int
    vat: int
    total: int
    items: list[dict]
    promotions: list[dict]
    qr_payload: str | None
    created_at: str
    expires_at: str | None
    paid_at: str | None
    payment_ref: str | None
    session_id: str | None = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class Storage:
    def __init__(self, path: str | Path = "data/aistaff.db"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    # ------------------------------------------------------------------ stores
    def upsert_store(self, store_id: str, name: str, address: str = "", phone: str = "", config: dict | None = None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO stores(id,name,address,phone,config_json,updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name,address=excluded.address,phone=excluded.phone,"
                "config_json=excluded.config_json,updated_at=excluded.updated_at",
                (store_id, name, address, phone, json.dumps(config or {}, ensure_ascii=False), _iso(_utcnow())),
            )

    def get_store(self, store_id: str) -> dict | None:
        r = self._db.execute("SELECT * FROM stores WHERE id=?", (store_id,)).fetchone()
        return dict(r) if r else None

    # ------------------------------------------------------------------ orders
    def create_order(
        self,
        store_id: str,
        kiosk_no: int,
        prefix: str,
        items: list[dict],
        promotions: list[dict],
        subtotal: int,
        discount: int,
        vat: int,
        total: int,
        payment_method: str = "vietqr",
        expire_minutes: int | None = 10,
        session_id: str | None = None,
    ) -> Order:
        now = _utcnow()
        status = "pending_payment" if payment_method == "vietqr" else "awaiting_cash"
        expires = now + timedelta(minutes=expire_minutes) if (expire_minutes and payment_method == "vietqr") else None
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                cur = self._db.execute(
                    "INSERT INTO orders(store_id,kiosk_no,session_id,status,payment_method,subtotal,discount,vat,total,"
                    "items_json,promotions_json,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (store_id, kiosk_no, session_id, status, payment_method, subtotal, discount, vat, total,
                     json.dumps(items, ensure_ascii=False), json.dumps(promotions, ensure_ascii=False),
                     _iso(now), _iso(expires)),
                )
                oid = int(cur.lastrowid)
                code = f"{prefix}{kiosk_no:02d}{oid:06d}"
                self._db.execute("UPDATE orders SET code=? WHERE id=?", (code, oid))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return self.get_order(code)  # type: ignore[return-value]

    def set_qr(self, code: str, payload: str) -> None:
        with self._lock:
            self._db.execute("UPDATE orders SET qr_payload=? WHERE code=?", (payload, code))

    def _row_to_order(self, r: sqlite3.Row) -> Order:
        return Order(
            id=r["id"], code=r["code"], store_id=r["store_id"], status=r["status"],
            payment_method=r["payment_method"], subtotal=r["subtotal"], discount=r["discount"], vat=r["vat"],
            total=r["total"], items=json.loads(r["items_json"]), promotions=json.loads(r["promotions_json"]),
            qr_payload=r["qr_payload"], created_at=r["created_at"], expires_at=r["expires_at"],
            paid_at=r["paid_at"], payment_ref=r["payment_ref"], session_id=r["session_id"],
        )

    def get_order(self, code: str) -> Order | None:
        r = self._db.execute("SELECT * FROM orders WHERE code=?", (code.upper(),)).fetchone()
        return self._row_to_order(r) if r else None

    def list_orders(self, status: str | None = None, limit: int = 50) -> list[Order]:
        if status:
            rows = self._db.execute("SELECT * FROM orders WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit))
        else:
            rows = self._db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
        return [self._row_to_order(r) for r in rows.fetchall()]

    def set_status(self, code: str, status: str) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE orders SET status=? WHERE code=? AND status IN ('pending_payment','awaiting_cash')",
                (status, code),
            )
            return cur.rowcount > 0

    def mark_paid(self, code: str, ref: str = "manual") -> bool:
        """Đánh dấu đã thanh toán (idempotent). True nếu vừa chuyển trạng thái."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE orders SET status='paid', paid_at=?, payment_ref=? "
                "WHERE code=? AND status IN ('pending_payment','awaiting_cash','expired')",
                (_iso(_utcnow()), ref, code.upper()),
            )
            return cur.rowcount > 0

    def expire_overdue(self, now: datetime | None = None) -> list[str]:
        now_s = _iso(now or _utcnow())
        with self._lock:
            rows = self._db.execute(
                "SELECT code FROM orders WHERE status='pending_payment' AND expires_at IS NOT NULL AND expires_at < ?",
                (now_s,),
            ).fetchall()
            codes = [r["code"] for r in rows]
            for c in codes:
                self._db.execute("UPDATE orders SET status='expired' WHERE code=?", (c,))
        return codes

    # ------------------------------------------------------------------ payments
    def record_payment(self, provider: str, txn_id: str, amount: int, content: str, raw: dict) -> bool:
        """Lưu giao dịch nhận được. False nếu đã nhận trước đó (webhook gửi lại)."""
        with self._lock:
            try:
                self._db.execute(
                    "INSERT INTO payments(provider,txn_id,amount,content,raw_json,received_at) VALUES(?,?,?,?,?,?)",
                    (provider, str(txn_id), int(amount), content, json.dumps(raw, ensure_ascii=False), _iso(_utcnow())),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def link_payment(self, provider: str, txn_id: str, order_code: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE payments SET order_code=?, matched=1 WHERE provider=? AND txn_id=?",
                (order_code, provider, str(txn_id)),
            )

    def payments(self, limit: int = 50) -> list[dict]:
        rows = self._db.execute("SELECT * FROM payments ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ hội thoại & thống kê
    def log_turn(self, session_id: str, role: str, text: str, intent: str | None = None, latency_ms: float | None = None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO turns(session_id,role,text,intent,latency_ms,created_at) VALUES(?,?,?,?,?,?)",
                (session_id, role, text, intent, latency_ms, _iso(_utcnow())),
            )

    def stats(self, since: datetime | None = None) -> dict:
        since_s = _iso(since or (_utcnow() - timedelta(days=1)))
        r = self._db.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(total),0) revenue, COALESCE(SUM(discount),0) discount "
            "FROM orders WHERE status='paid' AND created_at >= ?",
            (since_s,),
        ).fetchone()
        counts: dict[str, int] = {}
        for row in self._db.execute("SELECT items_json FROM orders WHERE status='paid' AND created_at >= ?", (since_s,)):
            for it in json.loads(row["items_json"]):
                counts[it["name"]] = counts.get(it["name"], 0) + int(it["qty"])
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:10]
        return {"orders": r["n"], "revenue": r["revenue"], "discount": r["discount"], "top_items": top}
