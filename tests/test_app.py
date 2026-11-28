import pytest
from fastapi.testclient import TestClient

from m32_monitor.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "M32 Simulation" in response.text


def test_status_reports_simulator(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["mode"] == "simulator"
    assert response.json()["online"] is True


def test_channel_endpoint_has_channel_mapping(client):
    response = client.get("/api/channels")
    assert response.status_code == 200
    assert response.json()[0]["sourceLabel"] == "IN01"
    assert response.json()[0]["number"] == 1


def test_osc_catalogue_endpoint_lists_categories_and_commands(client):
    response = client.get("/api/osc-catalogue")
    assert response.status_code == 200
    data = response.json()
    names = {category["category"] for category in data["categories"]}
    assert "Configuration and stereo linking" in names
    assert "Input channels" in names
    assert "Meters and subscriptions" in names
    assert any(command["address"] == "/node" for command in data["commands"])


def test_channel_endpoint_preserves_off_strips_and_reports_dca_state(client):
    response = client.get("/api/channels")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 48
    assert all("active" in item for item in data)
    assert all("mutedDcas" in item and "dcaMuteUnknown" in item for item in data)
