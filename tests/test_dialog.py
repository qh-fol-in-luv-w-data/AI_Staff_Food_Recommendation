from .conftest import SAT_NOON, TUE_HAPPY


def lines(r):
    return {(ln["entry_id"], ln["qty"]) for ln in r.cart["lines"]}


def test_greeting_introduces_promotions(make_dm):
    dm = make_dm(TUE_HAPPY)
    r = dm.greet(dm.new_session(seed=1))
    assert "Mai" in r.text and "ưu đãi" in r.text and "giảm 10 phần trăm" in r.text


def test_full_voice_like_flow(make_dm, storage):
    dm = make_dm(TUE_HAPPY)
    s = dm.new_session(seed=1)
    dm.greet(s)
    r = dm.handle(s, "gợi ý cho anh món gì ngon đi")
    assert r.intent == "ask_pref" and s.state == "asking_pref"  # hỏi khẩu vị trước khi gợi ý
    r = dm.handle(s, "anh thích ăn cay, không ăn được hải sản")
    assert r.intent == "recommend" and r.recommendations
    first = r.recommendations[0]["entry_id"]
    r = dm.handle(s, "lấy món thứ nhất")
    assert (first, 1) in lines(r)
    r = dm.handle(s, "không")  # từ chối upsell / không thêm gì -> có thể sang chốt đơn
    if r.state != "confirm_order":
        r = dm.handle(s, "chốt đơn")
    assert r.state == "confirm_order" and "TỔNG CỘNG" in r.text
    r = dm.handle(s, "đúng rồi")
    assert r.state == "awaiting_payment" and r.qr and r.qr["amount"] == r.cart["total"]
    order = storage.get_order(r.qr["code"])
    assert order.status == "pending_payment" and order.qr_payload == r.qr["payload"]
    r = dm.payment_received(s)
    assert r.state == "done" and r.end and "Cảm ơn" in r.text


def test_clarify_generic_then_choose_by_word(make_dm):
    dm = make_dm()
    s = dm.new_session(seed=2)
    dm.greet(s)
    r = dm.handle(s, "cho 2 phở bò")
    assert r.intent == "clarify" and {o["entry_id"] for o in r.options} == {"pho-bo-tai", "pho-bo-chin"}
    r = dm.handle(s, "tái")
    assert ("pho-bo-tai", 2) in lines(r)


def test_edit_cart(make_dm):
    dm = make_dm()
    s = dm.new_session(seed=3)
    dm.greet(s)
    dm.handle(s, "cho tôi hai tô phở bò tái và một ly trà đá")
    r = dm.handle(s, "trà đá thành 3 ly")
    assert ("tra-da", 3) in lines(r)
    r = dm.handle(s, "bỏ trà đá")
    assert all(e != "tra-da" for e, _ in lines(r))
    r = dm.handle(s, "đổi phở bò tái thành phở gà")
    assert lines(r) == {("pho-ga", 2)}


def test_upsell_accept(make_dm):
    dm = make_dm()
    s = dm.new_session(seed=4)
    dm.greet(s)
    r = dm.handle(s, "cho một phở gà")
    assert s.pending and s.pending["type"] == "upsell"
    up = s.pending["entry_id"]
    r = dm.handle(s, "có")
    assert (up, 1) in lines(r)


def test_promo_hint_after_add(make_dm):
    dm = make_dm(TUE_HAPPY)
    s = dm.new_session(seed=5)
    dm.greet(s)
    r = dm.handle(s, "cho một phở đặc biệt")
    assert "gọi thêm 25.000đ" in r.text  # 75k -> còn 25k là đạt giờ vàng 100k


def test_cash_payment(make_dm, storage):
    dm = make_dm(SAT_NOON)
    s = dm.new_session(seed=6)
    dm.greet(s)
    dm.handle(s, "cho 2 cơm tấm")
    r = dm.handle(s, "thanh toán tiền mặt")
    assert r.state == "confirm_order"
    r = dm.handle(s, "đúng rồi")
    assert r.state == "awaiting_cash" and storage.get_order(s.order_code).payment_method == "cash"


def test_modify_while_awaiting_payment_cancels_qr(make_dm, storage):
    dm = make_dm()
    s = dm.new_session(seed=7)
    dm.greet(s)
    dm.handle(s, "cho 1 bún chả")
    dm.handle(s, "chốt đơn")
    r = dm.handle(s, "quét mã")
    old = r.qr["code"]
    r = dm.handle(s, "thêm 1 trà đá")
    assert storage.get_order(old).status == "cancelled" and s.state == "ordering" and ("tra-da", 1) in lines(r)


def test_touch_actions_share_state(make_dm):
    dm = make_dm()
    s = dm.new_session(seed=8)
    dm.handle_action(s, {"type": "add", "entry_id": "bun-cha", "qty": 2})
    r = dm.handle(s, "xem lại đơn")
    assert "2 Bún chả" in r.text
    r = dm.handle_action(s, {"type": "confirm", "method": "vietqr"})
    assert r.qr and r.qr["amount"] == 110000


def test_unknown_and_recovery(make_dm):
    dm = make_dm()
    s = dm.new_session(seed=9)
    dm.greet(s)
    assert dm.handle(s, "blah blah xyz").intent == "unknown"
    assert dm.handle(s, "cho 1 trà tắc").intent == "add"


def test_latency_budget(make_dm):
    import time

    dm = make_dm()
    s = dm.new_session(seed=10)
    dm.greet(s)
    t0 = time.perf_counter()
    for u in ["cho tôi hai tô phở bò tái", "gợi ý món cay", "có khuyến mãi gì không", "xem lại đơn"]:
        dm.handle(s, u)
    assert (time.perf_counter() - t0) / 4 < 0.05


def test_clarify_by_ordinal_keeps_quantity(make_dm):
    dm = make_dm()
    s = dm.new_session(seed=11)
    dm.greet(s)
    r = dm.handle(s, "cho 3 phở")
    second = r.options[1]["entry_id"]
    r = dm.handle(s, "món thứ hai")  # "hai" là thứ tự, không phải số lượng
    assert (second, 3) in lines(r)
