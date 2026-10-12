from tests.conftest import register


def test_register_login_me_logout(client):
    data, headers = register(client)
    assert data["user"]["email"] == "owner@exemple.com"
    r = data["restaurant"]
    assert r["currency"] == "Ar" and r["logoUrl"] == "" and r["openingHours"] == "" and r["tagline"] == ""
    assert r["email"] == "owner@exemple.com" and r["createdAt"].endswith("Z")
    assert "password" not in str(data).lower()

    login = client.post("/auth/login", json={"email": " Owner@Exemple.com ", "password": "motdepasse123"})
    assert login.status_code == 200 and login.json()["user"]["id"] == data["user"]["id"]

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["restaurant"]["id"] == r["id"]

    assert client.post("/auth/logout", headers=headers).status_code == 204
    after = client.get("/auth/me", headers=headers)
    assert after.status_code == 401 and after.json()["error"]["code"] == "UNAUTHORIZED"


def test_register_validation_codes(client):
    base = {
        "restaurantName": "X", "email": "a@b.com", "password": "secret1", "phone": "1",
        "address": "A", "latitude": 0, "longitude": 0,
    }
    r = client.post("/auth/register", json={**base, "email": "pas-un-email"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_EMAIL"

    r = client.post("/auth/register", json={**base, "password": "123"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "WEAK_PASSWORD"

    bad = {k: v for k, v in base.items() if k != "phone"}
    r = client.post("/auth/register", json=bad)
    err = r.json()["error"]
    assert r.status_code == 400 and err["code"] == "VALIDATION_ERROR" and "phone" in err["details"]

    r = client.post("/auth/register", json={**base, "latitude": 123})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_duplicate_email(client):
    register(client)
    r = client.post("/auth/register", json={
        "restaurantName": "Autre", "email": "OWNER@exemple.com", "password": "secret1",
        "phone": "1", "address": "A", "latitude": 0, "longitude": 0,
    })
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_ALREADY_IN_USE"


def test_login_errors_are_indistinguishable(client):
    register(client)
    wrong_pw = client.post("/auth/login", json={"email": "owner@exemple.com", "password": "mauvais"})
    unknown = client.post("/auth/login", json={"email": "inconnu@exemple.com", "password": "motdepasse123"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()
    assert wrong_pw.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_rate_limit(client):
    register(client)
    codes = [
        client.post("/auth/login", json={"email": "owner@exemple.com", "password": "x"}).status_code
        for _ in range(10)
    ]
    assert codes[:8] == [401] * 8 and codes[8] == 429


def test_protected_routes_need_token(client):
    for path in ("/auth/me", "/orders", "/categories", "/menu-items", "/stock-items", "/access-links"):
        r = client.get(path)
        assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED", path
    r = client.get("/orders", headers={"Authorization": "Bearer n-importe-quoi"})
    assert r.status_code == 401


def test_update_profile(client, headers):
    body = {
        "name": "Nouveau Nom", "address": "Isoraka", "latitude": -18.91, "longitude": 47.52,
        "phone": "+261 34 99 999 99", "logoUrl": "", "openingHours": "10h00 - 22h00",
        "currency": "Ar", "email": "contact@exemple.com", "tagline": "Burgers gourmands",
    }
    r = client.put("/restaurant/profile", headers=headers, json=body)
    assert r.status_code == 200
    rest = r.json()["restaurant"]
    assert rest["name"] == "Nouveau Nom" and rest["openingHours"] == "10h00 - 22h00"
    assert client.get("/auth/me", headers=headers).json()["restaurant"]["tagline"] == "Burgers gourmands"
