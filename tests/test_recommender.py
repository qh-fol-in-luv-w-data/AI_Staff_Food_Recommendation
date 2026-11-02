from aistaff.nlu import Preferences
from aistaff.promotions import PromotionEngine
from aistaff.recommender import Recommender

from .conftest import TUE_HAPPY, WED_MORNING


def rec(cfg, now=WED_MORNING, **kw):
    return Recommender(cfg, PromotionEngine(cfg)).recommend(Preferences(**kw), now=now)


def test_vegetarian_only_veg(cfg):
    out = rec(cfg, vegetarian=True)
    assert out and all(cfg.menu.get(r.entry_id).is_vegetarian for r in out)


def test_exclusions_and_budget(cfg):
    for r in rec(cfg, exclude={"bò"}, budget=60000):
        e = cfg.menu.get(r.entry_id)
        assert "bò" not in e.contains and e.price // getattr(e, "serves", 1) <= 60000


def test_spicy_lover_gets_spicy(cfg):
    top = rec(cfg, likes={"cay": 1})[0]
    assert cfg.menu.get(top.entry_id).taste.cay >= 2 and "vị cay" in top.reasons


def test_no_spicy_filter(cfg):
    assert all(cfg.menu.get(r.entry_id).taste.cay < 2 for r in rec(cfg, dislikes={"cay"}))


def test_group_gets_matching_combo(cfg):
    out = rec(cfg, group_size=2, categories={"combo"})
    assert out[0].entry_id == "combo-doi" and "vừa cho 2 người" in out[0].reasons


def test_promo_reason(cfg):
    out = rec(cfg, now=TUE_HAPPY, categories={"combo"})
    assert any("đang có ưu đãi" in r.reasons for r in out)


def test_upsell_drink(cfg):
    from aistaff.cart import Cart

    c = Cart()
    c.add(cfg.menu.get("pho-bo-tai"), 1)
    up = Recommender(cfg, PromotionEngine(cfg)).upsell(c, Preferences(), WED_MORNING)
    assert up and cfg.menu.get(up.entry_id).is_drink
