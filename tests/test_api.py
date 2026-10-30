from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# An address where no database is running, so connecting fails immediately
DEAD_DB = "postgresql://user:supersecret@127.0.0.1:1/nodb"


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_503_when_database_is_down(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DEAD_DB)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not ready"


def test_ready_error_does_not_leak_password(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DEAD_DB)
    response = client.get("/ready")
    assert "supersecret" not in response.text


def test_create_item_rejects_empty_name():
    response = client.post("/items", json={"name": ""})
    assert response.status_code == 422


def test_create_item_rejects_too_long_name():
    response = client.post("/items", json={"name": "x" * 101})
    assert response.status_code == 422


def test_create_item_rejects_missing_name():
    response = client.post("/items", json={})
    assert response.status_code == 422

def test_version_endpoint_returns_a_version():
    response = client.get("/version")
    assert response.status_code == 200
    assert "version" in response.json()