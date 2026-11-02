import pytest

from aistaff.textnorm import ascii_slug, fold, format_money, money_to_words, normalize, number_to_words, parse_number, tts_normalize


@pytest.mark.parametrize("text,value", [
    ("hai mươi lăm", 25), ("mười lăm", 15), ("một trăm linh năm", 105), ("một trăm rưỡi", 150), ("hai lăm", 25),
    ("ba mốt", 31), ("băm lăm", 35), ("năm mươi nghìn", 50000), ("một trăm hai mươi lăm nghìn", 125000),
    ("hai nghìn rưỡi", 2500), ("một triệu hai", 1_200_000), ("1 triệu 2", 1_200_000), ("hai chục", 20),
    ("125000", 125000), ("50 nghìn", 50000), ("hai muoi lam", 25), ("một nghìn không trăm linh năm", 1005),
    ("chín mươi chín", 99), ("hai tô", 2), ("mười một", 11),
])
def test_parse_number(text, value):
    assert parse_number(text.split())[0] == value


def test_parse_number_stops_at_non_number_and_ambiguity():
    assert parse_number("tấm".split()) == (None, 0)          # "tấm" (cơm tấm) không phải "tám"
    assert parse_number("80 nghìn một người".split()) == (80000, 2)
    assert parse_number("hai ba".split())[0] == 2              # không hiểu nhầm thành 23


@pytest.mark.parametrize("n,words", [
    (55000, "năm mươi lăm nghìn"), (125000, "một trăm hai mươi lăm nghìn"), (205000, "hai trăm linh năm nghìn"),
    (1_050_000, "một triệu không trăm năm mươi nghìn"), (21000, "hai mươi mốt nghìn"), (15000, "mười lăm nghìn"),
    (1_000_000, "một triệu"), (0, "không"),
])
def test_number_to_words(n, words):
    assert number_to_words(n) == words


def test_money_and_tts_normalize():
    assert format_money(1250000) == "1.250.000đ"
    assert money_to_words(30000) == "ba mươi nghìn đồng"
    s = tts_normalize("Tổng 125.000đ, giảm 10%. Quét mã QR.")
    assert "một trăm hai mươi lăm nghìn đồng" in s and "mười phần trăm" in s and "kiu a" in s


def test_normalize_fold_slug():
    assert normalize("Cho tôi 2 Phở, giá 55.000đ hay 50k?") == "cho tôi 2 phở giá 55000 hay 50000"
    assert fold("Cơm tấm sườn ĐẶC BIỆT") == "com tam suon dac biet"
    assert ascii_slug("Thanh toán đơn DH01000123!") == "THANH TOAN DON DH01000123"
