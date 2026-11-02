import os

from aistaff.payments import PaymentHub


def new_order(storage, total=104000):
    return storage.create_order("s", 1, "DH", [{"name": "Phở bò tái", "qty": 2}], [], total, 0, 0, total)


def test_order_code_and_status(storage):
    o = new_order(storage)
    assert o.code == "DH01000001" and o.status == "pending_payment" and o.expires_at
    assert storage.mark_paid(o.code, "x") and not storage.mark_paid(o.code, "x")  # idempotent
    assert storage.get_order("dh01000001").status == "paid"
    assert storage.stats()["revenue"] == 104000


def test_cash_order(storage):
    o = storage.create_order("s", 2, "DH", [], [], 10, 0, 0, 10, payment_method="cash")
    assert o.code == "DH02000001" and o.status == "awaiting_cash" and o.expires_at is None


def test_match_transaction(cfg, storage):
    paid = []
    hub = PaymentHub(cfg, storage, on_paid=paid.append)
    o = new_order(storage)
    assert hub.find_code("MBVCB.123.DH01000001 thanh toan") == "DH01000001"
    assert hub.find_code("chuyen tien dh 01 000001") == "DH01000001"
    assert hub.process_transaction("sepay", "t1", 50000, f"{o.code}", {}) == "underpaid"
    assert hub.process_transaction("sepay", "t1", 104000, f"{o.code}", {}) == "duplicate"
    assert hub.process_transaction("sepay", "t2", 104000, f"CK {o.code} quet QR", {}) == "paid"
    assert paid and paid[0].order_code == o.code
    assert hub.process_transaction("sepay", "t3", 1000, "khong co ma", {}) == "unmatched"


def test_sepay_webhook_auth(cfg, storage, monkeypatch):
    hub = PaymentHub(cfg, storage)
    o = new_order(storage)
    body = {"id": 92704, "gateway": "Vietcombank", "transactionDate": "2026-11-03 15:01:00", "accountNumber": "0123456789",
            "code": None, "content": f"{o.code} chuyen tien", "transferType": "in", "transferAmount": 104000,
            "accumulated": 0, "subAccount": None, "referenceCode": "FT1", "description": ""}
    assert hub.sepay_webhook("Apikey x", body)[0] == 503  # chưa cấu hình key
    monkeypatch.setenv("SEPAY_WEBHOOK_API_KEY", "secret")
    assert hub.sepay_webhook("Apikey wrong", body)[0] == 401
    assert hub.sepay_webhook("Apikey secret", {**body, "transferType": "out"})[1]["message"] == "ignored"
    code, resp = hub.sepay_webhook("Apikey secret", body)
    assert code == 200 and resp["result"] == "paid"
    assert hub.sepay_webhook("Apikey secret", body)[1]["result"] == "duplicate"
    assert os.environ.get("SEPAY_WEBHOOK_API_KEY") == "secret"
