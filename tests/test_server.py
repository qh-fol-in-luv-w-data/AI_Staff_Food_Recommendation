import json

import pytest
from fastapi.testclient import TestClient

from aistaff.kiosk.server import create_app

from .conftest import STORE, TUE_HAPPY


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("ADMIN_PIN", raising=False)
    app = create_app(STORE, tmp_path / "t.db", tmp_path, speech=False, now_fn=lambda: TUE_HAPPY)
    with TestClient(app) as c:
        yield c


def recv_until(ws, kind):
    for _ in range(20):
        m = json.loads(ws.receive_text())
        if m["type"] == kind:
            return m
    raise AssertionError(kind)


def test_config_endpoint(client):
    d = client.get("/api/config").json()
    assert d["store"]["assistant"] == "Mai" and any(e["kind"] == "combo" for e in d["entries"])
    assert client.get("/healthz").json()["ok"]
    assert "Gọi món" in client.get("/").text


def test_ws_order_to_payment(client, monkeypatch):
    with client.websocket_connect("/ws") as ws:
        sess = recv_until(ws, "session")
        ws.send_text(json.dumps({"type": "start"}))
        assert "Mai" in recv_until(ws, "reply")["text"]
        ws.send_text(json.dumps({"type": "text", "text": "cho tôi hai tô phở bò tái và một ly trà đá"}))
        r = recv_until(ws, "reply")
        assert r["cart"]["subtotal"] == 115000
        ws.send_text(json.dumps({"type": "action", "action": {"type": "confirm", "method": "vietqr"}}))
        r = recv_until(ws, "reply")
        code = r["qr"]["code"]
        assert r["state"] == "awaiting_payment" and r["qr"]["svg"].startswith("<svg")
        # nhân viên xác nhận (localhost không cần PIN)
        assert client.post(f"/api/admin/orders/{code}/paid").json()["ok"]
        paid = recv_until(ws, "reply")
        assert paid["intent"] == "paid" and paid["state"] == "done"
    orders = client.get("/api/admin/orders").json()
    assert orders[0]["status"] == "paid" and orders[0]["payment_ref"].startswith("manual")
    assert sess["session_id"]


def test_sepay_webhook_marks_paid(client, monkeypatch):
    monkeypatch.setenv("SEPAY_WEBHOOK_API_KEY", "k")
    with client.websocket_connect("/ws") as ws:
        recv_until(ws, "session")
        ws.send_text(json.dumps({"type": "action", "action": {"type": "add", "entry_id": "bun-cha", "qty": 1}}))
        recv_until(ws, "reply")
        ws.send_text(json.dumps({"type": "action", "action": {"type": "confirm"}}))
        r = recv_until(ws, "reply")
        code, amount = r["qr"]["code"], r["qr"]["amount"]
        body = {"id": 1, "transferType": "in", "transferAmount": amount, "content": f"{code} ck", "code": None}
        assert client.post("/webhooks/sepay", json=body, headers={"Authorization": "Apikey bad"}).status_code == 401
        resp = client.post("/webhooks/sepay", json=body, headers={"Authorization": "Apikey k"})
        assert resp.json()["result"] == "paid"
        assert recv_until(ws, "reply")["intent"] == "paid"


def test_admin_requires_pin_when_set(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PIN", "9999")
    assert client.get("/api/admin/orders").status_code == 401
    assert client.get("/api/admin/orders?pin=9999").status_code == 200
