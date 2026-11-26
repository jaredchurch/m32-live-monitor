from fastapi.testclient import TestClient

from m32_monitor.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_loads() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "M32 Live Monitor" in response.text


def test_status_is_read_only(monkeypatch) -> None:
    monkeypatch.setenv("M32_MODE", "simulator")
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["mode"] == "simulator"
    assert response.json()["read_only"] is True
    assert response.json()["connection"] == "not_implemented"
