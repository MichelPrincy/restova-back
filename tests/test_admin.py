from tests.conftest import register


def test_categories_and_menu_flow(client, headers, menu):
    cat, item = menu
    assert item["price"] == 18000 and item["category"] == cat["id"]
    assert item["options"]["extras"][0] == {"id": "ext_1", "name": "Bacon", "price": 2000}
    assert "description" not in cat  # absente si vide

    dup = client.post("/categories", headers=headers, json={"name": "burgers"})
    assert dup.status_code == 409

    r = client.patch(f"/menu-items/{item['id']}", headers=headers, json={"isAvailable": False})
    assert r.status_code == 200 and r.json()["menuItem"]["isAvailable"] is False
    assert r.json()["menuItem"]["name"] == "Double Cheese"

    r = client.delete(f"/categories/{cat['id']}", headers=headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CATEGORY_NOT_EMPTY"

    assert client.delete(f"/menu-items/{item['id']}", headers=headers).status_code == 204
    assert client.delete(f"/categories/{cat['id']}", headers=headers).status_code == 204
    assert client.get("/menu-items", headers=headers).json() == {"menuItems": []}


def test_menu_item_validation(client, headers, menu):
    cat, _ = menu
    r = client.post("/menu-items", headers=headers, json={"name": "X", "price": 10, "category": "cat_inconnue"})
    assert r.status_code == 400 and "category" in r.json()["error"]["details"]
    r = client.post("/menu-items", headers=headers, json={"name": "X", "price": -1, "category": cat["id"]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_stock_quantity(client, headers):
    s = client.post("/stock-items", headers=headers, json={
        "name": "Steak haché", "category": "Viandes", "quantity": 40, "unit": "kg",
        "minThreshold": 10, "costPerUnit": 18000, "supplier": "Boucherie Centrale",
    })
    assert s.status_code == 201
    item = s.json()["stockItem"]
    assert item["quantity"] == 40 and item["supplier"] == "Boucherie Centrale"

    r = client.patch(f"/stock-items/{item['id']}/quantity", headers=headers, json={"delta": -5})
    assert r.json()["stockItem"]["quantity"] == 35
    r = client.patch(f"/stock-items/{item['id']}/quantity", headers=headers, json={"delta": -500})
    assert r.json()["stockItem"]["quantity"] == 0  # plancher à 0
    r = client.patch(f"/stock-items/{item['id']}/quantity", headers=headers, json={"quantity": 12})
    assert r.json()["stockItem"]["quantity"] == 12 and r.json()["stockItem"]["lastUpdated"].endswith("Z")
    r = client.patch(f"/stock-items/{item['id']}/quantity", headers=headers, json={"delta": 1, "quantity": 2})
    assert r.status_code == 400
    assert client.delete(f"/stock-items/{item['id']}", headers=headers).status_code == 204


def test_tenant_isolation(client, headers, menu):
    cat, item = menu
    stock = client.post("/stock-items", headers=headers, json={
        "name": "Pain", "category": "Boulangerie", "quantity": 5, "unit": "u", "minThreshold": 1, "costPerUnit": 100,
    }).json()["stockItem"]
    _, other = register(client, email="autre@exemple.com", name="Autre")

    assert client.get("/menu-items", headers=other).json() == {"menuItems": []}
    assert client.get("/categories", headers=other).json() == {"categories": []}
    assert client.patch(f"/menu-items/{item['id']}", headers=other, json={"name": "Piraté"}).status_code == 404
    assert client.delete(f"/menu-items/{item['id']}", headers=other).status_code == 404
    assert client.patch(f"/categories/{cat['id']}", headers=other, json={"name": "P"}).status_code == 404
    assert client.patch(f"/stock-items/{stock['id']}/quantity", headers=other, json={"delta": 1}).status_code == 404
    # un plat ne peut pas être rangé dans la catégorie d'une autre enseigne
    r = client.post("/menu-items", headers=other, json={"name": "X", "price": 1, "category": cat["id"]})
    assert r.status_code == 400


def test_purge_data(client, headers, menu):
    assert client.delete("/restaurant/data", headers=headers).status_code == 204
    assert client.get("/categories", headers=headers).json() == {"categories": []}
    assert client.get("/menu-items", headers=headers).json() == {"menuItems": []}
    assert client.get("/auth/me", headers=headers).status_code == 200  # compte conservé
