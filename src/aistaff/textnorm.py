"""Chuẩn hoá văn bản tiếng Việt: bỏ dấu, đọc số bằng chữ <-> số, đọc tiền cho TTS.

Mọi hàm ở đây là Python thuần, chạy < 0.1 ms/câu -> không ảnh hưởng độ trễ.
"""

from __future__ import annotations

import re
import unicodedata

_D = str.maketrans({"đ": "d", "Đ": "D"})
_PUNCT = re.compile(r"[^\w\s%]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def strip_diacritics(s: str) -> str:
    """'Phở bò tái' -> 'Pho bo tai'."""
    s = unicodedata.normalize("NFD", s.translate(_D))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", s)


def normalize(s: str) -> str:
    """Chữ thường, NFC, bỏ dấu câu, gộp khoảng trắng. Giữ nguyên dấu thanh tiếng Việt."""
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"(\d)[.,](\d{3})(?!\d)", r"\1\2", s)  # 55.000 -> 55000
    s = re.sub(r"(\d)[.,](\d{3})(?!\d)", r"\1\2", s)  # 1.250.000 -> 1250000
    s = _PUNCT.sub(" ", s)
    s = re.sub(r"(\d+)\s*k\b", lambda m: m.group(1) + "000", s)  # 50k -> 50000
    s = re.sub(r"\b(\d+)\s*(đ|vnd|vnđ|dong)\b", r"\1", s)
    s = re.sub(r"\bx\s*(\d+)\b", r"\1", s)  # "x2" -> "2"
    return _SPACES.sub(" ", s).strip()


def fold(s: str) -> str:
    """Chuẩn hoá + bỏ dấu (dùng so khớp khi khách gõ không dấu hoặc ASR nhận sai dấu)."""
    return strip_diacritics(normalize(s))


def has_diacritics(s: str) -> bool:
    return s != strip_diacritics(s)


def ascii_slug(s: str, max_len: int = 25) -> str:
    """Nội dung chuyển khoản an toàn cho mọi app ngân hàng: chữ/số không dấu, in hoa."""
    s = re.sub(r"[^A-Za-z0-9 ]", "", strip_diacritics(s)).upper()
    return _SPACES.sub(" ", s).strip()[:max_len]


# ============================================================ số bằng chữ -> số
_DIGIT = {
    "không": 0, "một": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4,
    "năm": 5, "lăm": 5, "nhăm": 5, "sáu": 6, "bảy": 7, "bẩy": 7, "tám": 8, "chín": 9,
}
# Khách gõ không dấu: chỉ nhận khi bản thân token không có dấu ("tấm" != "tám")
_DIGIT_FOLD = {"khong": 0, "mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5, "lam": 5,
               "sau": 6, "bay": 7, "tam": 8, "chin": 9}
_UNIT_ONLY = {"mốt", "tư", "lăm", "nhăm", "lam"}  # chỉ đứng sau hàng chục
_BIG = {"nghìn": 1000, "ngàn": 1000, "nghin": 1000, "ngan": 1000,
        "triệu": 1_000_000, "trieu": 1_000_000, "tỷ": 1_000_000_000, "tỉ": 1_000_000_000, "ty": 1_000_000_000}


_TRAILING_OK = {"đồng", "dong", "thôi", "nha", "nhé", "ạ", "a", "k", "nhe", "à", "đó", "vậy"}


def _kind(t: str) -> tuple[str, int]:
    plain = not has_diacritics(t)
    f = strip_diacritics(t)
    if t.isdigit():
        return "num", int(t)
    if t in _DIGIT:
        return "digit", _DIGIT[t]
    if plain and t in _DIGIT_FOLD:
        return "digit", _DIGIT_FOLD[t]
    if t == "mười":
        return "ten", 10
    if t == "mươi":
        return "tens", 10
    if plain and t == "muoi":
        return "muoi", 10
    if t in ("trăm",) or (plain and t == "tram"):
        return "hundred", 100
    if t in ("chục",) or (plain and t == "chuc"):
        return "chuc", 10
    if t in ("băm",) or (plain and t == "bam"):
        return "bam", 30
    if t in ("linh", "lẻ") or (plain and t == "le"):
        return "linh", 0
    if t in ("rưỡi",) or (plain and t == "ruoi"):
        return "ruoi", 0
    if t in _BIG and (t in ("nghìn", "ngàn", "triệu", "tỷ", "tỉ") or plain):
        return "big", _BIG[t]
    return "", 0


