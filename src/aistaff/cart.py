"""Giỏ hàng (đơn đang gọi) của một phiên khách."""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Entry, Option


@dataclass
class CartLine:
    entry_id: str
    name: str
    kind: str          # "item" | "combo"
    unit_price: int    # đã cộng tiền tuỳ chọn (size lớn...)
    qty: int
    unit: str = "phần"
    category: str = ""
    option_id: str | None = None
    option_name: str | None = None
    note: str = ""

    @property
    def key(self) -> tuple[str, str | None, str]:
        return (self.entry_id, self.option_id, self.note)

    @property
    def total(self) -> int:
        return self.unit_price * self.qty

    @property
    def display_name(self) -> str:
        s = self.name
        if self.option_name:
            s += f" ({self.option_name})"
        if self.note:
            s += f" - {self.note}"
        return s

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "name": self.name,
            "display_name": self.display_name,
            "kind": self.kind,
            "unit_price": self.unit_price,
            "qty": self.qty,
            "unit": self.unit,
            "option_id": self.option_id,
            "option_name": self.option_name,
            "note": self.note,
            "total": self.total,
        }


@dataclass
class Cart:
    lines: list[CartLine] = field(default_factory=list)

    def add(self, entry: Entry, qty: int = 1, option: Option | None = None, note: str = "") -> CartLine:
        qty = max(1, int(qty))
        price = entry.price + (option.price_delta if option else 0)
        line = CartLine(
            entry_id=entry.id,
            name=entry.name,
            kind=entry.kind,
            unit_price=price,
            qty=qty,
            unit=getattr(entry, "unit", "phần"),
            category=getattr(entry, "category", ""),
            option_id=option.id if option else None,
            option_name=option.name if option else None,
            note=note.strip(),
        )
        for existing in self.lines:
            if existing.key == line.key:
                existing.qty += qty
                return existing
        self.lines.append(line)
        return line

    def remove(self, entry_id: str, qty: int | None = None) -> int:
        """Bớt `qty` phần của món (None = bỏ hết). Trả về số phần đã bỏ."""
        removed = 0
        for line in [ln for ln in reversed(self.lines) if ln.entry_id == entry_id]:
            if qty is None or line.qty <= (qty - removed):
                removed += line.qty
                self.lines.remove(line)
            else:
                line.qty -= qty - removed
                removed = qty
            if qty is not None and removed >= qty:
                break
        return removed

    def set_qty(self, entry_id: str, qty: int) -> None:
        current = self.qty_of(entry_id)
        if qty <= 0:
            self.remove(entry_id)
        elif qty < current:
            self.remove(entry_id, current - qty)
        elif qty > current:
            line = next(ln for ln in self.lines if ln.entry_id == entry_id)
            line.qty += qty - current

    def qty_of(self, entry_id: str) -> int:
        return sum(ln.qty for ln in self.lines if ln.entry_id == entry_id)

    def has(self, entry_id: str) -> bool:
        return self.qty_of(entry_id) > 0

    def clear(self) -> None:
        self.lines.clear()

    @property
    def subtotal(self) -> int:
        return sum(ln.total for ln in self.lines)

    @property
    def count(self) -> int:
        return sum(ln.qty for ln in self.lines)

    @property
    def is_empty(self) -> bool:
        return not self.lines

    def to_list(self) -> list[dict]:
        return [ln.to_dict() for ln in self.lines]
