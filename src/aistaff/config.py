"""Đọc + kiểm tra cấu hình quán (store.yaml, menu.yaml, promotions.yaml).

Tất cả cấu hình được validate bằng pydantic khi khởi động -> lỗi cấu hình (giá âm, combo trỏ
tới món không tồn tại, mã BIN sai...) bị phát hiện ngay chứ không lỗi giữa lúc khách đang gọi món.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

TASTES = ("cay", "ngot", "chua", "dam", "beo")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class _Base(BaseModel):
    model_config = {"extra": "forbid"}


# ----------------------------------------------------------------------------- menu
class Taste(_Base):
    cay: int = Field(0, ge=0, le=3)
    ngot: int = Field(0, ge=0, le=3)
    chua: int = Field(0, ge=0, le=3)
    dam: int = Field(0, ge=0, le=3)
    beo: int = Field(0, ge=0, le=3)

    def get(self, name: str) -> int:
        return int(getattr(self, name))


class Option(_Base):
    id: str
    name: str
    price_delta: int = 0
    aliases: list[str] = []


class Category(_Base):
    id: str
    name: str
    aliases: list[str] = []


class MenuItem(_Base):
    id: str
    name: str
    aliases: list[str] = []
    category: str
    price: int = Field(ge=0)
    unit: str = "phần"
    description: str = ""
    taste: Taste = Taste()
    style: Literal["nuoc", "kho", "uong", "trang_mieng", "an_kem"] = "kho"
    temp: Literal["nong", "lanh"] = "nong"
    portion: Literal["lon", "vua", "nhe"] = "vua"
    contains: list[str] = []
    diet: list[str] = []
    allergens: list[str] = []
    best_seller: bool = False
    boost: int = Field(0, ge=-2, le=2)
    available: bool = True
    pairs_with: list[str] = []
    options: list[Option] = []

    @property
    def kind(self) -> str:
        return "item"

    @property
    def is_vegetarian(self) -> bool:
        return "chay" in self.diet

    @property
    def is_drink(self) -> bool:
        return self.style == "uong"


class ComboPart(_Base):
    item: str
    qty: int = Field(1, ge=1)


class Combo(_Base):
    id: str
    name: str
    aliases: list[str] = []
    price: int = Field(ge=0)
    serves: int = Field(1, ge=1)
    description: str = ""
    items: list[ComboPart]
    best_seller: bool = False
    boost: int = Field(0, ge=-2, le=2)
    available: bool = True
    unit: str = "phần"
    # Các trường dưới được tính tự động từ món con (xem Menu._derive_combo)
    taste: Taste = Taste()
    contains: list[str] = []
    diet: list[str] = []
    category: str = "combo"
    style: str = "combo"
    temp: str = "nong"
    portion: str = "lon"
    pairs_with: list[str] = []
    options: list[Option] = []

    @property
    def kind(self) -> str:
        return "combo"

    @property
    def is_vegetarian(self) -> bool:
        return "chay" in self.diet

    @property
    def is_drink(self) -> bool:
        return False


Entry = MenuItem | Combo


class Menu(_Base):
    categories: list[Category]
    items: list[MenuItem]
    combos: list[Combo] = []

    @model_validator(mode="after")
    def _check(self) -> "Menu":
        cat_ids = {c.id for c in self.categories}
        seen: set[str] = set()
        for e in [*self.items, *self.combos]:
            if e.id in seen:
                raise ValueError(f"Trùng id món: {e.id}")
            seen.add(e.id)
        item_ids = {i.id for i in self.items}
        for it in self.items:
            if it.category not in cat_ids:
                raise ValueError(f"Món {it.id}: category '{it.category}' không tồn tại")
            for p in it.pairs_with:
                if p not in seen:
                    raise ValueError(f"Món {it.id}: pairs_with '{p}' không tồn tại")
        for c in self.combos:
            for part in c.items:
                if part.item not in item_ids:
                    raise ValueError(f"Combo {c.id}: món '{part.item}' không tồn tại")
            self._derive_combo(c)
        return self

    def _derive_combo(self, c: Combo) -> None:
        parts = [(self.item(p.item), p.qty) for p in c.items]
        foods = [it for it, _ in parts if not it.is_drink] or [it for it, _ in parts]
        c.taste = Taste(**{t: max(it.taste.get(t) for it in foods) for t in TASTES})
        contains: list[str] = []
        for it, _ in parts:
            for x in it.contains:
                if x not in contains:
                    contains.append(x)
        c.contains = contains
        c.diet = ["chay"] if all(it.is_vegetarian for it, _ in parts) else []

    # --------------------------------------------------------------- lookup
    def item(self, item_id: str) -> MenuItem:
        for it in self.items:
            if it.id == item_id:
                return it
        raise KeyError(item_id)

    def get(self, entry_id: str) -> Entry:
        for e in [*self.items, *self.combos]:
            if e.id == entry_id:
                return e
        raise KeyError(entry_id)

    def entries(self, available_only: bool = True) -> list[Entry]:
        es: list[Entry] = [*self.items, *self.combos]
        return [e for e in es if e.available] if available_only else es

    def category(self, cat_id: str) -> Category | None:
        return next((c for c in self.categories if c.id == cat_id), None)

    def combo_value(self, c: Combo) -> int:
        """Tổng giá lẻ của các món trong combo (để tính 'tiết kiệm được bao nhiêu')."""
        return sum(self.item(p.item).price * p.qty for p in c.items)


# ----------------------------------------------------------------------------- promotions
class Schedule(_Base):
    days: list[str] = list(DAYS)
    start: str | None = None  # "HH:MM"
    end: str | None = None

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[str]) -> list[str]:
        bad = [d for d in v if d not in DAYS]
        if bad:
            raise ValueError(f"Ngày không hợp lệ {bad}, dùng {DAYS}")
        return v

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str | None) -> str | None:
        if v is None:
            return v
        h, m = v.split(":")
        if not (0 <= int(h) <= 24 and 0 <= int(m) < 60):
            raise ValueError(f"Giờ không hợp lệ: {v}")
        return v


class PromoTarget(_Base):
    items: list[str] = []
    categories: list[str] = []
    combos: list[str] | Literal["all"] = []


class PromoQty(_Base):
    item: str
    qty: int = Field(1, ge=1)


class Promotion(_Base):
    id: str
    name: str
    type: Literal[
        "percent_off_order",
        "amount_off_order",
        "percent_off_items",
        "amount_off_items",
        "buy_x_get_y",
        "free_item",
    ]
    value: float = 0
    min_subtotal: int = 0
    max_discount: int | None = None
    targets: PromoTarget = PromoTarget()
    buy: PromoQty | None = None
    get: PromoQty | None = None
    reward: Literal["free_added", "discount_in_cart"] = "free_added"
    schedule: Schedule | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    stackable: bool = False
    priority: int = 0
    announce: bool = True
    active: bool = True
    hint_within: int = 0
    pitch: str = ""

    @model_validator(mode="after")
    def _check(self) -> "Promotion":
        if self.type.startswith("percent") and not (0 < self.value <= 100):
            raise ValueError(f"Ưu đãi {self.id}: value phải trong (0, 100]")
        if self.type.startswith("amount") and self.value <= 0:
            raise ValueError(f"Ưu đãi {self.id}: value phải > 0")
        if self.type == "buy_x_get_y" and not (self.buy and self.get):
            raise ValueError(f"Ưu đãi {self.id}: cần buy và get")
        if self.type == "free_item" and not self.get:
            raise ValueError(f"Ưu đãi {self.id}: cần get")
        return self


class Promotions(_Base):
    promotions: list[Promotion] = []


# ----------------------------------------------------------------------------- store
class Assistant(_Base):
    name: str = "Mai"
    self_pronoun: str = "em"
    customer_pronoun: str = "quý khách"
    max_recommendations: int = Field(3, ge=1, le=6)
    upsell: bool = True
    announce_promotions: bool = True
    idle_reset_seconds: int = 90


class Pricing(_Base):
    currency: Literal["VND"] = "VND"
    prices_include_vat: bool = True
    vat_percent: float = Field(0, ge=0, le=20)
    discount_rounding: int = Field(1000, ge=1)


class SePayCfg(_Base):
    webhook_api_key_env: str = "SEPAY_WEBHOOK_API_KEY"
    api_token_env: str = "SEPAY_API_TOKEN"
    poll_interval_seconds: float = 4
    api_url: str = "https://my.sepay.vn/userapi/transactions/list"


class Payment(_Base):
    bank_bin: str
    bank_name: str = ""
    account_number: str
    account_name: str = ""
    order_prefix: str = "DH"
    qr_expire_minutes: int = Field(10, ge=1, le=120)
    allow_cash: bool = True
    confirm_mode: Literal["manual", "sepay_webhook", "sepay_polling"] = "manual"
    sepay: SePayCfg = SePayCfg()

    @field_validator("bank_bin")
    @classmethod
    def _bin(cls, v: str) -> str:
        if not (v.isdigit() and len(v) == 6):
            raise ValueError("bank_bin phải là 6 chữ số (vd 970436 = Vietcombank)")
        return v

    @field_validator("account_number")
    @classmethod
    def _acc(cls, v: str) -> str:
        v = v.replace(" ", "")
        if not (v.isalnum() and 4 <= len(v) <= 19):
            raise ValueError("account_number phải gồm 4-19 ký tự chữ/số")
        return v

    @field_validator("order_prefix")
    @classmethod
    def _prefix(cls, v: str) -> str:
        if not (v.isascii() and v.isalpha() and 1 <= len(v) <= 4):
            raise ValueError("order_prefix: 1-4 chữ cái không dấu (vd DH)")
        return v.upper()


class Speech(_Base):
    enabled: bool = False
    models_dir: str = "models"
    asr_model: str = "sherpa-onnx-zipformer-vi-30M-int8-2026-02-09"
    tts_voice: str = "vits-piper-vi_VN-vais1000-medium"
    tts_speed: float = Field(1.0, gt=0.3, lt=3)
    num_threads: int = Field(2, ge=1, le=8)
    hotwords_score: float = 1.5
    vad_min_silence: float = 0.5


class LLMFallback(_Base):
    enabled: bool = False
    base_url: str = "http://127.0.0.1:8081/v1"
    model: str = "local"
    api_key_env: str = "LLM_API_KEY"
    timeout_seconds: float = 6


class Store(_Base):
    id: str
    name: str
    short_name: str = ""
    address: str = ""
    phone: str = ""
    timezone: str = "Asia/Ho_Chi_Minh"
    kiosk_no: int = Field(1, ge=0, le=99)
    assistant: Assistant = Assistant()
    pricing: Pricing = Pricing()
    payment: Payment
    speech: Speech = Speech()
    llm_fallback: LLMFallback = LLMFallback()

    @property
    def display_name(self) -> str:
        return self.short_name or self.name


class StoreConfig(BaseModel):
    """Toàn bộ cấu hình của 1 quán."""

    store: Store
    menu: Menu
    promotions: list[Promotion]
    base_dir: Path | None = None

    @model_validator(mode="after")
    def _check_promos(self) -> "StoreConfig":
        ids = {e.id for e in self.menu.entries(available_only=False)}
        cats = {c.id for c in self.menu.categories}
        combo_ids = {c.id for c in self.menu.combos}
        seen = set()
        for p in self.promotions:
            if p.id in seen:
                raise ValueError(f"Trùng id ưu đãi: {p.id}")
            seen.add(p.id)
            for ref in [p.buy, p.get]:
                if ref and ref.item not in ids:
                    raise ValueError(f"Ưu đãi {p.id}: món '{ref.item}' không tồn tại")
            for i in p.targets.items:
                if i not in ids:
                    raise ValueError(f"Ưu đãi {p.id}: món '{i}' không tồn tại")
            for c in p.targets.categories:
                if c not in cats:
                    raise ValueError(f"Ưu đãi {p.id}: nhóm '{c}' không tồn tại")
            if isinstance(p.targets.combos, list):
                for c in p.targets.combos:
                    if c not in combo_ids:
                        raise ValueError(f"Ưu đãi {p.id}: combo '{c}' không tồn tại")
        return self


def _read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_store(store_dir: str | Path) -> StoreConfig:
    """Đọc thư mục cấu hình quán: store.yaml + menu.yaml + promotions.yaml (tuỳ chọn)."""
    d = Path(store_dir)
    store = Store(**_read_yaml(d / "store.yaml"))
    menu = Menu(**_read_yaml(d / "menu.yaml"))
    promo_file = d / "promotions.yaml"
    promos = Promotions(**_read_yaml(promo_file)).promotions if promo_file.exists() else []
    return StoreConfig(store=store, menu=menu, promotions=promos, base_dir=d.resolve())