def is_number_token(tok: str) -> bool:
    return _kind(tok)[0] != ""


def parse_number(tokens: list[str], start: int = 0) -> tuple[int | None, int]:
    """Đọc số bắt đầu tại tokens[start]. Trả về (giá_trị | None, vị_trí_kết_thúc).

    Hỗ trợ: "hai mươi lăm" 25, "mười lăm" 15, "một trăm linh năm" 105, "một trăm rưỡi" 150,
    "hai lăm" 25 (nói tắt), "băm lăm" 35, "năm mươi nghìn" 50000, "hai nghìn rưỡi" 2500,
    "một triệu hai" 1200000, "1 triệu 2", "hai chục" 20, "125000", gõ không dấu "hai muoi lam".
    """
    i, n = start, len(tokens)
    total = group = 0
    pending: int | None = None   # chữ số chưa biết là hàng chục hay đơn vị
    tens_done = False
    seen = False
    last = ""
    last_big = 0
    after_big = False
    digit_pos = start

    while i < n:
        t = tokens[i]
        k, v = _kind(t)
        if k == "num":
            if seen and last != "big":
                break
            if last == "big" and v < 10 and (i + 1 >= n or _kind(tokens[i + 1])[0] != "big"):
                total += v * (last_big // 10)   # "1 triệu 2" = 1.200.000
                last, i = "colloq", i + 1
                continue
            if v >= 1000:
                total += v
            else:
                group += v
            seen, last, i = True, "num", i + 1
            continue
        if k == "digit":
            if pending is not None and last == "digit" and not tens_done and t in _UNIT_ONLY:
                group += pending * 10 + v          # "hai lăm" = 25
                pending, tens_done, last, i = None, True, "unit", i + 1
                continue
            if last in ("digit", "unit", "num"):
                break
            if t in _UNIT_ONLY and not tens_done and last != "big":
                break
            after_big = last == "big"
            digit_pos = i
            pending, seen, last, i = v, True, "digit", i + 1
            continue
        if k == "muoi":  # gõ không dấu: "muoi" = mươi nếu có chữ số đứng trước, ngược lại = mười
            k = "tens" if pending is not None else "ten"
        if k == "ten":
            if pending is not None or tens_done:
                break
            group += 10
            tens_done, seen, last, i = True, True, "ten", i + 1
            continue
        if k in ("tens", "chuc"):
            if pending is None:
                break
            group += pending * 10
            pending, tens_done, last, i = None, True, "ten", i + 1
            continue
        if k == "bam":
            if pending is not None or tens_done:
                break
            group += 30
            tens_done, seen, last, i = True, True, "ten", i + 1
            continue
        if k == "linh":
            if last != "hundred":
                break
            tens_done, last, i = True, "linh", i + 1
            continue
        if k == "hundred":
            h = pending if pending is not None else (1 if (group == 0 and not seen) else None)
            if h is None or group % 1000 >= 100:
                break
            group += h * 100
            pending, tens_done, seen, last, i = None, False, True, "hundred", i + 1
            continue
        if k == "big":
            if not seen and pending is None:
                break
            if pending is not None:
                group += pending
                pending = None
            total += (group or 1) * v
            group, tens_done, last, last_big, seen, i = 0, False, "big", v, True, i + 1
            continue
        if k == "ruoi":
            if last == "hundred":
                group += 50
            elif last == "big":
                total += last_big // 2
            else:
                break
            last, i = "ruoi", i + 1
            continue
        break

    if not seen:
        return None, start
    if pending is not None:
        if last == "digit" and after_big and group == 0 and total:
            if i < n and _kind(tokens[i])[0] == "" and tokens[i] not in _TRAILING_OK:
                return total, digit_pos   # "80 nghìn một người": "một" thuộc về "người"
            total += pending * (last_big // 10)   # "một triệu hai", "hai nghìn tư"
        else:
            group += pending
    return total + group, i


# ============================================================ số -> chữ (cho TTS)
_W = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _read_triple(n: int, full: bool) -> str:
    """Đọc số 0..999. full=True: đọc đủ 'không trăm', 'linh' (nhóm không đứng đầu)."""
    h, t, u = n // 100, (n // 10) % 10, n % 10
    parts: list[str] = []
    if h or full:
        parts += [_W[h], "trăm"]
    if t == 0:
        if u and (h or full):
            parts.append("linh")
    elif t == 1:
        parts.append("mười")
    else:
        parts += [_W[t], "mươi"]
    if u:
        if u == 1 and t >= 2:
            parts.append("mốt")
        elif u == 5 and t >= 1:
            parts.append("lăm")
        else:
            parts.append(_W[u])
    return " ".join(parts)


def number_to_words(n: int) -> str:
    """125000 -> 'một trăm hai mươi lăm nghìn'; 1050000 -> 'một triệu không trăm năm mươi nghìn'."""
    if n == 0:
        return "không"
    if n < 0:
        return "âm " + number_to_words(-n)
    units = ["", "nghìn", "triệu", "tỷ"]
    groups: list[int] = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    words: list[str] = []
    top = len(groups) - 1
    for idx in range(top, -1, -1):
        g = groups[idx]
        if g == 0:
            continue
        lead = idx == top
        w = _read_triple(g, full=not lead)
        unit = units[idx % 4] if idx < 4 else "nghìn tỷ"
        words.append(f"{w} {unit}".strip())
    return " ".join(words)


def money_to_words(amount: int) -> str:
    return number_to_words(int(amount)) + " đồng"


def format_money(amount: int) -> str:
    """55000 -> '55.000đ'."""
    return f"{int(amount):,}".replace(",", ".") + "đ"


_ABBR = {
    r"\bQR\b": "kiu a",
    r"\bcombo\b": "com bô",
    r"\bCombo\b": "Com bô",
    r"\bVAT\b": "thuế vê a tê",
    r"\bAI\b": "ây ai",
    r"\bok\b": "ô kê",
    r"\bsize\b": "sai",
}


def tts_normalize(text: str) -> str:
    """Chuẩn bị câu cho TTS: '55.000đ' -> 'năm mươi lăm nghìn đồng', 'x2' -> 'hai', 'QR' -> 'kiu a'."""
    s = text
    s = re.sub(r"(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(đ|₫|VNĐ|VND|đồng)", lambda m: money_to_words(int(re.sub(r"[.,]", "", m.group(1)))), s)
    s = re.sub(r"(\d+)\s*%", lambda m: number_to_words(int(m.group(1))) + " phần trăm", s)
    s = re.sub(r"\bx(\d+)\b", lambda m: number_to_words(int(m.group(1))), s)
    s = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: number_to_words(int(m.group(1))) + " giờ" + (
        "" if m.group(2) == "00" else " " + number_to_words(int(m.group(2)))), s)
    s = re.sub(r"\d{1,3}(?:\.\d{3})+", lambda m: number_to_words(int(m.group(0).replace(".", ""))), s)
    s = re.sub(r"\b\d+\b", lambda m: number_to_words(int(m.group(0))) if len(m.group(0)) <= 12 else m.group(0), s)
    for pat, rep in _ABBR.items():
        s = re.sub(pat, rep, s)
    s = s.replace("&", " và ").replace("+", " cộng ").replace("/", " trên ")
    return _SPACES.sub(" ", s).strip()
