"""API Gateway tests — each test gets its own isolated SQLite DB."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    # Re-import so init_db() runs against the test DB
    import importlib
    import app.main as m
    importlib.reload(m)
    return TestClient(m.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_add_service(client):
    r = client.post("/api/services", json={"name": "TestSvc", "url": "https://example.com"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "TestSvc"
    assert data["id"] == 1


def test_list_services_empty(client):
    r = client.get("/api/services")
    assert r.status_code == 200
    assert r.json() == []


def test_list_services(client):
    client.post("/api/services", json={"name": "A", "url": "https://a.com"})
    client.post("/api/services", json={"name": "B", "url": "https://b.com"})
    r = client.get("/api/services")
    assert len(r.json()) == 2


def test_duplicate_service(client):
    client.post("/api/services", json={"name": "Dup", "url": "https://dup.com"})
    r = client.post("/api/services", json={"name": "Dup", "url": "https://dup2.com"})
    assert r.status_code == 400


def test_get_service(client):
    client.post("/api/services", json={"name": "S1", "url": "https://s1.com"})
    r = client.get("/api/services/1")
    assert r.status_code == 200
    assert r.json()["name"] == "S1"


def test_get_service_not_found(client):
    r = client.get("/api/services/999")
    assert r.status_code == 404


def test_delete_service(client):
    client.post("/api/services", json={"name": "Del", "url": "https://del.com"})
    r = client.delete("/api/services/1")
    assert r.status_code == 204
    assert client.get("/api/services/1").status_code == 404


def test_record_check(client):
    client.post("/api/services", json={"name": "Chk", "url": "https://chk.com"})
    r = client.post("/api/checks", json={"service_id": 1, "status": "up", "latency_ms": 42.5})
    assert r.status_code == 201
    assert r.json()["status"] == "up"


def test_get_checks(client):
    client.post("/api/services", json={"name": "C2", "url": "https://c2.com"})
    client.post("/api/checks", json={"service_id": 1, "status": "up", "latency_ms": 10.0})
    client.post("/api/checks", json={"service_id": 1, "status": "down", "latency_ms": None})
    r = client.get("/api/checks/1")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_last_status_reflected(client):
    client.post("/api/services", json={"name": "Ls", "url": "https://ls.com"})
    client.post("/api/checks", json={"service_id": 1, "status": "up", "latency_ms": 55.0})
    r = client.get("/api/services/1")
    assert r.json()["last_status"] == "up"
    assert r.json()["last_latency_ms"] == 55.0
