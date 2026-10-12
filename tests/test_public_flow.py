import hashlib
import hmac
import json

from tests.conftest import order_body, register


def make_link(client, headers, **body):
    r = client.post("/access-links", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["accessLink"]


def test_access_link_lifecycle_and_public_menu(client, headers, menu):
    _, item = menu
    link = make_link(client, headers, tableNumber="04", label="Table 4", expiresInHours=24)
    assert len(link["token"]) >= 43 and link["tableNumber"] == "04" and link["expiresAt"].endswith("Z")
    assert link["revokedAt"] is None

    r = client.get(f"/public/access/{link['token']}/menu")
    assert r.status_code == 200
    body = r.json()
    assert body["tableNumber"] == "04" and "email" not in body["restaurant"]
    assert [m["id"] for m in body["menuItems"]] == [item["id"]]

    client.patch(f"/menu-items/{item['id']}", headers=headers, json={"isAvailable": False})
    assert client.get(f"/public/access/{link['token']}/menu").json()["menuItems"] == []

    bad = client.get("/public/access/inconnu/menu")
    assert bad.status_code == 404 and bad.json()["error"]["code"] == "ACCESS_LINK_INVALID"

    rev = client.post(f"/access-links/{link['id']}/revoke", headers=headers)
    assert rev.status_code == 200 and rev.json()["accessLink"]["revokedAt"] is not None
    gone = client.get(f"/public/access/{link['token']}/menu")
    assert gone.status_code == 410 and gone.json()["error"]["code"] == "ACCESS_LINK_REVOKED"


def test_order_pricing_table_and_tracking(client, headers, menu):
    _, item = menu
    link = make_link(client, headers, tableNumber="04")
    r = client.post(f"/public/access/{link['token']}/orders", json=order_body(item))
    assert r.status_code == 201, r.text
    order = r.json()["order"]

    assert order["total"] == 40000 and order["subtotal"] == 40000 and order["tax"] == 0  # (18000+2000)*2
    assert order["items"][0]["price"] == 20000 and order["items"][0]["selectedExtras"][0]["price"] == 2000
    assert order["tableNumber"] == "04"  # la table du lien l'emporte
    assert order["orderNumber"] == "#R-101" and order["status"] == "recue"
    assert order["paymentStatus"] == "pending" and order["isPaid"] is False
    assert order["paymentTransactionId"].startswith("TXN-") and "paymentInstructions" in order
    assert order["estimatedDeliveryMinutes"] == 12 and order["trackingToken"].startswith("tk_")

    second = client.post(f"/public/access/{link['token']}/orders", json=order_body(item)).json()["order"]
    assert second["orderNumber"] == "#R-102"

    tracked = client.get(f"/public/orders/{order['trackingToken']}")
    assert tracked.status_code == 200 and tracked.json()["order"]["id"] == order["id"]
    assert client.get("/public/orders/tk_inconnu").status_code == 404

    listed = client.get("/orders", headers=headers).json()["orders"]
    assert [o["orderNumber"] for o in listed] == ["#R-102", "#R-101"]  # plus récent d'abord
    assert client.get("/access-links", headers=headers).json()["accessLinks"][0]["ordersCount"] == 2

    # un lien révoqué n'empêche pas de suivre une commande déjà passée
    client.post(f"/access-links/{link['id']}/revoke", headers=headers)
    assert client.get(f"/public/orders/{order['trackingToken']}").status_code == 200
    assert client.post(f"/public/access/{link['token']}/orders", json=order_body(item)).status_code == 410


def test_order_validation_and_unavailable(client, headers, menu):
    _, item = menu
    link = make_link(client, headers)
    url = f"/public/access/{link['token']}/orders"

    r = client.post(url, json=order_body(item, payerPhone=None))
    assert r.status_code == 400 and "payerPhone" in r.json()["error"]["details"]

    r = client.post(url, json=order_body(item, orderType="livraison", paymentMethod="especes", payerPhone=None))
    assert r.status_code == 400 and "deliveryAddress" in r.json()["error"]["details"]

    bad_sauce = order_body(item)
    bad_sauce["items"][0]["selectedSauce"] = "Inconnue"
    assert client.post(url, json=bad_sauce).status_code == 400

    ok = order_body(
        item, orderType="livraison", paymentMethod="especes", payerPhone=None, tableNumber=None,
        deliveryAddress="Isoraka", deliveryCoordinates={"lat": -18.91, "lng": 47.52},
        deliveryDistanceKm=2.4, deliveryDurationMin=18, deliveryInstructions="Portail bleu",
    )
    r = client.post(url, json=ok)
    assert r.status_code == 201
    o = r.json()["order"]
    assert o["paymentStatus"] == "cash" and o["isPaid"] is False and o["tableNumber"] is None
    assert o["deliveryCoordinates"] == {"lat": -18.91, "lng": 47.52} and o["estimatedDeliveryMinutes"] == 30

    client.patch(f"/menu-items/{item['id']}", headers=headers, json={"isAvailable": False})
    r = client.post(url, json=order_body(item))
    assert r.status_code == 422 and r.json()["error"]["code"] == "ITEM_UNAVAILABLE"


def test_status_flow_and_isolation(client, headers, menu):
    _, item = menu
    link = make_link(client, headers)
    order = client.post(
        f"/public/access/{link['token']}/orders",
        json=order_body(item, paymentMethod="especes", payerPhone=None),
    ).json()["order"]

    r = client.patch(f"/orders/{order['id']}/status", headers=headers,
                     json={"status": "en_livraison", "deliveryPersonName": "Faly"})
    assert r.status_code == 200 and r.json()["order"]["deliveryPersonName"] == "Faly"
    assert client.patch(f"/orders/{order['id']}/status", headers=headers, json={"status": "livree"}).status_code == 200
    r = client.patch(f"/orders/{order['id']}/status", headers=headers, json={"status": "recue"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    assert client.patch(f"/orders/{order['id']}/status", headers=headers, json={"status": "nimporte"}).status_code == 400

    _, other = register(client, email="autre@exemple.com", name="Autre")
    assert client.patch(f"/orders/{order['id']}/status", headers=other, json={"status": "prete"}).status_code == 404
    assert client.get("/orders", headers=other).json() == {"orders": []}
    # un jeton de lien n'ouvre aucune route admin
    assert client.get("/orders", headers={"Authorization": f"Bearer {link['token']}"}).status_code == 401


def test_mock_payment_confirmation(client, headers, menu):
    _, item = menu
    link = make_link(client, headers)
    order = client.post(f"/public/access/{link['token']}/orders", json=order_body(item, paymentMethod="carte_bancaire",
                        payerPhone=None)).json()["order"]
    assert order["paymentRedirectUrl"].endswith("/checkout") and order["paymentStatus"] == "pending"

    txn = order["paymentTransactionId"]
    assert client.get(f"/dev/payments/{txn}/checkout").status_code == 200
    r = client.get(f"/dev/payments/{txn}/complete?result=paid", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith(f"/?t={link['token']}")

    tracked = client.get(f"/public/orders/{order['trackingToken']}").json()["order"]
    assert tracked["isPaid"] is True and tracked["paymentStatus"] == "paid" and "paymentRedirectUrl" not in tracked


def test_payment_webhook_signature(client, headers, menu):
    _, item = menu
    link = make_link(client, headers)
    order = client.post(f"/public/access/{link['token']}/orders", json=order_body(item)).json()["order"]

    raw = json.dumps({"transactionId": order["paymentTransactionId"], "status": "paid"}).encode()
    sig = hmac.new(b"whsec", raw, hashlib.sha256).hexdigest()
    ctype = {"Content-Type": "application/json"}

    assert client.post("/webhooks/payments", content=raw, headers={**ctype, "X-Signature": "00"}).status_code == 401
    assert client.post("/webhooks/payments", content=raw, headers=ctype).status_code == 401
    ok = client.post("/webhooks/payments", content=raw, headers={**ctype, "X-Signature": sig})
    assert ok.status_code == 200

    tracked = client.get(f"/public/orders/{order['trackingToken']}").json()["order"]
    assert tracked["isPaid"] is True
