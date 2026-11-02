"""NLU tiếng Việt cho gọi món: ý định (intent) + thực thể (món, số lượng, tuỳ chọn, khẩu vị...).

Thiết kế cho edge device:
- Luật + từ điển + so khớp mờ (rapidfuzz, viết bằng C++) -> ~1 ms/câu trên CPU ARM, không cần GPU/LLM.
- Chịu được lỗi ASR ("cầm tấm sườn" -> "cơm tấm sườn") và khách gõ không dấu ("pho bo tai").
- Tên món/alias lấy trực tiếp từ menu.yaml -> đổi menu không cần huấn luyện lại.
- Câu nào luật không chắc chắn (confidence thấp) có thể chuyển cho LLM dự phòng (llm.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from .config import Menu
from .textnorm import fold, has_diacritics, normalize, parse_number, strip_diacritics

# ============================================================================ từ điển
CLASSIFIERS = {
    "tô", "bát", "ly", "cốc", "phần", "suất", "đĩa", "dĩa", "chén", "chai", "lon", "cái", "miếng",
    "cuốn", "xiên", "hộp", "gói", "set", "cây", "ổ", "trái", "quả", "cặp", "phần ăn", "combo",
}
CLASSIFIERS_FOLD = {strip_diacritics(c) for c in CLASSIFIERS}
# Lỗi ASR hay gặp với số đếm (chỉ dùng khi đứng ngay trước lượng từ: "hài ly" -> 2 ly)
ASR_QTY_CONFUSIONS = {"hài": 2, "hải": 2, "hại": 2, "bà": 3, "bá": 3, "bổn": 4, "bộn": 4, "nắm": 5, "sấu": 6, "bẩy": 7}

TASTE_WORDS = {
    "cay": ["cay", "cay cay", "ớt", "spicy", "cay nồng"],
    "ngot": ["ngọt", "ngòn ngọt", "ngọt ngọt"],
    "chua": ["chua", "chua chua", "chua ngọt"],
    "dam": ["đậm đà", "đậm vị", "đậm", "mặn", "đậm đặc"],
    "beo": ["béo", "ngậy", "béo ngậy", "nhiều dầu mỡ"],
}
LIGHT_WORDS = ["thanh đạm", "nhẹ nhàng", "thanh mát", "thanh", "healthy", "ít dầu mỡ", "ít dầu", "không dầu mỡ",
               "ăn kiêng", "giảm cân", "eat clean", "ít béo", "không béo"]
NEGATORS = ["không ăn được", "không ăn", "không thích", "không uống", "không muốn", "không", "chẳng", "ít", "sợ",
            "kiêng", "kỵ", "dị ứng", "đừng", "bớt", "trừ"]
INGREDIENTS = {
    "bò": ["bò", "thịt bò", "beef"],
    "heo": ["heo", "lợn", "thịt heo", "thịt lợn", "sườn"],
    "gà": ["gà", "thịt gà", "chicken"],
    "hải sản": ["hải sản", "đồ biển", "seafood"],
    "tôm": ["tôm"],
    "cua": ["cua", "ghẹ"],
    "mực": ["mực"],
    "cá": ["cá"],
    "trứng": ["trứng"],
    "sữa": ["sữa", "lactose"],
    "đậu phộng": ["đậu phộng", "lạc", "đậu phụng"],
    "hành": ["hành", "hành lá"],
    "nấm": ["nấm"],
    "mắm tôm": ["mắm tôm"],
}
# "không ăn thịt" => coi như ăn chay
VEG_WORDS = ["ăn chay", "đồ chay", "món chay", "thuần chay", "chay", "vegan", "vegetarian", "không ăn thịt",
             "không thịt"]
STYLE_WORDS = {
    "nuoc": ["món nước", "có nước", "ăn nước", "đồ nước", "húp", "nước lèo", "nước dùng", "món súp"],
    "kho": ["món khô", "ăn khô", "đồ khô", "không có nước"],
}
TEMP_WORDS = {
    "nong": ["nóng", "ấm", "nóng hổi", "ấm bụng"],
    "lanh": ["mát", "lạnh", "giải nhiệt", "mát lạnh", "giải khát", "đá"],
}
HUNGRY_WORDS = ["đói", "đói bụng", "ăn no", "no bụng", "thật no", "ăn nhiều", "chắc bụng", "no nê"]
LIGHT_MEAL_WORDS = ["ăn nhẹ", "ăn vặt", "lót dạ", "không đói lắm", "không đói", "ăn chơi", "nhẹ bụng"]
CHEAP_WORDS = ["rẻ", "rẻ rẻ", "tiết kiệm", "bình dân", "giá mềm", "giá rẻ", "vừa túi tiền", "sinh viên"]
PREMIUM_WORDS = ["sang", "xịn", "đặc biệt", "nhiều topping", "đầy đủ", "thịnh soạn", "ngon nhất"]
DRINK_WORDS = ["đồ uống", "nước uống", "thức uống", "uống gì", "uống", "giải khát"]
DESSERT_WORDS = ["tráng miệng", "đồ ngọt", "món ngọt"]
MODIFIER_HEADS = ["không", "ít", "nhiều", "thêm", "bỏ", "khỏi", "riêng", "cho", "không cho", "đừng cho"]
MODIFIER_OBJECTS = ["hành", "hành lá", "ngò", "rau", "rau thơm", "đá", "đường", "cay", "ớt", "béo", "mỡ", "nước béo",
                    "giá", "chanh", "tiêu", "bột ngọt", "mì chính", "sữa", "tỏi", "nước", "ngọt", "mặn"]

# Mẫu câu theo ý định. Cờ "D" = chỉ khớp khi câu có dấu (bản không dấu dễ nhầm, vd "bỏ"->"bo" trùng "bò").
_INTENT_SPECS: dict[str, list[tuple[str, str]]] = {
    "cancel": [(r"hu[ỷy] (cả |hết |toàn bộ )?đơn", ""), (r"không (mua|đặt|gọi|ăn) nữa", ""), (r"bắt đầu lại", ""),
               (r"làm lại từ đầu", ""), (r"hu[ỷy] hết", ""), (r"xo[áa] hết", ""), (r"bỏ hết", "D"), (r"đổi ý không mua", "")],
    "checkout": [(r"thanh toán", ""), (r"tính tiền", ""), (r"chốt( lại)?( đơn| order| luôn| nha| nhé| đi)?\b", ""),
                 (r"xong rồi", ""), (r"(vậy|thế|nhiêu đó|nhiêu đây|bấy nhiêu|như vậy) (thôi|đủ rồi|là đủ)", ""),
                 (r"(đủ|hết) rồi", "D"), (r"chỉ (vậy|thế)( thôi)?", ""), (r"trả tiền", ""), (r"\bbill\b", ""),
                 (r"lên đơn", ""), (r"đặt (đơn|luôn)", ""), (r"order luôn", ""), (r"tổng kết", ""), (r"\bxong\b", "D"),
                 (r"lấy (nhiêu|bấy nhiêu|nhiêu đó) thôi", "")],
    "pay_cash": [(r"tiền mặt", ""), (r"trả mặt", ""), (r"\bcash\b", ""), (r"trả (tại|ở) quầy", "")],
    "pay_qr": [(r"chuyển khoản", ""), (r"quét (mã|qr|kiu)", ""), (r"\bqr\b", ""), (r"\bck\b", ""), (r"ngân hàng", ""),
               (r"\b(momo|zalopay|zalo pay|vnpay|ví điện tử)\b", "")],
    "view_cart": [(r"(đã|vừa) (gọi|đặt|order|chọn) (những )?(gì|món gì|mấy món)", ""), (r"xem (lại )?(đơn|giỏ|order)", ""),
                  (r"đơn (của )?(tôi|mình|em|anh|chị|tao) (có )?(gì|những gì|sao rồi)", ""), (r"kiểm tra (lại )?(đơn|order)", ""),
                  (r"đọc lại (đơn|order|món)", ""), (r"(tổng|tổng cộng|tất cả) (là |hết |được )?bao nhiêu", ""),
                  (r"hết bao nhiêu", ""), (r"giỏ hàng", ""), (r"(đơn|order) (gồm|có) (gì|những gì)", "")],
    "ask_promo": [(r"khuyến m[ãạ]i", ""), (r"ưu đãi", ""), (r"giảm giá", ""), (r"\bsale\b", ""), (r"voucher", ""),
                  (r"chương trình", ""), (r"\bdeal\b", ""), (r"mã giảm", ""), (r"(có )?(gì|món gì) (đang )?(giảm|rẻ)", ""),
                  (r"được tặng", ""), (r"quà tặng", "")],
    "ask_menu": [(r"\bmenu\b", ""), (r"thực đơn", ""), (r"có (những |các )?món (gì|nào)", ""),
                 (r"(quán|bên mình|ở đây) (có|bán) (những |các )?(gì|món gì|món nào)", ""), (r"bán (những )?(món )?gì", ""),
                 (r"danh sách (món|đồ)", ""), (r"xem (các |danh sách )?món", ""), (r"có gì (ăn|uống)", "")],
    "ask_recommend": [(r"gợi ý", ""), (r"giới thiệu", ""), (r"tư vấn", ""), (r"\bnên (ăn|gọi|uống|chọn|lấy)", ""),
                      (r"(món|cái) (gì|nào) (ngon|đặc biệt|đặc sắc|hấp dẫn|hợp|phù hợp|được)", ""), (r"(có )?gì ngon", ""),
                      (r"ngon nhất", ""), (r"bán chạy", ""), (r"đặc sản", ""), (r"(chưa|không) biết (ăn|gọi|chọn|uống)", ""),
                      (r"\brecommend", ""), (r"best ?seller", ""), (r"chọn (giúp|dùm|hộ)", ""), (r"(ăn|uống) gì (đây|bây giờ|giờ|nhỉ|ta)", ""),
                      (r"(món|cái) (gì|nào) (cũng được|đi)", ""), (r"(em|bạn) (thấy|nghĩ) (món )?(gì|nào)", ""),
                      (r"đề xuất", ""), (r"(nên|muốn) (thử|ăn thử)", ""), (r"tùy em|tuỳ em|em chọn", ""),
                      (r"(món|cái|đồ|thứ) (gì|nào) (\w+ )?(cay|ngọt|chua|đậm|béo|thanh|nhẹ|mát|nóng|chay|rẻ|no|lạnh)", ""),
                      (r"muốn (ăn|uống) (món |cái |đồ )?(gì|nào)", ""), (r"(ăn|uống) (gì|món gì) (cho|để|được)", "")],
    "remove": [(r"\bbỏ\b", "D"), (r"\bxo[áa]\b", ""), (r"\bbớt\b", "D"), (r"hu[ỷy] (món|ly|tô|phần)", ""),
               (r"không (lấy|gọi|đặt|order) (nữa|món|ly|tô|phần)?", ""), (r"\bkhỏi\b", "D"), (r"\bthôi (bỏ|không lấy)", ""),
               (r"\bthôi\b(?! chốt)", "D"), (r"\bloại bỏ\b", "")],
    "set_qty": [(r"\b(đổi|sửa|chỉnh|tăng|giảm) .*(thành|lên|xuống|còn) ", ""), (r"\b(thành|còn|lên|xuống) (\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\b", "D")],
    "swap": [(r"\b(đổi|thay) .+ (thành|bằng|sang|qua)\b", "")],
    "ask_price": [(r"bao nhiêu (tiền|một|1)", ""), (r"giá (bao nhiêu|thế nào|sao|nhiêu)", ""), (r"\bgiá\b", "D"),
                  (r"mấy (nghìn|ngàn|tiền|k)\b", ""), (r"bao nhiêu\b", "D"), (r"\bnhiêu (tiền|vậy)", "")],
    "ask_info": [(r"\b(là|có) (món )?gì\b", "D"), (r"gồm (những )?(gì|món gì|có gì)", ""), (r"(như|ra) (thế|sao) nào", ""),
                 (r"(có )?ngon không", ""), (r"\bcó .+ không( em| ạ| vậy| nhỉ)?$", "D"), (r"\b(cay|ngọt|chua|mặn|béo) không( em| ạ| vậy)?$", "D"),
                 (r"\bthế nào\b", ""), (r"\bmô tả\b", ""), (r"\bthành phần\b", "")],
    "repeat": [(r"nói lại", ""), (r"nhắc lại", ""), (r"lặp lại", ""), (r"\bgì cơ\b", ""), (r"(chưa|không) nghe (rõ|kịp|thấy)", ""),
               (r"^(hả|hở|sao)\??$", "D"), (r"nói chậm", "")],
    "thanks": [(r"c[ảá]m ơn", ""), (r"\bthank", ""), (r"\btks\b", "")],
    "goodbye": [(r"tạm biệt", ""), (r"\bbye\b", ""), (r"hẹn gặp lại", "")],
    "greet": [(r"^(xin )?chào\b", ""), (r"^(alo|hello|hi|hế lô)\b", ""), (r"^chào (em|bạn|shop|quán)", "")],
    "help": [(r"hướng dẫn", ""), (r"làm (sao|thế nào) (để )?(gọi|đặt|order)", ""), (r"(giúp|hỗ trợ) (tôi|mình|với)", "")],
}
_YES = re.compile(r"^(dạ |vâng |ừ |ờ |ok |à )?(đúng|đúng rồi|đúng vậy|chính xác|chuẩn|chuẩn rồi|ok|oke|okay|ô kê|okê|được|được rồi|"
                  r"đồng ý|xác nhận|có|vâng|dạ|ừ|ừm|ờ|phải|yes|làm luôn|lấy luôn|chốt luôn|chuẩn luôn|ừ đúng|đúng thế|"
                  r"được đó|ok luôn|tất nhiên|chắc chắn rồi|có chứ|lấy|lấy đi)( rồi| luôn| nhé| nha| em| ạ| đi| đó| vậy| chứ)*$")
_NO = re.compile(r"^(dạ |à )?(không|không phải|sai|sai rồi|chưa|chưa đúng|khoan|khoan đã|đợi đã|đợi chút|từ từ|no|"
                 r"không đúng|chưa phải|thôi khỏi|không cần|khỏi|không cần đâu|không lấy)( rồi| em| ạ| nha| nhé| đâu| đã)*$")
_ORDINALS = [
    (re.compile(r"\b(món|cái|số|lựa chọn|phương án|combo|ly|tô)? ?(thứ nhất|đầu tiên|số một|số 1|thứ 1)\b"), 1),
    (re.compile(r"\b(món|cái|lựa chọn|phương án|combo|ly|tô) (đầu)\b"), 1),
    (re.compile(r"\b(món|cái|số|lựa chọn|phương án|combo|ly|tô)? ?(thứ hai|số hai|số 2|thứ 2)\b"), 2),
    (re.compile(r"\b(món|cái|số|lựa chọn|phương án|combo|ly|tô)? ?(thứ ba|số ba|số 3|thứ 3)\b"), 3),
    (re.compile(r"\b(món|cái|số|lựa chọn|phương án|combo|ly|tô)? ?(thứ tư|số bốn|số 4|thứ 4)\b"), 4),
    (re.compile(r"\b(món|cái|lựa chọn|phương án|combo) (cuối|cuối cùng|sau cùng)\b"), -1),
]
_DEICTIC = re.compile(r"\b(món|cái|ly|tô|phần|combo) (đó|này|ấy|kia|vừa rồi|vừa nói|em nói|bạn nói)\b|\b(lấy|chọn|gọi) (luôn|nó)\b|\bmón đấy\b")


def _compile(specs: dict[str, list[tuple[str, str]]]) -> dict[str, list[tuple[re.Pattern, re.Pattern | None]]]:
    out = {}
    for intent, pats in specs.items():
        out[intent] = [(re.compile(p), None if "D" in flags else re.compile(strip_diacritics(p))) for p, flags in pats]
    return out


_INTENTS = _compile(_INTENT_SPECS)


def _phrase_re(words: list[str]) -> re.Pattern:
    words = sorted(set(words), key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in words) + r")(?!\w)")


# từ chức năng không bao giờ là một phần tên món (trừ khi tên món chứa đúng từ đó)
_FUNCTION_WORDS = {"đó", "này", "ấy", "kia", "nào", "gì", "không", "có", "là", "và", "với", "của", "cho", "nhé", "nha", "ạ"}


# ============================================================================ kết quả
@dataclass
class ItemMention:
    entry_id: str
    start: int
    end: int
    score: float
    qty: int | None = None
    option_id: str | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class GenericMention:
    """Khách nói chung chung ('cho 2 phở') mà menu có nhiều loại -> cần hỏi lại."""

    head: str
    candidates: list[str]
    start: int
    end: int
    qty: int | None = None


@dataclass
class Preferences:
    likes: dict[str, int] = field(default_factory=dict)       # vị thích: {"cay": 1}
    dislikes: set[str] = field(default_factory=set)            # vị không thích
    light: bool = False                                        # thanh đạm
    vegetarian: bool = False
    exclude: set[str] = field(default_factory=set)             # thành phần kiêng
    include: set[str] = field(default_factory=set)             # thành phần muốn ăn
    style: str | None = None                                   # nuoc | kho
    temp: str | None = None                                    # nong | lanh
    categories: set[str] = field(default_factory=set)          # pho, bun, do-uong...
    portion: str | None = None                                 # lon | nhe
    budget: int | None = None                                  # ngân sách / người
    cheap: bool = False
    premium: bool = False
    group_size: int | None = None

    def is_empty(self) -> bool:
        return not any([self.likes, self.dislikes, self.light, self.vegetarian, self.exclude, self.include, self.style,
                        self.temp, self.categories, self.portion, self.budget, self.cheap, self.premium, self.group_size])

    def merge(self, other: "Preferences") -> "Preferences":
        """Gộp sở thích mới vào sở thích cũ (câu sau ghi đè/ bổ sung câu trước)."""
        m = Preferences(**{k: (v.copy() if isinstance(v, (set, dict)) else v) for k, v in self.__dict__.items()})
        for t, w in other.likes.items():
            m.likes[t] = w
            m.dislikes.discard(t)
        for t in other.dislikes:
            m.dislikes.add(t)
            m.likes.pop(t, None)
        m.light = m.light or other.light
        m.vegetarian = m.vegetarian or other.vegetarian
        m.exclude |= other.exclude
        m.include = (m.include | other.include) - other.exclude
        m.exclude -= other.include
        for k in ("style", "temp", "portion", "budget", "group_size"):
            if getattr(other, k) is not None:
                setattr(m, k, getattr(other, k))
        if other.categories:
            m.categories = set(other.categories)
        m.cheap = other.cheap or (m.cheap and not other.premium)
        m.premium = other.premium or (m.premium and not other.cheap)
        return m

    def to_dict(self) -> dict:
        return {k: (sorted(v) if isinstance(v, set) else v) for k, v in self.__dict__.items()}


@dataclass
class NLUResult:
    text: str
    norm: str
    intent: str
    confidence: float
    items: list[ItemMention] = field(default_factory=list)
    generic: list[GenericMention] = field(default_factory=list)
    prefs: Preferences = field(default_factory=Preferences)
    intents: set[str] = field(default_factory=set)
    ordinal: int | None = None
    deictic: bool = False
    qty: int | None = None              # số lượng không gắn với món nào ("thêm 1 ly nữa")
    target_qty: int | None = None       # "thành 3 tô"
    number: int | None = None           # số đầu tiên trong câu (khi AI hỏi "mấy phần ạ?")
    yes: bool = False
    no: bool = False
    is_question: bool = False
    takeaway: bool | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text, "norm": self.norm, "intent": self.intent, "confidence": self.confidence,
            "items": [m.to_dict() for m in self.items],
            "generic": [g.__dict__ for g in self.generic], "prefs": self.prefs.to_dict(),
            "intents": sorted(self.intents), "ordinal": self.ordinal, "deictic": self.deictic, "qty": self.qty,
            "target_qty": self.target_qty, "number": self.number, "yes": self.yes, "no": self.no, "is_question": self.is_question,
            "takeaway": self.takeaway,
        }


# ============================================================================ so khớp tên món
@dataclass
class _Surface:
    entry_id: str
    diac: str
    fold: str
    ntok: int
    plain: bool  # alias viết không dấu -> chỉ so bản không dấu


class MenuMatcher:
    def __init__(self, menu: Menu, threshold: float = 82.0):
        self.menu = menu
        self.threshold = threshold
        self.surfaces: list[_Surface] = []
        for e in menu.entries():
            for i, s in enumerate([e.name, *e.aliases]):
                d = normalize(s)
                self.surfaces.append(_Surface(e.id, d, strip_diacritics(d), len(d.split()), not has_diacritics(s)))
        self.max_ntok = max(s.ntok for s in self.surfaces)
        self._by_len: dict[int, list[int]] = {}
        for idx, s in enumerate(self.surfaces):
            self._by_len.setdefault(s.ntok, []).append(idx)
        # tiền tố chung của nhiều món: "phở" -> [phở bò tái, phở gà...], "phở bò" -> [tái, chín]
        prefix: dict[str, set[str]] = {}
        for e in menu.entries():
            toks = normalize(e.name).split()
            for k in (1, 2):
                if len(toks) > k:
                    prefix.setdefault(" ".join(toks[:k]), set()).add(e.id)
        order = {e.id: i for i, e in enumerate(menu.entries())}
        self.generic = {p: sorted(ids, key=order.get) for p, ids in prefix.items() if len(ids) >= 2}
        if menu.combos:
            self.generic.setdefault("combo", [c.id for c in menu.combos if c.available])
            self.generic.setdefault("côm bô", [c.id for c in menu.combos if c.available])
        for c in menu.categories:  # tên nhóm: "đồ uống" -> các món trong nhóm
            ids = [i.id for i in menu.items if i.category == c.id and i.available]
            if len(ids) >= 2:
                for n in [c.name, *c.aliases]:
                    self.generic.setdefault(normalize(n), ids)
        self._generic_fold = {strip_diacritics(k): k for k in self.generic}
        # tuỳ chọn (size) theo món
        self.options: dict[str, list[tuple[str, str]]] = {}
        for e in menu.entries():
            for o in e.options:
                for s in [o.name, *o.aliases]:
                    self.options.setdefault(e.id, []).append((o.id, normalize(s)))

    def find(self, toks: list[str], toks_f: list[str], diac: bool) -> list[ItemMention]:
        n = len(toks)
        cands: list[tuple[float, int, int, str]] = []
        fold_choices = [s.fold for s in self.surfaces]
        for L in range(min(self.max_ntok + 1, n), 0, -1):
            idxs = [i for k in (L - 1, L, L + 1) for i in self._by_len.get(k, [])]
            if not idxs:
                continue
            choices = {i: fold_choices[i] for i in idxs}
            for st in range(0, n - L + 1):
                wf = " ".join(toks_f[st : st + L])
                wd = " ".join(toks[st : st + L])
                hits = process.extract(wf, choices, scorer=fuzz.ratio, score_cutoff=self.threshold - 8, limit=6)
                for _, sf, idx in hits:
                    s = self.surfaces[idx]
                    if fuzz.ratio(toks_f[st], s.fold.split()[0]) < 60:
                        continue  # chữ đầu phải gần giống: "có 4 người" != "combo 4 người"
                    if any(t in _FUNCTION_WORDS and t not in s.diac.split() for t in toks[st : st + L]):
                        continue  # "combo đó" != "combo đôi", "món gì cay" != "mì cay"
                    if diac and not s.plain:
                        sd = fuzz.ratio(wd, s.diac)
                        score = 0.5 * sf + 0.5 * sd
                    else:
                        score = sf - (0 if not diac else 3)
                    if s.ntok != L:
                        score -= 4 * abs(s.ntok - L)
                    if L == 1 and score < 97:
                        continue
                    thr = self.threshold + max(0.0, 12 - len(s.fold)) * 1.5  # tên ngắn phải khớp chặt hơn
                    if score >= thr:
                        cands.append((score, st, st + L, s.entry_id))
        cands.sort(key=lambda c: (round(c[0], 1) + 3 * (c[2] - c[1]), c[2] - c[1]), reverse=True)
        taken = [False] * n
        out: list[ItemMention] = []
        for score, a, b, eid in cands:
            if any(taken[a:b]):
                continue
            for k in range(a, b):
                taken[k] = True
            out.append(ItemMention(eid, a, b, round(score, 1)))
        out.sort(key=lambda m: m.start)
        return out

    def find_generic(self, toks: list[str], toks_f: list[str], taken: list[bool]) -> list[GenericMention]:
        out = []
        n = len(toks)
        i = 0
        while i < n:
            hit = None
            for L in (2, 1):
                if i + L > n or any(taken[i : i + L]):
                    continue
                d = " ".join(toks[i : i + L])
                f = " ".join(toks_f[i : i + L])
                key = d if d in self.generic else (self._generic_fold.get(f) if not has_diacritics(d) else None)
                if key:
                    hit = GenericMention(key, self.generic[key], i, i + L)
                    break
            if hit:
                out.append(hit)
                i = hit.end
            else:
                i += 1
        return out


# ============================================================================ NLU chính
class NLU:
    def __init__(self, menu: Menu):
        self.menu = menu
        self.matcher = MenuMatcher(menu)
        self._taste_re = {t: _phrase_re(ws) for t, ws in TASTE_WORDS.items()}
        self._light_re = _phrase_re(LIGHT_WORDS)
        self._veg_re = _phrase_re(VEG_WORDS)
        self._ingr = {k: _phrase_re(v) for k, v in INGREDIENTS.items()}
        self._style = {k: _phrase_re(v) for k, v in STYLE_WORDS.items()}
        self._temp = {k: _phrase_re(v) for k, v in TEMP_WORDS.items()}
        self._hungry = _phrase_re(HUNGRY_WORDS)
        self._lightmeal = _phrase_re(LIGHT_MEAL_WORDS)
        self._cheap = _phrase_re(CHEAP_WORDS)
        self._premium = _phrase_re(PREMIUM_WORDS)
        self._drink = _phrase_re(DRINK_WORDS)
        self._dessert = _phrase_re(DESSERT_WORDS)
        self._neg = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in sorted(NEGATORS, key=len, reverse=True)) + r")\s+(\w+\s+){0,2}$")
        self._mod = re.compile(
            r"(?<!\w)(" + "|".join(re.escape(h) for h in sorted(MODIFIER_HEADS, key=len, reverse=True)) + r")\s+("
            + "|".join(re.escape(o) for o in sorted(MODIFIER_OBJECTS, key=len, reverse=True)) + r")(?!\w)"
        )
        # ASR hay nghe "combo" (từ mượn) thành "còn một", "có một", "cơm bô"... -> sửa khi đứng trước tên combo
        suffixes = set()
        for c in menu.combos:
            for n in [c.name, *c.aliases]:
                toks = normalize(n).split()
                if toks and strip_diacritics(toks[0]) in ("combo", "com", "com bo") or (len(toks) > 1 and toks[0] in ("côm", "com")):
                    rest = toks[2:] if toks[0] in ("côm", "com") and len(toks) > 2 else toks[1:]
                    if rest:
                        suffixes.add(" ".join(rest[:2]))
        self._combo_fix = re.compile(  # chỉ sửa khi đứng sau động từ gọi món / số lượng (tránh "có một gia đình...")
            r"(?<!\w)(cho|lấy|thêm|gọi|đặt|một|hai|ba|bốn|năm|\d+|anh|em|tôi|chị|mình|và|với) "
            r"(?:còn|có|cơm|côm|com|cầm|con|cam|gom|cờm) (?:một|mốt|bô|bộ|bố|mô|bơ|bò|vô)\s+(?=(" +
            "|".join(re.escape(x) for x in sorted(suffixes, key=len, reverse=True)) + r")(?!\w))"
        ) if suffixes else None
        cat_words: dict[str, str] = {}
        for c in menu.categories:
            for w in [c.name, *c.aliases]:
                cat_words[normalize(w)] = c.id
        self._cat_words = cat_words
        self._cat_re = _phrase_re(list(cat_words))

    # ------------------------------------------------------------------ public
    def parse(self, text: str) -> NLUResult:
        norm = normalize(text)
        if self._combo_fix is not None:
            norm = self._combo_fix.sub(r"\1 combo ", norm)
        diac = has_diacritics(norm)
        toks = norm.split()
        toks_f = [strip_diacritics(t) for t in toks]
        folded = " ".join(toks_f)
        res = NLUResult(text=text, norm=norm, intent="unknown", confidence=0.0)
        if not toks:
            return res

        res.yes = bool(_YES.match(norm)) or (not diac and bool(re.match(r"^(dung|dung roi|ok|oke|duoc|co|vang|da|u|uh|chuan)( roi| luon| nhe| nha| em| a)*$", folded)))
        res.no = bool(_NO.match(norm)) or (not diac and bool(re.match(r"^(khong|khong phai|sai|chua|khoan|thoi khoi|khong can)( roi| em| a| nha| nhe| dau)*$", folded)))
        res.is_question = bool(re.search(r"\b(không|chưa|hả|nhỉ|sao|nào|gì|bao nhiêu|à)( em| ạ| vậy| nhỉ| thế)?\s*$", norm)) or "?" in text

        # 1) ý định theo mẫu câu
        for intent, pats in _INTENTS.items():
            for pd, pf in pats:
                if pd.search(norm) or (pf is not None and pf.search(folded)):
                    res.intents.add(intent)
                    break

        # 2) món ăn
        items = self.matcher.find(toks, toks_f, diac)
        taken = [False] * len(toks)
        for m in items:
            for k in range(m.start, m.end):
                taken[k] = True
        # cụm từ khẩu vị ("có nước", "món nước", "đồ uống mát") không phải tên món chung chung
        for rx in [*self._style.values(), self._light_re, self._veg_re]:
            for mm in rx.finditer(norm):
                a = len(norm[: mm.start()].split())
                b = a + len(mm.group(0).split())
                for k in range(a, min(b, len(taken))):
                    taken[k] = True
        generic = self.matcher.find_generic(toks, toks_f, taken)
        for g in generic:
            for k in range(g.start, g.end):
                taken[k] = True
        spans = sorted([(m.start, m.end, m) for m in items] + [(g.start, g.end, g) for g in generic], key=lambda x: x[0])
        for idx, (a, b, m) in enumerate(spans):
            nxt = spans[idx + 1][0] if idx + 1 < len(spans) else len(toks)
            prv = spans[idx - 1][1] if idx > 0 else 0
            m.qty = self._qty_before(toks, prv, a) or self._qty_after(toks, b, nxt)
            if isinstance(m, ItemMention):
                m.option_id = self._option(m.entry_id, toks, prv, a, b, nxt)
                m.note = self._note(" ".join(toks[b:nxt]))
        res.items = items
        res.generic = generic

        # 3) sở thích / khẩu vị (bỏ phần ghi chú món như "không hành" để không thành kiêng toàn cục)
        pnorm = self._mod.sub(lambda m: " " * len(m.group(0)), norm) if items else norm
        res.prefs = self.prefs(pnorm, items)
        res.number = next((v for k in range(len(toks)) for v in [parse_number(toks, k)[0]] if v is not None), None)
        # 4) tham chiếu: "món thứ hai", "món đó", "thêm 1 ly nữa"
        for rx, val in _ORDINALS:
            if rx.search(norm):
                res.ordinal = val
                break
        res.deictic = bool(_DEICTIC.search(norm))
        if not items and not generic:
            res.qty = self._free_qty(toks)
        m_t = re.search(r"\b(thành|còn|lên|xuống|lại) (\S+(?: \S+)?)", norm)
        if m_t:
            v, _ = parse_number(m_t.group(2).split())
            res.target_qty = v
        if re.search(r"mang (về|đi)|\btake ?away\b|gói (lại|mang)|đem về", norm):
            res.takeaway = True
        elif re.search(r"ăn (tại chỗ|ở đây|tại quán)|ngồi (đây|ăn)", norm):
            res.takeaway = False

        res.intent, res.confidence = self._decide(res)
        return res

    # ------------------------------------------------------------------ helpers
    def _qty_before(self, toks: list[str], lo: int, a: int) -> int | None:
        j = a
        if j - 1 >= lo and (toks[j - 1] in CLASSIFIERS or toks[j - 1] in CLASSIFIERS_FOLD):
            j -= 1
            if j - 1 >= lo and toks[j - 1] in ASR_QTY_CONFUSIONS:
                return ASR_QTY_CONFUSIONS[toks[j - 1]]
        for k in range(max(lo, j - 4), j):
            v, end = parse_number(toks, k)
            if v is not None and end == j and 0 < v <= 99:
                return v
        return None

    def _qty_after(self, toks: list[str], b: int, hi: int) -> int | None:
        if b >= hi:
            return None
        v, end = parse_number(toks, b)
        if v is not None and 0 < v <= 99:
            if end < hi and (toks[end] in CLASSIFIERS or toks[end] in CLASSIFIERS_FOLD):
                return v
            if end == len(toks) or (end < len(toks) and toks[end] in ("nữa", "nha", "nhé", "thôi", "ạ", "và", "với")):
                return v
        if b < hi and toks[b] in ASR_QTY_CONFUSIONS and b + 1 < hi and toks[b + 1] in CLASSIFIERS:
            return ASR_QTY_CONFUSIONS[toks[b]]
        return None

    def _free_qty(self, toks: list[str]) -> int | None:
        for k in range(len(toks)):
            v, end = parse_number(toks, k)
            if v is not None and 0 < v <= 20 and end < len(toks) and (toks[end] in CLASSIFIERS or toks[end] in CLASSIFIERS_FOLD):
                return v
            if v is not None and 0 < v <= 20 and end < len(toks) and toks[end] == "nữa":
                return v
        return None

    def _option(self, eid: str, toks: list[str], lo: int, a: int, b: int, hi: int) -> str | None:
        opts = self.matcher.options.get(eid)
        if not opts:
            return None
        before = " " + " ".join(toks[max(lo, a - 3) : a]) + " "
        after = " " + " ".join(toks[b : min(hi, b + 4)]) + " "
        for oid, s in sorted(opts, key=lambda x: -len(x[1])):
            if f" {s} " in after or f" {s} " in before:
                return oid
        return None

    def _note(self, seg: str) -> str:
        mods = [m.group(0) for m in self._mod.finditer(seg)]
        return ", ".join(dict.fromkeys(mods))

    def _negated(self, norm: str, start: int) -> bool:
        return bool(self._neg.search(norm[:start]))

    def prefs(self, norm: str, items: list[ItemMention] | None = None) -> Preferences:
        p = Preferences()
        for t, rx in self._taste_re.items():
            for m in rx.finditer(norm):
                # "có cay không" là câu hỏi, không phải sở thích
                tail = norm[m.end():]
                if re.match(r"^\s*(không|ko|hông|chưa)\s*(em|ạ|vậy|nhỉ)?\s*$", tail) and re.search(r"\bcó\s+(\w+\s+){0,2}$", norm[: m.start()] + " "):
                    continue
                if self._negated(norm, m.start()):
                    p.dislikes.add(t)
                    p.likes.pop(t, None)
                else:
                    p.likes[t] = 2 if re.search(r"(rất|thật|siêu|cực|nhiều|thích)\s+$", norm[: m.start()]) else 1
                    p.dislikes.discard(t)
        if self._light_re.search(norm):
            p.light = True
            p.dislikes.update({"beo"})
        if self._veg_re.search(norm):
            p.vegetarian = True
        for name, rx in self._ingr.items():
            for m in rx.finditer(norm):
                if self._inside_item(norm, m.start(), items):
                    continue
                pre = norm[: m.start()]
                if self._negated(norm, m.start()) or re.search(r"(dị ứng|kiêng|kỵ|trừ|không có)\s+(\w+\s+){0,1}$", pre):
                    p.exclude.add(name)
                elif re.search(r"(thích|muốn|ăn|món|thèm|có)\s+(\w+\s+){0,1}$", pre) and not re.search(r"(không|chẳng)\s+(\w+\s+){0,2}$", pre):
                    p.include.add(name)
        if "hải sản" in p.exclude:
            p.exclude.update({"tôm", "cua", "mực", "cá"})
        for k, rx in self._style.items():
            if rx.search(norm):
                p.style = k
        for k, rx in self._temp.items():
            m = rx.search(norm)
            if m and not self._inside_item(norm, m.start(), items) and not self._negated(norm, m.start()):
                p.temp = k
        if self._hungry.search(norm):
            p.portion = "lon"
        if self._lightmeal.search(norm):
            p.portion = "nhe"
        if self._cheap.search(norm):
            p.cheap = True
        if self._premium.search(norm) and not items:
            p.premium = True
        cats = set()
        for m in self._cat_re.finditer(norm):
            if not self._inside_item(norm, m.start(), items):
                cats.add(self._cat_words[m.group(1)])
        if self._drink.search(norm):
            cats.add("do-uong")
        if self._dessert.search(norm):
            cats.add("trang-mieng")
        if re.search(r"(?<!\w)(combo|côm bô|com bô|set ăn)(?!\w)", norm) and not any(
                self.menu.get(m.entry_id).kind == "combo" for m in (items or [])):
            cats.add("combo")
        p.categories = {c for c in cats if c == "combo" or self.menu.category(c)}
        p.budget = self._budget(norm)
        p.group_size = self._group(norm)
        return p

    def _inside_item(self, norm: str, char_pos: int, items: list[ItemMention] | None) -> bool:
        if not items:
            return False
        tok_idx = len(norm[:char_pos].split())
        return any(m.start <= tok_idx < m.end for m in items)

    def _budget(self, norm: str) -> int | None:
        money_units = ("nghìn", "ngàn", "nghin", "ngan", "k", "cành", "xị", "đồng", "dong")
        for m in re.finditer(r"(?<!\w)(dưới|không quá|tối đa|tầm|khoảng|chừng|max|trong vòng|budget|ngân sách|có)(?=\s)", norm):
            toks = norm[m.end():].split()
            v, end = parse_number(toks, 0)
            if v is None:
                continue
            unit = toks[end] if end < len(toks) else ""
            if m.group(1) == "có" and unit not in money_units and v < 1000:
                continue
            if v < 1000:
                if unit in money_units or m.group(1) != "có":
                    v *= 1000
            if 5000 <= v <= 5_000_000:
                return v
        return None

    def _group(self, norm: str) -> int | None:
        m = re.search(r"(\S+(?: \S+)?)\s+(người|đứa|bạn|vị|khách|mạng)\b", norm)
        if m:
            toks = m.group(1).split()
            for k in range(len(toks)):
                v, end = parse_number(toks, k)
                if v and end == len(toks) and 1 <= v <= 30:
                    return v
        m = re.search(r"\b(nhóm|bàn|đoàn|gia đình|nhà)\s+(\S+)", norm)
        if m:
            v, _ = parse_number([m.group(2)])
            if v and 1 <= v <= 30:
                return v
        if re.search(r"(vợ chồng|cặp đôi|hai đứa|2 đứa|người yêu|bạn gái|bạn trai|hai mẹ con|hai bố con|hai anh em|hai chị em)", norm):
            return 2
        if re.search(r"\b(gia đình|cả nhà|đại gia đình)\b", norm):
            return 4
        if re.search(r"\b(một mình|mình tôi|mình em|1 mình|ăn một mình)\b", norm):
            return 1
        return None

    def _decide(self, r: NLUResult) -> tuple[str, float]:
        I = r.intents
        if r.items:
            if "swap" in I and len(r.items) >= 2:
                return "swap", 0.9
            if "remove" in I and "checkout" not in I:
                return "remove", 0.9
            if "set_qty" in I and r.target_qty:
                return "set_qty", 0.85
            if ("ask_price" in I) and not re.search(r"\b(cho|lấy|thêm|gọi|đặt)\b", r.norm):
                return "ask_price", 0.85
            if ("ask_info" in I or r.is_question) and not re.search(r"\b(cho|lấy|thêm|gọi|đặt|order)\b", r.norm):
                return "ask_info", 0.8
            if "ask_recommend" in I and not re.search(r"\b(cho|lấy|thêm|gọi|đặt|order)\b", r.norm):
                return "ask_info", 0.7
            return "add", 0.95 if min(m.score for m in r.items) >= 90 else 0.75
        if "cancel" in I:
            return "cancel", 0.9
        if r.deictic or (r.ordinal is not None and not r.generic):
            return "select", 0.8
        if r.generic and re.search(r"\b(nào|gì)\b", r.norm) and not r.prefs.is_empty():
            return "ask_recommend", 0.75  # "combo nào cho 4 người", "phở gì không cay"
        if r.generic and not ({"ask_recommend", "ask_menu", "ask_promo"} & I) and not r.is_question:
            if "remove" in I:
                return "remove_generic", 0.6
            return "add_generic", 0.7
        if r.yes:
            return "yes", 0.9
        if r.no:
            return "no", 0.9
        if "ask_menu" in I and not r.prefs.is_empty():
            return "ask_recommend", 0.8
        for name in ("pay_cash", "pay_qr", "checkout", "view_cart", "ask_promo", "ask_menu", "ask_recommend"):
            if name in I:
                return name, 0.85
        if r.ordinal is not None or r.deictic:
            return "select", 0.75
        if not r.prefs.is_empty():
            return "preference", 0.75
        if r.generic:
            return "ask_category", 0.6
        if r.qty and re.search(r"\b(thêm|nữa)\b", r.norm):
            return "add_more", 0.6
        for name in ("remove", "repeat", "thanks", "goodbye", "help", "greet", "ask_price", "ask_info"):
            if name in I:
                return name, 0.7
        if re.search(r"\b(đói|ăn gì|ăn|uống)\b", r.norm):
            return "ask_recommend", 0.5
        return "unknown", 0.0
