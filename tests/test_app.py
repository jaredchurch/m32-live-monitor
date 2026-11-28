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

def test_monitor_tabs_are_deep_linkable(client):
    response = client.get("/")
    assert response.status_code == 200
    for panel in ("matrix", "channels-panel", "routing-panel", "diagnostics-panel", "simulator-panel", "catalogue-panel"):
        assert f'href="#{panel}"' in response.text


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
    from m32_monitor.main import state
    state.channels[1].dca_mask = 1
    state.buses[1]["dca_mask"] = 2
    state.dca_mutes_enabled = True
    state.dcas[2]["on"] = False
    state.strip_nodes["/ch/01/eq/on"] = 1
    state.strip_nodes["/ch/01/eq/1/g"] = 5.0
    response = client.get("/api/channels")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 64
    assert sum(item["stripType"] == "bus" for item in data) == 16
    assert all("active" in item for item in data)
    assert all("mutedDcas" in item and "dcaMuteUnknown" in item for item in data)
    assert all("dcaLabels" in item and "eqBands" in item for item in data)
    assert all(len(item["eqBands"]) == (6 if item["stripType"] == "bus" else 4)
               for item in data)
    channel = next(item for item in data if item["stripType"] == "channel" and item["number"] == 1)
    bus = next(item for item in data if item["stripType"] == "bus" and item["number"] == 1)
    assert channel["dcaNumbers"] == [1]
    assert channel["eqOn"] is True and channel["eqBands"][0]["gain"] == 5.0
    assert bus["dcaNumbers"] == [2] and bus["mutedDcas"] == [2]
