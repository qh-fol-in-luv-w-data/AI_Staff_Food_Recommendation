"""Gợi ý món theo khẩu vị (content-based scoring, không cần train, < 1 ms).

Bước 1 - lọc cứng: món chay, thành phần kiêng/dị ứng, ngân sách/người, vị không ăn được, nhóm món khách hỏi.
Bước 2 - chấm điểm: vị thích, thanh đạm, món nước/khô, nóng/lạnh, no/nhẹ, bán chạy, đang ưu đãi,
         combo hợp số người, quán muốn đẩy (boost), tránh món đã gọi.
Bước 3 - đa dạng: không gợi ý 3 món cùng nhóm (trừ khi khách hỏi đúng nhóm đó).
Kèm lý do bằng tiếng Việt để AI giải thích ("vì quý khách thích cay", "đang giảm 15%").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .cart import Cart
from .config import TASTES, Entry, StoreConfig
from .nlu import Preferences
from .promotions import PromotionEngine

TASTE_NAMES = {"cay": "cay", "ngot": "ngọt", "chua": "chua", "dam": "đậm đà", "beo": "béo"}
SEAFOOD = {"tôm", "cua", "mực", "cá", "hải sản"}


@dataclass
class Recommendation:
    entry_id: str
    name: str
    kind: str
    price: int
    score: float
    reasons: list[str] = field(default_factory=list)
    promos: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class Recommender:
    def __init__(self, cfg: StoreConfig, engine: PromotionEngine):
        self.cfg = cfg
        self.menu = cfg.menu
        self.engine = engine
        prices = [e.price for e in self.menu.entries()] or [1]
        self.max_price = max(prices)

    def _per_person(self, e: Entry) -> int:
        return e.price // getattr(e, "serves", 1)

    def _excluded(self, e: Entry, prefs: Preferences) -> bool:
        contains = set(e.contains)
        if contains & SEAFOOD:
            contains.add("hải sản")
        return bool(contains & prefs.exclude)

    def score(self, e: Entry, prefs: Preferences, cart: Cart | None, now: datetime | None) -> tuple[float, list[str], list[str]] | None:
        if not e.available:
            return None
        if prefs.vegetarian and not e.is_vegetarian:
            return None
        if self._excluded(e, prefs):
            return None
        if prefs.budget and self._per_person(e) > prefs.budget:
            return None
        for t in prefs.dislikes:
            if e.taste.get(t) >= 2:
                return None
        is_combo = e.kind == "combo"
        cats = prefs.categories
        if "combo" in cats:  # khách hỏi đúng combo
            if not is_combo:
                return None
        elif cats and not is_combo and e.category not in cats:
            return None
        elif cats and is_combo and not (prefs.group_size and prefs.group_size >= 2):
            return None
        if prefs.style and not is_combo and e.style in ("nuoc", "kho") and e.style != prefs.style:
            return None

        s, why = 0.0, []
        for t, w in prefs.likes.items():
            v = e.taste.get(t)
            s += v * 1.5 * w
            if v >= 2:
                why.append(f"vị {TASTE_NAMES[t]}")
            elif v == 0:
                s -= 2
        for t in prefs.dislikes:
            s -= e.taste.get(t) * 2
        if prefs.light:
            lightness = 3 - e.taste.beo - max(0, e.taste.dam - 1)
            s += lightness * 0.8
            if lightness >= 2:
                why.append("thanh đạm")
        for ing in prefs.include:
            if ing in e.contains:
                s += 2.5
                why.append(f"có {ing}")
        if prefs.style and getattr(e, "style", "") == prefs.style:
            s += 2
            why.append("món nước" if prefs.style == "nuoc" else "món khô")
        if prefs.temp and getattr(e, "temp", "") == prefs.temp:
            s += 1.5
            if prefs.temp == "lanh":
                why.append("mát lạnh")
        if prefs.portion and getattr(e, "portion", "") == prefs.portion:
            s += 1.5
            why.append("ăn no bụng" if prefs.portion == "lon" else "ăn nhẹ")
        if prefs.vegetarian:
            why.append("món chay")
        if e.best_seller:
            s += 1.5
            why.append("món bán chạy")
        s += e.boost
        promos = self.engine.promos_for_entry(e.id, now)
        if promos:
            s += 2
            why.append("đang có ưu đãi")
        if prefs.cheap:
            s += (1 - self._per_person(e) / self.max_price) * 3
        if prefs.premium:
            s += (e.price / self.max_price) * 3
        n = prefs.group_size
        if is_combo:
            serves = getattr(e, "serves", 1)
            if n and serves == n:
                s += 4.5
                why.insert(0, f"vừa cho {n} người")
            elif n and abs(serves - n) == 1:
                s += 1
            elif n:
                s -= 4  # combo 4 người không hợp nhóm 2 người
            else:
                s -= 0.5
            saved = self.menu.combo_value(e) - e.price  # type: ignore[arg-type]
            if saved > 0:
                why.append(f"tiết kiệm {saved // 1000} nghìn")
        elif n and n >= 3:
            s -= 1
        if not cats and getattr(e, "style", "") in ("uong", "trang_mieng", "an_kem"):
            s -= 2.5
        if cart and cart.has(e.id):
            s -= 3
        return s, list(dict.fromkeys(why)), [p.name for p in promos]

    def recommend(
        self,
        prefs: Preferences,
        cart: Cart | None = None,
        k: int | None = None,
        now: datetime | None = None,
        avoid: tuple[str, ...] | list[str] = (),
    ) -> list[Recommendation]:
        k = k or self.cfg.store.assistant.max_recommendations
        scored: list[Recommendation] = []
        for e in self.menu.entries():
            r = self.score(e, prefs, cart, now)
            if r is None:
                continue
            s, why, promos = r
            if e.id in avoid:
                s -= 1.5
            scored.append(Recommendation(e.id, e.name, e.kind, e.price, round(s, 2), why, promos, getattr(e, "description", "")))
        scored.sort(key=lambda r: -r.score)
        if not scored:
            return []
        # món chính trước; đồ uống/tráng miệng/ăn kèm chỉ khi khách hỏi đúng nhóm đó
        side = ("uong", "trang_mieng", "an_kem")
        mains = [r for r in scored if prefs.categories or getattr(self.menu.get(r.entry_id), "style", "") not in side]
        pool = [r for r in (mains or scored) if r.score >= scored[0].score - 6]
        out: list[Recommendation] = []
        per_cat: dict[str, int] = {}
        limit_per_cat = k if len(prefs.categories) == 1 else 1
        for r in pool:  # vòng 1: mỗi nhóm 1 món cho đa dạng
            cat = self.menu.get(r.entry_id).category
            if per_cat.get(cat, 0) >= limit_per_cat:
                continue
            out.append(r)
            per_cat[cat] = per_cat.get(cat, 0) + 1
            if len(out) >= k:
                return out
        for r in pool:  # vòng 2: chưa đủ thì lấy thêm theo điểm
            if r not in out:
                out.append(r)
            if len(out) >= k:
                break
        return out

    def unmet_tastes(self, prefs: Preferences, recs: list[Recommendation]) -> list[str]:
        """Vị khách thích mà không món gợi ý nào đáp ứng (để AI nói thật với khách)."""
        out = []
        for t in prefs.likes:
            if not any(self.menu.get(r.entry_id).taste.get(t) >= 2 for r in recs):
                out.append(TASTE_NAMES[t])
        return out

    def upsell(self, cart: Cart, prefs: Preferences, now: datetime | None = None, already: set[str] | None = None) -> Recommendation | None:
        """Gợi ý thêm 1 món: đồ uống nếu chưa có, hoặc món ăn kèm hay đi cùng (pairs_with)."""
        already = already or set()
        if cart.is_empty:
            return None
        has_drink = any(
            (ln.kind == "item" and self.menu.get(ln.entry_id).is_drink)
            or (ln.kind == "combo" and any(self.menu.item(p.item).is_drink for p in self.menu.get(ln.entry_id).items))  # type: ignore[union-attr]
            for ln in cart.lines
        )
        cands: list[str] = []
        last = self.menu.get(cart.lines[-1].entry_id)
        if not has_drink:
            drinks = [i for i in self.menu.items if i.is_drink and i.available]
            ranked = []
            for d in drinks:
                r = self.score(d, Preferences(categories={d.category}, vegetarian=prefs.vegetarian, exclude=prefs.exclude), cart, now)
                if r:
                    bonus = 3 if d.id in last.pairs_with else 0
                    ranked.append((r[0] + bonus, d.id))
            cands += [i for _, i in sorted(ranked, reverse=True)]
        cands += [p for p in last.pairs_with if not cart.has(p)]
        for eid in cands:
            if eid in already or cart.has(eid):
                continue
            e = self.menu.get(eid)
            if prefs.vegetarian and not e.is_vegetarian:
                continue
            if self._excluded(e, prefs):
                continue
            promos = [p.name for p in self.engine.promos_for_entry(eid, now)]
            return Recommendation(e.id, e.name, e.kind, e.price, 0.0, [], promos, getattr(e, "description", ""))
        return None


__all__ = ["Recommender", "Recommendation", "TASTE_NAMES", "TASTES"]
