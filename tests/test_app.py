from fastapi.testclient import TestClient
from m32_monitor.main import app
client=TestClient(app)

def test_health_endpoint():
    response=client.get("/health")
    assert response.status_code==200
    assert response.json()=={"status":"ok"}

def test_home_page_loads():
    response=client.get("/")
    assert response.status_code==200
    assert "M32 Live Monitor" in response.text

def test_status_reports_simulator(monkeypatch):
    response=client.get("/api/status")
    assert response.status_code==200
    assert response.json()["mode"]=="simulator"
    assert response.json()["online"] is True

def test_channel_endpoint_has_channel_mapping():
    response=client.get("/api/channels")
    assert response.status_code==200
    assert response.json()[0]["sourceLabel"]=="IN01"
    assert response.json()[0]["number"]==1
