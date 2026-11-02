"""Quản lý hội thoại (dialog manager) - máy trạng thái điều khiển toàn bộ luồng bán hàng.

  idle --(khách tới / bấm màn hình / "xin chào")--> greeting (chào + giới thiệu ưu đãi)
  ordering <-> asking_pref (hỏi khẩu vị) -> gợi ý -> chọn món -> upsell / nhắc ưu đãi
  ordering --("chốt đơn"/"thanh toán")--> confirm_order (đọc lại đơn + tổng tiền)
  confirm_order --(đồng ý)--> awaiting_payment (hiện QR) | awaiting_cash (trả tại quầy)
  awaiting_payment --(ngân hàng báo đã nhận tiền / nhân viên xác nhận)--> done --> idle

Toàn bộ logic giá, ưu đãi, mã QR là code tất định -> không bao giờ "bịa" giá như LLM.
Câu trả lời có 2 dạng: `text` (hiện trên màn hình) và `speech` (đã chuẩn hoá cho TTS, ngắn hơn).
"""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import vietqr
from .cart import Cart
from .config import Entry, StoreConfig
from .nlu import NLU, NLUResult, Preferences
from .promotions import PriceBreakdown, PromotionEngine
from .recommender import Recommendation, Recommender
from .storage import Storage
from .textnorm import format_money, normalize, strip_diacritics, tts_normalize


@dataclass
class Session:
    id: str
    state: str = "idle"
    cart: Cart = field(default_factory=Cart)
    prefs: Preferences = field(default_factory=Preferences)
    last_recs: list[str] = field(default_factory=list)
    last_entry: str | None = None
    pending: dict | None = None
    order_code: str | None = None
    order_total: int = 0
    order_expires: datetime | None = None
    payment_method: str | None = None
    takeaway: bool | None = None
    announced: set[str] = field(default_factory=set)
    upsold: set[str] = field(default_factory=set)
    asked_pref: bool = False
    misses: int = 0
    turns: int = 0
    last_text: str = ""
    last_speech: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    rng: random.Random = field(default_factory=random.Random)


