from aistaff.cart import Cart
from aistaff.promotions import PromotionEngine

from .conftest import SAT_NOON, TUE_HAPPY, WED_MORNING


def cart_of(cfg, *pairs):
    c = Cart()
    for eid, q in pairs:
        c.add(cfg.menu.get(eid), q)
    return c


def test_schedule(cfg):
    eng = PromotionEngine(cfg)
    ids = lambda now: {p.id for p in eng.active(now)}  # noqa: E731
    assert {"gio-vang", "thu-ba-combo"} <= ids(TUE_HAPPY)
    assert "gio-vang" not in ids(WED_MORNING) and "cuoi-tuan" in ids(SAT_NOON)


def test_percent_off_with_cap_and_rounding(cfg):
    eng = PromotionEngine(cfg)
    pb = eng.price(cart_of(cfg, ("pho-dac-biet", 2), ("com-tam", 1)), TUE_HAPPY)  # 210k
    # stackable: tặng chè (25k) > giờ vàng 10% (21k) -> chọn phương án có lợi nhất
    assert [a.id for a in pb.applied] == ["hoa-don-200k-tang-che"] and pb.total == 210000
    pb = eng.price(cart_of(cfg, ("pho-dac-biet", 2), ("com-tam", 1), ("bun-bo-hue", 1)), TUE_HAPPY)  # 270k
    assert pb.applied[0].id == "gio-vang" and pb.discount == 27000 and pb.total == 243000
    pb = eng.price(cart_of(cfg, ("pho-dac-biet", 6)), TUE_HAPPY)  # 450k -> 45k nhưng tối đa 30k
    assert pb.discount == 30000


def test_combo_percent_on_tuesday(cfg):
    pb = PromotionEngine(cfg).price(cart_of(cfg, ("combo-doi", 1)), TUE_HAPPY)
    assert pb.discount == 22000 and pb.total == 127000  # 15% của 149k = 22.35k -> làm tròn xuống 22k


def test_buy_x_get_y_and_hint(cfg):
    eng = PromotionEngine(cfg)
    pb = eng.price(cart_of(cfg, ("tra-tac", 4)), WED_MORNING)
    assert pb.free_items[0].entry_id == "tra-tac" and pb.free_items[0].qty == 2
    pb = eng.price(cart_of(cfg, ("tra-tac", 1)), WED_MORNING)
    assert any("tặng" in h.message for h in pb.hints)


def test_near_miss_hint(cfg):
    pb = PromotionEngine(cfg).price(cart_of(cfg, ("pho-dac-biet", 2)), TUE_HAPPY)  # 150k, giờ vàng đã áp
    hints = {h.id: h for h in pb.hints}
    assert hints["hoa-don-200k-tang-che"].missing_amount == 50000


def test_weekend_amount_off(cfg):
    pb = PromotionEngine(cfg).price(cart_of(cfg, ("combo-gia-dinh", 1)), SAT_NOON)  # 289k
    # tặng chè 25k (stackable) > giảm 20k (độc quyền)
    assert pb.free_items and pb.total == 289000
    pb = PromotionEngine(cfg).price(cart_of(cfg, ("pho-dac-biet", 4)), SAT_NOON)  # 300k
    assert {a.id for a in pb.applied} == {"hoa-don-200k-tang-che"}


def test_vat_when_not_included(cfg):
    c2 = cfg.model_copy(deep=True)
    c2.store.pricing.prices_include_vat = False
    c2.store.pricing.vat_percent = 8
    pb = PromotionEngine(c2).price(cart_of(c2, ("pho-ga", 2)), WED_MORNING)
    assert pb.vat == 8000 and pb.total == 108000
