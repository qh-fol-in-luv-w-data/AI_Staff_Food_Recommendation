"""Công cụ (tool use) cho Claude: mọi thao tác chạm tới giỏ hàng, giá, ưu đãi, đơn và QR đều tất định.

LLM chỉ quyết định *gọi công cụ nào với tham số gì*. Code kiểm tra lại từng tham số (id món phải có trong
menu, số lượng hợp lệ...). Code tính tiền, áp ưu đãi, tạo mã QR, rồi trả kết quả gọn để LLM nói lại.
Mỗi công cụ cũng sinh "sự kiện giao diện" (giỏ hàng, thẻ gợi ý, phóng to món, phiếu, QR) gửi lên màn hình.
"""

from __future__ import annotations

import json
from typing import Any

from ..config import TASTES
from ..dialog import DialogManager, Session
from ..nlu import Preferences
from ..textnorm import format_money

MAX_QTY = 20


class ToolInputError(ValueError):
    pass


class ToolBox:
    def __init__(self, dm: DialogManager, session: Session):
        self.dm = dm
        self.s = session
        self.menu = dm.menu
        self.events: list[dict] = []
        self._ids = [e.id for e in self.menu.entries()]
        cats = [c.id for c in self.menu.categories] + (["combo"] if self.menu.combos else [])
        self._specs = self._build_specs(cats)

    # ================================================================== định nghĩa công cụ (cố định trong phiên)
    def specs(self) -> list[dict]:
        return self._specs

    def _build_specs(self, cats: list[str]) -> list[dict]:
        item = {"type": "string", "enum": self._ids, "description": "id món hoặc combo trong THỰC ĐƠN"}
        taste = {"type": "array", "items": {"type": "string", "enum": list(TASTES)}}
        taste_hint = " (cay, ngot = ngọt, chua, dam = đậm đà, beo = béo)"
        tools = [
            {
                "name": "add_to_cart",
                "description": "Thêm món hoặc combo vào mâm (giỏ hàng) của khách. Gọi ngay khi khách đã gọi món rõ ràng. "
                               "Trả về giỏ hàng mới, tổng tiền, gợi ý ưu đãi sắp đạt và gợi ý mời thêm.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "item_id": item,
                        "quantity": {"type": "integer", "minimum": 1, "maximum": MAX_QTY},
                        "option_id": {"type": "string", "description": "id tuỳ chọn (vd size lớn) nếu khách chọn"},
                        "note": {"type": "string", "description": "ghi chú cho bếp, vd 'không hành', 'ít đá'"},
                    },
                    "required": ["item_id", "quantity"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "update_cart_item",
                "description": "Đổi số lượng một món đã có trong mâm. quantity = 0 để bỏ món đó.",
                "input_schema": {
                    "type": "object",
                    "properties": {"item_id": item, "quantity": {"type": "integer", "minimum": 0, "maximum": MAX_QTY}},
                    "required": ["item_id", "quantity"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "recommend_dishes",
                "description": "Gợi ý món hợp khẩu vị, kiêng cữ, ngân sách và số người. Màn hình hiện thẻ món gợi ý. "
                               "Trả về món kèm lý do và ưu đãi liên quan. Luôn lọc bỏ món có thành phần khách kiêng.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "likes": {**taste, "description": "vị khách thích" + taste_hint},
                        "dislikes": {**taste, "description": "vị khách không ăn được" + taste_hint},
                        "light": {"type": "boolean", "description": "khách muốn thanh đạm"},
                        "vegetarian": {"type": "boolean"},
                        "exclude_ingredients": {"type": "array", "items": {"type": "string"},
                                                "description": "thành phần kiêng/dị ứng, vd bò, hải sản, đậu phộng"},
                        "include_ingredients": {"type": "array", "items": {"type": "string"}},
                        "max_price_per_person": {"type": "integer", "minimum": 0},
                        "group_size": {"type": "integer", "minimum": 1, "maximum": 30},
                        "style": {"type": "string", "enum": ["nuoc", "kho"]},
                        "temperature": {"type": "string", "enum": ["nong", "lanh"]},
                        "category": {"type": "string", "enum": cats},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 4},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "show_dish",
                "description": "Phóng to một món trên màn hình (ảnh, vị, tuỳ chọn) khi khách muốn xem hoặc hỏi kỹ về món. "
                               "Trả về thông tin chi tiết của món.",
                "input_schema": {
                    "type": "object",
                    "properties": {"item_id": item},
                    "required": ["item_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "review_order",
                "description": "Khi khách nói xong hoặc muốn tính tiền: hiện phiếu gọi món trên màn hình và trả về "
                               "các món, ưu đãi đã áp dụng, quà tặng, tổng tiền để đọc lại cho khách.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "place_order",
                "description": "Tạo đơn và hiện mã QR (vietqr) hoặc số thứ tự trả tiền mặt (cash). CHỈ gọi sau khi khách "
                               "đã đồng ý rõ ràng với đơn đã đọc lại và chọn cách thanh toán.",
                "input_schema": {
                    "type": "object",
                    "properties": {"payment_method": {"type": "string", "enum": ["vietqr", "cash"]}},
                    "required": ["payment_method"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "cancel_order",
                "description": "Huỷ toàn bộ đơn và làm trống mâm khi khách muốn huỷ hoặc gọi lại từ đầu.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        ]
        # Streaming + công cụ phía client: bật eager input streaming; code tự kiểm tra tham số (validate bên dưới)
        for t in tools:
            t["eager_input_streaming"] = True
        return tools

    # ================================================================== chạy công cụ
    def run(self, name: str, args: Any) -> tuple[str, bool]:
        """Trả về (nội dung tool_result, is_error)."""
        fn = getattr(self, f"_t_{name}", None)
        if fn is None:
            return json.dumps({"error": f"không có công cụ {name}"}, ensure_ascii=False), True
        if not isinstance(args, dict):
            return json.dumps({"INVALID_JSON": json.dumps(args, ensure_ascii=False)}, ensure_ascii=False), True
        try:
            out = fn(**args)
        except ToolInputError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False), True
        except TypeError as e:  # tham số lạ / thiếu
            return json.dumps({"error": f"tham số không hợp lệ: {e}"}, ensure_ascii=False), True
        return json.dumps(out, ensure_ascii=False), False

    def drain_events(self) -> list[dict]:
        ev, self.events = self.events, []
        return ev

    # ------------------------------------------------------------------ kiểm tra tham số
    def _entry(self, item_id: Any):
        if not isinstance(item_id, str) or item_id not in self._ids:
            raise ToolInputError(f"item_id '{item_id}' không có trong thực đơn")
        return self.menu.get(item_id)

    @staticmethod
    def _int(v: Any, lo: int, hi: int, name: str) -> int:
        if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
            raise ToolInputError(f"{name} phải là số nguyên từ {lo} đến {hi}")
        return v

    def _drop_pending_order(self) -> None:
        """Đơn đã tạo (đang chờ quét QR / trả tiền mặt) mà khách đổi ý -> huỷ đơn cũ để không lệch tiền."""
        if self.s.state in ("awaiting_payment", "awaiting_cash") and self.s.order_code:
            if self.dm.storage:
                self.dm.storage.set_status(self.s.order_code, "cancelled")
            self.s.order_code = None

    def _unlock_cart(self) -> None:
        """Khách sửa món khi đang ở phiếu gọi món / màn hình thanh toán: quay về trạng thái gọi món."""
        self._drop_pending_order()
        if self.s.state != "ordering":
            self.s.state = "ordering"
            self.events.append({"type": "state", "state": "ordering"})

    # ------------------------------------------------------------------ tóm tắt giỏ cho LLM
    def cart_summary(self) -> dict:
        pb = self.dm.engine.price(self.s.cart, self.dm.now_fn())
        return {
            "items": [f"{ln.qty} {ln.unit} {ln.display_name}: {format_money(ln.total)}" for ln in self.s.cart.lines],
            "subtotal": format_money(pb.subtotal),
            "discounts": [f"{a.name}: -{format_money(a.discount)}" for a in pb.applied if a.discount],
            "gifts": [f"{f.qty} {f.name} ({a.name})" for a in pb.applied for f in a.free_items],
            "total": format_money(pb.total),
            "promo_hints": [h.message for h in pb.hints],
        }

    def _push_cart(self) -> None:
        self.events.append({"type": "cart", "cart": self.dm._cart_dict(self.s)})

    # ------------------------------------------------------------------ các công cụ
    def _t_add_to_cart(self, item_id: str, quantity: int, option_id: str | None = None, note: str | None = None) -> dict:
        e = self._entry(item_id)
        qty = self._int(quantity, 1, MAX_QTY, "quantity")
        opt = None
        if option_id:
            opt = next((o for o in e.options if o.id == option_id), None)
            if opt is None:
                raise ToolInputError(f"món {e.name} không có tuỳ chọn '{option_id}'")
        note = (note or "").strip()[:80] if isinstance(note, (str, type(None))) else ""
        self._unlock_cart()
        ln = self.s.cart.add(e, qty, opt, note)
        self.s.last_entry = e.id
        self._push_cart()
        out: dict = {"added": f"{qty} {getattr(e, 'unit', 'phần')} {ln.display_name}", "cart": self.cart_summary()}
        up = self.dm.rec.upsell(self.s.cart, self.s.prefs, self.dm.now_fn(), self.s.upsold) if self.dm.a.upsell else None
        if up:
            self.s.upsold.add(up.entry_id)
            out["upsell_suggestion"] = f"{up.name} {format_money(up.price)}" + (f" (ưu đãi: {up.promos[0]})" if up.promos else "")
        return out

    def _t_update_cart_item(self, item_id: str, quantity: int) -> dict:
        e = self._entry(item_id)
        qty = self._int(quantity, 0, MAX_QTY, "quantity")
        if not self.s.cart.has(e.id) and qty > 0:
            raise ToolInputError(f"{e.name} chưa có trong mâm, hãy dùng add_to_cart")
        self._unlock_cart()
        self.s.cart.set_qty(e.id, qty)
        self._push_cart()
        return {"updated": f"{e.name}: {qty}", "cart": self.cart_summary()}

    def _t_recommend_dishes(self, likes: list | None = None, dislikes: list | None = None, light: bool = False,
                            vegetarian: bool = False, exclude_ingredients: list | None = None,
                            include_ingredients: list | None = None, max_price_per_person: int | None = None,
                            group_size: int | None = None, style: str | None = None, temperature: str | None = None,
                            category: str | None = None, limit: int = 3) -> dict:
        def strs(v: Any) -> list[str]:
            return [str(x).strip().lower() for x in (v or []) if isinstance(x, str) and x.strip()]

        likes_l = [t for t in strs(likes) if t in TASTES]
        exclude = set(strs(exclude_ingredients))
        if "hải sản" in exclude:
            exclude |= {"tôm", "cua", "mực", "cá"}
        prefs = Preferences(
            likes={t: 1 for t in likes_l},
            dislikes={t for t in strs(dislikes) if t in TASTES},
            light=bool(light),
            vegetarian=bool(vegetarian),
            exclude=exclude,
            include=set(strs(include_ingredients)),
            style=style if style in ("nuoc", "kho") else None,
            temp=temperature if temperature in ("nong", "lanh") else None,
            categories={category} if category else set(),
            budget=max_price_per_person if isinstance(max_price_per_person, int) and max_price_per_person > 0 else None,
            group_size=group_size if isinstance(group_size, int) and group_size > 0 else None,
        )
        self.s.prefs = self.s.prefs.merge(prefs)
        k = limit if isinstance(limit, int) and 1 <= limit <= 4 else 3
        recs = self.dm.rec.recommend(prefs, self.s.cart, k=k, now=self.dm.now_fn(), avoid=self.s.last_recs)
        self.s.last_recs = [r.entry_id for r in recs]
        if recs:
            self.s.last_entry = recs[0].entry_id
        self.events.append({"type": "recs", "items": [r.to_dict() for r in recs]})
        unmet = self.dm.rec.unmet_tastes(prefs, recs) if recs else []
        return {
            "dishes": [{"id": r.entry_id, "name": r.name, "price": format_money(r.price), "reasons": r.reasons,
                        "promotions": r.promos} for r in recs],
            "note": ("không món nào đáp ứng vị: " + ", ".join(unmet)) if unmet else ("không có món phù hợp" if not recs else ""),
        }

    def _t_show_dish(self, item_id: str) -> dict:
        e = self._entry(item_id)
        self.s.last_entry = e.id
        self.events.append({"type": "show_dish", "id": e.id})
        info: dict = {"id": e.id, "name": e.name, "price": format_money(e.price), "description": getattr(e, "description", ""),
                      "taste": e.taste.model_dump(), "ingredients": list(e.contains), "vegetarian": e.is_vegetarian,
                      "promotions": [p.name for p in self.dm.engine.promos_for_entry(e.id, self.dm.now_fn())]}
        if e.options:
            info["options"] = [f"{o.name} +{format_money(o.price_delta)}" for o in e.options]
        if e.kind == "combo":
            info["includes"] = [f"{p.qty} {self.menu.item(p.item).name}" for p in e.items]  # type: ignore[union-attr]
        return info

    def _t_review_order(self) -> dict:
        if self.s.cart.is_empty:
            raise ToolInputError("mâm đang trống, chưa có món để đọc lại")
        self._drop_pending_order()
        self.s.state = "confirm_order"
        self.s.pending = None
        self.events.append({"type": "state", "state": "confirm_order"})
        self._push_cart()
        out = self.cart_summary()
        out["payment_options"] = ["vietqr", "cash"] if self.dm.store.payment.allow_cash else ["vietqr"]
        return out

    def _t_place_order(self, payment_method: str) -> dict:
        if self.s.cart.is_empty:
            raise ToolInputError("mâm đang trống")
        if payment_method not in ("vietqr", "cash"):
            raise ToolInputError("payment_method phải là vietqr hoặc cash")
        if payment_method == "cash" and not self.dm.store.payment.allow_cash:
            raise ToolInputError("quán không nhận tiền mặt, chỉ nhận quét mã QR")
        self._drop_pending_order()
        reply = self.dm._place_order(self.s, payment_method)
        self.events.append({"type": "state", "state": self.s.state, "qr": reply.qr, "order": reply.order})
        code = self.s.order_code or ""
        return {"order_code": code, "queue_number": str(int(code[-6:])) if code[-6:].isdigit() else code,
                "total": format_money(self.s.order_total), "payment_method": payment_method,
                "qr_valid_minutes": self.dm.store.payment.qr_expire_minutes if payment_method == "vietqr" else None}

    def _t_cancel_order(self) -> dict:
        if self.dm.storage and self.s.order_code:
            self.dm.storage.set_status(self.s.order_code, "cancelled")
        self.s.cart.clear()
        self.s.order_code = None
        self.s.state = "ordering"
        self.s.pending = None
        self.events.append({"type": "state", "state": "ordering"})
        self._push_cart()
        return {"cancelled": True}
