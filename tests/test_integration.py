import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Only run these when a real database is configured (CI sets DATABASE_URL)
pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="needs a real database (set DATABASE_URL)",
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_ready_with_real_database(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_create_then_list_item(client):
    created = client.post("/items", json={"name": "integration-test"})
    assert created.status_code == 201

    items = client.get("/items").json()
    assert created.json() in items


def test_get_missing_item_returns_404(client):
    response = client.get("/items/999999")
    assert response.status_code == 404
