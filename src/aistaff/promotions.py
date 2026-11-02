"""Engine ưu đãi + tính tiền.

Nguyên tắc:
- Giá & giảm giá LUÔN tính bằng code (không để AI/LLM tự tính) -> không sai tiền.
- Ưu đãi stackable=true cộng dồn với nhau; stackable=false đứng một mình.
  Hệ thống thử mọi phương án và chọn phương án có lợi nhất cho khách.
- Sinh "gợi ý sắp đạt ưu đãi" (hint) để AI nhắc khách gọi thêm (upsell có lợi cho cả 2 bên).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .cart import Cart, CartLine
from .config import DAYS, Promotion, StoreConfig
from .textnorm import format_money


@dataclass
class FreeItem:
    entry_id: str
    name: str
    qty: int
    value: int

    def to_dict(self) -> dict:
        return {"entry_id": self.entry_id, "name": self.name, "qty": self.qty, "value": self.value}


@dataclass
class AppliedPromo:
    id: str
    name: str
    discount: int = 0
    free_items: list[FreeItem] = field(default_factory=list)

    @property
    def benefit(self) -> int:
        return self.discount + sum(f.value for f in self.free_items)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "discount": self.discount,
            "free_items": [f.to_dict() for f in self.free_items],
        }


@dataclass
class PromoHint:
    id: str
    name: str
    message: str            # câu AI có thể nói luôn
    missing_amount: int = 0

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "message": self.message, "missing_amount": self.missing_amount}


@dataclass
class PriceBreakdown:
    subtotal: int
    discount: int
    vat: int
    total: int
    applied: list[AppliedPromo]
    hints: list[PromoHint]

    @property
    def free_items(self) -> list[FreeItem]:
        return [f for a in self.applied for f in a.free_items]

    @property
    def benefit(self) -> int:
        return sum(a.benefit for a in self.applied)

    def to_dict(self) -> dict:
        return {
            "subtotal": self.subtotal,
            "discount": self.discount,
            "vat": self.vat,
            "total": self.total,
            "applied": [a.to_dict() for a in self.applied],
            "free_items": [f.to_dict() for f in self.free_items],
            "hints": [h.to_dict() for h in self.hints],
        }


class PromotionEngine:
    def __init__(self, cfg: StoreConfig):
        self.cfg = cfg
        self.menu = cfg.menu
        self.tz = ZoneInfo(cfg.store.timezone)
        self.rounding = cfg.store.pricing.discount_rounding

    # ------------------------------------------------------------------ thời gian
    def now(self) -> datetime:
        return datetime.now(self.tz)

    def _local(self, now: datetime | None) -> datetime:
        if now is None:
            return self.now()
        return now.astimezone(self.tz) if now.tzinfo else now.replace(tzinfo=self.tz)

    def is_active(self, p: Promotion, now: datetime | None = None) -> bool:
        if not p.active:
            return False
        t = self._local(now)
        d = t.date()
        if p.valid_from and d < date.fromisoformat(p.valid_from):
            return False
        if p.valid_to and d > date.fromisoformat(p.valid_to):
            return False
        if p.schedule:
            if DAYS[t.weekday()] not in p.schedule.days:
                return False
            hm = t.hour * 60 + t.minute
            if p.schedule.start:
                h, m = map(int, p.schedule.start.split(":"))
                if hm < h * 60 + m:
                    return False
            if p.schedule.end:
                h, m = map(int, p.schedule.end.split(":"))
                if hm >= h * 60 + m:
                    return False
        return True

    def active(self, now: datetime | None = None) -> list[Promotion]:
        ps = [p for p in self.cfg.promotions if self.is_active(p, now)]
        return sorted(ps, key=lambda p: -p.priority)

    def _targets(self, p: Promotion, entry_id: str, kind: str, category: str) -> bool:
        tg = p.targets
        if entry_id in tg.items:
            return True
        if kind == "item" and category in tg.categories:
            return True
        if kind == "combo" and (tg.combos == "all" or entry_id in tg.combos):
            return True
        return False

    def promos_for_entry(self, entry_id: str, now: datetime | None = None) -> list[Promotion]:
        """Ưu đãi liên quan trực tiếp tới 1 món (để AI nói 'món này đang giảm 15%')."""
        e = self.menu.get(entry_id)
        out = []
        for p in self.active(now):
            if p.type in ("percent_off_items", "amount_off_items") and self._targets(
                p, e.id, e.kind, getattr(e, "category", "")
            ):
                out.append(p)
            elif p.type == "buy_x_get_y" and p.buy and p.buy.item == entry_id:
                out.append(p)
        return out

    # ------------------------------------------------------------------ tính từng ưu đãi
    def _round(self, amount: float) -> int:
        r = self.rounding
        return int(amount // r * r) if amount >= r else int(amount)

    def _item_level(self, p: Promotion, lines: list[CartLine]) -> AppliedPromo | None:
        if p.type in ("percent_off_items", "amount_off_items"):
            base = sum(ln.total for ln in lines)
            if base < p.min_subtotal:
                return None
            hit = [ln for ln in lines if self._targets(p, ln.entry_id, ln.kind, ln.category)]
            if not hit:
                return None
            if p.type == "percent_off_items":
                d = self._round(sum(ln.total for ln in hit) * p.value / 100)
            else:
                d = sum(min(int(p.value), ln.unit_price) * ln.qty for ln in hit)
            if p.max_discount is not None:
                d = min(d, p.max_discount)
            return AppliedPromo(p.id, p.name, discount=d) if d > 0 else None
        if p.type == "buy_x_get_y":
            assert p.buy and p.get
            bought = sum(ln.qty for ln in lines if ln.entry_id == p.buy.item)
            get_entry = self.menu.get(p.get.item)
            if p.reward == "discount_in_cart" and p.get.item == p.buy.item:
                times = bought // (p.buy.qty + p.get.qty)
                d = times * p.get.qty * get_entry.price
                return AppliedPromo(p.id, p.name, discount=d) if d > 0 else None
            times = bought // p.buy.qty
            if times <= 0:
                return None
            q = times * p.get.qty
            return AppliedPromo(p.id, p.name, free_items=[FreeItem(get_entry.id, get_entry.name, q, q * get_entry.price)])
        return None

    def _order_level(self, p: Promotion, base: int) -> AppliedPromo | None:
        if base < p.min_subtotal or base <= 0:
            return None
        if p.type == "percent_off_order":
            d = self._round(base * p.value / 100)
            if p.max_discount is not None:
                d = min(d, p.max_discount)
            return AppliedPromo(p.id, p.name, discount=d) if d > 0 else None
        if p.type == "amount_off_order":
            return AppliedPromo(p.id, p.name, discount=min(int(p.value), base))
        if p.type == "free_item":
            assert p.get
            e = self.menu.get(p.get.item)
            return AppliedPromo(p.id, p.name, free_items=[FreeItem(e.id, e.name, p.get.qty, p.get.qty * e.price)])
        return None

    def _apply_set(self, promos: list[Promotion], cart: Cart) -> list[AppliedPromo]:
        applied: list[AppliedPromo] = []
        item_disc = 0
        for p in promos:
            if p.type in ("percent_off_items", "amount_off_items", "buy_x_get_y"):
                a = self._item_level(p, cart.lines)
                if a:
                    applied.append(a)
                    item_disc += a.discount
        base = cart.subtotal - item_disc
        for p in promos:
            if p.type in ("percent_off_order", "amount_off_order", "free_item"):
                a = self._order_level(p, base)
                if a:
                    applied.append(a)
                    base -= a.discount
        return applied

    # ------------------------------------------------------------------ API chính
    def price(self, cart: Cart, now: datetime | None = None) -> PriceBreakdown:
        active = self.active(now)
        stackable = [p for p in active if p.stackable]
        options: list[list[AppliedPromo]] = [self._apply_set(stackable, cart)]
        for p in active:
            if not p.stackable:
                options.append(self._apply_set([p], cart))
        best = max(options, key=lambda opt: (sum(a.benefit for a in opt), -len(opt)))
        discount = min(sum(a.discount for a in best), cart.subtotal)
        pr = self.cfg.store.pricing
        vat = 0 if pr.prices_include_vat else round((cart.subtotal - discount) * pr.vat_percent / 100)
        total = cart.subtotal - discount + vat
        hints = self.hints(cart, active, best)
        return PriceBreakdown(cart.subtotal, discount, vat, total, best, hints)

    def reward_text(self, p: Promotion) -> str:
        """Phần thưởng của ưu đãi dạng câu ngắn: 'giảm 10%, tối đa 30.000đ', 'tặng 1 Chè ba màu'."""
        if p.type in ("percent_off_order", "percent_off_items"):
            s = f"giảm {p.value:g}%"
            if p.max_discount:
                s += f", tối đa {format_money(p.max_discount)}"
            return s
        if p.type in ("amount_off_order", "amount_off_items"):
            return f"giảm {format_money(int(p.value))}"
        if p.get:
            return f"tặng {p.get.qty} {self.menu.get(p.get.item).name}"
        return p.name

    def hints(self, cart: Cart, active: list[Promotion], applied: list[AppliedPromo]) -> list[PromoHint]:
        got = {a.id for a in applied}
        out: list[PromoHint] = []
        sub = cart.subtotal
        for p in active:
            if p.id in got or cart.is_empty:
                continue
            if p.type in ("percent_off_order", "amount_off_order", "free_item") and p.min_subtotal > sub:
                miss = p.min_subtotal - sub
                if p.hint_within and miss <= p.hint_within:
                    out.append(PromoHint(p.id, p.name, f"gọi thêm {format_money(miss)} nữa là được {self.reward_text(p)}", miss))
            elif p.type == "buy_x_get_y" and p.buy and p.get:
                q = cart.qty_of(p.buy.item)
                group = p.buy.qty + (p.get.qty if p.reward == "discount_in_cart" else 0)
                need = group - (q % group)
                if q > 0 and need == 1:
                    name = self.menu.get(p.buy.item).name
                    gift = self.menu.get(p.get.item).name
                    msg = f"thêm 1 {name} nữa là được tặng {p.get.qty} {gift}"
                    if p.reward == "discount_in_cart":
                        msg = f"thêm 1 {name} nữa là ly đó miễn phí"
                    out.append(PromoHint(p.id, p.name, msg, 0))
        return out