@dataclass
class Reply:
    text: str
    speech: str
    state: str
    intent: str = ""
    cart: dict | None = None
    recommendations: list[dict] = field(default_factory=list)
    options: list[dict] = field(default_factory=list)   # lựa chọn để khách bấm (khi hỏi lại)
    suggestions: list[str] = field(default_factory=list)  # nút trả lời nhanh
    qr: dict | None = None
    order: dict | None = None
    end: bool = False
    nlu: dict | None = None
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class DialogManager:
    def __init__(
        self,
        cfg: StoreConfig,
        storage: Storage | None = None,
        now_fn: Callable[[], datetime] | None = None,
        llm: object | None = None,
    ):
        self.cfg = cfg
        self.store = cfg.store
        self.menu = cfg.menu
        self.a = cfg.store.assistant
        self.nlu = NLU(cfg.menu)
        self.engine = PromotionEngine(cfg)
        self.rec = Recommender(cfg, self.engine)
        self.storage = storage
        self.now_fn = now_fn or self.engine.now
        self.llm = llm
        self.sp = self.a.self_pronoun            # em
        self.cp = self.a.customer_pronoun        # quý khách
        if storage:
            storage.upsert_store(self.store.id, self.store.name, self.store.address, self.store.phone,
                                 self.store.model_dump(exclude={"payment": {"sepay"}}))

    # ================================================================== tiện ích câu chữ
    def _cap(self, s: str) -> str:
        return s[:1].upper() + s[1:] if s else s

    def _pick(self, s: Session, *variants: str) -> str:
        return s.rng.choice(variants)

    def _qty_name(self, qty: int, e: Entry | None = None, name: str = "", unit: str = "") -> str:
        unit = unit or (getattr(e, "unit", "") if e else "")
        name = name or (e.name if e else "")
        return f"{qty} {unit} {name}".replace("  ", " ") if unit and unit != "phần" else f"{qty} {name}"

    def _price_line(self, pb: PriceBreakdown) -> tuple[str, str]:
        """(text hiển thị, câu nói) cho phần tiền."""
        t = [f"Tạm tính: {format_money(pb.subtotal)}"]
        say = []
        for a in pb.applied:
            if a.discount:
                t.append(f"Ưu đãi \"{a.name}\": -{format_money(a.discount)}")
                say.append(f"được giảm {format_money(a.discount)} nhờ chương trình {a.name}")
            for f in a.free_items:
                t.append(f"Tặng kèm: {f.qty} {f.name} ({a.name})")
                say.append(f"được tặng {f.qty} {f.name}")
        if pb.vat:
            t.append(f"VAT: {format_money(pb.vat)}")
        t.append(f"TỔNG CỘNG: {format_money(pb.total)}")
        spoken = (", ".join(say) + ". " if say else "") + f"Tổng cộng {format_money(pb.total)}"
        return "\n".join(t), spoken

    def _promo_pitch(self, s: Session, limit: int = 2) -> str:
        if not self.a.announce_promotions:
            return ""
        ps = [p for p in self.engine.active(self.now_fn()) if p.announce and p.id not in s.announced][:limit]
        if not ps:
            return ""
        for p in ps:
            s.announced.add(p.id)
        parts = [p.pitch or p.name for p in ps]
        return "Hôm nay quán đang có ưu đãi: " + "; ".join(parts) + "."

    def _cart_dict(self, s: Session) -> dict:
        pb = self.engine.price(s.cart, self.now_fn())
        return {"lines": s.cart.to_list(), "count": s.cart.count, **pb.to_dict()}

    def _reply(self, s: Session, text: str, say: str | None = None, intent: str = "", **kw) -> Reply:
        say = text if say is None else say
        r = Reply(text=text, speech=tts_normalize(say), state=s.state, intent=intent, cart=self._cart_dict(s), **kw)
        s.last_text, s.last_speech = r.text, r.speech
        return r

    # ================================================================== vòng đời phiên
    def new_session(self, session_id: str | None = None, seed: int | None = None) -> Session:
        s = Session(id=session_id or uuid.uuid4().hex[:12])
        if seed is not None:
            s.rng.seed(seed)
        return s

    def greet(self, s: Session) -> Reply:
        s.state = "ordering"
        s.updated_at = time.time()
        hello = self._pick(s, "Xin chào", "Dạ xin chào", "Chào mừng")
        intro = f"{hello} {self.cp}! {self._cap(self.sp)} là {self.a.name}, nhân viên AI của {self.store.display_name}."
        pitch = self._promo_pitch(s)
        ask = (f"{self._cap(self.cp)} muốn gọi món luôn, hay để {self.sp} gợi ý món theo khẩu vị ạ?")
        text = " ".join(x for x in [intro, pitch, ask] if x)
        return self._reply(s, text, intent="greet",
                           suggestions=["Gợi ý món ngon", "Xem thực đơn", "Có khuyến mãi gì?", "Combo cho 2 người"])

    def reset(self, s: Session) -> None:
        fresh = self.new_session(s.id)
        fresh.rng = s.rng
        s.__dict__.update(fresh.__dict__)

    # ================================================================== xử lý câu nói
    def handle(self, s: Session, text: str) -> Reply:
        t0 = time.perf_counter()
        s.turns += 1
        s.updated_at = time.time()
        if s.state in ("idle", "done"):
            if s.state == "done":
                self.reset(s)
            greeting = self.greet(s)
            r0 = self.nlu.parse(text)
            if r0.intent in ("greet", "unknown", "thanks") or not text.strip():
                return self._finish(s, greeting, r0, t0)
            pre = greeting.text
        else:
            pre = ""
        r = self.nlu.parse(text)
        if r.intent == "unknown" and self.llm is not None:
            r = self._llm_fallback(text, r)
        reply = self._dispatch(s, r)
        if pre:
            reply.text = pre + "\n" + reply.text
            reply.speech = tts_normalize(pre) + " " + reply.speech
        return self._finish(s, reply, r, t0)

    def _finish(self, s: Session, reply: Reply, r: NLUResult, t0: float) -> Reply:
        reply.nlu = r.to_dict()
        reply.state = s.state
        reply.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if self.storage:
            self.storage.log_turn(s.id, "user", r.text, r.intent)
            self.storage.log_turn(s.id, "assistant", reply.text, None, reply.latency_ms)
        return reply

    def _llm_fallback(self, text: str, r: NLUResult) -> NLUResult:
        try:
            hint = self.llm.rewrite(text, self.menu)  # type: ignore[attr-defined]
        except Exception:
            return r
        if not hint:
            return r
        r2 = self.nlu.parse(hint)
        return r2 if r2.intent != "unknown" else r

    def _dispatch(self, s: Session, r: NLUResult) -> Reply:
        if r.takeaway is not None:
            s.takeaway = r.takeaway
        # trạng thái chờ thanh toán: chỉ cho phép đổi phương thức / huỷ / sửa đơn
        if s.state == "awaiting_payment":
            return self._during_payment(s, r)
        if s.state == "awaiting_cash":
            if r.intent == "cancel":
                return self._cancel(s)
            return self._reply(s, f"Dạ, mời {self.cp} thanh toán {format_money(s.order_total)} tại quầy, mã đơn {s.order_code} ạ.",
                               intent="awaiting_cash")
        if s.state == "confirm_order":
            out = self._confirming(s, r)
            if out:
                return out
        pend = s.pending
        if pend and pend.get("type") == "clarify":
            out = self._clarifying(s, r)
            if out:
                return out
        if pend and pend.get("type") in ("upsell", "anything_else") and (r.yes or r.no) and not r.items:
            return self._answer_pending(s, r)
        if s.state == "asking_pref":
            out = self._pref_answer(s, r)
            if out:
                return out

        handler = {
            "add": self._add, "add_generic": self._add_generic, "add_more": self._add_more, "select": self._select,
            "remove": self._remove, "remove_generic": self._remove_generic, "set_qty": self._set_qty, "swap": self._swap,
            "ask_recommend": self._recommend, "preference": self._recommend, "ask_category": self._recommend,
            "ask_menu": self._menu, "ask_promo": self._promos, "ask_price": self._price, "ask_info": self._info,
            "view_cart": self._view_cart, "checkout": self._checkout, "pay_cash": self._checkout, "pay_qr": self._checkout,
            "cancel": self._cancel, "repeat": self._repeat, "thanks": self._thanks, "goodbye": self._goodbye,
            "greet": self._greet_again, "help": self._help, "yes": self._yes_no, "no": self._yes_no,
        }.get(r.intent, self._unknown)
        if r.intent != "unknown":
            s.misses = 0
        return handler(s, r)

    # ================================================================== gọi món
    def _add_entries(self, s: Session, adds: list[tuple[Entry, int, str | None, str]], intent: str = "add", then_checkout: bool = False) -> Reply:
        added = []
        for e, qty, opt_id, note in adds:
            opt = next((o for o in e.options if o.id == opt_id), None)
            ln = s.cart.add(e, qty, opt, note)
            added.append(self._qty_name(qty, e, name=ln.display_name))
            s.last_entry = e.id
        s.pending = None
        s.state = "ordering"
        if then_checkout:
            return self._checkout(s, None, prefix=f"Dạ, {self.sp} đã thêm " + ", ".join(added) + ".")
        text = f"Dạ, {self.sp} đã thêm " + ", ".join(added) + " vào đơn."
        extra = self._after_add(s)
        return self._reply(s, text + (" " + extra[0] if extra[0] else ""), intent=intent,
                           suggestions=extra[1] or ["Chốt đơn", "Xem lại đơn", "Gợi ý thêm"])

    def _after_add(self, s: Session) -> tuple[str, list[str]]:
        """Sau khi thêm món: nhắc ưu đãi sắp đạt -> upsell -> hỏi thêm gì nữa."""
        now = self.now_fn()
        pb = self.engine.price(s.cart, now)
        for h in pb.hints:
            key = f"hint:{h.id}:{h.missing_amount // 10000}"
            if key not in s.announced:
                s.announced.add(key)
                s.pending = {"type": "anything_else"}
                return (f"{self._cap(self.cp)} {h.message} ạ. {self._cap(self.cp)} có muốn gọi thêm gì không ạ?",
                        ["Gợi ý thêm", "Chốt đơn"])
        for a in pb.applied:
            key = f"applied:{a.id}"
            if key not in s.announced:
                s.announced.add(key)
                s.pending = {"type": "anything_else"}
                gift = ", ".join(f"{f.qty} {f.name}" for f in a.free_items)
                what = f"được tặng {gift}" if gift else f"được giảm {format_money(a.discount)}"
                return (f"Đơn đã {what} nhờ ưu đãi \"{a.name}\" rồi ạ. {self._cap(self.cp)} cần thêm gì nữa không ạ?",
                        ["Chốt đơn", "Xem lại đơn"])
        if self.a.upsell:
            up = self.rec.upsell(s.cart, s.prefs, now, s.upsold)
            if up:
                s.upsold.add(up.entry_id)
                s.pending = {"type": "upsell", "entry_id": up.entry_id}
                promo = f" (đang có ưu đãi {up.promos[0]})" if up.promos else ""
                return (f"{self._cap(self.cp)} dùng thêm {up.name} {format_money(up.price)}{promo} không ạ?",
                        [f"Thêm {up.name}", "Không, cảm ơn", "Chốt đơn"])
        s.pending = {"type": "anything_else"}
        return (f"{self._cap(self.cp)} cần thêm gì nữa không ạ?", [])

    def _add(self, s: Session, r: NLUResult) -> Reply:
        adds = [(self.menu.get(m.entry_id), m.qty or 1, m.option_id, m.note) for m in r.items]
        reply = self._add_entries(s, adds, then_checkout="checkout" in r.intents)
        if r.generic:  # vd "cho 1 phở bò tái với 2 bún" -> thêm phở, hỏi lại loại bún
            g = r.generic[0]
            clar = self._ask_clarify(s, g.candidates, g.qty or 1, g.head)
            reply.text += "\n" + clar.text
            reply.speech += " " + clar.speech
            reply.options = clar.options
            reply.state = s.state
        return reply

    def _ask_clarify(self, s: Session, candidates: list[str], qty: int, head: str, remove: bool = False) -> Reply:
        es = [self.menu.get(c) for c in candidates]
        names = [e.name for e in es]
        s.pending = {"type": "clarify", "candidates": candidates, "qty": qty, "remove": remove}
        listing = ", ".join(f"{e.name} {format_money(e.price)}" for e in es[:6])
        spoken = ", ".join(names[:-1]) + (f" và {names[-1]}" if len(names) > 1 else names[0])
        text = f"Dạ, quán có {listing}. {self._cap(self.cp)} chọn loại nào ạ?"
        say = f"Dạ, quán có {spoken}. {self._cap(self.cp)} chọn loại nào ạ?"
        return self._reply(s, text, say, intent="clarify",
                           options=[{"entry_id": e.id, "name": e.name, "price": e.price} for e in es])

    def _clarifying(self, s: Session, r: NLUResult) -> Reply | None:
        pend = s.pending or {}
        cands: list[str] = pend.get("candidates", [])
        spoken_qty = r.number if (r.number and r.number <= 20 and r.ordinal is None) else None  # "thứ hai" != 2 phần
        qty = r.qty or spoken_qty or pend.get("qty", 1)
        chosen: list[str] = [m.entry_id for m in r.items if m.entry_id in cands]
        if not chosen and r.ordinal is not None and cands:
            idx = r.ordinal - 1 if r.ordinal > 0 else len(cands) - 1
            if 0 <= idx < len(cands):
                chosen = [cands[idx]]
        if not chosen:  # khách chỉ nói phần khác biệt: "tái", "gà", "đặc biệt"
            words = set(strip_diacritics(r.norm).split()) - {"cho", "toi", "lay", "mon", "loai", "em", "a", "nha", "nhe", "di"}
            best, best_hits = None, 0
            for c in cands:
                name_words = set(strip_diacritics(normalize(self.menu.get(c).name)).split())
                hits = len(words & name_words)
                common = set.intersection(*[set(strip_diacritics(normalize(self.menu.get(x).name)).split()) for x in cands])
                hits_unique = len((words & name_words) - common)
                if hits_unique > best_hits:
                    best, best_hits = c, hits_unique
            if best:
                chosen = [best]
        if chosen:
            s.pending = None
            if pend.get("remove"):
                s.cart.remove(chosen[0])
                s.state = "ordering"
                return self._reply(s, f"Dạ, {self.sp} đã bỏ {self.menu.get(chosen[0]).name} khỏi đơn ạ.", intent="remove")
            m = next((m for m in r.items if m.entry_id == chosen[0]), None)
            return self._add_entries(s, [(self.menu.get(chosen[0]), (m.qty if m and m.qty else qty) or 1,
                                          m.option_id if m else None, m.note if m else "")])
        if r.no or r.intent == "cancel":
            s.pending = None
            return self._reply(s, f"Dạ vâng. {self._cap(self.cp)} muốn dùng món gì khác ạ?", intent="clarify_cancel")
        if r.intent in ("add", "checkout", "ask_recommend", "ask_menu", "ask_promo", "view_cart", "preference"):
            s.pending = None
            return None  # khách chuyển ý -> xử lý bình thường
        return self._ask_clarify(s, cands, pend.get("qty", 1), "")

    def _add_generic(self, s: Session, r: NLUResult) -> Reply:
        g = r.generic[0]
        if len(g.candidates) == 1:
            return self._add_entries(s, [(self.menu.get(g.candidates[0]), g.qty or 1, None, "")])
        return self._ask_clarify(s, g.candidates, g.qty or 1, g.head)

    def _add_more(self, s: Session, r: NLUResult) -> Reply:
        if s.last_entry:
            return self._add_entries(s, [(self.menu.get(s.last_entry), r.qty or 1, None, "")])
        return self._unknown(s, r)

    def _select(self, s: Session, r: NLUResult) -> Reply:
        """'lấy món thứ hai', 'món đó', 'lấy luôn'."""
        target = None
        if r.ordinal is not None and s.last_recs:
            idx = r.ordinal - 1 if r.ordinal > 0 else len(s.last_recs) - 1
            if 0 <= idx < len(s.last_recs):
                target = s.last_recs[idx]
        elif r.deictic:
            target = s.last_entry or (s.last_recs[0] if s.last_recs else None)
            if "combo" in r.norm or "côm bô" in r.norm:  # "lấy combo đó" -> combo vừa gợi ý
                target = next((x for x in s.last_recs if self.menu.get(x).kind == "combo"), target)
            elif any(w in r.norm.split() for w in ("ly", "cốc", "chai", "lon")):
                target = next((x for x in s.last_recs if self.menu.get(x).is_drink), target)
        if not target and r.generic:
            return self._add_generic(s, r)
        if not target:
            return self._reply(s, f"Dạ, {self.cp} muốn chọn món nào ạ? {self._cap(self.cp)} có thể nói tên món giúp {self.sp} nhé.",
                               intent="select")
        return self._add_entries(s, [(self.menu.get(target), r.qty or 1, None, "")], intent="select")

    def _remove(self, s: Session, r: NLUResult) -> Reply:
        done, missing = [], []
        for m in r.items:
            e = self.menu.get(m.entry_id)
            n = s.cart.remove(e.id, m.qty)
            (done if n else missing).append(self._qty_name(n, e) if n else e.name)
        s.state = "ordering"
        parts = []
        if done:
            parts.append(f"Dạ, {self.sp} đã bỏ " + ", ".join(done) + " khỏi đơn.")
        if missing:
            parts.append("Trong đơn chưa có " + ", ".join(missing) + " ạ.")
        if s.cart.is_empty:
            parts.append(f"Đơn hiện đang trống, {self.cp} muốn dùng món gì ạ?")
        else:
            parts.append(f"{self._cap(self.cp)} cần gì thêm không ạ?")
            s.pending = {"type": "anything_else"}
        return self._reply(s, " ".join(parts), intent="remove")

    def _remove_generic(self, s: Session, r: NLUResult) -> Reply:
        g = r.generic[0]
        in_cart = [c for c in g.candidates if s.cart.has(c)]
        if len(in_cart) == 1:
            s.cart.remove(in_cart[0], g.qty)
            return self._reply(s, f"Dạ, {self.sp} đã bỏ {self.menu.get(in_cart[0]).name} khỏi đơn ạ.", intent="remove")
        if not in_cart:
            return self._reply(s, f"Dạ, trong đơn chưa có món {g.head} nào ạ.", intent="remove")
        return self._ask_clarify(s, in_cart, g.qty or 1, g.head, remove=True)

    def _set_qty(self, s: Session, r: NLUResult) -> Reply:
        m = r.items[0]
        e = self.menu.get(m.entry_id)
        q = r.target_qty or 1
        if not s.cart.has(e.id):
            return self._add_entries(s, [(e, q, m.option_id, m.note)])
        s.cart.set_qty(e.id, q)
        return self._reply(s, f"Dạ, {self.sp} đã sửa {e.name} thành {q} {getattr(e, 'unit', 'phần')} ạ.", intent="set_qty")

    def _swap(self, s: Session, r: NLUResult) -> Reply:
        a, b = r.items[0], r.items[1]
        qty = s.cart.qty_of(a.entry_id) or a.qty or 1
        s.cart.remove(a.entry_id)
        ea, eb = self.menu.get(a.entry_id), self.menu.get(b.entry_id)
        s.cart.add(eb, b.qty or qty, None, b.note)
        s.last_entry = eb.id
        return self._reply(s, f"Dạ, {self.sp} đã đổi {ea.name} thành {self._qty_name(b.qty or qty, eb)} ạ.", intent="swap")

    # ================================================================== gợi ý
    def _recommend(self, s: Session, r: NLUResult) -> Reply:
        new = r.prefs
        if r.intent == "ask_category" and r.generic:
            new = new.merge(Preferences(categories={self.menu.get(r.generic[0].candidates[0]).category}))
        if new.is_empty() and s.prefs.is_empty() and not s.asked_pref:
            s.asked_pref = True
            s.state = "asking_pref"
            text = (f"Dạ, để {self.sp} gợi ý đúng ý, {self.cp} cho {self.sp} hỏi chút: {self.cp} thích món nước hay món khô, "
                    f"thích vị cay, chua ngọt hay thanh đạm, có kiêng gì không ạ (ví dụ ăn chay, không ăn bò, dị ứng hải sản)? "
                    f"Và {self.cp} đi mấy người ạ?")
            return self._reply(s, text, intent="ask_pref",
                               suggestions=["Cay cay", "Thanh đạm", "Ăn chay", "Đi 2 người", "Gì cũng được"])
        s.prefs = s.prefs.merge(new)
        s.state = "ordering"
        return self._present_recs(s)

    def _pref_answer(self, s: Session, r: NLUResult) -> Reply | None:
        if r.intent == "add_generic" and not r.prefs.is_empty():
            pass  # "thích phở, ăn cay" -> vẫn là trả lời khẩu vị
        elif r.intent in ("add", "add_generic", "checkout", "cancel", "view_cart", "ask_promo", "ask_menu", "select"):
            s.state = "ordering"
            return None
        s.state = "ordering"
        if not r.prefs.is_empty():
            s.prefs = s.prefs.merge(r.prefs)
        return self._present_recs(s)

    def _present_recs(self, s: Session) -> Reply:
        now = self.now_fn()
        recs = self.rec.recommend(s.prefs, s.cart, now=now, avoid=s.last_recs)
        if not recs:
            s.prefs = Preferences(vegetarian=s.prefs.vegetarian, exclude=s.prefs.exclude)
            recs = self.rec.recommend(s.prefs, s.cart, now=now)
            if not recs:
                return self._reply(s, f"Dạ, tiếc quá, hiện chưa có món nào phù hợp yêu cầu của {self.cp}. "
                                      f"{self._cap(self.cp)} xem thực đơn trên màn hình giúp {self.sp} nhé.", intent="recommend")
            lead = f"Dạ, chưa có món đúng hết yêu cầu, {self.sp} gợi ý {self.cp} mấy món gần nhất:"
        elif self.rec.unmet_tastes(s.prefs, recs):
            miss = " và ".join(self.rec.unmet_tastes(s.prefs, recs))
            lead = (f"Dạ, món vị {miss} hợp với yêu cầu còn lại của {self.cp} thì quán chưa có, "
                    f"{self.sp} gợi ý mấy món gần nhất:")
        else:
            lead = self._pick(s, f"Dạ, theo khẩu vị của {self.cp}, {self.sp} gợi ý:",
                              f"Dạ, {self.sp} nghĩ {self.cp} sẽ thích:")
        s.last_recs = [x.entry_id for x in recs]
        s.last_entry = recs[0].entry_id
        lines, spoken = [], []
        ordinal = ["Một", "Hai", "Ba", "Bốn", "Năm", "Sáu"]
        for i, x in enumerate(recs):
            why = ", ".join(x.reasons[:3])
            lines.append(f"{i + 1}. {x.name} - {format_money(x.price)}" + (f" ({why})" if why else ""))
            spoken.append(f"{ordinal[i]}, {x.name}, {format_money(x.price)}" + (f", {x.reasons[0]}" if x.reasons else ""))
        promo = next((x for x in recs if x.promos), None)
        tail = f"{self._cap(self.cp)} chọn món nào ạ? Có thể nói \"lấy món thứ nhất\"."
        promo_txt = f" {promo.name} đang có ưu đãi \"{promo.promos[0]}\" ạ." if promo else ""
        text = lead + "\n" + "\n".join(lines) + "\n" + promo_txt.strip() + ("\n" if promo_txt else "") + tail
        say = lead + " " + ". ".join(spoken) + "." + promo_txt + " " + f"{self._cap(self.cp)} chọn món nào ạ?"
        return self._reply(s, text, say, intent="recommend", recommendations=[x.to_dict() for x in recs],
                           suggestions=["Lấy món thứ nhất", "Lấy món thứ hai", "Gợi ý món khác"])

    # ================================================================== hỏi đáp
    def _menu(self, s: Session, r: NLUResult) -> Reply:
        cats = ", ".join(c.name for c in self.menu.categories)
        best = [e.name for e in self.menu.entries() if e.best_seller][:3]
        text = (f"Dạ, quán có các nhóm món: {cats}" + (f" và {len(self.menu.combos)} combo tiết kiệm" if self.menu.combos else "")
                + ". " + (f"Món bán chạy nhất là {', '.join(best)}. " if best else "")
                + f"Thực đơn đầy đủ đang hiện trên màn hình, {self.cp} muốn dùng món gì ạ?")
        return self._reply(s, text, intent="ask_menu", suggestions=["Gợi ý món ngon", "Combo", "Đồ uống"])

    def _promos(self, s: Session, r: NLUResult) -> Reply:
        ps = self.engine.active(self.now_fn())
        if not ps:
            return self._reply(s, f"Dạ, hiện tại quán chưa có chương trình ưu đãi nào ạ. {self._cap(self.cp)} muốn dùng món gì ạ?",
                               intent="ask_promo")
        for p in ps:
            s.announced.add(p.id)
        lines = [f"- {p.name}: {p.pitch}" if p.pitch else f"- {p.name}" for p in ps]
        say = "; ".join(p.pitch or p.name for p in ps)
        text = "Dạ, hôm nay quán đang có các ưu đãi:\n" + "\n".join(lines) + f"\nHệ thống tự áp dụng ưu đãi có lợi nhất cho {self.cp} ạ."
        return self._reply(s, text, f"Dạ, hôm nay quán đang có: {say}. Hệ thống sẽ tự áp dụng ưu đãi có lợi nhất cho {self.cp} ạ.",
                           intent="ask_promo")

    def _price(self, s: Session, r: NLUResult) -> Reply:
        parts = []
        for m in r.items:
            e = self.menu.get(m.entry_id)
            parts.append(f"{e.name} giá {format_money(e.price)}" + (f" một {e.unit}" if getattr(e, 'unit', '') else ""))
            s.last_entry = e.id
        promos = [p for m in r.items for p in self.engine.promos_for_entry(m.entry_id, self.now_fn())]
        extra = f" Món này đang có ưu đãi \"{promos[0].name}\" ạ." if promos else ""
        s.pending = {"type": "upsell", "entry_id": s.last_entry}
        return self._reply(s, "Dạ, " + "; ".join(parts) + " ạ." + extra + f" {self._cap(self.cp)} có muốn gọi không ạ?",
                           intent="ask_price")

    def _info(self, s: Session, r: NLUResult) -> Reply:
        e = self.menu.get(r.items[0].entry_id)
        s.last_entry = e.id
        facts = []
        if e.taste.cay >= 2:
            facts.append("món này khá cay")
        elif e.taste.cay == 1:
            facts.append("món này hơi cay nhẹ")
        elif "cay" in r.norm:
            facts.append("món này không cay")
        if e.is_vegetarian:
            facts.append("là món chay")
        elif "chay" in r.norm:
            facts.append("món này không phải món chay")
        if e.kind == "combo":
            facts.append(f"phù hợp cho {e.serves} người")  # type: ignore[union-attr]
        desc = getattr(e, "description", "")
        text = f"Dạ, {e.name} giá {format_money(e.price)}" + (f": {desc}" if desc else "") + "."
        if facts:
            text += " " + self._cap(", ".join(facts)) + " ạ."
        text += f" {self._cap(self.cp)} có muốn gọi món này không ạ?"
        s.pending = {"type": "upsell", "entry_id": e.id}
        return self._reply(s, text, intent="ask_info")

    def _view_cart(self, s: Session, r: NLUResult | None) -> Reply:
        if s.cart.is_empty:
            return self._reply(s, f"Dạ, đơn của {self.cp} hiện chưa có món nào ạ.", intent="view_cart")
        pb = self.engine.price(s.cart, self.now_fn())
        items = ", ".join(self._qty_name(ln.qty, name=ln.display_name, unit=ln.unit) for ln in s.cart.lines)
        price_text, price_say = self._price_line(pb)
        text = f"Dạ, đơn của {self.cp} gồm: {items}.\n{price_text}"
        return self._reply(s, text, f"Dạ, đơn của {self.cp} gồm: {items}. {price_say}.", intent="view_cart",
                           suggestions=["Chốt đơn", "Gợi ý thêm"])

    # ================================================================== chốt đơn & thanh toán
    def _checkout(self, s: Session, r: NLUResult | None, prefix: str = "") -> Reply:
        if r is not None and r.intent == "pay_cash":
            s.payment_method = "cash" if self.store.payment.allow_cash else "vietqr"
        elif r is not None and r.intent == "pay_qr":
            s.payment_method = "vietqr"
        if s.cart.is_empty:
            s.state = "ordering"
            return self._reply(s, f"Dạ, {self.cp} chưa chọn món nào. {self._cap(self.cp)} muốn dùng món gì, hay để {self.sp} gợi ý ạ?",
                               intent="checkout", suggestions=["Gợi ý món ngon", "Xem thực đơn"])
        pb = self.engine.price(s.cart, self.now_fn())
        items = ", ".join(self._qty_name(ln.qty, name=ln.display_name, unit=ln.unit) for ln in s.cart.lines)
        price_text, price_say = self._price_line(pb)
        s.state = "confirm_order"
        s.pending = None
        how = ""
        if self.store.payment.allow_cash and s.payment_method is None:
            how = f" {self._cap(self.cp)} thanh toán quét mã QR hay tiền mặt ạ?"
        elif s.payment_method == "cash":
            how = f" {self._cap(self.cp)} thanh toán tiền mặt tại quầy, {self.sp} xác nhận đơn nhé?"
        else:
            how = f" {self._cap(self.cp)} xác nhận để {self.sp} tạo mã QR thanh toán nhé?"
        takeaway = " (mang về)" if s.takeaway else ""
        head = (prefix + " ") if prefix else ""
        text = f"{head}Dạ, {self.sp} xin đọc lại đơn{takeaway}: {items}.\n{price_text}\n{how.strip()}"
        say = f"{head}Dạ, {self.sp} xin đọc lại đơn: {items}. {price_say}.{how}"
        sugg = ["Quét mã QR", "Tiền mặt", "Sửa đơn"] if self.store.payment.allow_cash else ["Xác nhận", "Sửa đơn"]
        return self._reply(s, text, say, intent="checkout", suggestions=sugg)

    def _confirming(self, s: Session, r: NLUResult) -> Reply | None:
        if r.intent == "pay_cash" or (r.yes and s.payment_method == "cash"):
            return self._place_order(s, "cash" if self.store.payment.allow_cash else "vietqr")
        if r.intent in ("pay_qr", "checkout") or r.yes:
            return self._place_order(s, "vietqr")
        if r.no:
            s.state = "ordering"
            return self._reply(s, f"Dạ vâng, {self.cp} muốn sửa gì trong đơn ạ? Có thể nói \"thêm\", \"bỏ\" hoặc \"đổi\" món.",
                               intent="edit_order")
        if r.intent in ("add", "add_generic", "remove", "set_qty", "swap", "cancel", "ask_recommend", "ask_promo",
                        "view_cart", "select", "preference", "ask_info", "ask_price", "ask_menu"):
            s.state = "ordering"
            return None
        return self._reply(s, f"Dạ, {self.cp} xác nhận đơn này chứ ạ? Nói \"đúng rồi\" để thanh toán bằng mã QR"
                           + (", hoặc \"tiền mặt\"" if self.store.payment.allow_cash else "") + " ạ.", intent="confirm_order",
                           suggestions=["Đúng rồi", "Tiền mặt", "Sửa đơn"] if self.store.payment.allow_cash else ["Đúng rồi", "Sửa đơn"])

    def _place_order(self, s: Session, method: str) -> Reply:
        pb = self.engine.price(s.cart, self.now_fn())
        pay = self.store.payment
        items = s.cart.to_list() + [
            {"entry_id": f.entry_id, "name": f.name, "display_name": f"{f.name} (tặng)", "kind": "gift", "unit_price": 0,
             "qty": f.qty, "total": 0, "note": "quà tặng"} for f in pb.free_items
        ]
        if self.storage:
            order = self.storage.create_order(
                self.store.id, self.store.kiosk_no, pay.order_prefix, items, [a.to_dict() for a in pb.applied],
                pb.subtotal, pb.discount, pb.vat, pb.total, payment_method=method,
                expire_minutes=pay.qr_expire_minutes, session_id=s.id,
            )
            code, expires = order.code, (datetime.fromisoformat(order.expires_at) if order.expires_at else None)
        else:  # chạy thử không có DB
            code = f"{pay.order_prefix}{self.store.kiosk_no:02d}{int(time.time()) % 1_000_000:06d}"
            expires = datetime.now(timezone.utc) + timedelta(minutes=pay.qr_expire_minutes) if method == "vietqr" else None
        s.order_code, s.order_total, s.order_expires, s.payment_method = code, pb.total, expires, method
        order_info = {"code": code, "total": pb.total, "method": method, "items": items,
                      "expires_at": expires.isoformat() if expires else None, "takeaway": bool(s.takeaway)}
        short_no = str(int(code[-6:]))
        if method == "cash":
            s.state = "awaiting_cash"
            text = (f"Dạ, {self.sp} đã tạo đơn {code}. Mời {self.cp} thanh toán {format_money(pb.total)} bằng tiền mặt tại quầy. "
                    f"Số thứ tự của {self.cp} là {short_no} ạ.")
            return self._reply(s, text, intent="order_cash", order=order_info)
        payload = vietqr.build_payload(pay.bank_bin, pay.account_number, pb.total, code)
        if self.storage:
            self.storage.set_qr(code, payload)
        qr = {
            "payload": payload, "svg": vietqr.to_svg(payload, scale=8), "amount": pb.total, "code": code,
            "bank_name": pay.bank_name, "bank_bin": pay.bank_bin, "account_number": pay.account_number,
            "account_name": pay.account_name, "expires_at": order_info["expires_at"],
        }
        s.state = "awaiting_payment"
        text = (f"Dạ, {self.sp} đã tạo đơn {code}. Mời {self.cp} mở app ngân hàng quét mã QR trên màn hình để thanh toán "
                f"{format_money(pb.total)}, nội dung chuyển khoản {code} đã có sẵn trong mã. Mã có hiệu lực {pay.qr_expire_minutes} phút ạ.")
        say = (f"Dạ, mời {self.cp} quét mã QR trên màn hình để thanh toán {format_money(pb.total)}. "
               f"Nội dung chuyển khoản đã có sẵn trong mã ạ.")
        return self._reply(s, text, say, intent="order_qr", qr=qr, order=order_info, suggestions=["Trả tiền mặt", "Huỷ đơn"])

    def _during_payment(self, s: Session, r: NLUResult) -> Reply:
        if r.intent == "pay_cash" and self.store.payment.allow_cash:
            if self.storage and s.order_code:
                self.storage.set_status(s.order_code, "cancelled")
            return self._place_order(s, "cash")
        if r.intent == "cancel":
            return self._cancel(s)
        if r.intent in ("add", "add_generic", "remove", "set_qty", "swap") or (r.no and not r.items):
            if self.storage and s.order_code:
                self.storage.set_status(s.order_code, "cancelled")
            s.order_code, s.state = None, "ordering"
            if r.intent in ("add", "add_generic", "remove", "set_qty", "swap"):
                rep = self._dispatch(s, r)
                rep.text = f"Dạ, {self.sp} huỷ mã QR cũ để sửa đơn. " + rep.text
                return rep
            return self._reply(s, f"Dạ, {self.sp} đã huỷ mã QR cũ. {self._cap(self.cp)} muốn sửa gì trong đơn ạ?", intent="edit_order")
        return self._reply(s, f"Dạ, {self.sp} đang chờ ngân hàng xác nhận thanh toán {format_money(s.order_total)} cho đơn {s.order_code}. "
                              f"{self._cap(self.cp)} quét mã QR trên màn hình giúp {self.sp} nhé.", intent="awaiting_payment",
                           suggestions=["Trả tiền mặt", "Huỷ đơn"])

    def payment_received(self, s: Session, amount: int | None = None) -> Reply:
        s.state = "done"
        no = str(int(s.order_code[-6:])) if s.order_code else ""
        paid = format_money(amount if amount is not None else s.order_total)
        text = (f"Dạ, quán đã nhận được {paid}. Cảm ơn {self.cp}! Đơn số {no} đang được chuẩn bị, "
                f"{self.cp} vui lòng chờ trong giây lát ạ. Chúc {self.cp} ngon miệng!")
        r = self._reply(s, text, intent="paid", order={"code": s.order_code, "total": s.order_total, "status": "paid"})
        r.end = True
        return r

    def tick(self, s: Session, now_ts: float | None = None) -> Reply | None:
        """Gọi định kỳ (mỗi vài giây): hết hạn QR, khách bỏ đi giữa chừng."""
        now_ts = now_ts or time.time()
        if s.state == "awaiting_payment" and s.order_expires and datetime.now(timezone.utc) > s.order_expires:
            if self.storage and s.order_code:
                self.storage.set_status(s.order_code, "expired")
            s.state = "confirm_order"
            s.order_code = None
            return self._reply(s, f"Dạ, mã QR đã hết hạn. {self._cap(self.cp)} muốn {self.sp} tạo mã mới không ạ?", intent="qr_expired",
                               suggestions=["Tạo mã mới", "Tiền mặt", "Huỷ đơn"])
        idle = now_ts - s.updated_at
        if s.state not in ("idle", "awaiting_payment", "awaiting_cash") and idle > self.a.idle_reset_seconds:
            self.reset(s)
            r = self._reply(s, "Phiên đã kết thúc do không có tương tác. Mời quý khách tiếp theo!", intent="timeout")
            r.end = True
            return r
        return None

    def _cancel(self, s: Session, r: NLUResult | None = None) -> Reply:
        if self.storage and s.order_code:
            self.storage.set_status(s.order_code, "cancelled")
        self.reset(s)
        s.state = "ordering"
        return self._reply(s, f"Dạ, {self.sp} đã huỷ đơn. {self._cap(self.cp)} muốn gọi lại từ đầu không ạ?", intent="cancel",
                           suggestions=["Gợi ý món ngon", "Xem thực đơn"])

    # ================================================================== xã giao & dự phòng
    def _answer_pending(self, s: Session, r: NLUResult) -> Reply:
        pend = s.pending or {}
        s.pending = None
        if pend.get("type") == "upsell":
            if r.yes:
                return self._add_entries(s, [(self.menu.get(pend["entry_id"]), r.qty or 1, None, "")])
            return self._reply(s, f"Dạ vâng. {self._cap(self.cp)} cần thêm gì nữa không ạ?", intent="no",
                               suggestions=["Chốt đơn", "Gợi ý thêm"]) if not s.cart.is_empty else \
                self._reply(s, f"Dạ vâng. {self._cap(self.cp)} muốn dùng món gì ạ?", intent="no")
        if r.no:  # "cần thêm gì nữa không?" -> "không" => chốt đơn
            return self._checkout(s, r)
        return self._reply(s, f"Dạ, {self.cp} muốn thêm món gì ạ?", intent="yes", suggestions=["Gợi ý thêm", "Đồ uống"])

    def _yes_no(self, s: Session, r: NLUResult) -> Reply:
        if r.yes and s.last_entry and not s.cart.has(s.last_entry) and s.last_recs:
            return self._add_entries(s, [(self.menu.get(s.last_entry), 1, None, "")])
        if r.no and not s.cart.is_empty:
            return self._checkout(s, r)
        return self._reply(s, f"Dạ, {self.cp} muốn dùng món gì ạ? {self._cap(self.sp)} có thể gợi ý món ngon nếu {self.cp} cần.",
                           intent=r.intent, suggestions=["Gợi ý món ngon", "Xem thực đơn"])

    def _repeat(self, s: Session, r: NLUResult) -> Reply:
        rep = self._reply(s, s.last_text or "Dạ, em xin nhắc lại.", intent="repeat")
        rep.speech = s.last_speech or rep.speech
        return rep

    def _thanks(self, s: Session, r: NLUResult) -> Reply:
        return self._reply(s, f"Dạ, không có gì ạ. {self._cap(self.cp)} cần thêm gì cứ nói với {self.sp} nhé.", intent="thanks")

    def _goodbye(self, s: Session, r: NLUResult) -> Reply:
        rep = self._reply(s, f"Dạ, cảm ơn {self.cp}, hẹn gặp lại {self.cp} ạ!", intent="goodbye")
        if s.cart.is_empty:
            rep.end = True
            self.reset(s)
        return rep

    def _greet_again(self, s: Session, r: NLUResult) -> Reply:
        return self._reply(s, f"Dạ, {self.sp} chào {self.cp}! {self._cap(self.cp)} muốn gọi món gì ạ?", intent="greet",
                           suggestions=["Gợi ý món ngon", "Xem thực đơn"])

    def _help(self, s: Session, r: NLUResult) -> Reply:
        text = (f"Dạ, {self.cp} cứ nói tự nhiên, ví dụ: \"cho tôi hai phở bò tái\", \"gợi ý món cay\", \"bỏ trà đá\", "
                f"\"có khuyến mãi gì không\", hoặc \"chốt đơn\". {self._cap(self.cp)} cũng có thể bấm chọn món trên màn hình ạ.")
        return self._reply(s, text, intent="help")

    def _unknown(self, s: Session, r: NLUResult) -> Reply:
        s.misses += 1
        if s.misses >= 3:
            text = (f"Dạ, xin lỗi {self.cp}, {self.sp} vẫn chưa hiểu ý. {self._cap(self.cp)} có thể bấm chọn món trên màn hình, "
                    f"hoặc gọi nhân viên hỗ trợ ạ.")
        else:
            text = self._pick(
                s,
                f"Dạ, {self.sp} chưa nghe rõ. {self._cap(self.cp)} nói tên món giúp {self.sp}, ví dụ \"cho tôi một phở bò tái\", "
                f"hoặc nói \"gợi ý\" để {self.sp} giới thiệu món ngon nhé.",
                f"Dạ, {self.cp} nói lại giúp {self.sp} được không ạ? Ví dụ \"cho hai cơm tấm\" hoặc \"có món gì ngon\".",
            )
        return self._reply(s, text, intent="unknown", suggestions=["Gợi ý món ngon", "Xem thực đơn", "Chốt đơn"])

    # ================================================================== thao tác chạm (màn hình cảm ứng)
    def handle_action(self, s: Session, action: dict) -> Reply:
        """Màn hình cảm ứng và giọng nói dùng chung 1 trạng thái phiên."""
        t0 = time.perf_counter()
        s.updated_at = time.time()
        kind = action.get("type")
        if s.state in ("idle", "done") and kind not in ("reset",):
            if s.state == "done":
                self.reset(s)
            s.state = "ordering"
        if s.state == "awaiting_payment" and kind in ("add", "remove", "set_qty"):
            if self.storage and s.order_code:
                self.storage.set_status(s.order_code, "cancelled")
            s.order_code, s.state = None, "ordering"
        if s.state == "confirm_order" and kind in ("add", "remove", "set_qty"):
            s.state = "ordering"
        fake = NLUResult(text=f"[{kind}]", norm="", intent=f"action:{kind}", confidence=1.0)
        if kind == "add":
            e = self.menu.get(action["entry_id"])
            reply = self._add_entries(s, [(e, int(action.get("qty", 1)), action.get("option_id"), action.get("note", ""))],
                                      intent="action_add")
        elif kind == "remove":
            e = self.menu.get(action["entry_id"])
            s.cart.remove(e.id, action.get("qty"))
            reply = self._reply(s, f"Dạ, {self.sp} đã bỏ {e.name}.", intent="action_remove")
        elif kind == "set_qty":
            e = self.menu.get(action["entry_id"])
            s.cart.set_qty(e.id, int(action["qty"]))
            reply = self._reply(s, f"Dạ, {e.name}: {int(action['qty'])} {getattr(e, 'unit', 'phần')}.", intent="action_set_qty")
        elif kind == "checkout":
            reply = self._checkout(s, None)
        elif kind == "confirm":
            method = action.get("method", "vietqr")
            if s.cart.is_empty:
                reply = self._checkout(s, None)
            else:
                reply = self._place_order(s, "cash" if (method == "cash" and self.store.payment.allow_cash) else "vietqr")
        elif kind == "recommend":
            reply = self._present_recs(s)
        elif kind == "cancel":
            reply = self._cancel(s)
        elif kind == "greet":
            self.reset(s)
            reply = self.greet(s)
        elif kind == "reset":
            self.reset(s)
            reply = self._reply(s, "", intent="reset")
        else:
            reply = self._reply(s, "", intent="noop")
        return self._finish(s, reply, fake, t0)
