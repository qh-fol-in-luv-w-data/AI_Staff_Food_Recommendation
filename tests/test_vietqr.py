import pytest

from aistaff import vietqr


def test_crc_check_value():
    assert vietqr.crc16_ccitt(b"123456789") == 0x29B1  # giá trị kiểm chuẩn CRC-16/CCITT-FALSE


def test_dynamic_payload_roundtrip():
    p = vietqr.build_payload("970436", "0123456789", 125000, "DH01000123")
    assert p.startswith("000201010212") and vietqr.verify(p)
    d = vietqr.decode(p)
    assert (d.bank_bin, d.account, d.amount, d.purpose, d.service, d.dynamic) == (
        "970436", "0123456789", 125000, "DH01000123", "QRIBFTTA", True)
    top = vietqr.parse_tlv(p)
    assert top["53"] == "704" and top["58"] == "VN" and vietqr.parse_tlv(top["38"])["00"] == "A000000727"


def test_static_payload_and_sanitized_purpose():
    p = vietqr.build_payload("970422", "9999", purpose="Thanh toán đơn #12 cho Quán Ngon nhé!!!")
    d = vietqr.decode(p)
    assert d.amount is None and not d.dynamic
    assert d.purpose == "THANH TOAN DON 12 CHO QUA" and len(d.purpose) <= 25


def test_tamper_detected_and_bad_input():
    p = vietqr.build_payload("970436", "0123456789", 50000, "DH1")
    assert not vietqr.verify(p.replace("50000", "10000"))
    with pytest.raises(ValueError):
        vietqr.build_payload("97043", "0123456789", 1000)
    with pytest.raises(ValueError):
        vietqr.build_payload("970436", "0123456789", 0)


def test_svg_render():
    svg = vietqr.to_svg(vietqr.build_payload("970436", "0123456789", 1000, "X"))
    assert svg.startswith("<svg") and "path" in svg
