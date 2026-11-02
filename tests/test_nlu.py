import pytest

from aistaff.nlu import NLU


@pytest.fixture(scope="module")
def nlu(cfg):
    return NLU(cfg.menu)


def items(r):
    return [(m.entry_id, m.qty) for m in r.items]


def test_order_with_quantities(nlu):
    r = nlu.parse("cho tôi hai tô phở bò tái và một ly trà đá")
    assert r.intent == "add" and items(r) == [("pho-bo-tai", 2), ("tra-da", 1)]


def test_asr_uppercase_and_no_diacritics(nlu):
    assert items(nlu.parse("CHO TÔI HAI TÔ PHỞ BÒ TÁI")) == [("pho-bo-tai", 2)]
    assert items(nlu.parse("cho toi 2 pho bo tai voi 1 tra tac")) == [("pho-bo-tai", 2), ("tra-tac", 1)]


def test_asr_errors_are_tolerated(nlu):
    assert items(nlu.parse("thêm một phần cầm tấm sườn bì chả")) == [("com-tam", 1)]
    assert nlu.parse("thôi chốt đơn vị").intent == "checkout"
    assert items(nlu.parse("cho anh một combo gia đình với hài ly trà tắc")) == [("combo-gia-dinh", 1), ("tra-tac", 2)]


def test_no_false_positive_dishes(nlu):
    r = nlu.parse("tôi muốn ăn món gì cay cay không có thịt bò")
    assert r.items == [] and r.intent == "ask_recommend"
    assert r.prefs.likes == {"cay": 1} and "bò" in r.prefs.exclude
    assert nlu.parse("nhà có 4 người").items == []          # không nhầm thành "combo 4 người"
    assert nlu.parse("lấy combo đó").intent == "select"    # "đó" != "đôi"


def test_generic_needs_clarification(nlu):
    r = nlu.parse("cho 2 phở")
    assert r.intent == "add_generic" and r.generic[0].qty == 2 and len(r.generic[0].candidates) == 4
    assert len(nlu.parse("cho 2 phở bò").generic[0].candidates) == 2


def test_remove_set_swap(nlu):
    assert nlu.parse("bỏ bớt một ly cà phê sữa đá").intent == "remove"
    r = nlu.parse("trà đá thành 3 ly")
    assert r.intent == "set_qty" and r.target_qty == 3
    assert nlu.parse("đổi phở bò tái thành phở gà").intent == "swap"


def test_options_and_notes(nlu):
    r = nlu.parse("phở bò tái tô lớn không hành")
    m = r.items[0]
    assert (m.entry_id, m.option_id, m.note) == ("pho-bo-tai", "lon", "không hành")
    assert "hành" not in r.prefs.exclude  # ghi chú món không thành kiêng toàn cục
    assert nlu.parse("trà tắc ít đường nhiều đá").items[0].note == "ít đường, nhiều đá"


def test_preferences(nlu):
    p = nlu.parse("nhà có 4 người, không ăn được cay, dưới 80 nghìn một người").prefs
    assert p.group_size == 4 and "cay" in p.dislikes and p.budget == 80000
    p = nlu.parse("mình ăn chay, có món nào thanh đạm không").prefs
    assert p.vegetarian and p.light
    assert {"tôm", "cua", "hải sản"} <= nlu.parse("dị ứng hải sản").prefs.exclude
    assert nlu.parse("tôi muốn uống gì đó mát mát").prefs.categories == {"do-uong"}


@pytest.mark.parametrize("text,intent", [
    ("gợi ý cho anh món gì ngon đi", "ask_recommend"), ("có khuyến mãi gì không", "ask_promo"),
    ("tổng cộng bao nhiêu tiền", "view_cart"), ("phở đặc biệt giá bao nhiêu", "ask_price"),
    ("bún bò huế có cay không", "ask_info"), ("trả tiền mặt nhé", "pay_cash"), ("hủy đơn", "cancel"),
    ("xin chào", "greet"), ("đúng rồi", "yes"), ("không", "no"), ("lấy món thứ hai", "select"),
    ("thêm 1 ly nữa", "add_more"), ("có combo nào cho 2 người không", "ask_recommend"),
])
def test_intents(nlu, text, intent):
    assert nlu.parse(text).intent == intent


def test_takeaway_and_speed(nlu):
    import time

    assert nlu.parse("cho 3 cơm tấm mang về").takeaway is True
    t0 = time.perf_counter()
    for _ in range(50):
        nlu.parse("cho tôi hai tô phở bò tái và một ly trà đá")
    assert (time.perf_counter() - t0) / 50 < 0.02  # < 20 ms/câu kể cả máy CI chậm


def test_asr_combo_confusion_fix(nlu):
    # ASR hay nghe "combo" thành "còn một"/"có một"/"cơm bô"
    assert items(nlu.parse("cho anh một còn một gia đình")) == [("combo-gia-dinh", 1)]
    assert items(nlu.parse("lấy cơm bô đôi"))[0][0] == "combo-doi"
    # nhưng không sửa khi là câu kể bình thường
    r = nlu.parse("có một gia đình bốn người")
    assert r.items == [] and r.prefs.group_size == 4
