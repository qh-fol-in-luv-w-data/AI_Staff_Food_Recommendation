"""Sinh mã VietQR (chuẩn EMVCo Merchant-Presented Mode + đặc tả NAPAS) - chạy offline 100%.

Cấu trúc payload (TLV = Tag 2 số + Length 2 số + Value):
  00 02 "01"                         Payload Format Indicator
  01 02 "12"                         Point of Initiation: 11 = QR tĩnh, 12 = QR động (có số tiền, dùng 1 lần)
  38 LL                              Merchant Account Information (NAPAS)
     00 10 "A000000727"              GUID của NAPAS
     01 LL                           Beneficiary Organization
        00 06 <BIN ngân hàng>        vd 970436 = Vietcombank
        01 LL <số tài khoản/số thẻ>
     02 08 "QRIBFTTA"                Dịch vụ: QRIBFTTA = chuyển nhanh 247 tới TÀI KHOẢN, QRIBFTTC = tới THẺ
  53 03 "704"                        Tiền tệ VND
  54 LL <số tiền>                    (tuỳ chọn) số nguyên, không dấu phân cách
  58 02 "VN"                         Quốc gia
  62 LL                              Additional Data
     08 LL <nội dung chuyển khoản>   (purpose of transaction) vd "DH01000123"
  63 04 <CRC>                        CRC-16/CCITT-FALSE tính trên toàn bộ chuỗi trước đó + "6304"

Mọi app ngân hàng / ví ở Việt Nam hỗ trợ VietQR đều quét được -> quán nhận tiền thẳng vào tài khoản,
phí 0đ (chuyển khoản NAPAS 247), không qua trung gian.
"""

from __future__ import annotations

from dataclasses import dataclass

from .textnorm import ascii_slug

NAPAS_GUID = "A000000727"
SERVICE_ACCOUNT = "QRIBFTTA"
SERVICE_CARD = "QRIBFTTC"

# Mã BIN (Bank Identification Number) phổ biến - đối chiếu lại danh sách NAPAS/VietQR trước khi dùng
BANK_BINS: dict[str, str] = {
    "VCB": "970436",   # Vietcombank
    "ICB": "970415",   # VietinBank
    "BIDV": "970418",  # BIDV
    "VBA": "970405",   # Agribank
    "MB": "970422",    # MBBank
    "TCB": "970407",   # Techcombank
    "ACB": "970416",   # ACB
    "VPB": "970432",   # VPBank
    "TPB": "970423",   # TPBank
    "STB": "970403",   # Sacombank
    "VIB": "970441",   # VIB
    "HDB": "970437",   # HDBank
    "SHB": "970443",   # SHB
    "MSB": "970426",   # MSB
    "OCB": "970448",   # OCB
    "SEAB": "970440",  # SeABank
    "EIB": "970431",   # Eximbank
    "LPB": "970449",   # LPBank
    "NAB": "970428",   # Nam A Bank
    "ABB": "970425",   # ABBANK
    "BAB": "970409",   # Bac A Bank
    "VCCB": "970454",  # BVBank (Viet Capital)
    "NCB": "970419",   # NCB
    "PVCB": "970412",  # PVcomBank
    "KLB": "970452",   # KienlongBank
    "SGICB": "970400", # Saigonbank
    "VAB": "970427",   # VietABank
    "VIETBANK": "970433",
    "BVB": "970438",   # BaoVietBank
    "PGB": "970430",   # PGBank
    "CAKE": "546034",  # CAKE by VPBank
    "UBANK": "546035", # Ubank by VPBank
    "TIMO": "963388",  # Timo
}


def tlv(tag: str, value: str) -> str:
    if len(value) > 99:
        raise ValueError(f"Giá trị tag {tag} quá dài ({len(value)} > 99)")
    return f"{tag}{len(value):02d}{value}"


def crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, không đảo bit, không XOR cuối."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def build_payload(
    bank_bin: str,
    account: str,
    amount: int | None = None,
    purpose: str | None = None,
    service: str = SERVICE_ACCOUNT,
    dynamic: bool | None = None,
) -> str:
    """Tạo chuỗi VietQR. amount=None -> QR tĩnh (khách tự nhập tiền)."""
    if not (bank_bin.isdigit() and len(bank_bin) == 6):
        raise ValueError("bank_bin phải là 6 chữ số")
    account = account.replace(" ", "")
    if not account.isalnum():
        raise ValueError("Số tài khoản không hợp lệ")
    if dynamic is None:
        dynamic = amount is not None
    beneficiary = tlv("00", bank_bin) + tlv("01", account)
    mai = tlv("00", NAPAS_GUID) + tlv("01", beneficiary) + tlv("02", service)
    p = tlv("00", "01") + tlv("01", "12" if dynamic else "11") + tlv("38", mai) + tlv("53", "704")
    if amount is not None:
        amount = int(amount)
        if amount <= 0 or len(str(amount)) > 13:
            raise ValueError("Số tiền không hợp lệ")
        p += tlv("54", str(amount))
    p += tlv("58", "VN")
    if purpose:
        p += tlv("62", tlv("08", ascii_slug(purpose, 25)))
    p += "6304"
    return p + f"{crc16_ccitt(p.encode('ascii')):04X}"


def parse_tlv(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    i = 0
    while i < len(s):
        tag, ln = s[i : i + 2], int(s[i + 2 : i + 4])
        out[tag] = s[i + 4 : i + 4 + ln]
        i += 4 + ln
    return out


def verify(payload: str) -> bool:
    if len(payload) < 8 or payload[-8:-4] != "6304":
        return False
    return f"{crc16_ccitt(payload[:-4].encode('ascii')):04X}" == payload[-4:].upper()


@dataclass
class DecodedQR:
    bank_bin: str
    account: str
    service: str
    amount: int | None
    purpose: str | None
    dynamic: bool


def decode(payload: str) -> DecodedQR:
    if not verify(payload):
        raise ValueError("CRC sai")
    top = parse_tlv(payload)
    mai = parse_tlv(top["38"])
    if mai.get("00") != NAPAS_GUID:
        raise ValueError("Không phải VietQR (NAPAS)")
    ben = parse_tlv(mai["01"])
    add = parse_tlv(top["62"]) if "62" in top else {}
    return DecodedQR(
        bank_bin=ben["00"],
        account=ben["01"],
        service=mai.get("02", ""),
        amount=int(top["54"]) if "54" in top else None,
        purpose=add.get("08"),
        dynamic=top.get("01") == "12",
    )


def to_svg(payload: str, scale: int = 8, border: int = 2, dark: str = "#000", light: str = "#fff") -> str:
    """Render QR ra SVG (không cần Pillow, nhẹ cho thiết bị edge)."""
    import segno

    qr = segno.make(payload, error="m", micro=False)
    return qr.svg_inline(scale=scale, border=border, dark=dark, light=light)


def to_png(payload: str, path: str, scale: int = 10, border: int = 2) -> None:
    import segno

    segno.make(payload, error="m", micro=False).save(path, scale=scale, border=border)


def to_terminal(payload: str) -> str:
    """In QR ra terminal (debug / máy không màn hình đồ hoạ)."""
    import io

    import segno

    buf = io.StringIO()
    segno.make(payload, error="m", micro=False).terminal(out=buf, compact=True)
    return buf.getvalue()
