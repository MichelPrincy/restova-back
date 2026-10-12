import os
import tempfile

# Variables d'environnement AVANT d'importer l'application.
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'test.db')}"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"
os.environ["ENV"] = "development"
os.environ["PAYMENT_PROVIDER"] = "mock"
os.environ["PAYMENT_WEBHOOK_SECRET"] = "whsec"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models as _models  # noqa: E402,F401
from app.database import Base, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.ratelimit import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limiter.reset_all()
    yield


@pytest.fixture
def client():
    with TestClient(fastapi_app) as c:
        yield c


def register(client, email="owner@exemple.com", name="Chez Rakoto Burger", **extra):
    body = {
        "restaurantName": name, "email": email, "password": "motdepasse123",
        "phone": "+261 34 00 000 00", "address": "Analakely, Antananarivo 101",
        "latitude": -18.9086, "longitude": 47.5253, **extra,
    }
    r = client.post("/auth/register", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    return data, {"Authorization": f"Bearer {data['token']}"}


@pytest.fixture
def owner(client):
    return register(client)


@pytest.fixture
def headers(owner):
    return owner[1]


@pytest.fixture
def menu(client, headers):
    """Une catégorie + un plat (sauces et extras) ; renvoie (category, item)."""
    cat = client.post("/categories", headers=headers, json={"name": "Burgers", "icon": "🍔"}).json()["category"]
    item = client.post("/menu-items", headers=headers, json={
        "name": "Double Cheese", "description": "Deux steaks", "price": 18000, "category": cat["id"],
        "preparationTimeMinutes": 12, "ingredients": ["Pain", "Steak"],
        "options": {"sauces": ["Barbecue", "Mayo"], "extras": [{"id": "ext_1", "name": "Bacon", "price": 2000}]},
    }).json()["menuItem"]
    return cat, item


def order_body(item, **over):
    body = {
        "customerName": "Hery", "customerPhone": "+261 34 11 111 11", "orderType": "sur_place",
        "tableNumber": "99",
        "items": [{
            "id": "ci_1", "menuItemId": item["id"], "name": item["name"], "price": 1,  # prix client ignoré
            "quantity": 2, "selectedSauce": "Barbecue",
            "selectedExtras": [{"id": "ext_1", "name": "Bacon", "price": 1}],
        }],
        "paymentMethod": "mvola", "payerPhone": "+261 34 22 222 22",
    }
    body.update(over)
    return body
