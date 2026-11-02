import copy

import pytest
import yaml
from pydantic import ValidationError

from aistaff.config import Menu, Payment, load_store

from .conftest import STORE


def test_load_sample_store(cfg):
    assert cfg.store.payment.bank_bin == "970436"
    assert len(cfg.menu.items) >= 20 and len(cfg.menu.combos) == 4
    fam = cfg.menu.get("combo-gia-dinh")
    assert "bò" in fam.contains and fam.diet == []            # thuộc tính combo suy ra từ món con
    assert cfg.menu.get("combo-chay").is_vegetarian
    assert cfg.menu.combo_value(fam) == 325000


def test_menu_rejects_bad_references():
    data = yaml.safe_load((STORE / "menu.yaml").read_text(encoding="utf-8"))
    bad = copy.deepcopy(data)
    bad["combos"][0]["items"][0]["item"] = "khong-ton-tai"
    with pytest.raises(ValidationError):
        Menu(**bad)
    bad = copy.deepcopy(data)
    bad["items"].append(copy.deepcopy(bad["items"][0]))  # trùng id
    with pytest.raises(ValidationError):
        Menu(**bad)


def test_payment_validation():
    with pytest.raises(ValidationError):
        Payment(bank_bin="12345", account_number="0123456789")
    with pytest.raises(ValidationError):
        Payment(bank_bin="970436", account_number="01-23")
    assert Payment(bank_bin="970436", account_number="0123 456 789", order_prefix="dh").order_prefix == "DH"
